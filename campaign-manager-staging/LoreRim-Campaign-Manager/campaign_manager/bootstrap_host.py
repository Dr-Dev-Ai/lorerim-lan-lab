"""Capture a first host backup into a new staging store; never modifies game files."""
import argparse
import json
import os
import uuid
from pathlib import Path
from .store import Store
from .checkpoints import capture, profile_manifest, runtime_fingerprint, verify_snapshot

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', required=True)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--file', action='append', required=True)
    args = parser.parse_args()
    root = Path(args.data)
    if root.exists() and any(root.iterdir()):
        raise ValueError('Initial host backup requires a new or empty staging directory')
    profile = Path(args.profile)
    saves = list((profile / 'saves').glob('*.ess'))
    if not saves:
        raise ValueError('No profile saves found')
    latest = max(saves, key=lambda p:p.stat().st_mtime_ns)
    runtime = runtime_fingerprint('installed-runtime-baseline-file-backup-only', args.file)
    store = Store(root)
    try:
        campaign = store.create_campaign('LoreRim staged campaign', profile_manifest(profile, runtime))
        players = [store.add_player(campaign['id'], 'Host', True), store.add_player(campaign['id'], 'Partner')]
        directory = root / 'credentials'; directory.mkdir()
        for identity in players:
            fd = os.open(directory / (identity['player'] + '.json'), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(identity, stream, indent=2)
        (root/'runtime.json').write_text(json.dumps(runtime, indent=2), encoding='utf-8')
        snapshot = capture(store, campaign['id'], players[0]['player'], latest, profile, runtime, str(uuid.uuid4()))
        row = store.one('SELECT * FROM snapshot WHERE id=?', (snapshot['id'],))
        verify_snapshot(store, row)
        record = {'campaign': campaign['id'], 'host': players[0]['player'], 'partner': players[1]['player'],
                  'host_snapshot': snapshot['id'], 'source_save': str(latest), 'file_backup_verified': True,
                  'paired_checkpoint_complete': False, 'game_integration_enabled': False,
                  'note': 'Partner capture and coherent world/ledger validation remain pending.'}
        (root/'HOST_BASELINE.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
        print(json.dumps(record, indent=2))
    finally:
        store.close()

if __name__ == '__main__':
    main()
