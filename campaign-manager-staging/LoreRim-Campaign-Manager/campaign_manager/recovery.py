"""Prepare a coherent historical campaign copy. Never overwrites a live profile."""
import json
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from .store import Store, Conflict, canonical
from .checkpoints import blob_path, verify_snapshot, sha_file


def prepare_recovery(store, cid, pid, checkpoint_id, destination):
    """Rewind campaign records and both save pairs into a new, verified directory.

    Credentials keep their existing hashes. No plaintext credential is copied.
    The output is a separate branch and must not run beside the original campaign.
    Native character/quest equivalence still requires in-game verification.
    """
    destination = Path(destination).resolve()
    if destination.exists():
        raise Conflict('Recovery destination must not already exist')
    if store.root == destination or store.root in destination.parents:
        raise Conflict('Recovery destination must be outside the current data store')
    with store.transaction():
        store.leader(cid, pid)
        selected = store.one('SELECT * FROM checkpoint WHERE campaign=? AND id=?', (cid, checkpoint_id))
        state = json.loads(selected['state'])
        if state['campaign']['id'] != cid or state['campaign']['revision'] != selected['revision']:
            raise Conflict('Checkpoint domain state does not match its revision')
        recorded = {row['id'] for row in state['player']}
        bindings={row['player']:row for row in state.get('native_player',[])}
        if bindings and set(bindings)!=recorded:raise Conflict('Managed recovery requires native identities for every player')
        recovery_epoch=str(uuid.uuid4())
        current = {row['id']: dict(row) for row in store.db.execute('SELECT * FROM player WHERE campaign=?', (cid,))}
        if recorded != set(current):
            raise Conflict('Campaign membership changed; automatic historical identity recovery is unavailable')
        # Retain only the selected lineage, never later snapshots/transactions.
        lineage, seen = [], set()
        cursor = selected
        while cursor:
            if cursor['id'] in seen:
                raise Conflict('Cyclic checkpoint lineage')
            seen.add(cursor['id']); lineage.append(cursor)
            cursor = store.one('SELECT * FROM checkpoint WHERE campaign=? AND id=?', (cid, cursor['parent'])) if cursor['parent'] else None
        snapshots = {}
        for checkpoint in lineage:
            for sid in json.loads(checkpoint['snapshots']):
                if sid not in snapshots:
                    snapshot = store.one('SELECT * FROM snapshot WHERE campaign=? AND id=?', (cid, sid))
                    verify_snapshot(store, snapshot)
                    snapshots[sid] = snapshot
        chosen = [snapshots[sid] for sid in json.loads(selected['snapshots'])]
        if len(chosen) != len(recorded) or {row['player'] for row in chosen} != recorded:
            raise Conflict('Checkpoint does not contain exactly one save pair per player')
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix='.campaign-recovery-', dir=destination.parent))
        clone = None
        try:
            clone = Store(staging / 'data')
            campaign = dict(state['campaign']); campaign['head'] = selected['id']
            def insert(table, row):
                columns = list(row)
                clone.db.execute('INSERT INTO '+table+' ('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')',
                                 tuple(row[column] for column in columns))
            with clone.transaction():
                insert('campaign', campaign)
                clone.db.execute('INSERT INTO native_epoch VALUES(?,?)',(cid,recovery_epoch))
                for player in state['player']:
                    row = dict(current[player['id']]); row['name'] = player['name']; row['online'] = 0
                    insert('player', row)
                for table in ('follower','artifact','item','npc_rule'):
                    for old in state[table]:
                        row = dict(old)
                        if table == 'follower' and row['state'] != 'dead': row['parked'] = 1
                        insert(table, row)
                for snapshot in snapshots.values(): insert('snapshot', snapshot)
                for checkpoint in reversed(lineage): insert('checkpoint', checkpoint)
                clone.event(cid, 'historical_recovery_prepared', {'checkpoint': checkpoint_id, 'apply_required': True})
            for snapshot in snapshots.values():
                for name, info in json.loads(snapshot['files']).items():
                    target = blob_path(clone, info['sha256'])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.exists(): shutil.copyfile(blob_path(store, info['sha256']), target)
                    if target.stat().st_size != info['bytes'] or sha_file(target) != info['sha256']:
                        raise Conflict('Recovered blob failed verification')
            pairs = []
            for snapshot in chosen:
                files = json.loads(snapshot['files'])
                for name, info in files.items():
                    target = staging / 'players' / snapshot['player'] / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(blob_path(clone, info['sha256']), target)
                    if sha_file(target) != info['sha256']:
                        raise Conflict('Recovery output failed hash verification')
                if bindings:
                    from .cosave import rebranch,read_identity
                    from .checkpoints import put_blob
                    target=staging/'players'/snapshot['player']/'save/character.skse'
                    replacement=target.with_name('character.rebranched.skse')
                    identity=rebranch(target,replacement,recovery_epoch,checkpoint_id,clone.campaign(cid)['revision'])
                    if identity['character']!=bindings[snapshot['player']]['character'] or identity['campaign']!=cid:
                        raise Conflict('Historical native identity differs from the checkpoint player binding')
                    replacement.replace(target)
                    files['save/character.skse']=put_blob(clone,target)
                    with clone.transaction():
                        clone.db.execute('UPDATE snapshot SET files=? WHERE id=?',(canonical(files),snapshot['id']))
                        clone.db.execute('INSERT INTO native_player VALUES(?,?,?,?)',
                            (snapshot['player'],cid,identity['character'],snapshot['id']))
                pairs.append({'player': snapshot['player'], 'snapshot': snapshot['id'], 'files': files})
            if bindings:
                recovered_state=json.loads(selected['state'])
                recovered_state['native_epoch']=recovery_epoch
                recovered_state['native_player']=[dict(row) for row in clone.db.execute('SELECT * FROM native_player WHERE campaign=?',(cid,))]
                clone.db.execute('UPDATE checkpoint SET state=? WHERE id=?',(canonical(recovered_state),checkpoint_id))
            record = {'campaign':cid, 'checkpoint':checkpoint_id, 'created':time.time(), 'players':pairs,
                      'database_scope':'historical_checkpoint_domain_state', 'epoch':recovery_epoch, 'native_identity_rebranched':bool(bindings), 'applied':False,
                      'gameplay_verified':False, 'run_alongside_original':False,
                      'note':'Apply both save pairs and this campaign database together after closing both games and the server.'}
            (staging / 'RECOVERY.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
            clone.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            clone.close(); clone=None
            destination.mkdir() # Fail if another process reserved the destination.
            try:
                for child in staging.iterdir(): shutil.move(str(child), destination / child.name)
            except BaseException:
                (destination / 'INCOMPLETE').write_text('Incomplete recovery. Do not apply.')
                raise
        finally:
            if clone: clone.close()
            shutil.rmtree(staging,ignore_errors=True)
    return {'directory':str(destination), 'checkpoint':checkpoint_id, 'applied':False,
            'database_scope':'historical_checkpoint_domain_state'}
