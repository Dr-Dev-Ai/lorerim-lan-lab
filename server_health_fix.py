"""Exact-build server fix: discard health deltas for removed actor entities.

No Skyrim client hooks, protocol changes or actor ownership changes.
Default action only verifies; --apply/--restore require the server to be stopped.
"""
import argparse, hashlib, shutil, struct, sys, subprocess
from pathlib import Path

ORIGINAL = '0e8bd7a075e925eb9f674a1c5b1bd1e6fdd1a1ca371cbf73c8bb593f01997ff8'
BRANCH_RVA = 0x177CF1
OLD = bytes.fromhex('0f8483000000')
NEW = b'\x0f\x84' + struct.pack('<i', 0x177E36 - (BRANCH_RVA + 6))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect(path):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'analysis-libs'))
    import pefile
    raw = path.read_bytes()
    pe = pefile.PE(data=raw)
    offset = pe.get_offset_from_rva(BRANCH_RVA)
    pe.close()
    if raw[offset:offset+6] == OLD and digest(raw) == ORIGINAL:
        return 'original', offset, raw
    restored = raw[:offset] + OLD + raw[offset+6:]
    if raw[offset:offset+6] == NEW and digest(restored) == ORIGINAL:
        return 'patched', offset, raw
    raise RuntimeError('Unknown server DLL; refusing to modify it')


def ensure_stopped():
    # Query process identity; do not rely on localized tasklist text.
    cmd = ("[bool](Get-Process SkyrimTogetherServer -ErrorAction SilentlyContinue)")
    result = subprocess.run(['powershell', '-NoProfile', '-Command', cmd],
                            check=True, capture_output=True, text=True)
    if result.stdout.strip().lower() != 'false':
        raise RuntimeError('Stop the dedicated server before changing its DLL')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('server', type=Path)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--apply', action='store_true')
    action.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    path = args.server/'STServer.dll'
    state, offset, raw = inspect(path)
    print('State:', state, 'SHA256:', digest(raw), 'file offset:', hex(offset))
    if not (args.apply or args.restore):
        return
    ensure_stopped()
    backup = args.server/'health-fix-backup'/'STServer.dll.original'
    if args.apply and state == 'original':
        backup.parent.mkdir(exist_ok=True)
        if backup.exists():
            if digest(backup.read_bytes()) != ORIGINAL:
                raise RuntimeError('Existing original backup failed validation')
        else:
            shutil.copy2(path, backup)
        patched = raw[:offset] + NEW + raw[offset+6:]
        temporary = path.with_suffix('.dll.health-fix.tmp')
        temporary.write_bytes(patched)
        assert inspect(temporary)[0] == 'patched'
        temporary.replace(path)
        assert inspect(path)[0] == 'patched'
        print('Installed. Missing actor entities now return before notify construction.')
    elif args.restore and state == 'patched':
        if not backup.exists() or digest(backup.read_bytes()) != ORIGINAL:
            raise RuntimeError('Original backup missing or changed')
        shutil.copy2(backup, path)
        assert inspect(path)[0] == 'original'
        print('Restored original server DLL.')
    else:
        print('Already in requested state.')


if __name__ == '__main__':
    main()
