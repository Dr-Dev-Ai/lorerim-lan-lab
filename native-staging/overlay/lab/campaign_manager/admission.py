"""Bind a campaign character to a verified saved pair and check reconnect lineage."""
import json
import re
from .store import Conflict,Denied,canonical
from .cosave import guid,read_identity
from .checkpoints import verify_snapshot,blob_path

DIGEST=re.compile(r'^[0-9a-f]{64}$')

def enroll_snapshot(store,cid,pid,sid):
    with store.transaction():
        store.member(cid,pid)
        snapshot=store.one('SELECT * FROM snapshot WHERE campaign=? AND player=? AND id=?',(cid,pid,sid))
        files=verify_snapshot(store,snapshot)
        identity=read_identity(blob_path(store,files['save/character.skse']['sha256']))
        epoch=store.one('SELECT epoch FROM native_epoch WHERE campaign=?',(cid,))['epoch']
        campaign=store.campaign(cid)
        if identity['campaign']!=cid or identity['epoch']!=epoch or identity['checkpoint']!=(snapshot['parent'] or '') or identity['revision']!=snapshot['revision']:
            raise Conflict('Native save belongs to a different campaign epoch or checkpoint')
        if snapshot['revision']!=campaign['revision'] or snapshot['parent']!=campaign['head']:
            raise Conflict('Cannot enroll a stale capture')
        previous=store.db.execute('SELECT * FROM native_player WHERE player=?',(pid,)).fetchone()
        if previous and previous['character']!=identity['character']:
            raise Denied('A different character is already enrolled for this player')
        collision=store.db.execute('SELECT player FROM native_player WHERE campaign=? AND character=?',(cid,identity['character'])).fetchone()
        if collision and collision['player']!=pid:raise Denied('This character is already assigned to another player')
        store.db.execute('INSERT INTO native_player VALUES(?,?,?,?) ON CONFLICT(player) DO UPDATE SET snapshot=excluded.snapshot',
                         (pid,cid,identity['character'],sid))
        return {'player':pid,'character':identity['character'],'snapshot':sid,'epoch':epoch}

def check(store,cid,pid,proof):
    store.member(cid,pid)
    if store.db.execute("SELECT 1 FROM coop_request WHERE campaign=? AND state IN ('requested','frozen','saving') LIMIT 1",(cid,)).fetchone():
        raise Conflict('A paired checkpoint is in progress')
    for key in ('character','campaign','epoch'):guid(proof[key])
    guid(proof.get('checkpoint',''),empty=True)
    if proof['campaign']!=cid:raise Denied('Loaded character belongs to another campaign')
    epoch=store.one('SELECT epoch FROM native_epoch WHERE campaign=?',(cid,))['epoch']
    if proof['epoch']!=epoch:raise Denied('Loaded save belongs to a different recovery epoch')
    binding=store.one('SELECT * FROM native_player WHERE campaign=? AND player=?',(cid,pid))
    if binding['character']!=proof['character']:raise Denied('Loaded character does not match this campaign player')
    campaign=store.campaign(cid)
    sid=binding['snapshot']
    if campaign['head']:
        checkpoint=store.one('SELECT snapshots FROM checkpoint WHERE campaign=? AND id=?',(cid,campaign['head']))
        matches=[]
        for candidate in json.loads(checkpoint['snapshots']):
            snapshot=store.one('SELECT * FROM snapshot WHERE campaign=? AND id=?',(cid,candidate))
            if snapshot['player']==pid:matches.append(snapshot)
        if len(matches)!=1:raise Conflict('Campaign checkpoint has no unambiguous player save')
        snapshot=matches[0]
    else:snapshot=store.one('SELECT * FROM snapshot WHERE campaign=? AND player=? AND id=?',(cid,pid,sid))
    files=verify_snapshot(store,snapshot)
    for key,name in (('ess_sha256','save/character.ess'),('skse_sha256','save/character.skse')):
        if not isinstance(proof.get(key),str) or not DIGEST.fullmatch(proof[key]) or proof[key]!=files[name]['sha256']:
            raise Denied('Loaded save pair is not the enrolled campaign checkpoint; reconciliation is required')
    if proof.get('checkpoint','') not in ((snapshot['parent'] or ''),(campaign['head'] or '')):
        raise Denied('Loaded save has a different checkpoint lineage')
    if store.db.execute("SELECT id FROM transfer WHERE campaign=? AND state='pending'",(cid,)).fetchone():
        raise Conflict('Pending item transfer recovery blocks reconnect')
    if store.db.execute("SELECT 1 FROM event WHERE campaign=? AND revision>? AND kind NOT IN ('presence','follower_observed','historical_recovery_prepared') LIMIT 1",(cid,snapshot['revision'])).fetchone():
        raise Conflict('Campaign state advanced beyond this saved pair; create a new paired checkpoint or recover both players together')
    return {'allowed':True,'epoch':epoch,'checkpoint':campaign['head'] or '', 'revision':campaign['revision']}


def capture_native(store,cid,pid,ess,profile,runtime,operation,**kwargs):
    from .checkpoints import capture
    result=capture(store,cid,pid,ess,profile,runtime,operation,**kwargs)
    result['native_identity']=enroll_snapshot(store,cid,pid,result['id'])
    return result
