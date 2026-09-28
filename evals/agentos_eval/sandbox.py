"""Isolated AgentOS instances for evaluation.

Two steps:

1. ``snapshot_seed`` makes a sanitized seed folder once, from a data folder
   such as the owner's (read-only; SQLite files are copied with the SQLite
   backup API so a running server is never disturbed).  Sanitizing keeps the
   engine login, model keys and owner state, and removes what would let a
   sandbox act on the owner's outside world: the Telegram token (a sandbox
   must never poll or answer the owner's bot), Google connector tokens,
   connected Mac folders and the embedded-browser profile.  Queued Work and
   scheduled preparations are closed so a sandbox never re-runs the owner's
   pending work.
2. ``Sandbox`` copies a seed into a fresh folder and starts
   ``personal_agent.quickstart`` on its own loopback port, with its own
   engine-run folder, no browser, and PyObjC blocked (``sandbox_site``) so no
   window can open.  It never uses the owner's live port or data folder.

Secrets are copied file-to-file between owner-private (0600/0700) folders and
are never printed, logged or written into the repository.
"""
import fcntl
import json
import os
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .paths import LIVE_DATA, LIVE_PORTS, SANDBOX_SITE, SRC, eval_home

#: Secret slots a sandbox may keep: engine/model credentials and AgentOS's own
#: local signing keys.  Everything else (Telegram, OAuth tokens) is dropped.
KEEP_SECRETS = ('claude_code_token', 'model_key', 'lookup_state_key', 'memory_approval_secret', 'browser_step_secret')
KEEP_SECRET_PREFIXES = ('api_key:', 'decision_', 'search_key:')
#: Config rows removed from a seed: folder grants and the managed workspace.
DROP_CONFIG = ('file_roots', 'file_workspace')
#: Top-level files and folders of ``private/`` never copied into a seed.
SKIP_PRIVATE = {'logs', 'browser-profile', 'private', 'instance.lock', 'connections.lock', 'setup-link.txt',
                'drive-localhost-cert.pem', 'drive-localhost-key.pem'}
#: Environment names a sandbox server inherits from the eval process.
PASS_ENV = ('HOME', 'USER', 'LOGNAME', 'TMPDIR', 'LANG', 'LC_ALL', 'LC_CTYPE', 'CODEX_HOME', 'SHELL')


class SandboxError(RuntimeError):
    pass


def _keep_secret(name):
    return name in KEEP_SECRETS or any(name.startswith(prefix) for prefix in KEEP_SECRET_PREFIXES)


def sanitize_secrets(values):
    return {key: value for key, value in values.items() if _keep_secret(key)}


def _copy_sqlite(source, target):
    src = sqlite3.connect(f'file:{source}?mode=ro', uri=True)
    try:
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def sanitize_database(path):
    """Close the owner's pending work and outside-world bindings inside a seed database copy."""
    db = sqlite3.connect(path)
    try:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'config' in tables:
            for key in DROP_CONFIG:
                db.execute('DELETE FROM config WHERE key=?', (key,))
            row = db.execute("SELECT value FROM config WHERE key='telegram'").fetchone()
            if row:
                try:
                    telegram = json.loads(row[0]) if row[0] else {}
                except ValueError:
                    telegram = {}
                telegram = telegram if isinstance(telegram, dict) else {}
                telegram['enabled'] = False
                db.execute("UPDATE config SET value=? WHERE key='telegram'", (json.dumps(telegram),))
        if 'jobs' in tables:
            db.execute("UPDATE jobs SET status='interrupted' WHERE status IN ('queued','running')")
        if 'preparations' in tables:
            db.execute("UPDATE preparations SET state='cancelled' WHERE state IN ('proposed','scheduled','running')")
        if 'telegram_notifications' in tables:
            db.execute("DELETE FROM telegram_notifications WHERE state IN ('queued','sent')")
        db.commit()
    finally:
        db.close()


def snapshot_seed(source, target, overwrite=False):
    """Write a sanitized seed of data folder ``source`` into ``target``; returns a summary without values."""
    source, target = Path(source).expanduser().resolve(), Path(target).expanduser().resolve()
    if not (source / 'private' / 'quickstart.db').is_file():
        raise SandboxError(f'{source} is not an AgentOS data folder (private/quickstart.db missing)')
    if target == source or source in target.parents:
        raise SandboxError('the seed must live outside the source data folder')
    if target.exists():
        if not overwrite:
            raise SandboxError(f'{target} exists; pass overwrite to replace it')
        shutil.rmtree(target)
    old_umask = os.umask(0o077)
    try:
        (target / 'private').mkdir(parents=True, mode=0o700)
        copied = []
        for item in sorted((source / 'private').iterdir()):
            if item.name in SKIP_PRIVATE or item.suffix == '.log' or item.name.endswith(('-wal', '-shm', '-journal')):
                continue
            destination = target / 'private' / item.name
            if item.name == 'connections.json':
                values = json.loads(item.read_text())
                kept = sanitize_secrets(values if isinstance(values, dict) else {})
                destination.write_text(json.dumps(kept))
                copied.append(f'connections.json ({len(kept)} of {len(values)} slots kept)')
            elif item.suffix == '.db':
                _copy_sqlite(item, destination)
                sanitize_database(destination)
                copied.append(item.name)
            elif item.is_dir():
                shutil.copytree(item, destination, symlinks=False)
                copied.append(item.name + '/')
            elif item.is_file():
                shutil.copy2(item, destination)
                copied.append(item.name)
        for item in sorted(source.iterdir()):
            # Owner plugins travel with the profile; logs and engine runs do not.
            if item.name == 'plugins' and item.is_dir():
                shutil.copytree(item, target / 'plugins', symlinks=False)
                copied.append('plugins/')
    finally:
        os.umask(old_umask)
    (target / 'SEED.json').write_text(json.dumps({'source': str(source), 'created': time.time(), 'copied': copied},
                                                 ensure_ascii=False, indent=2))
    return {'seed': str(target), 'copied': copied}


def free_port(start=18900, end=19900, taken=()):
    for port in range(start, end):
        if port in LIVE_PORTS or port in taken or port + 1 in LIVE_PORTS:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(('127.0.0.1', port))
            except OSError:
                continue
        return port
    raise SandboxError('no free loopback port for a sandbox')


def sandbox_environment(data, base=None, src=SRC):
    """The minimal environment of one sandbox server: no AgentOS_* or connector settings inherited."""
    base = os.environ if base is None else base
    env = {name: base[name] for name in PASS_ENV if base.get(name)}
    extra_path = ['/opt/homebrew/bin', '/usr/local/bin',
                  str(Path(env.get('HOME', str(Path.home()))) / '.local' / 'bin')]
    env['PATH'] = os.pathsep.join(dict.fromkeys([*base.get('PATH', '').split(os.pathsep), *extra_path, '/usr/bin', '/bin']))
    env['PATH'] = os.pathsep.join(item for item in env['PATH'].split(os.pathsep) if item)
    env['PYTHONPATH'] = os.pathsep.join([str(SANDBOX_SITE), str(src)])
    env['AGENTOS_ENGINE_RUNS'] = str(Path(data) / 'engine-runs')
    env['PYTHONUNBUFFERED'] = '1'
    return env


#: Config rows that hold the Judgment AI qualification.  Its binding names the
#: store root and engine-run folder, so a qualification made in one sandbox
#: slot stays valid for that slot's stable path and is reused (``SandboxPool``).
JUDGMENT_KEYS = ('decision_route', 'decision_route_checks', 'decision_cli_capabilities', 'decision_model')


def seed_identity(seed):
    """What a cached qualification was made for: the seed path and its snapshot time."""
    if not seed:
        return 'fresh'
    try:
        created = json.loads((Path(seed) / 'SEED.json').read_text()).get('created')
    except (OSError, ValueError):
        created = None
    return f'{Path(seed).resolve()}@{created}'


def read_config(data, keys):
    """Config rows of a sandbox store (read-only; the server may be running)."""
    db = sqlite3.connect(f'file:{Path(data) / "private" / "quickstart.db"}?mode=ro', uri=True)
    try:
        marks = ','.join('?' * len(keys))
        return dict(db.execute(f'SELECT key, value FROM config WHERE key IN ({marks})', tuple(keys)).fetchall())
    finally:
        db.close()


def write_config(data, rows):
    db = sqlite3.connect(Path(data) / 'private' / 'quickstart.db')
    try:
        db.executemany('INSERT OR REPLACE INTO config(key, value) VALUES (?, ?)', list(rows.items()))
        db.commit()
    finally:
        db.close()


class Sandbox:
    """One fresh AgentOS instance on a copy of ``seed`` (or an empty folder when ``seed`` is None).

    With ``slot`` the data folder is ``<root>/slot-<n>`` (a stable path, wiped
    and re-copied for every run); without it a new temporary folder is used.
    """

    def __init__(self, root, seed=None, port=None, slot=None, python=None, src=SRC, keep=False, start_timeout=60):
        self.root = Path(root)
        self.seed = Path(seed).expanduser() if seed else None
        self.port = port
        self.slot = slot
        self.python = python or os.environ.get('AGENTOS_EVAL_SERVER_PYTHON') or shutil.which('python3') or sys.executable
        self.src = Path(src)
        self.keep = keep
        self.start_timeout = start_timeout
        self.process = None
        self.data = None
        self.log = None

    @property
    def url(self):
        return f'http://127.0.0.1:{self.port}'

    def prepare(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.slot is None:
            self.data = Path(tempfile.mkdtemp(prefix='sandbox-', dir=self.root))
        else:
            self.data = self.root / f'slot-{self.slot}'
            if self.data.exists():
                shutil.rmtree(self.data)
            self.data.mkdir(mode=0o700)
        resolved = self.data.resolve()
        if resolved == LIVE_DATA.resolve() or LIVE_DATA.resolve() in resolved.parents:
            raise SandboxError('refusing to run a sandbox inside the live AgentOS data folder')
        if self.seed:
            if not (self.seed / 'private' / 'quickstart.db').is_file():
                raise SandboxError(f'seed {self.seed} has no private/quickstart.db; run `snapshot` first')
            shutil.rmtree(self.data)
            shutil.copytree(self.seed, self.data, symlinks=False, ignore=shutil.ignore_patterns('SEED.json'))
        return self.data

    def start(self, config=None):
        """Copy the seed, apply ``config`` rows (a cached qualification) and start the server."""
        if self.port is None:
            self.port = free_port()
        if self.port in LIVE_PORTS:
            raise SandboxError('refusing to bind the live AgentOS port')
        self.prepare()
        if config and (self.data / 'private' / 'quickstart.db').is_file():
            write_config(self.data, config)
        argv = [self.python, '-m', 'personal_agent.quickstart', 'start', '--host', '127.0.0.1',
                '--port', str(self.port), '--drive-handoff-port', str(self.port + 1),
                '--data', str(self.data), '--no-browser']
        self.log = open(self.data / 'server.log', 'ab')
        self.process = subprocess.Popen(argv, cwd=str(self.data), env=sandbox_environment(self.data, src=self.src),
                                        stdin=subprocess.DEVNULL, stdout=self.log, stderr=subprocess.STDOUT,
                                        start_new_session=True)
        return self.process

    def wait_healthy(self, client, sleep=time.sleep, clock=time.monotonic):
        deadline = clock() + self.start_timeout
        while clock() < deadline:
            if self.process and self.process.poll() is not None:
                raise SandboxError(f'sandbox server exited with {self.process.returncode}; see {self.data}/server.log')
            if client.healthy():
                return True
            sleep(0.5)
        raise SandboxError(f'sandbox server did not become healthy within {self.start_timeout}s')

    def read_config(self, keys):
        return read_config(self.data, keys)

    def stop(self):
        if self.process and self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
                self.process.wait(timeout=10)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        if self.log:
            self.log.close()
        if self.data and self.data.exists() and not self.keep:
            shutil.rmtree(self.data, ignore_errors=True)


class SandboxPool:
    """At most ``size`` concurrent sandboxes; each scenario run gets a fresh copy of the seed.

    A fresh copy per run keeps trials independent (the docs' clean-state
    trials): Memory written by one scenario never leaks into another.  Runs
    use stable slot folders under ``root`` (one exclusive file lock per slot,
    so two sweeps never share one), which lets a Judgment AI qualification
    made in a slot be cached per slot, worker and seed and reused instead of
    re-running it (about a minute and a dozen model calls) on every run.
    """

    MAX_SLOTS = 16

    def __init__(self, size=3, seed=None, root=None, keep=False, sandbox_factory=Sandbox):
        if not 1 <= size <= self.MAX_SLOTS:
            raise ValueError(f'instances must be between 1 and {self.MAX_SLOTS}')
        self.size = size
        self.seed = seed
        self.root = Path(root) if root else eval_home() / 'sandboxes'
        self.keep = keep
        self.factory = sandbox_factory
        self.slots = threading.BoundedSemaphore(size)
        self.lock = threading.Lock()
        self.ports = set()
        self.held = {}

    def _claim_slot(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for slot in range(self.MAX_SLOTS):
            if slot in self.held:
                continue
            handle = open(self.root / f'slot-{slot}.lock', 'a')
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                handle.close()
                continue
            self.held[slot] = handle
            return slot
        raise SandboxError('every sandbox slot is in use by another sweep')

    def _release_slot(self, slot):
        handle = self.held.pop(slot, None)
        if handle:
            fcntl.flock(handle, fcntl.LOCK_UN)
            handle.close()

    def _cache_path(self, slot, worker):
        return self.root / f'slot-{slot}.{worker}.judgment.json'

    def cached_judgment(self, slot, worker):
        try:
            data = json.loads(self._cache_path(slot, worker).read_text())
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or data.get('seed') != seed_identity(self.seed):
            return None
        rows = data.get('rows')
        return rows if isinstance(rows, dict) and rows else None

    def store_judgment(self, slot, worker, rows):
        path = self._cache_path(slot, worker)
        path.write_text(json.dumps({'seed': seed_identity(self.seed), 'rows': rows, 'saved': time.time()}))
        os.chmod(path, 0o600)

    def forget_judgment(self, slot, worker):
        self._cache_path(slot, worker).unlink(missing_ok=True)

    @contextmanager
    def sandbox(self, worker=None):
        with self.slots:
            with self.lock:
                slot = self._claim_slot()
                port = free_port(taken=self.ports)
                self.ports.update({port, port + 1})
            box = self.factory(self.root, seed=self.seed, port=port, slot=slot, keep=self.keep)
            box.cached = self.cached_judgment(slot, worker) if worker else None
            try:
                box.start(config=box.cached)
                yield box
            finally:
                box.stop()
                with self.lock:
                    self.ports.difference_update({port, port + 1})
                    self._release_slot(slot)


def run_id():
    return time.strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:6]
