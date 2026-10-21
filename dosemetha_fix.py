"""Load the installed dosemetha before archive mapping, without changing its bytes.

Opt-in for a marked isolated lab. Close games and refresh MO2 after installation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

SHA256 = 'e64dc70941dbe5cfa97b3198a9a4ec376f50cfaf9de8e73bbec7d372cb0a44a7'
MOD = "Don't send me there again (dosemetha)"
DIRECTORY = Path('mods') / MOD / 'SKSE/Plugins'
ORIGINAL = 'dosemetha.dll'
EARLY = '000_dosemetha.dll'


def apply(lab, restore=False):
    lab = Path(lab).resolve()
    marker = json.loads((lab / 'LORERIM_LAB.json').read_text(encoding='utf-8-sig'))
    original_root = Path(marker['source']).resolve()
    if lab == original_root or original_root in lab.parents or lab in original_root.parents:
        raise ValueError('Refusing original or overlapping installation')
    if os.name != 'nt':
        raise OSError('Installation requires Windows')
    processes = subprocess.check_output(['tasklist', '/fo', 'csv', '/nh'], text=True).casefold()
    if any('"' + name + '"' in processes for name in ('skyrimse.exe', 'skyrimtogether.exe')):
        raise ValueError('Close all game clients before changing load order')
    folder = lab / DIRECTORY
    old, new = folder / ORIGINAL, folder / EARLY
    if restore:
        old, new = new, old
    if any(p.is_symlink() or p.is_junction() for p in (old, new, *folder.parents, folder)):
        raise ValueError('Linked installation requires manual review')
    if old.exists() and new.exists():
        raise ValueError('Both DLL names exist; refusing duplicate plugin load')
    present = old if old.exists() else new
    data = present.read_bytes()
    if present.stat().st_nlink != 1 or hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('Unsupported or hardlinked DLL; refusing change')
    if not old.exists():
        return {'status': 'already restored' if restore else 'already installed', 'sha256': SHA256}
    # Windows rename fails if the destination exists; never overwrite another DLL.
    old.rename(new)
    if new.read_bytes() != data:
        raise ValueError('Renamed DLL verification failed')
    return {'status': 'restored' if restore else 'installed', 'sha256': SHA256,
            'filename': new.name, 'binary_bytes_changed': 0, 'gameplay_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('lab', type=Path)
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    print(json.dumps(apply(args.lab, args.restore), indent=2))
