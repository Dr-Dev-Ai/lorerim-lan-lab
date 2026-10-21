/* MIT. A narrow OS-API adapter for the pinned BSAMemoryMap 1.6.0 build.
 * No engine hooks or game structures. The installed native plugin performs all
 * archive/cache work. Imports adapt mappings, a verified trampoline-allocation
 * request and the native self-path; instruction bytes never change.
 */
#define WIN32_LEAN_AND_MEAN
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00
#endif
#include <windows.h>
#include <bcrypt.h>
#include <winternl.h>
#include <MinHook.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <wchar.h>

#include "bsa_guard_build.h"

/* SKSE PluginAPI.h, SKSEPluginVersionData v1: preserve native metadata exactly. */
__declspec(dllexport) const unsigned char SKSEPlugin_Version[848] = BSA_VERSION_DATA;
static HMODULE self_module, native_module;
static INIT_ONCE initialization = INIT_ONCE_STATIC_INIT;
static BOOL ready;
static wchar_t self_path[32768], native_path[32768], log_path[32768];
static volatile LONG mapped_views, failed_views;
typedef PVOID (WINAPI *map3_fn)(HANDLE, HANDLE, PVOID, ULONG64, SIZE_T, ULONG,
                               ULONG, MEM_EXTENDED_PARAMETER *, ULONG);
static map3_fn map3;
typedef PVOID (WINAPI *alloc2_fn)(HANDLE, PVOID, SIZE_T, ULONG, ULONG,
                                 MEM_EXTENDED_PARAMETER *, ULONG);
static alloc2_fn alloc2;
static LPVOID (WINAPI *real_map)(HANDLE, DWORD, DWORD, DWORD, SIZE_T);
static LPVOID (WINAPI *real_alloc)(LPVOID, SIZE_T, DWORD, DWORD);
static SIZE_T (WINAPI *real_query)(LPCVOID, PMEMORY_BASIC_INFORMATION, SIZE_T);
static LONG (WINAPI *query_object)(HANDLE, ULONG, PVOID, ULONG, PULONG);
static _Thread_local int shared_map_active;
static DWORD (WINAPI *real_module_name)(HMODULE, LPSTR, DWORD);
static struct { BYTE *base; volatile LONG used; } hook_pools[4];

__declspec(dllexport) BOOL BsaGuard_IsAddressTableName(const wchar_t *name) {
    if (!name) return FALSE;
    const wchar_t *leaf = wcsrchr(name, L'\\');
    leaf = leaf ? leaf + 1 : name;
    return !wcscmp(leaf, L"CommonLibSSEOffsets-v2-1-6-1170-0") ||
           !wcscmp(leaf, L"Shared-AddressLibrary-1-versionlib-1-6-1170-0") ||
           !wcscmp(leaf, L"COMMONLIB_IDDB_OFFSETS_1_6_1170_0");
}

static BOOL is_address_table(HANDLE handle) {
    if (!query_object) return FALSE;
    /* NtQueryObject's UNICODE_STRING points inside this returned buffer. Only
     * section handles supplied to MapViewOfFile are queried, never file/pipe I/O. */
    union { void *alignment; BYTE bytes[2048]; } buffer;
    ULONG needed;
    if (query_object(handle, 1, &buffer, sizeof(buffer), &needed) < 0) return FALSE;
    UNICODE_STRING *name = (UNICODE_STRING *)&buffer;
    uintptr_t begin = (uintptr_t)&buffer, pointer = (uintptr_t)name->Buffer;
    if (!name->Length || name->Length % 2 || pointer < begin ||
        pointer > begin + sizeof(buffer) || name->Length > begin + sizeof(buffer) - pointer)
        return FALSE;
    wchar_t text[1024];
    SIZE_T length = name->Length / sizeof(wchar_t);
    if (length >= 1024) return FALSE;
    memcpy(text, name->Buffer, name->Length);
    text[length] = 0;
    return BsaGuard_IsAddressTableName(text);
}

static void log_line(const char *text) {
    if (!log_path[0]) return;
    DWORD error = GetLastError(), written;
    HANDLE file = CreateFileW(log_path, FILE_APPEND_DATA, FILE_SHARE_READ |
        FILE_SHARE_WRITE, NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file != INVALID_HANDLE_VALUE) {
        WriteFile(file, text, (DWORD)strlen(text), &written, NULL);
        CloseHandle(file);
    }
    SetLastError(error);
}

__declspec(dllexport) LPVOID WINAPI BsaGuard_MapTable(HANDLE mapping, DWORD access,
        DWORD offset_high, DWORD offset_low, SIZE_T size) {
    ULONG protection;
    if (access == FILE_MAP_ALL_ACCESS || access == FILE_MAP_WRITE ||
        access == (FILE_MAP_READ | FILE_MAP_WRITE)) protection = PAGE_READWRITE;
    else if (access == FILE_MAP_READ) protection = PAGE_READONLY;
    else { SetLastError(ERROR_INVALID_PARAMETER); return NULL; }
    SYSTEM_INFO system;
    GetSystemInfo(&system);
    MEM_ADDRESS_REQUIREMENTS range = {0};
    range.LowestStartingAddress = (PVOID)(uintptr_t)0x1000000000ULL;
    range.HighestEndingAddress = system.lpMaximumApplicationAddress;
    MEM_EXTENDED_PARAMETER parameter = {0};
    parameter.Type = MemExtendedParameterAddressRequirements;
    parameter.Pointer = &range;
    return map3(mapping, GetCurrentProcess(), NULL,
        ((ULONG64)offset_high << 32) | offset_low, size, 0, protection, &parameter, 1);
}

static LPVOID WINAPI shared_map(HANDLE mapping, DWORD access, DWORD high, DWORD low, SIZE_T size) {
    if (!shared_map_active && map3 &&
        (access == FILE_MAP_READ || access == FILE_MAP_WRITE ||
         access == (FILE_MAP_READ | FILE_MAP_WRITE) || access == FILE_MAP_ALL_ACCESS)) {
        shared_map_active = 1;
        BOOL selected = is_address_table(mapping);
        if (selected) {
            LPVOID view = BsaGuard_MapTable(mapping, access, high, low, size);
            log_line(view ? "OK shared Address Library view mapped above 64 GiB\r\n" :
                            "FAIL high shared Address Library mapping\r\n");
            shared_map_active = 0;
            return view;
        }
        shared_map_active = 0;
    }
    return real_map(mapping, access, high, low, size);
}

/* All MapViewOfFile calls in the pinned native source are FILE_MAP_READ.
 * MapViewOfFile3 preserves offsets, whole-section size=0, unmapping, demand
 * paging and read-only permissions, while reserving the entire low 64 GiB for
 * game code, loader reservations and short-range trampolines.
 */
__declspec(dllexport) LPVOID WINAPI BsaGuard_MapRead(HANDLE mapping, DWORD access,
        DWORD offset_high, DWORD offset_low, SIZE_T size) {
    if (!map3 || !real_map) {
        log_line("FAIL mapping adapter not initialized\r\n");
        InterlockedIncrement(&failed_views);
        SetLastError(ERROR_INVALID_PARAMETER);
        return NULL;
    }
    /* Statically linked CommonLib also imports MapViewOfFile for writable
     * Address Library shared tables. Preserve their original access semantics. */
    if (access != FILE_MAP_READ)
        return shared_map(mapping, access, offset_high, offset_low, size);
    MEM_ADDRESS_REQUIREMENTS range = {0};
    SYSTEM_INFO system;
    GetSystemInfo(&system);
    range.LowestStartingAddress = (PVOID)(uintptr_t)0x1000000000ULL;
    range.HighestEndingAddress = system.lpMaximumApplicationAddress;
    /* MapViewOfFile3 requires this member to remain zero on supported Windows;
     * section views already receive the system allocation-granularity alignment. */
    MEM_EXTENDED_PARAMETER parameter = {0};
    parameter.Type = MemExtendedParameterAddressRequirements;
    parameter.Pointer = &range;
    LPVOID view = map3(mapping, GetCurrentProcess(), NULL,
        ((ULONG64)offset_high << 32) | offset_low, size, 0, PAGE_READONLY,
        &parameter, 1);
    if (view) {
        LONG count = InterlockedIncrement(&mapped_views);
        if (count == 1) log_line("OK first read-only view mapped above 64 GiB\r\n");
    } else {
        InterlockedIncrement(&failed_views);
        log_line("FAIL high-address mapping; no low-address fallback\r\n");
    }
    return view;
}

static DWORD WINAPI module_name(HMODULE module, LPSTR path, DWORD size) {
    /* Preserve the original INI name/location despite the native backup suffix. */
    return real_module_name(module == native_module ? self_module : module, path, size);
}

__declspec(dllexport) LPVOID WINAPI BsaGuard_Allocate(LPVOID address, SIZE_T size,
        DWORD allocation, DWORD protection) {
    if (!real_alloc) { SetLastError(ERROR_INVALID_FUNCTION); return NULL; }
    LPVOID block = real_alloc(address, size, allocation, protection);
    if (block) return block;
    uintptr_t base = (uintptr_t)GetModuleHandleW(NULL);
    /* The pinned source's private ReadFromSource trampoline tries only ABOVE
     * the executable, starting at +64 KiB. STR occupies that range. Handle only
     * that exact first 64-byte request; other allocations retain Win32 behavior. */
    if (alloc2 && size == 64 && allocation == (MEM_COMMIT | MEM_RESERVE) &&
        protection == PAGE_EXECUTE_READWRITE &&
        (uintptr_t)address == base + 0x10000 && base > 0x40010000) {
        MEM_ADDRESS_REQUIREMENTS range = {0};
        range.LowestStartingAddress = (PVOID)(base - 0x40000000);
        range.HighestEndingAddress = (PVOID)(base - 1);
        MEM_EXTENDED_PARAMETER parameter = {0};
        parameter.Type = MemExtendedParameterAddressRequirements;
        parameter.Pointer = &range;
        block = alloc2(GetCurrentProcess(), NULL, size, allocation, protection, &parameter, 1);
        log_line(block ? "OK private 64-byte trampoline allocated below executable\r\n" :
                         "FAIL private trampoline allocation below executable\r\n");
    }
    return block;
}

static BOOL hash_matches(const wchar_t *path, const unsigned char expected[32]) {
    unsigned char digest[32], buffer[65536];
    BCRYPT_ALG_HANDLE algorithm = NULL;
    BCRYPT_HASH_HANDLE hash = NULL;
    HANDLE file = INVALID_HANDLE_VALUE;
    BOOL result = FALSE;
    DWORD count;
    if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, NULL, 0) < 0)
        goto done;
    if (BCryptCreateHash(algorithm, &hash, NULL, 0, NULL, 0, 0) < 0) goto done;
    file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING,
                       FILE_FLAG_SEQUENTIAL_SCAN, NULL);
    if (file == INVALID_HANDLE_VALUE) goto done;
    for (;;) {
        if (!ReadFile(file, buffer, sizeof(buffer), &count, NULL)) goto done;
        if (!count) break;
        if (BCryptHashData(hash, buffer, count, 0) < 0) goto done;
    }
    if (BCryptFinishHash(hash, digest, sizeof(digest), 0) < 0) goto done;
    result = memcmp(digest, expected, 32) == 0;
done:
    if (file != INVALID_HANDLE_VALUE) CloseHandle(file);
    if (hash) BCryptDestroyHash(hash);
    if (algorithm) BCryptCloseAlgorithmProvider(algorithm, 0);
    return result;
}

static BOOL inside(DWORD rva, SIZE_T length, DWORD image_size) {
    return rva < image_size && length <= image_size - rva;
}

/* Resolve only named imports in the hash-pinned image, and verify the current
 * address before changing the IAT. Instruction bytes are never rewritten.
 */
static void **find_import(HMODULE module, const char *wanted, void *expected) {
    BYTE *base = (BYTE *)module;
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)base;
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0) return NULL;
    IMAGE_NT_HEADERS64 *nt = (IMAGE_NT_HEADERS64 *)(base + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE ||
        nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC) return NULL;
    DWORD extent = nt->OptionalHeader.SizeOfImage;
    IMAGE_DATA_DIRECTORY imports = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if (!inside(imports.VirtualAddress, imports.Size, extent)) return NULL;
    IMAGE_IMPORT_DESCRIPTOR *descriptors = (void *)(base + imports.VirtualAddress);
    void **found = NULL;
    for (SIZE_T d = 0; (d + 1) * sizeof(*descriptors) <= imports.Size; ++d) {
        IMAGE_IMPORT_DESCRIPTOR *desc = &descriptors[d];
        if (!desc->Name) return found;
        if (!desc->OriginalFirstThunk) continue;
        for (SIZE_T i = 0; i < extent / sizeof(IMAGE_THUNK_DATA64); ++i) {
            SIZE_T advance = i * sizeof(IMAGE_THUNK_DATA64);
            if (advance > MAXDWORD - desc->OriginalFirstThunk ||
                advance > MAXDWORD - desc->FirstThunk) return NULL;
            DWORD names_rva = desc->OriginalFirstThunk + (DWORD)advance;
            DWORD slot_rva = desc->FirstThunk + (DWORD)advance;
            if (!inside(names_rva, 8, extent) || !inside(slot_rva, 8, extent)) return NULL;
            IMAGE_THUNK_DATA64 *name = (void *)(base + names_rva);
            if (!name->u1.AddressOfData) break;
            if (IMAGE_SNAP_BY_ORDINAL64(name->u1.Ordinal)) continue;
            ULONGLONG rva64 = name->u1.AddressOfData;
            if (rva64 > MAXDWORD || !inside((DWORD)rva64, 3, extent)) return NULL;
            char *text = (char *)(base + rva64 + 2);
            SIZE_T remaining = extent - (DWORD)rva64 - 2;
            if (!memchr(text, 0, remaining)) return NULL;
            if (!strcmp(text, wanted)) {
                void **slot = (void **)(base + slot_rva);
                if (found || *slot != expected) return NULL;
                found = slot;
            }
        }
    }
    return NULL;
}

static BOOL exchange_import(void **slot, void *replacement) {
    DWORD protection, ignored;
    if (!VirtualProtect(slot, sizeof(*slot), PAGE_READWRITE, &protection)) return FALSE;
    InterlockedExchangePointer(slot, replacement);
    return VirtualProtect(slot, sizeof(*slot), protection, &ignored);
}

/* These four private reservations belong to this adapter. Only the hash-pinned
 * Better AltTab allocator sees an available slot through its own imports.
 * Other callers see MEM_RESERVE and cannot consume the slot during form loading.
 */
__declspec(dllexport) BOOL BsaGuard_ReserveHookSpace(void) {
    uintptr_t base = (uintptr_t)GetModuleHandleW(NULL);
    if (!alloc2 || base <= 0x20010000) return FALSE;
    MEM_ADDRESS_REQUIREMENTS range = {0};
    range.LowestStartingAddress = (PVOID)(base - 0x20000000);
    range.HighestEndingAddress = (PVOID)(base - 1);
    MEM_EXTENDED_PARAMETER parameter = {0};
    parameter.Type = MemExtendedParameterAddressRequirements;
    parameter.Pointer = &range;
    for (unsigned i = 0; i < 4; ++i) {
        if (!hook_pools[i].base)
            hook_pools[i].base = alloc2(GetCurrentProcess(), NULL, 0x10000,
                MEM_RESERVE, PAGE_NOACCESS, &parameter, 1);
        if (!hook_pools[i].base) return FALSE;
    }
    return TRUE;
}

__declspec(dllexport) LPVOID BsaGuard_HookPoolAddress(unsigned index) {
    return index < 4 ? hook_pools[index].base : NULL;
}

__declspec(dllexport) SIZE_T WINAPI BsaGuard_BetterQuery(LPCVOID address,
        PMEMORY_BASIC_INFORMATION info, SIZE_T size) {
    SIZE_T result = real_query(address, info, size);
    if (!result || size < sizeof(*info)) return result;
    for (unsigned i = 0; i < 4; ++i) {
        uintptr_t base = (uintptr_t)hook_pools[i].base, pointer = (uintptr_t)address;
        if (base && pointer >= base && pointer - base < 0x10000 &&
            InterlockedCompareExchange(&hook_pools[i].used, 0, 0) == 0) {
            memset(info, 0, sizeof(*info));
            info->BaseAddress = (PVOID)base;
            info->RegionSize = 0x10000;
            info->State = MEM_FREE;
            info->Protect = PAGE_NOACCESS;
            return sizeof(*info);
        }
    }
    return result;
}

__declspec(dllexport) LPVOID WINAPI BsaGuard_BetterAlloc(LPVOID address, SIZE_T size,
        DWORD allocation, DWORD protection) {
    if (address && size && size <= 0x10000 && allocation == (MEM_COMMIT | MEM_RESERVE) &&
        protection == PAGE_EXECUTE_READWRITE) {
        for (unsigned i = 0; i < 4; ++i) {
            if (address == hook_pools[i].base &&
                InterlockedCompareExchange(&hook_pools[i].used, 1, 0) == 0) {
                LPVOID result = real_alloc(address, size, MEM_COMMIT, protection);
                if (!result) InterlockedExchange(&hook_pools[i].used, 0);
                log_line(result ? "OK Better AltTab consumed its reserved near-code hook slot\r\n" :
                                  "FAIL committing Better AltTab hook slot\r\n");
                return result;
            }
        }
    }
    return real_alloc(address, size, allocation, protection);
}

static BOOL install_better_pool(HMODULE kernel) {
    HMODULE better = GetModuleHandleW(L"BetterAltTab.dll");
    if (!better) return TRUE;
    static const unsigned char expected[32] = {
        0x6b,0x76,0xf6,0xc5,0x4a,0xbc,0xe6,0xaf,0xdd,0x26,0x75,0xad,0x95,0xc1,0x45,0x4a,
        0x7f,0xf9,0xd9,0x07,0xbe,0x22,0xdd,0x4d,0x76,0xe9,0x81,0x74,0xea,0x87,0x68,0x82};
    wchar_t path[32768];
    DWORD length = GetModuleFileNameW(better, path, 32768);
    if (!length || length >= 32768 || !hash_matches(path, expected)) return FALSE;
    real_query = (void *)GetProcAddress(kernel, "VirtualQuery");
    void **query_slot = find_import(better, "VirtualQuery", (void *)real_query);
    void **alloc_slot = find_import(better, "VirtualAlloc", (void *)real_alloc);
    if (!real_query || !query_slot || !alloc_slot || !BsaGuard_ReserveHookSpace()) return FALSE;
    if (!exchange_import(query_slot, (void *)&BsaGuard_BetterQuery) ||
        !exchange_import(alloc_slot, (void *)&BsaGuard_BetterAlloc)) return FALSE;
    log_line("OK four private near-code slots reserved for pinned Better AltTab\r\n");
    return TRUE;
}

static BOOL CALLBACK initialize(PINIT_ONCE once, PVOID parameter, PVOID *context) {
    (void)once; (void)parameter; (void)context;
    DWORD length = GetModuleFileNameW(self_module, self_path, 32768);
    if (!length || length >= 32750) return TRUE;
    wchar_t *extension = wcsrchr(self_path, L'.');
    if (!extension || _wcsicmp(extension, L".dll")) return TRUE;
    wcscpy(native_path, self_path);
    wcscpy(native_path + (extension - self_path), L".native.bin");
    wcscpy(log_path, self_path);
    wcscpy(log_path + (extension - self_path), L".guard.log");
    log_line("START BSA mapping guard 1\r\n");
    static const unsigned char native_hash[32] = BSA_NATIVE_HASH;
    if (!hash_matches(native_path, native_hash)) {
        log_line("FAIL native DLL hash mismatch or missing backup\r\n");
        return TRUE;
    }
    HMODULE kernel = GetModuleHandleW(L"kernel32.dll");
    HMODULE kernelbase = GetModuleHandleW(L"kernelbase.dll");
    map3 = (void *)GetProcAddress(kernelbase, "MapViewOfFile3");
    alloc2 = (void *)GetProcAddress(kernelbase, "VirtualAlloc2");
    real_module_name = (void *)GetProcAddress(kernel, "GetModuleFileNameA");
    FARPROC original_map = GetProcAddress(kernel, "MapViewOfFile");
    real_map = (void *)original_map;
    real_alloc = (void *)GetProcAddress(kernel, "VirtualAlloc");
    real_query = (void *)GetProcAddress(kernel, "VirtualQuery");
    if (!map3 || !alloc2 || !real_module_name || !original_map || !real_alloc) {
        log_line("FAIL required Windows API unavailable\r\n"); return TRUE;
    }
    native_module = LoadLibraryExW(native_path, NULL, LOAD_WITH_ALTERED_SEARCH_PATH);
    if (!native_module) { log_line("FAIL loading native DLL\r\n"); return TRUE; }
    void **map_slot = find_import(native_module, "MapViewOfFile", (void *)original_map);
    void **path_slot = find_import(native_module, "GetModuleFileNameA", (void *)real_module_name);
    void **alloc_slot = find_import(native_module, "VirtualAlloc", (void *)real_alloc);
    if (!map_slot || !path_slot || !alloc_slot || !GetProcAddress(native_module, "SKSEPlugin_Load")) {
        log_line("FAIL unexpected native imports/exports\r\n"); return TRUE;
    }
    /* Pin before installing callbacks that the native module may retain. */
    HMODULE pinned;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
        GET_MODULE_HANDLE_EX_FLAG_PIN, (LPCWSTR)&initialize, &pinned)) return TRUE;
    if (!install_better_pool(kernel)) {
        log_line("FAIL verifying/reserving Better AltTab hook space\r\n"); return TRUE;
    }
    if (!exchange_import(path_slot, (void *)&module_name) ||
        !exchange_import(map_slot, (void *)&BsaGuard_MapRead) ||
        !exchange_import(alloc_slot, (void *)&BsaGuard_Allocate)) {
        log_line("FAIL installing mapping adapter\r\n"); return TRUE;
    }
    query_object = (void *)GetProcAddress(GetModuleHandleW(L"ntdll.dll"), "NtQueryObject");
    if (!query_object || MH_Initialize() != MH_OK ||
        MH_CreateHook((void *)original_map, (void *)&shared_map, (void **)&real_map) != MH_OK ||
        MH_EnableHook((void *)original_map) != MH_OK) {
        log_line("FAIL installing named-section mapping adapter\r\n"); return TRUE;
    }
    log_line("OK process mapping adapter limited to three named Address Library tables\r\n");
    ready = TRUE;
    log_line("OK native hash and imports verified; adapter installed\r\n");
    return TRUE;
}

static BOOL ensure_ready(void) {
    return InitOnceExecuteOnce(&initialization, initialize, NULL, NULL) && ready;
}

/* Allows the OS boundary integration tests to initialize without invoking SKSE. */
__declspec(dllexport) BOOL BsaGuard_Initialize(void) { return ensure_ready(); }

__declspec(dllexport) bool SKSEPlugin_Query(const void *skse, void *info) {
    if (!ensure_ready()) return false;
    typedef bool (*query_fn)(const void *, void *);
    query_fn query = (void *)GetProcAddress(native_module, "SKSEPlugin_Query");
    return query && query(skse, info);
}

__declspec(dllexport) bool SKSEPlugin_Load(const void *skse) {
    if (!ensure_ready()) {
        MessageBoxW(NULL, L"BSA mapping guard could not verify/install the adapter. Read BSAMemoryMap.guard.log.",
                    L"LoreRim lab BSA mapping guard", MB_OK | MB_ICONERROR);
        return false;
    }
    typedef bool (*load_fn)(const void *);
    load_fn load = (void *)GetProcAddress(native_module, "SKSEPlugin_Load");
    bool result = load(skse);
    log_line(result ? "OK native SKSEPlugin_Load returned true\r\n" :
                      "FAIL native SKSEPlugin_Load returned false\r\n");
    return result;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) self_module = instance;
    return TRUE;
}
