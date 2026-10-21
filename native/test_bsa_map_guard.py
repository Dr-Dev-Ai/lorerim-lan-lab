"""Real Windows mapping tests; native SKSEPlugin_Load is never called here."""
import argparse
import ctypes as c
from ctypes import wintypes as w
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor


class MemoryInfo(c.Structure):
    _fields_ = [('base', c.c_void_p), ('allocation', c.c_void_p), ('allocation_protect', w.DWORD),
                ('partition', w.WORD), ('size', c.c_size_t), ('state', w.DWORD),
                ('protect', w.DWORD), ('type', w.DWORD)]


class MappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = c.WinDLL(str(WORKER / 'BSAMemoryMap.dll'), use_last_error=True)
        cls.guard.BsaGuard_Initialize.restype = w.BOOL
        if not cls.guard.BsaGuard_Initialize():
            raise RuntimeError((WORKER / 'BSAMemoryMap.guard.log').read_text())
        cls.map = cls.guard.BsaGuard_MapRead
        cls.map.argtypes = [w.HANDLE, w.DWORD, w.DWORD, w.DWORD, c.c_size_t]
        cls.map.restype = c.c_void_p
        cls.kernel = c.WinDLL('kernel32', use_last_error=True)
        cls.kernel.CreateFileMappingW.argtypes = [w.HANDLE, c.c_void_p, w.DWORD, w.DWORD, w.DWORD, w.LPCWSTR]
        cls.kernel.CreateFileMappingW.restype = w.HANDLE
        cls.kernel.MapViewOfFile.argtypes = cls.map.argtypes
        cls.kernel.MapViewOfFile.restype = c.c_void_p
        cls.kernel.UnmapViewOfFile.argtypes = [c.c_void_p]
        cls.kernel.CloseHandle.argtypes = [w.HANDLE]
        cls.kernel.VirtualQuery.argtypes = [c.c_void_p, c.POINTER(MemoryInfo), c.c_size_t]
        cls.kernel.VirtualQuery.restype = c.c_size_t
        cls.kernel.VirtualFree.argtypes = [c.c_void_p, c.c_size_t, w.DWORD]
        cls.kernel.GetModuleHandleW.argtypes = [w.LPCWSTR]
        cls.kernel.GetModuleHandleW.restype = w.HMODULE

    def setUp(self):
        self.mapping = self.kernel.CreateFileMappingW(c.c_void_p(-1), None, 4, 0, 0x20000, None)
        self.assertTrue(self.mapping)
        self.addCleanup(self.kernel.CloseHandle, self.mapping)
        writable = self.kernel.MapViewOfFile(self.mapping, 2, 0, 0, 0)
        self.assertTrue(writable)
        c.memmove(writable, b'HEAD', 4)
        c.memmove(writable + 0x10000, b'OFFSET', 6)
        self.kernel.UnmapViewOfFile(writable)

    def checked_view(self, low=0, size=0):
        view = self.map(self.mapping, 4, 0, low, size)
        self.assertTrue(view, c.get_last_error())
        self.addCleanup(self.kernel.UnmapViewOfFile, view)
        self.assertGreaterEqual(view, 0x1000000000)
        info = MemoryInfo()
        self.assertTrue(self.kernel.VirtualQuery(view, c.byref(info), c.sizeof(info)))
        self.assertEqual(info.protect, 2)
        return view

    def test_whole_mapping_preserves_data_and_read_only_protection(self):
        view = self.checked_view()
        self.assertEqual(c.string_at(view, 4), b'HEAD')
        self.assertEqual(c.string_at(view + 0x10000, 6), b'OFFSET')

    def test_offset_and_explicit_view_size(self):
        view = self.checked_view(0x10000, 4096)
        self.assertEqual(c.string_at(view, 6), b'OFFSET')

    def test_invalid_offset_preserves_failure(self):
        self.assertFalse(self.map(self.mapping, 4, 0, 1, 4096))
        self.assertNotEqual(c.get_last_error(), 0)

    def test_writable_shared_mapping_preserves_original_semantics(self):
        view = self.map(self.mapping, 2, 0, 0, 0)
        self.assertTrue(view)
        self.addCleanup(self.kernel.UnmapViewOfFile, view)
        c.memmove(view, b'EDIT', 4)
        readonly = self.checked_view()
        self.assertEqual(c.string_at(readonly, 4), b'EDIT')

    def test_concurrent_mappings_are_above_hook_range(self):
        def worker(_):
            view = self.map(self.mapping, 4, 0, 0, 0)
            if not view:
                raise OSError('mapping failed')
            try:
                return view >= 0x1000000000 and c.string_at(view, 4) == b'HEAD'
            finally:
                self.kernel.UnmapViewOfFile(view)
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertTrue(all(pool.map(worker, range(64))))

    def test_native_metadata_is_preserved(self):
        native = c.WinDLL(str(WORKER / 'BSAMemoryMap.native.bin'))
        array = c.c_ubyte * 848
        self.assertEqual(bytes(array.in_dll(self.guard, 'SKSEPlugin_Version')),
                         bytes(array.in_dll(native, 'SKSEPlugin_Version')))

    def test_native_ini_lookup_uses_original_dll_path(self):
        native = c.WinDLL(str(WORKER / 'BSAMemoryMap.native.bin'))
        # Import slot inspected in the hash-pinned native build (not a game hook).
        address = c.c_void_p.from_address(native._handle + 0x5f0b0).value
        lookup = c.WINFUNCTYPE(w.DWORD, w.HMODULE, w.LPSTR, w.DWORD)(address)
        buffer = c.create_string_buffer(32768)
        self.assertTrue(lookup(native._handle, buffer, len(buffer)))
        self.assertEqual(Path(buffer.value.decode()).name, 'BSAMemoryMap.dll')

    def test_private_trampoline_allocation_is_near_executable(self):
        allocate = self.guard.BsaGuard_Allocate
        allocate.argtypes = [c.c_void_p, c.c_size_t, w.DWORD, w.DWORD]
        allocate.restype = c.c_void_p
        base = self.kernel.GetModuleHandleW(None)
        block = allocate(base + 0x10000, 64, 0x3000, 0x40)
        self.assertTrue(block, c.get_last_error())
        self.addCleanup(self.kernel.VirtualFree, block, 0, 0x8000)
        self.assertLess(block, base)
        self.assertLessEqual(base - block, 0x40000000)

    def test_only_verified_table_names_are_selected(self):
        select = self.guard.BsaGuard_IsAddressTableName
        select.argtypes = [w.LPCWSTR]
        select.restype = w.BOOL
        for name in ('CommonLibSSEOffsets-v2-1-6-1170-0',
                     r'\Sessions\6\BaseNamedObjects\Shared-AddressLibrary-1-versionlib-1-6-1170-0',
                     'COMMONLIB_IDDB_OFFSETS_1_6_1170_0'):
            self.assertTrue(select(name))
        for name in (None, '', 'SteamController_Master_mem-IPCWrapper',
                     'CommonLibSSEOffsets-v2-1-6-1170-0-Other',
                     'CommonLibSSEOffsets-v2-1-6-640-0'):
            self.assertFalse(select(name))

    def test_high_shared_table_mapping_preserves_writes(self):
        mapping = self.guard.BsaGuard_MapTable
        mapping.argtypes = self.map.argtypes
        mapping.restype = c.c_void_p
        writable = mapping(self.mapping, 0xf001f, 0, 0, 0)
        self.assertTrue(writable, c.get_last_error())
        self.addCleanup(self.kernel.UnmapViewOfFile, writable)
        self.assertGreaterEqual(writable, 0x1000000000)
        c.memmove(writable, b'TABLE', 5)
        readonly = self.checked_view()
        self.assertEqual(c.string_at(readonly, 5), b'TABLE')

    def test_private_hook_slot_is_reserved_from_other_allocators(self):
        self.guard.BsaGuard_ReserveHookSpace.restype = w.BOOL
        self.assertTrue(self.guard.BsaGuard_ReserveHookSpace())
        address = self.guard.BsaGuard_HookPoolAddress
        address.argtypes = [w.UINT]
        address.restype = c.c_void_p
        query = self.guard.BsaGuard_BetterQuery
        query.argtypes = self.kernel.VirtualQuery.argtypes
        query.restype = c.c_size_t
        allocate = self.guard.BsaGuard_BetterAlloc
        allocate.argtypes = [c.c_void_p, c.c_size_t, w.DWORD, w.DWORD]
        allocate.restype = c.c_void_p
        slot = address(0)
        self.assertTrue(slot)
        real, private = MemoryInfo(), MemoryInfo()
        self.assertTrue(self.kernel.VirtualQuery(slot, c.byref(real), c.sizeof(real)))
        self.assertEqual(real.state, 0x2000)  # Other callers see reserved memory.
        self.assertTrue(query(slot, c.byref(private), c.sizeof(private)))
        self.assertEqual(private.state, 0x10000)  # Better's allocator can claim it.
        self.assertEqual(allocate(slot, 0x10000, 0x3000, 0x40), slot)
        self.assertTrue(query(slot, c.byref(private), c.sizeof(private)))
        self.assertEqual(private.state, 0x1000)
        self.assertEqual(private.protect, 0x40)
        c.memmove(slot, b'PRIVATE', 7)
        self.assertEqual(c.string_at(slot, 7), b'PRIVATE')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adapter', type=Path)
    parser.add_argument('--native', type=Path)
    parser.add_argument('--worker', type=Path)
    args = parser.parse_args()
    if args.worker:
        WORKER = args.worker
        unittest.main(argv=[sys.argv[0]], verbosity=2)
    else:
        with tempfile.TemporaryDirectory(prefix='bsa-guard-test-') as directory:
            folder = Path(directory)
            shutil.copy2(args.adapter, folder / 'BSAMemoryMap.dll')
            shutil.copy2(args.native, folder / 'BSAMemoryMap.native.bin')
            # A separate process verifies fail-closed behavior before any native
            # module is loaded; its pinned DLLs are released on process exit.
            (folder / 'BSAMemoryMap.native.bin').write_bytes(b'unsupported native build')
            rejected = subprocess.call([sys.executable, '-c',
                'import ctypes,sys; p=ctypes.WinDLL(sys.argv[1]); '
                'assert not p.BsaGuard_Initialize()', str(folder / 'BSAMemoryMap.dll')])
            if rejected:
                raise SystemExit(rejected)
            shutil.copy2(args.native, folder / 'BSAMemoryMap.native.bin')
            code = subprocess.call([sys.executable, __file__, '--worker', str(folder)])
            print((folder / 'BSAMemoryMap.guard.log').read_text())
            raise SystemExit(code)
