"""Read-only live Windows image scan. Findings are NOT validated hook addresses.

Run while the camera error dialog is open. No injection, writes or protection
changes. Only the selected module is read; raw process memory is not saved.
"""
import argparse
import ctypes as c
from ctypes import wintypes as w
from datetime import datetime, timezone
import json
import os
from pathlib import Path

PATTERN = bytes.fromhex('0f28c1f30f5ec60f28f0')


def readable(state, protection):
    return state == 0x1000 and not protection & 0x100 and protection & 0xff in (2, 4, 8, 0x20, 0x40, 0x80)


def scan_range(read, start, end, pattern, chunk_size=1024 * 1024):
    """Bound reads, include overlapping matches and chunk-boundary matches.

    A failed/short read aborts: missing coverage must never look like no match.
    """
    if not pattern or chunk_size < len(pattern) or end < start:
        raise ValueError('Invalid scan bounds, pattern or chunk size')
    hits, tail, cursor = [], b'', start
    while cursor < end:
        size = min(chunk_size, end - cursor)
        block = read(cursor, size)
        if len(block) != size:
            raise OSError('Incomplete process memory read')
        data = tail + block
        offset = data.find(pattern)
        while offset >= 0:
            hits.append(cursor - len(tail) + offset)
            offset = data.find(pattern, offset + 1)
        tail = data[-(len(pattern) - 1):] if len(pattern) > 1 else b''
        cursor += size
    return hits


class ModuleInfo(c.Structure):
    _fields_ = [('base', c.c_void_p), ('size', w.DWORD), ('entry', c.c_void_p)]


class MemoryInfo(c.Structure):
    _fields_ = [('base', c.c_void_p), ('allocation_base', c.c_void_p),
                ('allocation_protect', w.DWORD), ('partition', w.WORD),
                ('size', c.c_size_t), ('state', w.DWORD),
                ('protect', w.DWORD), ('type', w.DWORD)]


def probe(pid, module_name):
    if os.name != 'nt' or c.sizeof(c.c_void_p) != 8:
        raise OSError('Requires 64-bit Python on Windows')
    kernel = c.WinDLL('kernel32', use_last_error=True)
    psapi = c.WinDLL('psapi', use_last_error=True)
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.ReadProcessMemory.argtypes = [w.HANDLE, c.c_void_p, c.c_void_p, c.c_size_t, c.POINTER(c.c_size_t)]
    kernel.VirtualQueryEx.argtypes = [w.HANDLE, c.c_void_p, c.POINTER(MemoryInfo), c.c_size_t]
    kernel.VirtualQueryEx.restype = c.c_size_t
    psapi.EnumProcessModulesEx.argtypes = [w.HANDLE, c.POINTER(c.c_void_p), w.DWORD, c.POINTER(w.DWORD), w.DWORD]
    psapi.GetModuleFileNameExW.argtypes = [w.HANDLE, c.c_void_p, w.LPWSTR, w.DWORD]
    psapi.GetModuleInformation.argtypes = [w.HANDLE, c.c_void_p, c.POINTER(ModuleInfo), w.DWORD]
    handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
    if not handle:
        raise c.WinError(c.get_last_error())
    try:
        modules = (c.c_void_p * 4096)()
        needed = w.DWORD()
        if not psapi.EnumProcessModulesEx(handle, modules, c.sizeof(modules), c.byref(needed), 3):
            raise c.WinError(c.get_last_error())
        if needed.value > c.sizeof(modules):
            raise OSError('Module list exceeds capacity')
        inventory, selected = [], []
        for module in modules[:needed.value // c.sizeof(c.c_void_p)]:
            name = c.create_unicode_buffer(32768)
            if not psapi.GetModuleFileNameExW(handle, module, name, len(name)):
                raise c.WinError(c.get_last_error())
            info = ModuleInfo()
            if not psapi.GetModuleInformation(handle, module, c.byref(info), c.sizeof(info)):
                raise c.WinError(c.get_last_error())
            record = {'path': name.value, 'base': info.base, 'size': info.size}
            inventory.append(record)
            if Path(name.value).name.casefold() == module_name.casefold():
                selected.append(record)
        if len(selected) != 1:
            raise ValueError(f'Expected one {module_name} module, found {len(selected)}')
        image = selected[0]
        start, end = image['base'], image['base'] + image['size']
        def read(address, size):
            buf, count = c.create_string_buffer(size), c.c_size_t()
            if not kernel.ReadProcessMemory(handle, address, buf, size, c.byref(count)):
                raise c.WinError(c.get_last_error())
            return buf.raw[:count.value]
        regions, matches, errors = [], [], []
        cursor = start
        while cursor < end:
            mem = MemoryInfo()
            if not kernel.VirtualQueryEx(handle, cursor, c.byref(mem), c.sizeof(mem)):
                errors.append({'address': cursor, 'error': str(c.WinError(c.get_last_error()))})
                break
            low, high = max(cursor, mem.base or 0), min(end, (mem.base or 0) + mem.size)
            if high <= cursor:
                raise OSError('Memory query made no progress')
            region = {'start_rva': low - start, 'size': high - low,
                      'state': mem.state, 'protect': mem.protect, 'read': False}
            if readable(mem.state, mem.protect):
                try:
                    hits = scan_range(read, low, high, PATTERN)
                    region['read'] = True
                    for address in hits:
                        matches.append({'rva': address - start, 'protect': mem.protect,
                                        'legacy_rx_predicate': bool(mem.protect & 0x20)})
                except OSError as exc:
                    errors.append({'address': low, 'error': str(exc)})
            regions.append(region)
            cursor = high
        return {'schema': 1, 'captured_utc': datetime.now(timezone.utc).isoformat(),
                'pid': pid, 'pattern': PATTERN.hex(), 'image': image,
                'modules': inventory, 'regions': regions, 'matches': matches,
                'errors': errors, 'readable_regions_complete': not errors,
                'limitations': 'Live non-atomic observation. Matches spanning protection regions are not searched. '
                               'No proof of scanner call arguments, hook correctness or gameplay compatibility.'}
    finally:
        kernel.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pid', type=int)
    parser.add_argument('output', type=Path)
    parser.add_argument('--module', default='SkyrimTogether.exe')
    args = parser.parse_args()
    # Reserve evidence path before probing; never overwrite an earlier capture.
    with args.output.open('x', encoding='utf-8') as stream:
        try:
            result = probe(args.pid, args.module)
        except (OSError, ValueError) as exc:
            json.dump({'error': str(exc), 'readable_regions_complete': False}, stream, indent=2)
            return 3
        json.dump(result, stream, indent=2)
    return 3 if result['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
