"""Configure an ALREADY COPIED portable MO2 lab; never point this at your original.

Requires a marker created by clone_lab.ps1. No game/mod assets are distributed here.
"""
import argparse
import configparser
import json
from pathlib import Path
import re
import shutil
import sys
import lancheck

MOD = 'LoreRim LAN - Skyrim Together 1.8.3 (1170)'
PROFILE = 'LoreRim LAN Test'

def configure(source, lab, package):
    source, lab, package = source.resolve(), lab.resolve(), package.resolve()
    if lab == source or source in lab.parents or lab in source.parents:
        raise ValueError('Source and lab must be separate trees')
    marker = lab / 'LORERIM_LAB.json'
    if not marker.exists() or Path(json.loads(marker.read_text(encoding='utf-8-sig'))['source']).resolve() != source:
        raise ValueError('Missing matching clone marker; use clone_lab.ps1 first')
    if (lab / 'profiles' / PROFILE).exists():
        raise ValueError('Lab profile already exists; refusing to overwrite')
    for required in ['SkyrimTogether.esp', 'SkyrimTogetherQuestPatches.esp', 'SkyrimTogetherReborn/SkyrimTogether.exe']:
        if not (package / required).is_file():
            raise ValueError(f'Missing release file: {required}')
    text = (lab / 'ModOrganizer.ini').read_text(encoding='utf-8-sig')
    m = re.search(r'selected_profile=@ByteArray\((.*?)\)', text)
    if not m:
        raise ValueError('Cannot determine source profile')
    original_profile = m[1]
    target = lab / 'profiles' / PROFILE
    shutil.copytree(lab / 'profiles' / original_profile, target, ignore=shutil.ignore_patterns('saves'))
    (target / 'saves').mkdir()
    shutil.copytree(package, lab / 'mods' / MOD)
    # STR only adds logo meshes; its scripts deliberately override competing scripts.
    # All conflicts are exported for review. No original mod is disabled.
    enabled, effective, providers = lancheck.resolve(lab, original_profile)
    conflicts = []
    for f in lancheck.tree(package):
        key = 'data/' + f.relative_to(package).as_posix().casefold()
        if key in effective:
            conflicts.append({'file': key, 'previous_provider': providers[key],
                              'previous_sha256': lancheck.sha(effective[key]), 'str_sha256': lancheck.sha(f)})
    (lab / 'str-overrides.json').write_text(json.dumps(conflicts, indent=2))
    modlist = target / 'modlist.txt'
    modlist.write_text('+' + MOD + '\n' + modlist.read_text(encoding='utf-8-sig'), encoding='utf-8')
    for name, prefix in [('plugins.txt', '*'), ('loadorder.txt', '')]:
        f = target / name
        content = f.read_text(encoding='utf-8-sig').rstrip() + '\n'
        for esp in ['SkyrimTogether.esp', 'SkyrimTogetherQuestPatches.esp']:
            content += prefix + esp + '\n'
        f.write_text(content, encoding='utf-8')
    settings = target / 'settings.ini'
    content = settings.read_text(encoding='utf-8-sig')
    content = re.sub(r'LocalSaves=.*', 'LocalSaves=true', content)
    content = re.sub(r'LocalSettings=.*', 'LocalSettings=true', content)
    settings.write_text(content, encoding='utf-8')
    # Only launch entries intended for this lab. Do not retain patch generators with
    # absolute output paths pointing at the original installation.
    text = re.sub(r'\[customExecutables\][\s\S]*?(?=\n\[|\Z)', '', text)
    text = text.replace('selected_profile=@ByteArray(' + original_profile + ')', 'selected_profile=@ByteArray(' + PROFILE + ')')
    for old, new in [(str(source).replace('\\', '\\\\'), str(lab).replace('\\', '\\\\')),
                     (source.as_posix(), lab.as_posix()), (str(source), str(lab))]:
        text = text.replace(old, new)
    executable = (lab / 'mods' / MOD / 'SkyrimTogetherReborn' / 'SkyrimTogether.exe').as_posix()
    text += f'\n[customExecutables]\nsize=1\n1\\title=LoreRim LAN Test\n1\\binary={executable}\n1\\arguments=\n1\\workingDirectory={(lab / "Stock Game").as_posix()}\n1\\hide=false\n1\\ownicon=false\n1\\toolbar=false\n'
    (lab / 'ModOrganizer.ini').write_text(text, encoding='utf-8')
    (lab / 'downloads').mkdir(exist_ok=True)
    # Separate server working directory; server does not need redistributed plugins.
    server = lab.parent / 'server'
    server.mkdir(exist_ok=False)
    for name in ['SkyrimTogetherServer.exe', 'STServer.dll']:
        shutil.copy2(package / 'SkyrimTogetherReborn' / name, server / name)
    (server / 'config').mkdir()
    config = (package / 'SkyrimTogetherReborn/config/STServer.ini').read_text()
    prefs = (target / 'SkyrimPrefs.ini').read_text(encoding='utf-8-sig')
    difficulty = re.search(r'iDifficulty\s*=\s*(\d+)', prefs)
    req_settings = effective.get('data/mcm/settings/requiem.ini')
    scale_match = re.search(r'fTimeScale\s*=\s*([\d.]+)', req_settings.read_text()) if req_settings else None
    if not scale_match:
        raise ValueError('Could not determine Requiem timescale; review before configuring server')
    changes = {'sServerName': 'LoreRim LAN LAB - UNVERIFIED', 'uMaxPlayerCount': '2',
               'bAnnounceServer': 'false', 'bEnableModCheck': 'true', 'bEnableDeathSystem': 'false',
               'bEnableXpSync': 'false', 'uDifficulty': difficulty[1] if difficulty else '1',
               'sPassword': 'LoreRimLab', 'uTimeScale': str(int(float(scale_match[1])))}
    for key, value in changes.items():
        config = re.sub(r'^' + key + '=.*$', key + '=' + value, config, flags=re.M)
    (server / 'config/STServer.ini').write_text(config)
    (server / 'Data').mkdir()
    (server / 'Data/loadorder.txt').write_text('\n'.join(lancheck.active_plugins(lab, PROFILE)) + '\n', encoding='utf-8')
    return {'lab': str(lab), 'profile': PROFILE, 'server': str(server), 'script_conflicts': conflicts,
            'status': 'PREPARED, NOT GAMEPLAY VERIFIED', 'changes': changes}

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('lab', type=Path)
    p.add_argument('package', type=Path)
    args = p.parse_args()
    try:
        print(json.dumps(configure(args.source, args.lab, args.package), indent=2))
    except (ValueError, OSError) as e:
        sys.exit(str(e))
