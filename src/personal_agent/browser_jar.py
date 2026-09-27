"""The encrypted browser sign-in cookie jar (SEC-BROWSER-02 #680).

The embedded WebKit worker keeps cookies in memory only.  AgentOS exports
them over the worker pipe when a session stops, hides or the owner closes
the login window, and keeps them here:

* one file under ``store.private`` (mode 0600, directory 0700), holding a
  Fernet token (the ``cryptography`` dependency ``EncryptedCalendarSecretStore``
  already uses) of ``{"sites": {site: {"cookies": [...], "last_used": t}}}``;
* the Fernet key in the **macOS Keychain** as a generic password (service
  ``personal-agentos.browser-jar``, account = this store's id), read and
  written through ``/usr/bin/security``.  The key never appears on a command
  line: it is written through ``security -i`` on standard input and read from
  ``find-generic-password -w`` output.

Nothing here logs, returns to the model or records as Evidence a cookie value
or the key; ``sites()`` returns names, counts and times only.  The jar is not
part of the portable export or the backup (they copy the database and plugin
manifests only) and a restored runtime starts without sessions.
"""
import hashlib
import json
import os
import secrets
import subprocess
import threading
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

SERVICE = 'personal-agentos.browser-jar'
JAR_NAME = 'session-jar.enc'
SECURITY = '/usr/bin/security'
SECURITY_TIMEOUT_SECONDS = 15
#: ``security`` exits 44 when the item does not exist.
NOT_FOUND = 44


class JarError(Exception):
    """A jar operation failed; the message is an AgentOS code, never a value."""


def store_account(root):
    """The Keychain account of one AgentOS data directory: a digest of its resolved path."""
    return 'store-' + hashlib.sha256(str(Path(root).expanduser().resolve()).encode()).hexdigest()[:24]


class KeychainKey:
    """The jar key as one macOS Keychain generic password (created on first save)."""

    location = 'macos-keychain'

    def __init__(self, account, service=SERVICE, security=SECURITY, runner=subprocess.run):
        # Both go into a ``security -i`` command line on stdin: plain tokens only.
        for value in (account, service):
            if not isinstance(value, str) or not value or not all(ch.isalnum() or ch in '._-' for ch in value):
                raise ValueError('Keychain account and service must be plain tokens.')
        self.account, self.service, self.security, self.runner = account, service, security, runner

    def _run(self, args, stdin=None):
        try:
            return self.runner([self.security, *args], input=stdin, capture_output=True, text=True,
                               timeout=SECURITY_TIMEOUT_SECONDS, check=False)
        except (OSError, subprocess.SubprocessError):
            raise JarError('keychain_unavailable') from None

    def get(self):
        """The key, or None when this item does not exist."""
        result = self._run(['find-generic-password', '-a', self.account, '-s', self.service, '-w'])
        if result.returncode == NOT_FOUND:
            return None
        if result.returncode != 0:
            raise JarError('keychain_unavailable')
        value = (result.stdout or '').strip()
        return value.encode() if value else None

    def create(self):
        """Generate and store a new key.  The key goes through stdin (``security -i``), hex-encoded."""
        key = Fernet.generate_key()
        command = f'add-generic-password -U -a {self.account} -s {self.service} -X {key.hex()}\n'
        result = self._run(['-i'], stdin=command)
        if result.returncode != 0 or self.get() != key:
            raise JarError('keychain_unavailable')
        return key

    def delete(self):
        result = self._run(['delete-generic-password', '-a', self.account, '-s', self.service])
        return result.returncode == 0


class MemoryKey:
    """An in-process key for tests and non-Keychain callers."""

    location = 'memory'

    def __init__(self, key=None):
        self.key = key

    def get(self):
        return self.key

    def create(self):
        self.key = Fernet.generate_key()
        return self.key

    def delete(self):
        existed, self.key = self.key is not None, None
        return existed


class CookieJar:
    """Per-site sign-in cookies, encrypted at rest.  Thread-safe within one process."""

    def __init__(self, path, key, clock=time.time):
        self.path, self.key, self.clock = Path(path), key, clock
        self._lock = threading.RLock()
        self._index = None   # cached {site: {'cookies': n, 'last_used': t}}: never values

    # -- storage -------------------------------------------------------------
    def _cipher(self, create=False):
        key = self.key.get()
        if key is None and create:
            key = self.key.create()
        if key is None:
            raise JarError('key_missing')
        try:
            return Fernet(key)
        except (TypeError, ValueError):
            raise JarError('key_invalid') from None

    def _read(self):
        """The decrypted payload; an absent jar is empty.  Raises JarError when unreadable."""
        if not self.path.is_file():
            return {'sites': {}}
        token = self.path.read_bytes()
        try:
            payload = json.loads(self._cipher().decrypt(token).decode())
        except InvalidToken:
            raise JarError('unreadable') from None
        except (ValueError, UnicodeDecodeError):
            raise JarError('unreadable') from None
        sites = payload.get('sites') if isinstance(payload, dict) else None
        return {'sites': sites if isinstance(sites, dict) else {}}

    def _write(self, payload):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.parent.chmod(0o700)
        token = self._cipher(create=True).encrypt(json.dumps(payload, separators=(',', ':')).encode())
        tmp = self.path.with_name(self.path.name + '.tmp-' + secrets.token_hex(6))
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(token)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, self.path)
        finally:
            if tmp.exists():
                tmp.unlink()
        self._index = _index(payload)

    # -- the owner-facing surface (no values) -----------------------------------
    def state(self):
        """``empty`` / ``stored`` / an unreadable code (``unreadable``, ``key_missing``, ...)."""
        with self._lock:
            if not self.path.is_file():
                return 'empty'
            try:
                self._load_index()
            except JarError as exc:
                return str(exc)
            return 'stored'

    def _load_index(self):
        if self._index is None:
            self._index = _index(self._read())
        return self._index

    def sites(self):
        """``[{site, cookies, last_used}]``, newest first.  Names, counts and times only."""
        with self._lock:
            if not self.path.is_file():
                return []
            try:
                index = self._load_index()
            except JarError:
                return []
            return sorted(({'site': site, **row} for site, row in index.items()),
                          key=lambda row: (-(row.get('last_used') or 0), row['site']))

    # -- the worker side ---------------------------------------------------------
    def cookies(self):
        """Every unexpired cookie row, for import into a new worker.  Empty when unreadable."""
        with self._lock:
            try:
                sites = self._read()['sites']
            except JarError:
                return []
            now = self.clock()
            return [row for entry in sites.values() if isinstance(entry, dict)
                    for row in entry.get('cookies') or []
                    if isinstance(row, dict) and not (isinstance(row.get('expires'), (int, float)) and row['expires'] <= now)]

    def save_export(self, grouped, hosts=()):
        """Replace the jar with a worker export ``{site: [cookie rows]}``.

        The worker held every imported cookie, so its export is the whole
        session.  A site's ``last_used`` becomes now when this worker opened
        a page of it (``hosts``) or it is new; otherwise it is kept.  An
        unreadable old jar is replaced (its sessions are already lost).
        """
        with self._lock:
            try:
                old = self._read()['sites']
            except JarError:
                old = {}
            now = self.clock()
            hosts = [str(host).lower() for host in hosts or ()]
            sites = {}
            for site, rows in (grouped or {}).items():
                rows = [row for row in rows or [] if isinstance(row, dict) and row.get('name')]
                if not site or not rows:
                    continue
                touched = any(host == site or host.endswith('.' + site) for host in hosts)
                previous = old.get(site) if isinstance(old.get(site), dict) else {}
                sites[site] = {'cookies': rows, 'last_used': now if touched or not previous else previous.get('last_used', now)}
            if not sites and not self.path.is_file():
                return
            self._write({'sites': sites})

    def remove(self, site):
        """Remove one site's cookies; True when it was stored."""
        with self._lock:
            payload = self._read()
            if site not in payload['sites']:
                return False
            payload['sites'].pop(site)
            self._write(payload)
            return True

    def clear(self):
        """Delete the jar file and the Keychain key this jar owns."""
        with self._lock:
            existed = self.path.is_file()
            if existed:
                self.path.unlink()
            self._index = None
            try:
                self.key.delete()
            except JarError:
                pass
            return existed


def _index(payload):
    return {site: {'cookies': len(entry.get('cookies') or []), 'last_used': entry.get('last_used')}
            for site, entry in (payload.get('sites') or {}).items() if isinstance(entry, dict)}
