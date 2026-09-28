"""Black-box client for one AgentOS instance over its local HTTP API.

Only public owner routes are used, exactly as the local web page uses them:
``/api/local-login`` (or the first local ``/api/claim`` of a fresh data
folder), ``/api/chat``, ``/api/tasks/<id>``, ``/api/state`` and the read-only
personal-space, owner-model, preparation and settings routes.  The transport
is injectable so tests run without a server.
"""
import json
import time
import uuid
from http.cookies import SimpleCookie
from urllib.error import HTTPError
from urllib.request import Request, urlopen

#: Work statuses that are still moving.  Anything else is where the turn ended.
MOVING = frozenset({'queued', 'running'})


class ClientError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def urllib_transport(method, url, body, headers, timeout=30):
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read() or b''


class AgentOSClient:
    def __init__(self, base_url, transport=None, clock=time.monotonic, sleep=time.sleep):
        self.base = base_url.rstrip('/')
        self.transport = transport or urllib_transport
        self.clock = clock
        self.sleep = sleep
        self.cookie = ''

    # -- plumbing -------------------------------------------------------------
    def request(self, method, path, payload=None):
        headers = {'Host': self.base.split('://', 1)[-1]}
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            headers['Content-Type'] = 'application/json'
        if self.cookie:
            headers['Cookie'] = f'agentos_session={self.cookie}'
        status, response_headers, raw = self.transport(method, self.base + path, body, headers)
        for name, value in response_headers.items():
            if name.lower() == 'set-cookie':
                jar = SimpleCookie()
                jar.load(value)
                if 'agentos_session' in jar and jar['agentos_session'].value:
                    self.cookie = jar['agentos_session'].value
        try:
            data = json.loads(raw or b'{}')
        except ValueError:
            data = {'raw': raw[:200].decode('utf-8', 'replace')}
        if status >= 400:
            message = data.get('error') if isinstance(data, dict) else None
            raise ClientError(f'{method} {path} -> {status}: {message or "error"}', status)
        return data

    def get(self, path):
        return self.request('GET', path)

    def post(self, path, payload):
        return self.request('POST', path, payload)

    # -- session and worker ---------------------------------------------------
    def healthy(self):
        try:
            return bool(self.get('/healthz').get('ok'))
        except (ClientError, OSError):
            return False

    def login(self):
        """Local passwordless login; a never-claimed folder is claimed for local access first."""
        status = self.get('/api/status')
        if not status.get('claimed'):
            self.post('/api/claim', {})
            return
        self.post('/api/local-login', {})

    def select_worker(self, worker):
        """Make ``codex`` or ``claude-code`` the Work engine of this sandbox (owner route #571)."""
        return self.post('/api/subscription-engines/connect', {'engine': worker, 'officially_authenticated': True})

    # -- Judgment AI (the decision model) -------------------------------------
    def judgment(self):
        """``{'mode', 'available', 'engine', 'main', 'qualification'}`` of the decision route."""
        route = (self.get('/api/state').get('settings') or {}).get('decision_route') or {}
        active = route.get('active') or {}
        return {'mode': route.get('mode'), 'available': bool(active.get('available')), 'engine': active.get('engine'),
                'model': active.get('requested_model') or active.get('model'), 'main': route.get('main'),
                'transport': active.get('transport'), 'qualification': route.get('qualification') or {},
                'active': active}

    @staticmethod
    def judgment_ready(status, worker):
        """Qualified and, when it follows the Main AI, following this worker."""
        if not status['available']:
            return False
        return status['mode'] != 'follow_main' or status['main'] == worker

    def requalify_judgment(self, worker, status):
        """Ask AgentOS to (re)qualify the Judgment AI through the owner's own routes."""
        if status['mode'] == 'follow_main':
            return self.post('/api/main-ai/activate', {'route': worker})
        active = status['active']
        body = {key: active[key] for key in ('transport', 'engine', 'model_policy', 'effort') if active.get(key)}
        if active.get('requested_model'):
            body['model'] = active['requested_model']
        if not body.get('transport') or body['transport'] in ('none', 'off'):
            return None
        return self.post('/api/decision-route/activate', body)

    def wait_judgment(self, worker, timeout=300, interval=4.0):
        deadline = self.clock() + timeout
        while True:
            status = self.judgment()
            state = status['qualification'].get('state')
            if self.judgment_ready(status, worker) and state not in ('queued', 'running'):
                return status
            if state in ('failed', 'cancelled', 'interrupted') or self.clock() >= deadline:
                return status
            self.sleep(interval)

    # -- one turn -------------------------------------------------------------
    def send(self, message, request_key=None):
        return self.post('/api/chat', {'message': message, 'request_key': request_key or f'eval-{uuid.uuid4()}'})['id']

    def wait(self, task_id, timeout=900, interval=2.0):
        """Poll ``/api/tasks/<id>`` until the Work stops moving; returns the task detail."""
        deadline = self.clock() + timeout
        while True:
            detail = self.get(f'/api/tasks/{task_id}').get('selected') or {}
            if detail.get('status') not in MOVING:
                return detail
            if self.clock() >= deadline:
                return {**detail, 'timed_out': True}
            self.sleep(interval)

    def answer(self, task_id):
        """The delivered answer as the owner's web reads it (a withheld answer stays withheld)."""
        state = self.get('/api/state')
        for job in state.get('jobs') or []:
            if job.get('id') == task_id:
                return {'response': job.get('response'), 'answer_withheld': bool(job.get('answer_withheld')),
                        'status': job.get('status')}
        return {'response': None, 'answer_withheld': False, 'status': None}

    # -- owner-model upkeep ---------------------------------------------------
    def upkeep_busy(self):
        """Upkeep rows still waiting or running, 0 when idle, None when the route is unreadable.

        Owner-model upkeep runs after a Work ends and asynchronously (#805), so
        a snapshot taken right after the last turn can race the Memory it
        proposes.  Paused upkeep, or a spent daily cap with nothing running,
        will not move and counts as idle.
        """
        try:
            view = self.get('/api/owner-model')
        except ClientError:
            return None
        if not isinstance(view, dict) or 'pending' not in view:
            return None
        running = int(view.get('running') or 0)
        pending = int(view.get('pending') or 0)
        if not view.get('enabled', True):
            pending = 0
        cap = view.get('daily_calls')
        if isinstance(cap, int) and int(view.get('calls_last_24h') or 0) >= cap:
            pending = 0
        return pending + running

    def wait_upkeep_idle(self, timeout=90, interval=2.0):
        """Wait, bounded, until the sandbox's owner-model upkeep queue is idle (#832)."""
        started = self.clock()
        deadline = started + timeout
        while True:
            busy = self.upkeep_busy()
            if not busy or self.clock() >= deadline:
                return {'idle': busy == 0, 'busy': busy, 'waited': round(self.clock() - started, 1)}
            self.sleep(interval)

    # -- state snapshot -------------------------------------------------------
    SNAPSHOT_ROUTES = {'personal_space': '/api/personal-space', 'candidates': '/api/personal-space/memory-candidates',
                       'profile': '/api/personal-space/profile', 'owner_model': '/api/owner-model',
                       'preparations': '/api/preparations', 'settings': '/api/settings'}

    def snapshot(self):
        """Owner-state views before and after a scenario; an unavailable route is recorded, not fatal."""
        views = {}
        for name, path in self.SNAPSHOT_ROUTES.items():
            try:
                views[name] = self.get(path)
            except ClientError as exc:
                views[name] = {'unavailable': exc.status}
        return views


def compact_events(detail, limit=40):
    """Tool/status pairs of a Work's events: enough to cluster failures, without payloads."""
    rows = []
    for event in (detail.get('events') or [])[:limit]:
        if isinstance(event, dict):
            rows.append({key: event.get(key) for key in ('tool', 'status', 'label') if event.get(key) is not None})
    return rows


def _rows(view, *keys):
    for key in keys:
        value = view.get(key) if isinstance(view, dict) else None
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def state_diff(before, after):
    """New Memory rows, MemoryCandidates and preparations a scenario produced, plus changed settings."""
    def new(view_name, *keys):
        seen = {row.get('id') for row in _rows(before.get(view_name, {}), *keys)}
        return [row for row in _rows(after.get(view_name, {}), *keys) if row.get('id') not in seen]
    candidates = new('candidates', 'candidates', 'memory_candidates', 'items')
    space_candidates = new('personal_space', 'memory_candidates')
    known = {row.get('id') for row in candidates}
    candidates.extend(row for row in space_candidates if row.get('id') not in known)
    return {'memories': new('personal_space', 'memories'),
            'candidates': candidates,
            'preparations': new('preparations', 'preparations', 'items'),
            'settings_changed': before.get('settings') != after.get('settings'),
            'owner_model_changed': before.get('owner_model') != after.get('owner_model')}
