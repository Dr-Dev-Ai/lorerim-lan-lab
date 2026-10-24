"""Authenticated, recoverable two-player checkpoint protocol over the native relay."""
import base64
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from .store import Conflict,Denied,canonical
from .cosave import guid,read_identity
from .checkpoints import sha_file,put_blob,blob_path,verify_snapshot

ACTIVE=('requested','frozen','saving')
KINDS={'ess':('.ess',b'TESV_SAVEGAME'),'skse':('.skse',b'SKSE')}
MAX_CHUNK=24576
MAX_SAVE=2*1024**3

def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS coop_request(
      id TEXT PRIMARY KEY, campaign TEXT NOT NULL REFERENCES campaign(id), epoch TEXT NOT NULL,
      parent TEXT, revision INTEGER NOT NULL, label TEXT NOT NULL, state TEXT NOT NULL,
      created REAL NOT NULL, expires REAL NOT NULL, failure TEXT NOT NULL DEFAULT '');
    CREATE UNIQUE INDEX IF NOT EXISTS coop_active ON coop_request(campaign) WHERE state IN ('requested','frozen','saving');
    CREATE TABLE IF NOT EXISTS coop_peer(
      proposal TEXT NOT NULL REFERENCES coop_request(id), player TEXT NOT NULL REFERENCES player(id),
      ready INTEGER NOT NULL DEFAULT 0, profile TEXT NOT NULL DEFAULT '{}', PRIMARY KEY(proposal,player));
    CREATE TABLE IF NOT EXISTS coop_upload(
      proposal TEXT NOT NULL REFERENCES coop_request(id), player TEXT NOT NULL REFERENCES player(id),
      kind TEXT NOT NULL, total INTEGER NOT NULL, sha256 TEXT NOT NULL, received INTEGER NOT NULL DEFAULT 0,
      verified INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(proposal,player,kind));
    ''')

def active(store,cid):
    row=store.db.execute("SELECT * FROM coop_request WHERE campaign=? AND state IN ('requested','frozen','saving')",(cid,)).fetchone()
    return dict(row) if row else None

def expire(store):
    with store.transaction():
        return store.db.execute("UPDATE coop_request SET state='aborted',failure='Checkpoint request expired' WHERE state IN ('requested','frozen','saving') AND expires<=?",(time.time(),)).rowcount

def request(store,cid,pid,label,operation):
    def apply():
        store.leader(cid,pid)
        if active(store,cid):raise Conflict('A co-op checkpoint is already in progress')
        players=[dict(row) for row in store.db.execute('SELECT id,online FROM player WHERE campaign=?',(cid,))]
        if len(players)<2 or not all(row['online'] for row in players):raise Conflict('Both campaign players must be connected before creating a co-op checkpoint')
        bindings={row['player'] for row in store.db.execute('SELECT player FROM native_player WHERE campaign=?',(cid,))}
        if bindings!={row['id'] for row in players}:raise Conflict('Every player needs an enrolled native save')
        if store.db.execute("SELECT 1 FROM transfer WHERE campaign=? AND state='pending'",(cid,)).fetchone():raise Conflict('Finish pending item transfers first')
        campaign=store.campaign(cid);epoch=store.one('SELECT epoch FROM native_epoch WHERE campaign=?',(cid,))['epoch']
        proposal=str(uuid.uuid4());now=time.time()
        store.db.execute('INSERT INTO coop_request(id,campaign,epoch,parent,revision,label,state,created,expires) VALUES(?,?,?,?,?,?,?,?,?)',
            (proposal,cid,epoch,campaign['head'],campaign['revision'],str(label)[:120],'requested',now,now+1800))
        for row in players:store.db.execute('INSERT INTO coop_peer(proposal,player) VALUES(?,?)',(proposal,row['id']))
        return status(store,cid,pid,proposal)
    return store.mutate(cid,operation,'coopsave_prepare',[pid,label],apply)

def status(store,cid,pid,proposal=None):
    store.member(cid,pid)
    if proposal:row=store.one('SELECT * FROM coop_request WHERE campaign=? AND id=?',(cid,guid(proposal)))
    else:
        found=store.db.execute('SELECT * FROM coop_request WHERE campaign=? ORDER BY created DESC LIMIT 1',(cid,)).fetchone()
        if not found:return {'state':'idle'}
        row=dict(found)
    row['peers']=[dict(p) for p in store.db.execute('SELECT player,ready FROM coop_peer WHERE proposal=?',(row['id'],))]
    row['uploads']=[dict(p) for p in store.db.execute('SELECT player,kind,total,received,verified FROM coop_upload WHERE proposal=?',(row['id'],))]
    return row

def _owned(store,cid,pid,proposal):
    row=store.one('SELECT * FROM coop_request WHERE campaign=? AND id=?',(cid,guid(proposal)))
    store.one('SELECT player FROM coop_peer WHERE proposal=? AND player=?',(proposal,pid))
    if row['state'] not in ACTIVE or row['expires']<=time.time():raise Conflict('Checkpoint is no longer active')
    epoch=store.one('SELECT epoch FROM native_epoch WHERE campaign=?',(cid,))['epoch']
    if row['epoch']!=epoch or row['parent']!=store.campaign(cid)['head']:raise Conflict('Campaign lineage changed during checkpoint')
    return row

def ready(store,cid,pid,proposal,profile):
    if not isinstance(profile,dict) or set(profile)!= {'plugins.txt','modlist.txt'}:raise ValueError('Both profile hashes are required')
    with store.transaction():
        row=_owned(store,cid,pid,proposal)
        if row['state'] not in ('requested','frozen'):raise Conflict('Checkpoint already sealed')
        binding=store.one('SELECT snapshot FROM native_player WHERE campaign=? AND player=?',(cid,pid))
        snapshot=store.one('SELECT * FROM snapshot WHERE id=?',(binding['snapshot'],))
        files=verify_snapshot(store,snapshot)
        for name,digest in profile.items():
            if files['profile/'+name]['sha256']!=digest:raise Conflict('The running profile changed since native enrollment')
        store.db.execute('UPDATE coop_peer SET ready=1,profile=? WHERE proposal=? AND player=?',(canonical(profile),proposal,pid))
        store.db.execute("UPDATE coop_request SET state='frozen' WHERE id=?",(proposal,))
        return {'ready':True}

def seal(store,cid,pid,proposal):
    with store.transaction():
        store.leader(cid,pid);row=_owned(store,cid,pid,proposal)
        if row['state']=='saving':return status(store,cid,pid,proposal)
        if store.db.execute('SELECT 1 FROM coop_peer WHERE proposal=? AND ready=0',(proposal,)).fetchone():raise Conflict('Waiting for both clients to pause')
        if store.db.execute("SELECT 1 FROM transfer WHERE campaign=? AND state='pending'",(cid,)).fetchone():raise Conflict('Item recovery blocks checkpoint sealing')
        store.db.execute("UPDATE coop_request SET state='saving',revision=? WHERE id=?",(store.campaign(cid)['revision'],proposal))
        return status(store,cid,pid,proposal)

def _path(store,proposal,pid,kind):
    guid(proposal);guid(pid)
    if kind not in KINDS:raise ValueError('Unknown save member')
    return store.root/'native-uploads'/proposal/pid/('character'+KINDS[kind][0])

def upload(store,cid,pid,proposal,kind,offset,total,digest,encoded):
    if type(offset) is not int or type(total) is not int or not 0<=offset<=total<=MAX_SAVE or total==0:raise ValueError('Invalid upload extent')
    if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('Invalid save digest')
    try:chunk=base64.b64decode(encoded,validate=True)
    except (ValueError,TypeError) as error:raise ValueError('Invalid chunk encoding') from error
    if not 0<len(chunk)<=MAX_CHUNK or offset+len(chunk)>total:raise ValueError('Invalid chunk length')
    with store.transaction():
        row=_owned(store,cid,pid,proposal)
        if row['state']!='saving':raise Conflict('Checkpoint is not sealed')
        path=_path(store,proposal,pid,kind)
        existing=store.db.execute('SELECT * FROM coop_upload WHERE proposal=? AND player=? AND kind=?',(proposal,pid,kind)).fetchone()
        if existing is None:
            if offset:raise Conflict('Upload must start at zero')
            store.db.execute('INSERT INTO coop_upload(proposal,player,kind,total,sha256) VALUES(?,?,?,?,?)',(proposal,pid,kind,total,digest))
            received=0
        else:
            if existing['total']!=total or existing['sha256']!=digest:raise Conflict('Upload identity changed')
            received=existing['received']
        if offset>received:raise Conflict('Out-of-order chunk')
        path.parent.mkdir(parents=True,exist_ok=True)
        # Exclusive creation; only files under the validated staging UUIDs are opened.
        if not path.exists():
            with path.open('xb'):pass
        with path.open('r+b') as stream:
            stream.seek(0,2);actual=stream.tell()
            if actual<received or actual>total:raise Conflict('Upload file and journal disagree')
            if offset<received:
                stream.seek(offset)
                if offset+len(chunk)>received or stream.read(len(chunk))!=chunk:raise Conflict('Retried chunk differs')
                return {'received':received,'verified':bool(existing['verified'])}
            if actual>offset:
                stream.seek(offset)
                if actual!=offset+len(chunk) or stream.read(len(chunk))!=chunk:raise Conflict('Uncommitted upload bytes differ; preserve for recovery')
            else:
                stream.write(chunk);stream.flush();os.fsync(stream.fileno())
        received=offset+len(chunk)
        verified=0
        if received==total:
            with path.open('rb') as stream:
                if stream.read(len(KINDS[kind][1]))!=KINDS[kind][1]:raise Conflict('Unrecognized save file header')
            if sha_file(path)!=digest:raise Conflict('Uploaded save hash differs')
            if kind=='skse':
                identity=read_identity(path)
                binding=store.one('SELECT character FROM native_player WHERE campaign=? AND player=?',(cid,pid))
                if (identity['campaign']!=cid or identity['character']!=binding['character'] or identity['epoch']!=row['epoch']
                    or identity['checkpoint']!=proposal or identity['revision']!=row['revision']):raise Conflict('Uploaded native identity differs from the sealed checkpoint')
            verified=1
        store.db.execute('UPDATE coop_upload SET received=?,verified=? WHERE proposal=? AND player=? AND kind=?',(received,verified,proposal,pid,kind))
        return {'received':received,'verified':bool(verified)}

def commit(store,cid,pid,proposal):
    with store.transaction():
        store.leader(cid,pid)
        row=store.one('SELECT * FROM coop_request WHERE campaign=? AND id=?',(cid,guid(proposal)))
        if row['state']=='committed':return {'committed':True,'checkpoint':proposal}
        row=_owned(store,cid,pid,proposal)
        if row['state']!='saving' or row['revision']!=store.campaign(cid)['revision']:raise Conflict('Sealed campaign state changed')
        peers=[p['player'] for p in store.db.execute('SELECT player FROM coop_peer WHERE proposal=?',(proposal,))]
        ids=[]
        for peer in peers:
            uploads={u['kind']:dict(u) for u in store.db.execute('SELECT * FROM coop_upload WHERE proposal=? AND player=?',(proposal,peer))}
            if set(uploads)!=set(KINDS) or not all(u['verified'] for u in uploads.values()):raise Conflict('Both complete save pairs are required')
            binding=store.one('SELECT snapshot FROM native_player WHERE player=? AND campaign=?',(peer,cid))
            old=store.one('SELECT * FROM snapshot WHERE id=?',(binding['snapshot'],))
            files=json.loads(old['files'])
            for kind in KINDS:
                path=_path(store,proposal,peer,kind)
                if sha_file(path)!=uploads[kind]['sha256']:raise Conflict('Upload changed before commit')
                files['save/character'+KINDS[kind][0]]=put_blob(store,path)
            sid=str(uuid.uuid4());ids.append(sid)
            store.db.execute('INSERT INTO snapshot VALUES(?,?,?,?,?,?,?,?)',
                (sid,cid,peer,row['revision'],row['parent'],store.campaign(cid)['manifest'],canonical(files),time.time()))
            store.db.execute('UPDATE native_player SET snapshot=? WHERE campaign=? AND player=?',(sid,cid,peer))
        state=store.domain_state(cid)
        store.db.execute('INSERT INTO checkpoint VALUES(?,?,?,?,?,?,?,?)',
            (proposal,cid,row['revision'],row['parent'],row['label'],canonical(ids),canonical(state),time.time()))
        store.db.execute('UPDATE campaign SET head=? WHERE id=?',(proposal,cid))
        store.db.execute("UPDATE coop_request SET state='committed' WHERE id=?",(proposal,))
        return {'committed':True,'checkpoint':proposal,'snapshots':ids}

def abort(store,cid,pid,proposal,reason='Checkpoint cancelled'):
    with store.transaction():
        store.member(cid,pid)
        row=store.one('SELECT * FROM coop_request WHERE campaign=? AND id=?',(cid,guid(proposal)))
        if row['state']=='committed':return {'committed':True,'checkpoint':proposal}
        store.one('SELECT player FROM coop_peer WHERE proposal=? AND player=?',(proposal,pid))
        store.db.execute("UPDATE coop_request SET state='aborted',failure=? WHERE id=?",(str(reason)[:200],proposal))
        return {'aborted':True,'checkpoint':store.campaign(cid)['head'] or ''}
