"""Read-only MO2 content audit. Python 3.12+, no third-party dependencies.

This verifies file parity, NOT multiplayer compatibility. It never launches Skyrim.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import time

SCHEMA = 1

def longpath(path):
    path = Path(path).absolute()
    if os.name == 'nt' and not str(path).startswith('\\\\?\\'):
        s = str(path)
        return Path('\\\\?\\UNC\\' + s[2:]) if s.startswith('\\\\') else Path('\\\\?\\' + s)
    return path

def sha(path):
    before = path.stat()
    with path.open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f'File changed while reading: {path}')
    return digest

def lines(path):
    return [s.strip() for s in path.read_text(encoding='utf-8-sig').splitlines()
            if s.strip() and not s.lstrip().startswith('#')]

def tree(root):
    if not root.is_dir():
        return
    pending = [root]
    while pending:
        parent = pending.pop()
        with os.scandir(parent) as entries:
            for entry in entries:
                if entry.is_symlink() or entry.is_junction():
                    raise ValueError(f'Link requires explicit review: {entry.path}')
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    yield Path(entry.path)

def resolve(root, profile):
    """MO2 modlist is highest priority first; overwrite wins last.

    Root Builder overlays tracked separately. Archives are hashed as opaque files;
    this does not pretend to resolve BSA-vs-loose record precedence.
    """
    root = longpath(root)
    p = root / 'profiles' / profile
    enabled = [s[1:] for s in lines(p / 'modlist.txt') if s.startswith('+')]
    if len({s.casefold() for s in enabled}) != len(enabled):
        raise ValueError('Duplicate enabled mod names')
    effective, sources = {}, {}
    layers = [('stock', root / 'Stock Game' / 'Data')]
    for name in reversed(enabled):
        folder = root / 'mods' / name
        if not folder.is_dir():
            raise ValueError(f'Enabled mod missing: {name}')
        layers.append((name, folder))
    layers.append(('overwrite', root / 'overwrite'))
    for source, folder in layers:
        for f in tree(folder):
            rel = f.relative_to(folder).as_posix()
            if rel.casefold() == 'meta.ini' or rel.casefold().endswith('.mohidden'):
                continue
            # Root Builder maps Root/ to the game directory, not Data/.
            key = rel if rel.lower().startswith('root/') else 'data/' + rel
            key = key.casefold()
            effective[key] = f
            sources[key] = source
    # Physical game-root files are separate from MO2 Data.
    for f in tree(root / 'Stock Game'):
        rel = f.relative_to(root / 'Stock Game').as_posix()
        if rel.lower().startswith('data/'):
            continue
        key = 'root/' + rel.casefold()
        if key not in effective:
            effective[key], sources[key] = f, 'stock-root'
    return enabled, effective, sources

def active_plugins(root, profile):
    p = root / 'profiles' / profile
    explicit = [s[1:] for s in lines(p / 'plugins.txt') if s.startswith('*')]
    implicit = ['Skyrim.esm', 'Update.esm', 'Dawnguard.esm', 'HearthFires.esm', 'Dragonborn.esm']
    ccc = root / 'Stock Game' / 'Skyrim.ccc'
    if ccc.exists():
        implicit += lines(ccc)
    order = lines(p / 'loadorder.txt')
    wanted = {s.casefold() for s in explicit + implicit}
    # MO2 omits always-loaded official masters/CC from plugins.txt.
    result = [s for s in order if s.casefold() in wanted]
    absent = wanted - {s.casefold() for s in result}
    if absent:
        raise ValueError(f'Active/implicit plugins absent from loadorder.txt: {sorted(absent)}')
    return result

def audit(root, profile, full=False):
    root = longpath(root.resolve())
    p = root / 'profiles' / profile
    enabled, effective, sources = resolve(root, profile)
    raw_plugins = lines(p / 'plugins.txt')
    plugins = active_plugins(root, profile)
    order = lines(p / 'loadorder.txt')
    if len({s.casefold() for s in plugins}) != len(plugins):
        raise ValueError('Duplicate active plugins')
    missing = [s for s in plugins if 'data/' + s.casefold() not in effective]
    if missing:
        raise ValueError(f'Active plugins missing: {missing}')
    metadata = {}
    for name in enabled:
        f = root / 'mods' / name / 'meta.ini'
        if f.exists():
            metadata[name] = dict(s.split('=', 1) for s in f.read_text(encoding='utf-8-sig', errors='replace').splitlines()
                                  if s.startswith(('version=', 'installationfile=', 'modid=')))
    files = {}
    essential = {'.esp', '.esm', '.esl', '.dll', '.exe', '.ini', '.toml', '.json', '.yaml', '.yml', '.xml', '.txt', '.pex', '.psc', '.hkx', '.bin', '.cfg'}
    for key, f in sorted(effective.items()):
        # audit mode is deliberately incomplete; compare refuses it.
        if full or f.suffix.lower() in essential:
            files[key] = {'sha256': sha(f), 'size': f.stat().st_size, 'source': sources[key]}
    profile_hashes = {f.name.casefold(): sha(f) for f in p.iterdir()
                      if f.is_file() and f.suffix.lower() in {'.ini', '.txt'} and not f.name.endswith('.bak')}
    return {'schema': SCHEMA, 'complete': full, 'scope': 'effective loose files + opaque archives + root overlays; no save/MCM runtime state',
            'created': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'root': str(root), 'profile': profile,
            'enabled_mods': enabled, 'plugins': plugins, 'loadorder': order,
            'profile_hashes': profile_hashes, 'metadata': metadata, 'files': files,
            'effective_file_count': len(effective),
            'skse_plugins': {k:v for k,v in files.items() if k.startswith('data/skse/plugins/') and k.endswith('.dll') and k.count('/') == 3}}

def compare(a, b):
    differences = []
    for doc in (a, b):
        if doc.get('schema') != SCHEMA or not doc.get('complete') or not doc.get('files'):
            raise ValueError('Both inputs must be complete manifests from snapshot --full; audit-only inputs cannot pass')
    for key in ('enabled_mods', 'plugins', 'loadorder', 'profile_hashes'):
        if a[key] != b[key]:
            differences.append({'kind': key, 'host': a[key], 'guest': b[key]})
    if a.get('server_config_sha256') != b.get('server_config_sha256'):
        differences.append({'kind': 'server_config', 'host': a.get('server_config_sha256'), 'guest': b.get('server_config_sha256')})
    for key in sorted(a['files'].keys() | b['files'].keys()):
        left, right = a['files'].get(key), b['files'].get(key)
        if left is None or right is None or left['sha256'] != right['sha256']:
            differences.append({'kind': 'content', 'file': key, 'host': left, 'guest': right})
    return differences

def metrics(path):
    """Summarize real measurement CSV; never manufacture gameplay measurements."""
    groups = {}
    with path.open(newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            key = (row['metric'], row['unit'])
            value = float(row['value'])
            if not __import__('math').isfinite(value) or value < 0:
                raise ValueError('Measurements must be finite and nonnegative')
            groups.setdefault(key, []).append(value)
    result = []
    for (name, unit), values in sorted(groups.items()):
        values.sort()
        def pct(p):
            return values[max(0, __import__('math').ceil(p * len(values)) - 1)]
        result.append({'metric': name, 'unit': unit, 'count': len(values), 'mean': sum(values)/len(values),
                       'p50': pct(.50), 'p95': pct(.95), 'p99': pct(.99), 'max': values[-1]})
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    snap = sub.add_parser('snapshot')
    snap.add_argument('root', type=Path)
    snap.add_argument('profile')
    snap.add_argument('output', type=Path)
    snap.add_argument('--full', action='store_true', help='Hash all effective content including assets and BSA archives')
    snap.add_argument('--server-config', type=Path, help='Include the intended STServer.ini hash')
    comp = sub.add_parser('compare')
    comp.add_argument('host', type=Path)
    comp.add_argument('guest', type=Path)
    comp.add_argument('output', type=Path)
    met = sub.add_parser('metrics')
    met.add_argument('csv', type=Path)
    met.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        status = 0
        if args.command == 'snapshot':
            result = audit(args.root, args.profile, args.full)
            if args.server_config:
                result['server_config_sha256'] = sha(args.server_config)
        elif args.command == 'compare':
            diffs = compare(json.loads(args.host.read_text()), json.loads(args.guest.read_text()))
            result = {'file_parity': not diffs, 'multiplayer_compatibility': 'UNVERIFIED', 'differences': diffs}
            status = 2 if diffs else 0
        else:
            result = metrics(args.csv)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(f'{args.command}: {args.output}; exit={status}')
        return status
    except (OSError, ValueError, KeyError) as exc:
        print(f'FAILED CLOSED: {exc}', file=sys.stderr)
        return 3

if __name__ == '__main__':
    sys.exit(main())
