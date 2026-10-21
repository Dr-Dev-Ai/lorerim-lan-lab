"""Correct the two verified RX-only scanner variants in Player Eyes Blink Fix AE."""
import argparse
import json
from pathlib import Path
from camera_fix import apply_exact

HASH = 'ed52173ed08a2c77b28d525b086b791b6202151e4635eb2d62935e7354913a49'
DLL = Path('mods/Player Eyes Blink Fix/SKSE/Plugins/PlayerEyesBlinkFix.dll')
PATCHES = ((0x558b, bytes.fromhex('a820746e0fbae0087268')),
           (0x5957, bytes.fromhex('a820743c0fbae0087236')))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('lab', type=Path)
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    print(json.dumps(apply_exact(args.lab, DLL, HASH, PATCHES, 'blink-fix-backup', args.restore), indent=2))
