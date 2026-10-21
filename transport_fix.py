"""Expand the verified STR 1.8.3 client send buffer/pool for this large lab."""
import argparse
import json
from pathlib import Path
from camera_fix import apply_exact

HASH = '27815f3be0375a5eeb52be935da0339b8dfe853c7edfbeaafd47c1bf267e8521'
DLL = Path('mods/LoreRim LAN - Skyrim Together 1.8.3 (1170)/SkyrimTogetherReborn/SkyrimTogether.exe')
# Two compiled Send paths: inlined authentication and ordinary Send.
# Change only the 32-bit size argument, preserving opcode and following context.
_CONTEXTS = (
    (0x2cc4bd, 'ba00000400488bcfe886672b00488d0d', 'ba00002000'),
    (0x2cc4f3, 'ba00000100488d4c2450e8ce612b0048', 'ba00000400'),
    (0x2cc875, 'ba00000400488bcfe8ce632b00488d0d', 'ba00002000'),
    (0x2cc8ae, 'ba00000100488d4c2430e8135e2b0048', 'ba00000400'),
)
PATCHES = tuple((offset, bytes.fromhex(context), bytes.fromhex(prefix) + bytes.fromhex(context)[5:])
                for offset, context, prefix in _CONTEXTS)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('lab', type=Path)
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    print(json.dumps(apply_exact(args.lab, DLL, HASH, PATCHES, 'transport-fix-backup', args.restore), indent=2))
