"""Loopback API for future native adapters; not an in-game enforcement mechanism."""
import json
import socket
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .store import Store, Conflict, Denied, canonical

MAX_BODY = 1024 * 1024

def dispatch(store, actor, route, body):
    cid, pid = actor['campaign'], actor['id']
    # Campaign/player IDs are always taken from the credential, never trusted from JSON.
    op = body.get('operation', '')
    if route.startswith('/v1/coopsave/'):
        from . import coopsave
        action=route.rsplit('/',1)[1]
        if action=='status':return coopsave.status(store,cid,pid,body.get('proposal'))
        if action=='prepare':return coopsave.request(store,cid,pid,body.get('label','Co-op save'),op)
        if action=='ready':return coopsave.ready(store,cid,pid,body['proposal'],body['profile'])
        if action=='seal':return coopsave.seal(store,cid,pid,body['proposal'])
        if action=='upload':return coopsave.upload(store,cid,pid,body['proposal'],body['kind'],body['offset'],body['total'],body['sha256'],body['data'])
        if action=='commit':return coopsave.commit(store,cid,pid,body['proposal'])
        if action=='abort':return coopsave.abort(store,cid,pid,body['proposal'],body.get('reason','Checkpoint cancelled'))
        raise ValueError('Unknown checkpoint action')
    if route == '/v1/me':
        return {'player': pid, 'campaign': cid, 'is_leader': store.campaign(cid)['leader'] == pid}
    if route == '/v1/state':
        return store.summary(cid)
    if route in ('/v1/session/open', '/v1/session/heartbeat', '/v1/session/close'):
        action=route.rsplit('/',1)[1]
        if action=='open' and not isinstance(body.get('proof'),dict):raise Denied('Native save proof is required before admission')
        return store.session(cid,pid,body['session'],action,body.get('proof'))
    if route == '/v1/world/dirty':
        return store.mark_native_world_changed(cid,pid,op)
    if route == '/v1/presence':
        if type(body.get('online')) is not bool:
            raise ValueError('online must be a boolean')
        return store.set_presence(cid, pid, body['online'], op)
    if route == '/v1/followers/policies':
        return {'followers': [dict(row) for row in store.db.execute('SELECT * FROM follower WHERE campaign=?', (cid,))]}
    if route == '/v1/followers/observe':
        return store.observe_follower(cid, pid, body['actor'], body['state'], op)
    if route == '/v1/followers/register':
        return store.register_follower(cid, pid, body['actor'], body.get('metadata', {}), op)
    if route == '/v1/followers/state':
        return store.follower_state(cid, pid, body['actor'], body['state'], body.get('metadata', {}), body['version'], op)
    if route == '/v1/npcs/rule':
        return store.set_npc_rule(cid, pid, body['actor'], body['category'], op)
    if route == '/v1/permission':
        return {'allowed': store.permission(cid, pid, body['actor'], body['action'])}
    if route == '/v1/dialogue/acquire':
        return store.acquire_dialogue(cid, pid, body['actor'], body.get('action', 'talk'))
    if route in ('/v1/dialogue/renew', '/v1/dialogue/release', '/v1/dialogue/check'):
        method = {'/v1/dialogue/renew': store.renew_dialogue, '/v1/dialogue/release': store.release_dialogue,
                  '/v1/dialogue/check': store.check_dialogue}[route]
        return method(cid, pid, body['actor'], body['token'], body['generation'])
    if route == '/v1/artifacts/define':
        return store.define_artifact(cid, pid, body['key'], body['name'], op)
    if route == '/v1/items/register':
        return store.register_item(cid, pid, body['holder'], body.get('metadata', {}), body.get('artifact'), op)
    if route == '/v1/transfers/prepare':
        return store.prepare_transfer(cid, pid, body['item'], body['destination'], body['version'], op)
    if route == '/v1/transfers/ack':
        return store.acknowledge_transfer(cid, pid, body['transfer'], body['phase'], op)
    if route == '/v1/transfers/abort':
        return store.abort_transfer(cid, pid, body['transfer'], op)
    raise ValueError('Unknown API route')

class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def log_message(self, *_):
        pass  # Never log credentials, item metadata or request bodies.

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def reply(self, code, value):
        data = canonical(value).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/health':
            self.reply(200, {'status': 'staged', 'game_integration': False, 'schema': 1})
        else:
            self.reply(404, {'error': 'Not found'})

    def do_POST(self):
        store = None
        try:
            if self.headers.get('Origin') is not None:
                raise Denied('Browser-origin requests are not supported')
            if self.headers.get('Transfer-Encoding'):
                raise ValueError('Chunked request bodies are not supported')
            length = int(self.headers.get('Content-Length', '-1'))
            if not 0 <= length <= MAX_BODY:
                self.reply(413, {'error': 'Request body too large or missing length'})
                return
            if self.headers.get_content_type() != 'application/json':
                raise ValueError('Content-Type must be application/json')
            token = self.headers.get('Authorization', '')
            if not token.startswith('Bearer '):
                raise Denied('Player credential required')
            store = Store(self.server.data_root)
            actor = store.authenticate(token[7:])
            payload = self.rfile.read(length)
            if len(payload) != length:
                raise ValueError('Incomplete request body')
            body = json.loads(payload)
            if not isinstance(body, dict):
                raise ValueError('JSON object required')
            result = dispatch(store, actor, self.path, body)
            self.reply(200, result)
        except Denied as error:
            self.reply(403, {'error': str(error)})
        except Conflict as error:
            self.reply(409, {'error': str(error)})
        except (ValueError, KeyError, TypeError, UnicodeError) as error:
            self.reply(400, {'error': str(error)})
        except Exception:
            self.reply(500, {'error': 'Internal error; no successful operation confirmed. Retry with the same operation ID.'})
        finally:
            if store:
                store.close()

class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, root, port=10579):
        self.data_root = str(root)
        super().__init__(('127.0.0.1', port), Handler)

    def service_actions(self):
        # Expire orphaned presence even when no HTTP client sends another request.
        store = Store(self.data_root)
        try:
            store.expire_sessions()
            from .coopsave import expire
            expire(store)
        finally:
            store.close()

    def verify_request(self, request, client_address):
        return client_address[0] == '127.0.0.1'

def serve(root, port=10579):
    with Server(root, port) as server:
        server.serve_forever()
