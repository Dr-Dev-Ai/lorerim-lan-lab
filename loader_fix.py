"""Stage installed KiLoader dependencies beside STR; never download mod assets.

STR 1.8.3 excludes PATH from DLL lookup but explicitly searches its own directory.
This local deployment workaround preserves the existing dependency bytes.
"""
import json
from pathlib import Path
import shutil
import sys
import lancheck

def stage(lab, profile, mod):
    lab = Path(lab).resolve()
    if not (lab / 'LORERIM_LAB.json').is_file():
        raise ValueError('Refusing an unmarked installation')
    _, files, providers = lancheck.resolve(lab, profile)
    destination = lab / 'mods' / mod / 'SkyrimTogetherReborn'
    if not (destination / 'SkyrimTogether.exe').is_file():
        raise ValueError('STR launcher missing')
    records = []
    for key, source in files.items():
        if not key.startswith('data/kiloader/dependencies/') or not key.endswith('.dll'):
            continue
        if key.count('/') != 3:
            raise ValueError('Nested dependency needs manual review: ' + key)
        target = destination / source.name
        digest = lancheck.sha(source)
        if target.exists() and lancheck.sha(target) != digest:
            raise ValueError('Refusing to replace a different launcher DLL: ' + str(target))
        if not target.exists():
            shutil.copy2(source, target)
        if lancheck.sha(target) != digest:
            raise ValueError('Dependency copy verification failed')
        records.append({'dependency': key, 'source_mod': providers[key], 'sha256': digest,
                        'target': target.name, 'gameplay_verified': False})
    (lab / 'loader-dependencies.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    return records

if __name__ == '__main__':
    print(json.dumps(stage(Path(sys.argv[1]), 'LoreRim LAN Test',
                           'LoreRim LAN - Skyrim Together 1.8.3 (1170)'), indent=2))
