"""Immutable file backups and paired checkpoints. No in-place save restoration."""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import stat
import tempfile
import time
import uuid
from pathlib import Path
from .store import Conflict, canonical

MAX_FILE = 2 * 1024**3

def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()

def file_identity(path):
    info = Path(path).stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE:
        raise Conflict('Backup source must be a regular file smaller than 2 GiB')
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

def profile_manifest(profile, runtime_manifest):
    """Order-sensitive enabled plugin/mod fingerprint; runtime hashes must be supplied separately."""
    profile = Path(profile)
    if not isinstance(runtime_manifest, dict) or not runtime_manifest:
        raise ValueError('A non-empty runtime/protocol manifest is required')
    result = {'runtime': runtime_manifest, 'fingerprint_scope': 'enabled_lists_and_supplied_runtime_files'}
    for filename, prefix in [('plugins.txt', '*'), ('modlist.txt', '+')]:
        entries = [line.strip().casefold() for line in (profile / filename).read_text(encoding='utf-8-sig').splitlines()
                   if line.strip().startswith(prefix)]
        if not entries:
            raise Conflict(f'No enabled entries found in {filename}')
        result[filename] = hashlib.sha256(canonical(entries).encode()).hexdigest()
    return result

def runtime_fingerprint(build, entries):
    if not isinstance(build, str) or not build.strip():
        raise ValueError('Runtime build identifier is required')
    files = {}
    for entry in entries:
        if '=' not in entry:
            raise ValueError('Use --file logical-name=absolute-path')
        name, path = entry.split('=', 1)
        if not name or name in files:
            raise ValueError('Runtime file names must be nonempty and unique')
        before = file_identity(path)
        digest = sha_file(path)
        if before != file_identity(path):
            raise Conflict('Runtime file changed during hashing')
        files[name] = {'sha256': digest, 'bytes': before[2]}
    if not files:
        raise ValueError('At least one actual runtime file is required')
    return {'protocol_build': build.strip(), 'files': files, 'adapter_schema': 1,
            'scope': 'supplied_files_only_not_full_mod_compatibility_certification'}

def blob_path(store, digest):
    if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise Conflict('Invalid blob digest')
    return store.root / 'blobs' / digest[:2] / digest

def put_blob(store, source):
    source = Path(source)
    before = file_identity(source)
    temp_root = store.root / 'incoming'
    temp_root.mkdir(exist_ok=True)
    fd, name = tempfile.mkstemp(dir=temp_root)
    try:
        digest = hashlib.sha256()
        with os.fdopen(fd, 'wb') as dest, source.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
                dest.write(chunk)
            dest.flush()
            os.fsync(dest.fileno())
        if before != file_identity(source):
            raise Conflict('Source changed while copying; save not backed up')
        value = digest.hexdigest()
        target = blob_path(store, value)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if sha_file(target) != value:
                raise Conflict('Existing backup blob is corrupt')
        else:
            os.replace(name, target)
        return {'sha256': value, 'bytes': before[2]}
    finally:
        Path(name).unlink(missing_ok=True)

def _validate_files(files):
    if not isinstance(files, dict) or len(files) < 2:
        raise Conflict('Snapshot does not contain a save pair')
    if 'save/character.ess' not in files or 'save/character.skse' not in files:
        raise Conflict('Snapshot is missing .ess or .skse')
    for name, info in files.items():
        parts = name.split('/')
        if not parts or any(p in ('', '.', '..') or ':' in p or '\\' in p for p in parts) or name.startswith('/'):
            raise Conflict('Unsafe snapshot path')
        if not isinstance(info, dict) or not isinstance(info.get('bytes'), int) or info['bytes'] < 0:
            raise Conflict('Invalid file metadata')
        if not isinstance(info.get('sha256'), str):
            raise Conflict('Invalid file digest')

def verify_snapshot(store, snapshot):
    files = json.loads(snapshot['files'])
    _validate_files(files)
    for name, info in files.items():
        path = blob_path(store, info['sha256'])
        if not path.is_file() or path.stat().st_size != info['bytes'] or sha_file(path) != info['sha256']:
            raise Conflict(f'Backup content failed verification: {name}')
    return files

def capture(store, cid, pid, ess_path, profile_path, runtime_manifest, operation, settle_seconds=1.0, extras=()):
    """Capture existing saves only. No save command is issued to a running game."""
    ess, profile = Path(ess_path), Path(profile_path)
    if ess.suffix.lower() != '.ess':
        raise ValueError('Select an .ess save')
    skse = ess.with_suffix('.skse')
    store.member(cid, pid)
    current = store.campaign(cid)
    manifest = profile_manifest(profile, runtime_manifest)
    if canonical(manifest) != current['manifest']:
        raise Conflict('Profile/runtime fingerprint differs from the campaign manifest')
    if settle_seconds < 0.1 or settle_seconds > 30:
        raise ValueError('Save stability interval must be 0.1–30 seconds')
    sources = {'save/character.ess': ess, 'save/character.skse': skse}
    for name in ('plugins.txt', 'modlist.txt', 'loadorder.txt', 'Skyrim.ini', 'SkyrimPrefs.ini'):
        if (profile / name).is_file():
            sources['profile/' + name] = profile / name
    for source in extras:
        source = Path(source)
        name = 'external/' + source.name
        if name in sources:
            raise Conflict('Duplicate external backup filename')
        sources[name] = source
    before = {name: file_identity(path) for name, path in sources.items()}
    time.sleep(settle_seconds)
    if before != {name: file_identity(path) for name, path in sources.items()}:
        raise Conflict('A save or profile file is still changing')
    with ess.open('rb') as stream:
        if stream.read(13) != b'TESV_SAVEGAME':
            raise Conflict('Unrecognized Skyrim save header')
    with skse.open('rb') as stream:
        if stream.read(4) != b'SKSE':
            raise Conflict('Unrecognized SKSE co-save header')
    files = {name: put_blob(store, path) for name, path in sources.items()}
    # Catch a pair member changing after its individual copy but before the whole set finished.
    if before != {name: file_identity(path) for name, path in sources.items()}:
        raise Conflict('Save pair/profile changed during capture; no snapshot published')
    if profile_manifest(profile, runtime_manifest) != manifest:
        raise Conflict('Compatibility manifest changed during capture')
    _validate_files(files)
    payload = {'player': pid, 'revision': current['revision'], 'parent': current['head'], 'manifest': manifest, 'files': files}
    def insert():
        latest = store.campaign(cid)
        if latest['revision'] != current['revision'] or latest['head'] != current['head']:
            raise Conflict('Campaign changed while capture was in progress')
        sid = str(uuid.uuid4())
        store.db.execute('INSERT INTO snapshot(id,campaign,player,revision,parent,manifest,files,created) VALUES(?,?,?,?,?,?,?,?)',
                         (sid, cid, pid, current['revision'], current['head'], canonical(manifest), canonical(files), time.time()))
        return {'id': sid, 'player': pid, 'revision': current['revision'], 'verification': 'file_backup_only'}
    return store.mutate(cid, operation, 'snapshot', payload, insert)

def checkpoint(store, cid, leader, snapshot_ids, label, operation):
    ids = list(snapshot_ids)
    def insert():
        store.leader(cid, leader)
        current = store.campaign(cid)
        players = {r[0] for r in store.db.execute('SELECT id FROM player WHERE campaign=?', (cid,))}
        if len(players) < 2 or len(ids) != len(players) or len(set(ids)) != len(ids):
            raise Conflict('Exactly one snapshot per campaign player is required (at least two players)')
        if store.db.execute("SELECT id FROM transfer WHERE campaign=? AND state='pending'", (cid,)).fetchone():
            raise Conflict('Resolve pending item transfers before checkpointing')
        seen = set()
        for sid in ids:
            row = store.one('SELECT * FROM snapshot WHERE id=? AND campaign=?', (sid, cid))
            if row['player'] in seen or row['revision'] != current['revision'] or row['parent'] != current['head'] or row['manifest'] != current['manifest']:
                raise Conflict('Snapshots do not share the current campaign revision, lineage and manifest')
            seen.add(row['player'])
            verify_snapshot(store, row)
        if seen != players:
            raise Conflict('Snapshot player set differs from campaign membership')
        kid = str(uuid.uuid4())
        store.db.execute('INSERT INTO checkpoint(id,campaign,revision,parent,label,snapshots,state,created) VALUES(?,?,?,?,?,?,?,?)',
                         (kid, cid, current['revision'], current['head'], label, canonical(ids), canonical(store.domain_state(cid)), time.time()))
        store.db.execute('UPDATE campaign SET head=? WHERE id=?', (kid, cid))
        return {'id': kid, 'revision': current['revision'], 'snapshots': ids, 'verification': 'file_backup_only'}
    return store.mutate(cid, operation, 'checkpoint', [leader, ids, label], insert)

def export_checkpoint(store, cid, checkpoint_id, destination):
    """Export to a NEW directory; deliberately offers no apply/restore-to-game operation."""
    destination = Path(destination)
    if destination.exists():
        raise Conflict('Export directory must not already exist')
    with store.transaction():
        row = store.one('SELECT * FROM checkpoint WHERE id=? AND campaign=?', (checkpoint_id, cid))
        snapshots = [store.one('SELECT * FROM snapshot WHERE id=? AND campaign=?', (sid, cid)) for sid in json.loads(row['snapshots'])]
        for snapshot in snapshots:
            verify_snapshot(store, snapshot)
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix='.campaign-export-', dir=destination.parent))
        try:
            for snapshot in snapshots:
                for name, info in json.loads(snapshot['files']).items():
                    target = staging / snapshot['player'] / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(blob_path(store, info['sha256']), target)
                    if sha_file(target) != info['sha256']:
                        raise Conflict('Export verification failed')
            # SQLite backup captures a consistent database; SQLite's backup API uses a separate connection.
            import sqlite3
            connection = sqlite3.connect(store.root / 'campaign.sqlite3')
            backup = sqlite3.connect(staging / 'campaign.sqlite3')
            try:
                connection.backup(backup)
            finally:
                backup.close()
                connection.close()
            metadata = {'checkpoint': row, 'snapshots': snapshots, 'game_integration': False,
                        'database_scope': 'current_database_for_audit_not_a_rewindable_world_snapshot',
                        'note': 'File backup only. Quest/world equivalence and native restore are not certified.'}
            (staging / 'CHECKPOINT.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
            # Reserve the destination without overwriting a concurrently created directory.
            destination.mkdir()
            try:
                for child in staging.iterdir():
                    shutil.move(str(child), destination / child.name)
            except BaseException:
                # Leave partial export clearly marked rather than deleting caller-created data.
                (destination / 'INCOMPLETE').write_text('Export failed. Do not restore this directory.')
                raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    return {'directory': str(destination), 'checkpoint': checkpoint_id, 'game_integration': False}
