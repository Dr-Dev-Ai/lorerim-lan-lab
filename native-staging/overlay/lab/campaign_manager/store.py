"""Transactional campaign state. This module never modifies Skyrim saves or actors."""
from __future__ import annotations
import hashlib
import json
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

SCHEMA = 1
FORM_KEY = re.compile(r'^[^/\\|\x00-\x1f]+\.(?:esm|esp|esl)\|[0-9a-fA-F]{1,8}$', re.I)

class Conflict(ValueError):
    pass

class Denied(ValueError):
    pass

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)

def form_key(value):
    if not isinstance(value, str) or not FORM_KEY.fullmatch(value):
        raise ValueError('Expected plugin-qualified local reference ID: Plugin.esp|001234')
    plugin, local = value.rsplit('|', 1)
    if int(local, 16) > 0xffffff:
        raise ValueError('Use the local reference ID, without a runtime load-order prefix')
    return plugin.casefold() + '|' + f'{int(local, 16):06x}'

class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / 'campaign.sqlite3', timeout=15, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, SCHEMA):
            self.close()
            raise Conflict(f'Unsupported database schema {version}')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS campaign(
          id TEXT PRIMARY KEY, name TEXT NOT NULL, leader TEXT, revision INTEGER NOT NULL DEFAULT 0,
          head TEXT, manifest TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS player(
          id TEXT PRIMARY KEY, campaign TEXT NOT NULL REFERENCES campaign(id), name TEXT NOT NULL,
          token_hash TEXT NOT NULL UNIQUE, online INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS presence_session(
          session TEXT PRIMARY KEY, campaign TEXT NOT NULL REFERENCES campaign(id),
          player TEXT NOT NULL REFERENCES player(id), expires REAL NOT NULL,
          state TEXT NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS presence_active ON presence_session(player) WHERE state='active';
        CREATE TABLE IF NOT EXISTS native_epoch(
          campaign TEXT PRIMARY KEY REFERENCES campaign(id), epoch TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS native_player(
          player TEXT PRIMARY KEY REFERENCES player(id), campaign TEXT NOT NULL REFERENCES campaign(id),
          character TEXT NOT NULL, snapshot TEXT NOT NULL REFERENCES snapshot(id), UNIQUE(campaign,character));
        CREATE TABLE IF NOT EXISTS follower(
          campaign TEXT NOT NULL REFERENCES campaign(id), actor TEXT NOT NULL,
          owner TEXT NOT NULL REFERENCES player(id), state TEXT NOT NULL, parked INTEGER NOT NULL,
          metadata TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(campaign,actor));
        CREATE TABLE IF NOT EXISTS npc_rule(
          campaign TEXT NOT NULL REFERENCES campaign(id), actor TEXT NOT NULL, category TEXT NOT NULL,
          PRIMARY KEY(campaign,actor));
        CREATE TABLE IF NOT EXISTS lease(
          campaign TEXT NOT NULL REFERENCES campaign(id), actor TEXT NOT NULL,
          player TEXT NOT NULL REFERENCES player(id), token TEXT NOT NULL,
          generation INTEGER NOT NULL, expires REAL NOT NULL, PRIMARY KEY(campaign,actor));
        CREATE TABLE IF NOT EXISTS artifact(
          campaign TEXT NOT NULL REFERENCES campaign(id), key TEXT NOT NULL, name TEXT NOT NULL,
          PRIMARY KEY(campaign,key));
        CREATE TABLE IF NOT EXISTS item(
          id TEXT PRIMARY KEY, campaign TEXT NOT NULL REFERENCES campaign(id), artifact TEXT,
          holder TEXT NOT NULL, metadata TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
          state TEXT NOT NULL DEFAULT 'active', UNIQUE(campaign,artifact),
          FOREIGN KEY(campaign,artifact) REFERENCES artifact(campaign,key));
        CREATE TABLE IF NOT EXISTS transfer(
          id TEXT PRIMARY KEY, campaign TEXT NOT NULL REFERENCES campaign(id), item TEXT NOT NULL REFERENCES item(id),
          source TEXT NOT NULL, destination TEXT NOT NULL, version INTEGER NOT NULL,
          state TEXT NOT NULL, source_ack INTEGER NOT NULL DEFAULT 0, destination_ack INTEGER NOT NULL DEFAULT 0);
        CREATE UNIQUE INDEX IF NOT EXISTS transfer_pending ON transfer(item) WHERE state='pending';
        CREATE TABLE IF NOT EXISTS snapshot(
          id TEXT PRIMARY KEY, campaign TEXT NOT NULL REFERENCES campaign(id), player TEXT NOT NULL REFERENCES player(id),
          revision INTEGER NOT NULL, parent TEXT, manifest TEXT NOT NULL, files TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS checkpoint(
          id TEXT PRIMARY KEY, campaign TEXT NOT NULL REFERENCES campaign(id), revision INTEGER NOT NULL,
          parent TEXT, label TEXT NOT NULL, snapshots TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS operation(
          campaign TEXT NOT NULL REFERENCES campaign(id), id TEXT NOT NULL, request TEXT NOT NULL,
          result TEXT NOT NULL, PRIMARY KEY(campaign,id));
        CREATE TABLE IF NOT EXISTS event(
          sequence INTEGER PRIMARY KEY AUTOINCREMENT, campaign TEXT NOT NULL REFERENCES campaign(id),
          revision INTEGER NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL, created REAL NOT NULL);
        ''')
        from .coopsave import initialize
        initialize(self.db)
        self.db.execute(f'PRAGMA user_version={SCHEMA}')
        for row in self.db.execute('SELECT id FROM campaign').fetchall():
            self.db.execute('INSERT OR IGNORE INTO native_epoch VALUES(?,?)',(row['id'],str(uuid.uuid4())))

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def one(self, sql, args=()):
        row = self.db.execute(sql, args).fetchone()
        if row is None:
            raise Conflict('Record not found')
        return dict(row)

    def campaign(self, cid):
        return self.one('SELECT * FROM campaign WHERE id=?', (cid,))

    def member(self, cid, pid):
        return self.one('SELECT * FROM player WHERE id=? AND campaign=?', (pid, cid))

    def leader(self, cid, pid):
        self.member(cid, pid)
        if self.campaign(cid)['leader'] != pid:
            raise Denied('Only the fixed campaign leader may perform this action')

    def event(self, cid, kind, data, advance=True):
        if advance:
            self.db.execute('UPDATE campaign SET revision=revision+1 WHERE id=?', (cid,))
        revision = self.campaign(cid)['revision']
        self.db.execute('INSERT INTO event(campaign,revision,kind,data,created) VALUES(?,?,?,?,?)',
                        (cid, revision, kind, canonical(data), time.time()))
        return revision

    def mutate(self, cid, operation, kind, payload, action):
        if not isinstance(operation, str) or not 8 <= len(operation) <= 128:
            raise ValueError('A persistent operation ID of 8–128 characters is required')
        request = canonical({'kind': kind, 'payload': payload})
        with self.transaction():
            self.campaign(cid)
            old = self.db.execute('SELECT request,result FROM operation WHERE campaign=? AND id=?', (cid, operation)).fetchone()
            if old:
                if old['request'] != request:
                    raise Conflict('Operation ID was already used for a different request')
                return json.loads(old['result'])
            if kind!='presence' and self.db.execute("SELECT 1 FROM coop_request WHERE campaign=? AND state='saving' LIMIT 1",(cid,)).fetchone():
                raise Conflict('Campaign is sealed while paired saves are captured')
            result = action()
            self.db.execute('INSERT INTO operation VALUES(?,?,?,?)', (cid, operation, request, canonical(result)))
            return result

    def create_campaign(self, name, manifest):
        if not isinstance(name, str) or not name.strip() or not isinstance(manifest, dict) or not manifest:
            raise ValueError('Campaign name and a non-empty compatibility manifest are required')
        cid = str(uuid.uuid4())
        with self.transaction():
            self.db.execute('INSERT INTO campaign(id,name,manifest) VALUES(?,?,?)', (cid, name.strip(), canonical(manifest)))
            self.db.execute('INSERT INTO native_epoch VALUES(?,?)',(cid,str(uuid.uuid4())))
        return self.campaign(cid)

    def add_player(self, cid, name, as_leader=False):
        if not isinstance(name, str) or not name.strip():
            raise ValueError('Player name is required')
        pid, token = str(uuid.uuid4()), secrets.token_urlsafe(32)
        with self.transaction():
            campaign = self.campaign(cid)
            if as_leader and campaign['leader']:
                raise Conflict('Campaign already has a fixed leader')
            self.db.execute('INSERT INTO player(id,campaign,name,token_hash) VALUES(?,?,?,?)',
                            (pid, cid, name.strip(), hashlib.sha256(token.encode()).hexdigest()))
            if as_leader:
                self.db.execute('UPDATE campaign SET leader=? WHERE id=?', (pid, cid))
            self.event(cid, 'player_added', {'player': pid, 'leader': as_leader})
        return {'campaign': cid, 'player': pid, 'token': token}

    def authenticate(self, token):
        if not isinstance(token, str) or not token:
            raise Denied('Missing player credential')
        row = self.db.execute('SELECT id,campaign,name FROM player WHERE token_hash=?',
                              (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if row is None:
            raise Denied('Invalid player credential')
        return dict(row)

    def set_presence(self, cid, pid, online, operation):
        def apply():
            self.member(cid, pid)
            self.db.execute('UPDATE player SET online=? WHERE id=?', (int(online), pid))
            self.db.execute("UPDATE follower SET parked=? WHERE campaign=? AND owner=? AND state!='dead'", (int(not online), cid, pid))
            if not online:
                self.db.execute('UPDATE lease SET expires=0 WHERE campaign=? AND player=?', (cid, pid))
            return {'revision': self.event(cid, 'presence', {'player': pid, 'online': online},advance=False)}
        return self.mutate(cid, operation, 'presence', [pid, bool(online)], apply)

    def _presence(self, cid, pid, online):
        self.db.execute('UPDATE player SET online=? WHERE id=? AND campaign=?', (int(online), pid, cid))
        self.db.execute("UPDATE follower SET parked=? WHERE campaign=? AND owner=? AND state!='dead'", (int(not online), cid, pid))
        if not online:
            self.db.execute('UPDATE lease SET expires=0 WHERE campaign=? AND player=?', (cid, pid))
        self.event(cid, 'presence', {'player': pid, 'online': online},advance=False)

    def _expire_sessions(self, now):
        rows = self.db.execute("SELECT * FROM presence_session WHERE state='active' AND expires<=?", (now,)).fetchall()
        for row in rows:
            self.db.execute("UPDATE presence_session SET state='expired' WHERE session=?", (row['session'],))
            self._presence(row['campaign'], row['player'], False)
        return len(rows)

    def expire_sessions(self):
        with self.transaction():
            return self._expire_sessions(time.time())

    def session(self, cid, pid, key, action, proof=None):
        if not isinstance(key, str) or not 16 <= len(key) <= 128 or not re.fullmatch(r'[A-Za-z0-9_-]+', key):
            raise ValueError('A connection-scoped session key is required')
        if action not in ('open', 'heartbeat', 'close'):
            raise ValueError('Unknown session action')
        with self.transaction():
            self.member(cid, pid)
            now = time.time()
            self._expire_sessions(now)
            admission = None
            if action == 'open' and proof is not None:
                from .admission import check
                admission = check(self,cid,pid,proof)
            row = self.db.execute('SELECT * FROM presence_session WHERE session=?', (key,)).fetchone()
            if row and (row['campaign'] != cid or row['player'] != pid):
                raise Denied('Session belongs to another player')
            if action == 'close':
                if row is None:
                    # Tombstone prevents a delayed asynchronous open after disconnect.
                    self.db.execute('INSERT INTO presence_session VALUES(?,?,?,?,?)', (key,cid,pid,now,'closed'))
                elif row['state'] == 'active':
                    self.db.execute("UPDATE presence_session SET state='closed',expires=? WHERE session=?", (now,key))
                    self._presence(cid,pid,False)
                return {'closed': True}
            if row and row['state'] != 'active':
                raise Denied('Session expired or closed; reconnect with a new session key')
            if action == 'heartbeat' and row is None:
                raise Denied('Session was never attached')
            if row is None:
                if self.db.execute("SELECT session FROM presence_session WHERE player=? AND state='active'", (pid,)).fetchone():
                    raise Conflict('Player is already attached to another connection')
                self.db.execute('INSERT INTO presence_session VALUES(?,?,?,?,?)', (key,cid,pid,now+45,'active'))
                self._presence(cid,pid,True)
            else:
                self.db.execute('UPDATE presence_session SET expires=? WHERE session=?', (now+45,key))
            campaign=self.campaign(cid)
            result = {'attached':True,'expires':now+45,'revision':campaign['revision'],
                      'epoch':self.one('SELECT epoch FROM native_epoch WHERE campaign=?',(cid,))['epoch'],'checkpoint':campaign['head'] or ''}
            if admission: result.update(admission)
            return result

    def mark_native_world_changed(self,cid,pid,operation):
        def apply():
            self.member(cid,pid)
            campaign=self.campaign(cid)
            epoch=self.one('SELECT epoch FROM native_epoch WHERE campaign=?',(cid,))['epoch']
            revision=self.event(cid,'native_world_changed',{'head':campaign['head'],'player':pid})
            return {'recorded':True,'epoch':epoch,'checkpoint':campaign['head'] or '', 'revision':revision}
        return self.mutate(cid,operation,'native_world_changed',[pid],apply)

    def register_follower(self, cid, pid, actor, metadata, operation):
        actor = form_key(actor)
        def apply():
            player = self.member(cid, pid)
            old = self.db.execute('SELECT * FROM follower WHERE campaign=? AND actor=?', (cid, actor)).fetchone()
            if old:
                if old['owner'] != pid or old['state'] == 'dead':
                    raise Conflict('Follower is already owned or permanently recorded as dead')
                return dict(old)
            self.db.execute('INSERT INTO follower(campaign,actor,owner,state,parked,metadata) VALUES(?,?,?,?,?,?)',
                            (cid, actor, pid, 'following', int(not player['online']), canonical(metadata)))
            self.event(cid, 'follower_registered', {'actor': actor, 'owner': pid})
            return self.one('SELECT * FROM follower WHERE campaign=? AND actor=?', (cid, actor))
        return self.mutate(cid, operation, 'follower_register', [pid, actor, metadata], apply)

    def follower_state(self, cid, pid, actor, state, metadata, expected, operation):
        actor = form_key(actor)
        if state not in ('following', 'waiting', 'dismissed', 'dead'):
            raise ValueError('Unknown follower state')
        def apply():
            self.member(cid, pid)
            row = self.one('SELECT * FROM follower WHERE campaign=? AND actor=?', (cid, actor))
            if row['owner'] != pid:
                raise Denied('This follower belongs to another player')
            if row['version'] != expected or row['state'] == 'dead':
                raise Conflict('Stale follower state, or follower is dead')
            self.db.execute('UPDATE follower SET state=?,metadata=?,version=version+1 WHERE campaign=? AND actor=?',
                            (state, canonical(metadata), cid, actor))
            self.event(cid, 'follower_state', {'actor': actor, 'state': state})
            return self.one('SELECT * FROM follower WHERE campaign=? AND actor=?', (cid, actor))
        return self.mutate(cid, operation, 'follower_state', [pid, actor, state, metadata, expected], apply)

    def observe_follower(self, cid, pid, actor, state, operation):
        """Native SFF adapter: claim before recruitment, then record owner commands.

        Ownership is independent of the transient client simulating the actor.
        Repeated observations do not advance revision or resurrect dead followers.
        """
        actor = form_key(actor)
        if state not in ('claim', 'seen', 'seen_waiting', 'following', 'waiting', 'dismissed', 'dead'):
            raise ValueError('Unknown follower observation')
        def apply():
            player = self.member(cid, pid)
            if not player['online']:
                raise Denied('Follower adapter requires an attached player')
            row = self.db.execute('SELECT * FROM follower WHERE campaign=? AND actor=?', (cid, actor)).fetchone()
            if row is None:
                if state not in ('claim','seen','seen_waiting'):
                    raise Denied('Claim the follower before changing its state')
                self.db.execute('INSERT INTO follower(campaign,actor,owner,state,parked,metadata) VALUES(?,?,?,?,?,?)',
                                (cid, actor, pid, 'waiting' if state == 'seen_waiting' else 'following', 0, canonical({'adapter': 'sff'})))
                self.event(cid, 'follower_observed' if state in ('seen','seen_waiting') else 'follower_registered', {'actor': actor, 'owner': pid},advance=state not in ('seen','seen_waiting'))
            else:
                if row['owner'] != pid:
                    raise Denied('This follower belongs to another player')
                if row['state'] == 'dead' and state not in ('dead','seen','seen_waiting'):
                    raise Conflict('A permanently dead follower cannot be recruited or restored')
                target = row['state'] if state in ('seen','seen_waiting') else ('following' if state == 'claim' else state)
                if row['state'] != target:
                    self.db.execute('UPDATE follower SET state=?,version=version+1 WHERE campaign=? AND actor=?',
                                    (target, cid, actor))
                    self.event(cid, 'follower_state', {'actor': actor, 'state': target})
            return self.one('SELECT * FROM follower WHERE campaign=? AND actor=?', (cid, actor))
        return self.mutate(cid, operation, 'follower_observe', [pid, actor, state], apply)

    def set_npc_rule(self, cid, pid, actor, category, operation):
        actor = form_key(actor)
        if category not in ('quest', 'service'):
            raise ValueError('NPC category must be quest or service')
        def apply():
            self.leader(cid, pid)
            self.db.execute('INSERT INTO npc_rule VALUES(?,?,?) ON CONFLICT(campaign,actor) DO UPDATE SET category=excluded.category',
                            (cid, actor, category))
            # Changing classification invalidates any previous conversation grant.
            self.db.execute('UPDATE lease SET expires=0 WHERE campaign=? AND actor=?', (cid, actor))
            return {'revision': self.event(cid, 'npc_rule', {'actor': actor, 'category': category})}
        return self.mutate(cid, operation, 'npc_rule', [pid, actor, category], apply)

    def permission(self, cid, pid, actor, action):
        self.member(cid, pid)
        actor = form_key(actor)
        follower = self.db.execute('SELECT * FROM follower WHERE campaign=? AND actor=?', (cid, actor)).fetchone()
        if action == 'observe':
            return True
        if action not in ('talk', 'command', 'trade', 'pickpocket', 'recruit', 'dismiss', 'quest'):
            raise Denied('Unsupported interaction')
        if follower:
            if follower['owner'] != pid or follower['parked'] or follower['state'] == 'dead':
                raise Denied('Follower is unavailable or belongs to another player')
        rule = self.db.execute('SELECT category FROM npc_rule WHERE campaign=? AND actor=?', (cid, actor)).fetchone()
        if action == 'quest' or (not follower and (not rule or rule['category'] != 'service')):
            self.leader(cid, pid)
        if action in ('command', 'recruit', 'dismiss') and not follower:
            raise Denied('Follower must be registered first')
        return True

    def acquire_dialogue(self, cid, pid, actor, action='talk', ttl=30):
        actor = form_key(actor)
        if action not in ('talk', 'trade', 'quest'):
            raise Denied('Only interactive dialogue actions can acquire a conversation grant')
        if isinstance(ttl, bool) or not isinstance(ttl, (int, float)) or not 1 <= ttl <= 60:
            raise ValueError('Lease duration must be 1–60 seconds')
        with self.transaction():
            self.permission(cid, pid, actor, action)
            now = time.time()
            row = self.db.execute('SELECT * FROM lease WHERE campaign=? AND actor=?', (cid, actor)).fetchone()
            if row and row['expires'] > now:
                raise Conflict('NPC is already in a conversation; renew the existing grant')
            generation = row['generation'] + 1 if row else 1
            token = secrets.token_urlsafe(24)
            self.db.execute('INSERT INTO lease(campaign,actor,player,token,generation,expires) VALUES(?,?,?,?,?,?) ON CONFLICT(campaign,actor) DO UPDATE SET '
                            'player=excluded.player,token=excluded.token,generation=excluded.generation,expires=excluded.expires',
                            (cid, actor, pid, token, generation, now + ttl))
            return {'actor': actor, 'token': token, 'generation': generation, 'expires': now + ttl}

    def check_dialogue(self, cid, pid, actor, token, generation, action='talk'):
        actor = form_key(actor)
        self.permission(cid, pid, actor, action)
        row = self.one('SELECT * FROM lease WHERE campaign=? AND actor=?', (cid, actor))
        if row['player'] != pid or not secrets.compare_digest(row['token'], token) or row['generation'] != generation or row['expires'] <= time.time():
            raise Denied('Expired or stale conversation grant')
        return row

    def renew_dialogue(self, cid, pid, actor, token, generation):
        with self.transaction():
            row = self.check_dialogue(cid, pid, actor, token, generation)
            expires = time.time() + 30
            self.db.execute('UPDATE lease SET expires=? WHERE campaign=? AND actor=?', (expires, cid, form_key(actor)))
            row['expires'] = expires
            return row

    def release_dialogue(self, cid, pid, actor, token, generation):
        with self.transaction():
            self.check_dialogue(cid, pid, actor, token, generation)
            self.db.execute('UPDATE lease SET expires=0 WHERE campaign=? AND actor=?', (cid, form_key(actor)))
        return {'released': True}

    def define_artifact(self, cid, pid, key, name, operation):
        key = form_key(key)
        def apply():
            self.leader(cid, pid)
            self.db.execute('INSERT INTO artifact VALUES(?,?,?) ON CONFLICT(campaign,key) DO UPDATE SET name=excluded.name', (cid, key, name))
            return {'revision': self.event(cid, 'artifact_defined', {'key': key, 'name': name})}
        return self.mutate(cid, operation, 'artifact_define', [pid, key, name], apply)

    def holder_owner(self, cid, holder):
        if not isinstance(holder, str) or ':' not in holder:
            raise ValueError('Holder must be player:<UUID>, follower:<reference>, or storage:<reference>')
        kind, key = holder.split(':', 1)
        if kind == 'player':
            self.member(cid, key)
            return key
        if kind == 'follower':
            return self.one('SELECT owner FROM follower WHERE campaign=? AND actor=?', (cid, form_key(key)))['owner']
        if kind == 'storage':
            form_key(key)
            return self.campaign(cid)['leader']
        raise ValueError('Unsupported holder type')

    def register_item(self, cid, pid, holder, metadata, artifact, operation):
        artifact = form_key(artifact) if artifact else None
        if not isinstance(metadata, dict):
            raise ValueError('Item metadata must be an object')
        metadata = dict(metadata)
        quantity = metadata.setdefault('quantity', 1)
        if type(quantity) is not int or not 1 <= quantity <= 2147483647 or (artifact and quantity != 1):
            raise Conflict('Item quantity is invalid, or a unique artifact has more than one copy')
        def apply():
            self.leader(cid, pid)  # authoritative adapter/admin registration, never arbitrary member inventory claims
            self.holder_owner(cid, holder)
            if artifact:
                self.one('SELECT key FROM artifact WHERE campaign=? AND key=?', (cid, artifact))
                if self.db.execute('SELECT id FROM item WHERE campaign=? AND artifact=?', (cid, artifact)).fetchone():
                    raise Conflict('This campaign artifact already exists; conflicting import held')
            iid = str(uuid.uuid4())
            self.db.execute('INSERT INTO item(id,campaign,artifact,holder,metadata) VALUES(?,?,?,?,?)', (iid, cid, artifact, holder, canonical(metadata)))
            self.event(cid, 'item_registered', {'item': iid, 'artifact': artifact, 'holder': holder})
            return self.one('SELECT * FROM item WHERE id=?', (iid,))
        return self.mutate(cid, operation, 'item_register', [pid, holder, metadata, artifact], apply)

    def prepare_transfer(self, cid, pid, iid, destination, expected, operation):
        def apply():
            row = self.one('SELECT * FROM item WHERE campaign=? AND id=?', (cid, iid))
            if self.holder_owner(cid, row['holder']) != pid:
                raise Denied('Only the current holder may initiate a transfer')
            self.holder_owner(cid, destination)
            if destination == row['holder'] or row['version'] != expected or row['state'] != 'active':
                raise Conflict('Stale or invalid item transfer')
            if self.db.execute("SELECT id FROM transfer WHERE item=? AND state='pending'", (iid,)).fetchone():
                raise Conflict('Item already has a pending transfer')
            tid = str(uuid.uuid4())
            self.db.execute('INSERT INTO transfer(id,campaign,item,source,destination,version,state) VALUES(?,?,?,?,?,?,?)',
                            (tid, cid, iid, row['holder'], destination, expected, 'pending'))
            self.event(cid, 'transfer_prepared', {'transfer': tid, 'item': iid})
            return self.one('SELECT * FROM transfer WHERE id=?', (tid,))
        return self.mutate(cid, operation, 'transfer_prepare', [pid, iid, destination, expected], apply)

    def acknowledge_transfer(self, cid, pid, tid, phase, operation):
        if phase not in ('source_removed', 'destination_added'):
            raise ValueError('Invalid transfer phase')
        def apply():
            row = self.one('SELECT * FROM transfer WHERE campaign=? AND id=?', (cid, tid))
            holder = row['source'] if phase == 'source_removed' else row['destination']
            if self.holder_owner(cid, holder) != pid:
                raise Denied('Wrong participant for transfer acknowledgement')
            if row['state'] == 'committed':
                return row
            if row['state'] != 'pending' or (phase == 'destination_added' and not row['source_ack']):
                raise Conflict('Transfer is not ready for this acknowledgement')
            column = 'source_ack' if phase == 'source_removed' else 'destination_ack'
            if not row[column]:
                self.db.execute(f'UPDATE transfer SET {column}=1 WHERE id=?', (tid,))
                self.event(cid, 'transfer_ack', {'transfer': tid, 'phase': phase})
            if phase == 'destination_added':
                changed = self.db.execute('UPDATE item SET holder=?,version=version+1 WHERE id=? AND campaign=? AND version=? AND holder=?',
                                          (row['destination'], row['item'], cid, row['version'], row['source'])).rowcount
                if changed != 1:
                    raise Conflict('Item changed during transfer; recovery required')
                self.db.execute("UPDATE transfer SET state='committed' WHERE id=?", (tid,))
            return self.one('SELECT * FROM transfer WHERE id=?', (tid,))
        return self.mutate(cid, operation, 'transfer_ack', [pid, tid, phase], apply)

    def abort_transfer(self, cid, pid, tid, operation):
        def apply():
            row = self.one('SELECT * FROM transfer WHERE campaign=? AND id=?', (cid, tid))
            if self.holder_owner(cid, row['source']) != pid:
                raise Denied('Only the source owner may cancel')
            if row['state'] != 'pending' or row['source_ack'] or row['destination_ack']:
                raise Conflict('Cannot cancel after game-side mutation; recover the pending transfer')
            self.db.execute("UPDATE transfer SET state='aborted' WHERE id=?", (tid,))
            return {'revision': self.event(cid, 'transfer_aborted', {'transfer': tid})}
        return self.mutate(cid, operation, 'transfer_abort', [pid, tid], apply)

    def domain_state(self, cid):
        result = {'campaign': self.campaign(cid)}
        for table in ('player', 'follower', 'artifact', 'item', 'npc_rule', 'native_player'):
            columns = 'id,name' if table == 'player' else '*'
            result[table] = [dict(row) for row in self.db.execute(f'SELECT {columns} FROM {table} WHERE campaign=?', (cid,))]
        result['native_epoch']=self.one('SELECT epoch FROM native_epoch WHERE campaign=?',(cid,))['epoch']
        return result

    def summary(self, cid):
        result = self.campaign(cid)
        for key, table in [('players','player'), ('followers','follower'), ('items','item'), ('transfers','transfer'), ('checkpoints','checkpoint')]:
            columns = 'id,name,online' if table == 'player' else '*'
            result[key] = [dict(row) for row in self.db.execute(f'SELECT {columns} FROM {table} WHERE campaign=?', (cid,))]
        result['native_epoch']=self.one('SELECT epoch FROM native_epoch WHERE campaign=?',(cid,))['epoch']
        result['native_players']=[dict(row) for row in self.db.execute('SELECT player,character,snapshot FROM native_player WHERE campaign=?',(cid,))]
        result['game_integration'] = False
        return result
