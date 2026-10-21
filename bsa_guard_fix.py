"""Install/restore the tested local BSA mapping adapter in a marked lab only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

NATIVE_HASH = '05e073b2083c2fb491902e95bbc16a06eaf75187354e552100decdc9e74fc640'
ADAPTER_HASH = '2599e9475852a61a26a8e22c85a380e34c615b119d0223bc56fe574c8c4163c4'
FOLDER = Path('mods/Faster File Copy/SKSE/Plugins')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def apply(lab, adapter=None, restore=False):
    lab = Path(lab).resolve()
    source = Path(json.loads((lab / 'LORERIM_LAB.json').read_text(encoding='utf-8-sig'))['source']).resolve()
    if source == lab or source in lab.parents or lab in source.parents:
        raise ValueError('Refusing original or overlapping installation')
    if os.name != 'nt':
        raise OSError('Installation requires Windows')
    processes = subprocess.check_output(['tasklist', '/fo', 'csv', '/nh'], text=True).casefold()
    if any('"' + name + '"' in processes for name in ('skyrimse.exe', 'skyrimtogether.exe')):
        raise ValueError('Close game clients before changing the adapter')
    folder = lab / FOLDER
    target = folder / 'BSAMemoryMap.dll'
    backup = folder / 'BSAMemoryMap.native.bin'
    for path in (target, backup, folder, *folder.parents):
        if path.is_symlink() or path.is_junction():
            raise ValueError('Linked installation requires manual review')
    for path in (target, backup):
        if path.exists() and path.stat().st_nlink != 1:
            raise ValueError('Shared files require manual review')
    current = target.read_bytes()
    if backup.exists():
        original = backup.read_bytes()
        if digest(original) != NATIVE_HASH:
            raise ValueError('Native backup differs from the supported build')
        if digest(current) not in (NATIVE_HASH, ADAPTER_HASH):
            raise ValueError('Refusing to overwrite a changed plugin')
    else:
        original = current
        if digest(original) != NATIVE_HASH:
            raise ValueError('Unrecognized plugin without native backup')
    if restore:
        wanted = original
    else:
        if adapter is None:
            raise ValueError('Supply the tested adapter DLL with --adapter')
        wanted = Path(adapter).read_bytes()
        if digest(wanted) != ADAPTER_HASH:
            raise ValueError('Adapter checksum differs from the tested build')
    if current == wanted:
        return {'status': 'already restored' if restore else 'already installed', 'sha256': digest(current)}
    # Keep the byte-identical native DLL next to the adapter. SKSE ignores .bin.
    if not backup.exists():
        with backup.open('xb') as stream:
            stream.write(original)
    if backup.read_bytes() != original:
        raise ValueError('Native backup verification failed')
    descriptor, temporary = tempfile.mkstemp(dir=folder, suffix='.guard-tmp')
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(wanted)
            stream.flush()
            os.fsync(stream.fileno())
        if Path(temporary).read_bytes() != wanted or target.read_bytes() != current:
            raise ValueError('Files changed while staging adapter')
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    if target.read_bytes() != wanted:
        raise ValueError('Installed file verification failed')
    return {'status': 'restored' if restore else 'installed', 'sha256': digest(wanted),
            'native_sha256': NATIVE_HASH, 'gameplay_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('lab', type=Path)
    parser.add_argument('--adapter', type=Path)
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    print(json.dumps(apply(args.lab, args.adapter, args.restore), indent=2))
