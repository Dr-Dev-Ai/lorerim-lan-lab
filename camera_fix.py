"""Experimental, exact-build camera scanner correction for a marked isolated lab.

No DLL is distributed. Only the verified protection-test immediate is changed.
The original bytes are retained outside the mod folder for rollback.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ORIGINAL_SHA256 = 'fd09d76ec7a3288787fbf3f0c1bfba69b43c12e73f48f3b7a146e4986430acb7'
DLL = Path('mods/Improved Alternate Conversation Camera/SKSE/Plugins/AlternateConversationCamera.dll')
# File offsets, not game addresses. Each disassembled VirtualQuery scanner
# checks MEM_COMMIT, then this RX predicate, then rejects PAGE_GUARD.
PATCHES = tuple((offset, bytes.fromhex(code)) for offset, code in (
    (0x112c, 'a82074400fbae008723a'),
    (0x15e0, 'a82074630fbae008725d'),
    (0x1ac0, 'a82074760fbae0087270'),
    (0x1fc4, 'a8200f847e0000000fba'),
    (0x24d0, 'a82074640fbae008725e'),
    (0x29b0, 'a82074760fbae0087270'),
    (0x15810, 'a82074660fbae0087260'),
    (0x15d04, 'a820747e0fbae0087278'),
    (0x161fc, 'a820743e0fbae0087238'),
    (0x165e0, 'a820745a0fbae0087254'),
    (0x18bf0, 'a82074660fbae0087260'),
    (0x19a34, 'a820747e0fbae0087278'),
    (0x19f30, 'a820745a0fbae0087254'),
    (0x1b950, 'a82074630fbae008725d'),
))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def patched(data):
    if digest(data) != ORIGINAL_SHA256:
        raise ValueError('Unsupported camera DLL; refusing to patch')
    result = bytearray(data)
    for offset, expected in PATCHES:
        if data[offset:offset + len(expected)] != expected:
            raise ValueError('Scanner instructions do not match')
        result[offset + 1] = 0x60  # RX | RWX; retain MEM_COMMIT and guard checks.
    return bytes(result)


def apply(lab, restore=False):
    lab = Path(lab).resolve()
    marker = json.loads((lab / 'LORERIM_LAB.json').read_text(encoding='utf-8-sig'))
    source = Path(marker['source']).resolve()
    if lab == source or source in lab.parents or lab in source.parents:
        raise ValueError('Refusing original or overlapping installation')
    if os.name != 'nt':
        raise OSError('Installation requires Windows')
    processes = subprocess.check_output(['tasklist', '/fo', 'csv', '/nh'], text=True).casefold()
    if any('"' + name + '"' in processes for name in ('skyrimse.exe', 'skyrimtogether.exe')):
        raise ValueError('Close all game clients before changing the DLL')
    target = lab / DLL
    if any(p.is_symlink() or p.is_junction() for p in [target, *target.parents]):
        raise ValueError('Linked installation requires manual review')
    backup = lab / 'camera-fix-backup' / 'AlternateConversationCamera.dll.original'
    if target.stat().st_nlink != 1 or any(p.is_symlink() or p.is_junction() for p in (backup, backup.parent)):
        raise ValueError('Linked DLL or backup requires manual review')
    current = target.read_bytes()
    original = backup.read_bytes() if backup.exists() else current
    replacement = patched(original)
    if current not in (original, replacement):
        raise ValueError('Camera changed since backup; refusing overwrite')
    wanted = original if restore else replacement
    if current == wanted:
        return {'status': 'already restored' if restore else 'already patched', 'sha256': digest(current)}
    backup.parent.mkdir(exist_ok=True)
    if not backup.exists():
        with backup.open('xb') as stream:
            stream.write(original)
    if backup.read_bytes() != original:
        raise ValueError('Backup verification failed')
    fd, temporary = tempfile.mkstemp(dir=target.parent, suffix='.camera-fix-tmp')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(wanted)
            stream.flush()
            os.fsync(stream.fileno())
        if Path(temporary).read_bytes() != wanted or target.read_bytes() != current:
            raise ValueError('Files changed during staging')
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    if target.read_bytes() != wanted:
        raise ValueError('Installed DLL verification failed')
    return {'status': 'restored' if restore else 'patched', 'sha256': digest(wanted),
            'backup': str(backup), 'changed_offsets': [offset + 1 for offset, _ in PATCHES],
            'gameplay_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('lab', type=Path)
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    print(json.dumps(apply(args.lab, args.restore), indent=2))
