"""Mirror upstream's removal of the unused second Better AltTab allocation.

Exact installed 1.0.1 build only. Audio and cursor hooks remain enabled.
"""
import argparse
import json
from pathlib import Path
from camera_fix import apply_exact

HASH = '662c15a7f586becbecc9ee156167b1c0075009429a5f278157fc847844641254'
DLL = Path('mods/Better AltTab/SKSE/Plugins/BetterAltTab.dll')
# RVA 0x6E0A: call Trampoline::create(64) in installToggleCursorHook.
# Upstream v1.0.2 removes this unused call; Detours installs the actual hook.
PATCHES = ((0x620a, bytes.fromhex('e8513a0200'), b'\x90' * 5),)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('lab', type=Path)
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    print(json.dumps(apply_exact(args.lab, DLL, HASH, PATCHES, 'alttab-fix-backup', args.restore), indent=2))
