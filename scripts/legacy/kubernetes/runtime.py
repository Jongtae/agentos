"""Single-user, single-replica runtime; bounded deterministic tools only."""
from contextlib import contextmanager
import hmac
import json
import os
from pathlib import Path
import signal
import sqlite3
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir(exist_ok=True)
        self.path = self.root / 'agent.db'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS memories (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL,
                    payload TEXT NOT NULL, due REAL NOT NULL, status TEXT NOT NULL,
                    result TEXT, created REAL NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def enqueue(self, body):
        if not isinstance(body, dict):
            raise ValueError('JSON object required')
        action = body.get('action')
        if action not in ('remember', 'recall', 'list_files'):
            raise ValueError('action must be remember, recall, or list_files')
        payload = {'action': action}
        for key in ('key', 'value'):
            if key in body:
                if not isinstance(body[key], str) or len(body[key]) > 4096:
                    raise ValueError('invalid ' + key)
                payload[key] = body[key]
        if action in ('remember', 'recall') and not payload.get('key'):
            raise ValueError('key required')
        if action == 'remember' and 'value' not in payload:
            raise ValueError('value required')
        delay = body.get('delay_seconds', 0)
        if type(delay) not in (int, float) or not 0 <= delay <= 604800:
            raise ValueError('delay_seconds must be between 0 and 604800')
        request_key = body.get('request_key') or str(uuid.uuid4())
        if not isinstance(request_key, str) or len(request_key) > 128:
            raise ValueError('invalid request_key')
        encoded = json.dumps({'tool': payload, 'delay': delay}, sort_keys=True)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM tasks WHERE request_key=?', (request_key,)).fetchone()
            if old:
                if old['payload'] != encoded:
                    raise ValueError('request_key already used with different arguments')
                return dict(old)
            task_id = str(uuid.uuid4())
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',
                       (task_id, request_key, encoded, time.time()+delay, 'queued', None, time.time()))
            return dict(db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone())

    def tick(self):
        # All current tools have local effects inside the same DB transaction.
        # External adapters must NOT inherit this execution/retry contract.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM tasks WHERE status='queued' AND due<=? ORDER BY due LIMIT 1", (time.time(),)).fetchone()
            if row is None:
                return
            tool = json.loads(row['payload'])['tool']
            if tool['action'] == 'remember':
                db.execute('INSERT INTO memories VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (tool['key'], tool['value']))
                result = {'saved': tool['key']}
            elif tool['action'] == 'recall':
                item = db.execute('SELECT value FROM memories WHERE key=?', (tool['key'],)).fetchone()
                result = {'value': item['value'] if item else None}
            else:
                result = {'files': sorted(p.name for p in self.workspace.iterdir())}
            db.execute("UPDATE tasks SET status='succeeded', result=? WHERE id=?", (json.dumps(result), row['id']))

    def tasks(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM tasks ORDER BY created DESC LIMIT 100')]


def handler(store, token, owner, healthy=lambda: True):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, data):
            raw = json.dumps(data).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self):
            if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer '+token):
                self.send(401, {'error': 'unauthorized'})
                return False
            return True

        def do_GET(self):
            if self.path == '/healthz':
                return self.send(200 if healthy() else 503, {'ok': healthy()})
            if not self.authorized():
                return
            if self.path == '/v1/me':
                self.send(200, {'owner': owner, 'tools': ['remember', 'recall', 'list_files'], 'mode': 'deterministic-mvp'})
            elif self.path == '/v1/tasks':
                self.send(200, {'tasks': store.tasks()})
            else:
                self.send(404, {'error': 'not_found'})

        def do_POST(self):
            if not self.authorized():
                return
            if self.path != '/v1/tasks':
                return self.send(404, {'error': 'not_found'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384:
                    raise ValueError('body must be 1–16384 bytes')
                body = json.loads(self.rfile.read(length))
                self.send(202, store.enqueue(body))
            except (ValueError, UnicodeDecodeError) as exc:
                self.send(400, {'error': str(exc)})
    return Handler


def main():
    token = os.environ['AGENT_TOKEN']
    if len(token) < 32:
        raise ValueError('AGENT_TOKEN must contain at least 32 characters')
    store = Store(os.environ.get('AGENT_DATA', '/data'))
    stop = threading.Event()
    def worker():
        while not stop.is_set():
            store.tick()
            stop.wait(0.25)
    worker_thread = threading.Thread(target=worker, daemon=True)
    worker_thread.start()
    server = ThreadingHTTPServer(('0.0.0.0', 8080), handler(
        store, token, os.environ['AGENT_OWNER'],
        healthy=lambda: worker_thread.is_alive() and not stop.is_set()))
    def shutdown(signum, frame):
        stop.set()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()
        worker_thread.join(timeout=15)


if __name__ == '__main__':
    main()
