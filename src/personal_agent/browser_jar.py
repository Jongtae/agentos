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

What the Keychain does and does not protect (#680 review P2-7): a copy of
the data folder (a backup, a synced folder, another account's access to the
disk) is useless without the key.  It does **not** protect against a program
running as the same macOS user: the item's access list trusts
``/usr/bin/security``, the tool that created it, so any such process can run
``security find-generic-password -w`` and read the key without a prompt.
Narrowing the access list with ``-T`` to the Python interpreter would not
change that, because AgentOS itself reads the key through
``/usr/bin/security``.  When the login keychain is locked a read fails (or
macOS prompts); the jar is then reported unreadable and never overwritten.

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
        """True when the item was deleted, False when there was none; raises ``JarError`` otherwise."""
        result = self._run(['delete-generic-password', '-a', self.account, '-s', self.service])
        if result.returncode == 0:
            return True
        if result.returncode == NOT_FOUND:
            return False
        raise JarError('keychain_delete_failed')


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
        self._index_stamp = None   # the file's (mtime_ns, size) the cache was read from

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
        self._index, self._index_stamp = _index(payload), self._stamp()

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

    def _stamp(self):
        try:
            stat = self.path.stat()
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def _load_index(self):
        """Names, counts and times, decrypted once per file version (another process may write it)."""
        stamp = self._stamp()
        if self._index is None or stamp != self._index_stamp:
            self._index = _index(self._read())
            self._index_stamp = stamp
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
            return self._sorted(index)

    # -- the worker side ---------------------------------------------------------
    def cookies(self):
        """Every unexpired cookie row.  Empty when unreadable (use ``import_rows`` to see why)."""
        try:
            return self.import_rows()[1]
        except JarError:
            return []

    def import_rows(self):
        """``(sites, rows)`` for a new worker: every stored site name and its unexpired rows.

        Raises ``JarError`` when the jar exists but cannot be read (locked or
        missing Keychain key, damaged file): the caller must then not save
        over it.  An absent jar is ``(set(), [])``.
        """
        with self._lock:
            sites = self._read()['sites']
            now = self.clock()
            rows = [row for entry in sites.values() if isinstance(entry, dict)
                    for row in entry.get('cookies') or []
                    if isinstance(row, dict) and not (isinstance(row.get('expires'), (int, float)) and row['expires'] <= now)]
            return set(sites), rows

    def save_export(self, grouped, hosts=(), imported=None):
        """Merge a worker export ``{site: [cookie rows]}`` into the jar.

        ``imported`` is the set of sites the worker was given at start.  A
        site in the export replaces its stored rows; an imported site missing
        from the export (signed out, expired, deleted in the worker) is
        dropped; a stored site that was never imported (the import failed for
        it, or another process added it meanwhile) is kept untouched.  With
        ``imported=None`` the export is the whole jar (every stored site
        counts as imported) and an unreadable old jar is replaced.  With a set
        an unreadable old jar raises ``JarError`` and nothing is written.

        A site's ``last_used`` becomes now when this worker opened a page of
        it (``hosts``) or it is new; otherwise it is kept.
        """
        with self._lock:
            if imported is None:
                try:
                    old = self._read()['sites']
                except JarError:
                    old = {}
                imported = set(old)
            else:
                old = self._read()['sites']
                imported = set(imported)
            now = self.clock()
            hosts = [str(host).lower() for host in hosts or ()]
            sites = {site: entry for site, entry in old.items() if site not in imported and isinstance(entry, dict)}
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

    def site_cookie_marks(self, host):
        """``(marks, now)`` for the stored sign-in cookies of the site(s) ``host`` belongs to (#709).

        ``marks`` is one ``(digest, expires, identity)`` per stored cookie: the
        digest covers the cookie's site, name, domain, path and value (never
        its expiry); ``identity`` covers the same but the value, so a cookie
        whose value rotated keeps its identity and only a new cookie has a new
        one (#765).  Neither returns a value.  ``now`` is this jar's clock, the
        same clock ``import_rows`` uses to drop expired rows, so two readings
        are compared over exactly the unexpired cookies (``unexpired``) a
        worker was given and could keep.  Raises ``JarError`` when the jar
        exists but cannot be read.
        """
        host = str(host or '').lower().rstrip('.')
        with self._lock:
            sites = self._read()['sites']
            now = self.clock()
        marks = []
        for site, entry in sites.items():
            if not isinstance(entry, dict) or not (host == site or host.endswith('.' + site) or site.endswith('.' + host)):
                continue
            for row in entry.get('cookies') or []:
                if not isinstance(row, dict):
                    continue
                identity = [site, str(row.get('name')), str(row.get('domain')), str(row.get('path'))]
                expires = row.get('expires') if isinstance(row.get('expires'), (int, float)) else None
                marks.append((_digest(identity + [str(row.get('value'))]), expires, _digest(identity)))
        return marks, now

    def cached_sites(self):
        """``(state, sites)`` without touching the Keychain, or None when the file changed since it was read."""
        with self._lock:
            if not self.path.is_file():
                return 'empty', []
            if self._index is None or self._stamp() != self._index_stamp:
                return None
            return 'stored', self._sorted(self._index)

    @staticmethod
    def _sorted(index):
        return sorted(({'site': site, **row} for site, row in index.items()),
                      key=lambda row: (-(row.get('last_used') or 0), row['site']))

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
        """Delete the jar file and the Keychain key this jar owns.

        Returns ``{'jar_deleted': bool, 'key_deleted': bool, 'key_error': code or None}``:
        a key that could not be removed is reported, never hidden.
        """
        with self._lock:
            existed = self.path.is_file()
            if existed:
                self.path.unlink()
            self._index = self._index_stamp = None
            try:
                return {'jar_deleted': existed, 'key_deleted': bool(self.key.delete()), 'key_error': None}
            except JarError as exc:
                return {'jar_deleted': existed, 'key_deleted': False, 'key_error': str(exc)}


def _index(payload):
    return {site: {'cookies': len(entry.get('cookies') or []), 'last_used': entry.get('last_used')}
            for site, entry in (payload.get('sites') or {}).items() if isinstance(entry, dict)}


def _digest(parts):
    return hashlib.sha256(json.dumps(parts, separators=(',', ':')).encode()).hexdigest()


def unexpired(marks, now):
    """The cookie digests of ``marks`` still unexpired at ``now``: the rule ``CookieJar.import_rows`` applies.

    Each mark is ``(digest, expires, ...)``; anything after the expiry is ignored."""
    return frozenset(mark[0] for mark in marks or ()
                     if not (isinstance(mark[1], (int, float)) and mark[1] <= now))
