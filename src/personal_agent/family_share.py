"""The owner shares one signed-in site with a family assistant (FAMILY-SHARE-01 #934).

A family member's agent is a separate AgentOS instance on the owner's Mac
(FAMILY-01 #893).  Logging it into the owner's account would hand over the
owner's password, which the owner could then no longer take back.  Instead
the owner shares the *session*: the sign-in cookies of one site, from the
owner's encrypted jar (``browser_jar``) into the family instance's.

* **Grant.** The owner's config row ``family_shared_sites`` lists
  ``{instance, site, since, synced, error, state}``; ``site`` is a registrable
  domain (``browser_session.registrable_domain``, the Public Suffix List), so
  a subdomain lookalike never matches.  The family instance's config row
  ``shared_sites`` marks ``{site: {from: 'owner', since}}``: its browser
  refuses payment steps there, and the mark is what its listing shows.
* **One-way push, owner to family.** Rows go over loopback to
  ``POST /api/family/shared-site`` on the family instance, when sharing
  starts, after every owner jar save or delete that touched the site
  (``BrowserProfile.on_saved``), at owner start and periodically while a
  push is pending.  The family instance's own browsing never sends anything
  back: an instance never pushes a site it received (``received``).
* **The link secret.** The owner's instance creates ``private/owner-link.secret``
  (mode 0600, in a 0700 folder) inside the family instance's data directory
  and sends it in ``X-AgentOS-Owner-Link``.  The family endpoint compares it
  in constant time and answers only a direct loopback request
  (``local_setup``: never a tunnel, never a forwarded request).  Both
  instances run as the same macOS user, so only that user's processes can
  write or read the file: this is the same trust boundary the jar's
  Keychain key already has (``browser_jar``), and nothing weaker.  Another
  macOS user, a backup or a synced copy of the folder cannot present it,
  and the secret never leaves this Mac.
* **Revocation.** "공유 그만" removes the site from the family jar and from its
  running worker (``BrowserProfile.delete_site``, the #680 path), deletes the
  family mark and the owner grant.  When the family instance is down the
  grant stays ``revoking``, no further rows are pushed, and the removal is
  retried until it is confirmed.  The owner's own session is untouched.
* **Payment.** On a shared site the family assistant can read pages and
  add to a cart; a step that would need payment approval is refused outright
  (``PAYMENT_REFUSED_TEXT``), without an approval request and whatever the
  family member approves.  The refusal sticks for the rest of the Work once
  it landed on a shared site, so a checkout handed to a payment page on
  another domain stays refused.  Widening this is an explicit owner decision.
* **Not onward.** A site an instance received is never its to share
  (``share`` and the settings draft refuse it), and a ``remove`` for a site
  an instance never received leaves the family member's own session alone.
* **Serialized.** Every change of one store's grants or marks, and the
  delivery in between, runs under that store's lock (``store_lock``);
  ``revoking`` is on disk before a ``remove`` is sent, a push whose grant was
  revoked meanwhile is followed by a ``remove``, and a failed delivery stays
  due until it lands.

Nothing here logs, returns to a model or records as Evidence a cookie value
or the link secret: site names and counts only.

**Any instance to any other (FAMILY-SHARE-03 #957).** The giver is whichever
instance holds the session, and a target is any *other* AgentOS instance on
this Mac: the owner's default service (``MAIN_INSTANCE``, located the way
``service_control`` does) and the launchd-named instances, never the
instance itself.  A family member thus shares a site with the owner's own
assistant too, and the machinery above runs unchanged in direction: the
giver writes the link secret into the receiver's data directory, the
receiver marks the site, refuses payment there and never opens a login
window for it, and nothing it received is ever its to pass on.  Each target
is named by its bot's Telegram display name (``telegram.bot_name``, kept
from ``getMe`` at connect and backfilled once at start) plus its instance
id, and its state comes from that instance's own store, read-only
(``instance_state``): ``paired``, ``setting_up`` or ``not_connected``.  No
site, person or bot name is written into code.

* **A receiver's own session is never replaced (#966 review P1-1).** A
  ``put`` for a site the receiver holds its own rows for, and never
  received, is refused before any mark is written (400 with the code
  ``receiver_signed_in``, content-free): the receiver keeps its session and
  all its authority there (payment, login window, onward sharing).  The
  giver records the refusal on the grant (``error``) and tells its owner in
  words; the refusal is retried only when the giver's rows for that site
  change or at start, not every retry tick.
* **A name resolves to exactly one instance (review P2-1).** An instance id
  wins over a display name; a display name two instances share is refused
  with the candidates and their ids.  An instance is never a target for
  itself (review P2-2): ``share`` refuses its own data directory, and
  ``main`` without a store there.
"""
import hmac
import json
import logging
import os
import secrets
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from .browser_jar import JarError
from .browser_session import registrable_domain
from .family_setup import _LOOPBACK, family_instances, read_setup, setup_path

LOG = logging.getLogger('personal_agent.family_share')

#: The owner's config row: one grant per (instance, site).
GRANTS_KEY = 'family_shared_sites'
#: The family instance's config row: the sites it holds from the owner.
SHARED_KEY = 'shared_sites'
LINK_SECRET_FILE = 'owner-link.secret'
LINK_HEADER = 'X-AgentOS-Owner-Link'
SHARE_PATH = '/api/family/shared-site'
#: A site's cookie rows are small; a body past this is refused unread.
MAX_BODY = 512 * 1024
PUSH_TIMEOUT = 20
#: How often the owner's service retries a pending push or revocation.
RETRY_SECONDS = 30
PAYMENT_REFUSED_TEXT = '결제는 계정 주인이 해 주세요. 공유받은 로그인으로는 결제 단계를 진행하지 않습니다.'
#: #940: a received site never gets a login window on this instance (explicit, in-flow or from the phone, #939).
LOGIN_REFUSED_TEXT = '이 사이트는 공유받은 로그인이라 여기서 다시 로그인할 수 없어요'
NO_SESSION_TEXT = ('{site}에 저장된 내 로그인 세션이 없어 공유하지 않았어요. 먼저 로그인 창에서 그 사이트에 로그인해 주세요.'
                   '{stored}')
NOT_INSTALLED_TEXT = "'{instance}' 비서가 이 Mac에 설치되어 있지 않아요."
NOT_YOURS_TEXT = '{site} 로그인은 계정 주인에게 받은 것이라 다른 비서에게 공유할 수 없어요. 아무것도 바꾸지 않았어요.'
SELF_TEXT = '이 비서 자신에게는 공유할 수 없어요. 아무것도 바꾸지 않았어요.'
#: #966 review P1-1: the receiving instance already holds its own session for the site.
RECEIVER_SIGNED_IN = 'receiver_signed_in'
RECEIVER_SIGNED_IN_TEXT = '이 비서는 그 사이트에 자기 계정으로 이미 로그인되어 있어 공유받지 않았어요.'
RECEIVER_SIGNED_IN_RECEIPT = ("'{label}' 비서는 {site}에 이미 자기 계정으로 로그인되어 있어 공유하지 않았어요. 그 비서의 로그인은 그대로예요. "
                              '그 비서가 그 사이트에서 로그아웃하면 다시 공유할 수 있어요.')
#: Refusals the receiver decided; retried only when the giver's rows change or at start, not every tick.
REFUSALS = frozenset({RECEIVER_SIGNED_IN})
#: #957: the owner's default service as a share target.  ``service_control`` refuses it as a named
#: instance's name, so the id can never collide with one read from a plist.
MAIN_INSTANCE = 'main'
#: #957: what each target's own store says about its Telegram (never the one-time setup link's expiry).
STATE_LABELS = {'paired': '연결됨', 'setting_up': '설정 중', 'not_connected': '연결 안 됨'}

#: Review P2-2: every read-modify-write of one store's grant list or received marks, and the
#: delivery in between, runs under that store's lock, so a push can never land after a remove.
_LOCKS, _LOCKS_GUARD = {}, threading.Lock()


def store_lock(store):
    key = str(getattr(store, 'root', id(store)))
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())
JAR_UNREADABLE_TEXT = '저장된 로그인 세션을 읽지 못해 공유하지 않았어요. 설정의 브라우저 로그인 세션 상태를 확인해 주세요.'


class Refused(ValueError):
    """A refusal the receiving instance decided, with a content-free ``code`` (``REFUSALS``)."""

    def __init__(self, code, text):
        super().__init__(text)
        self.code = code


# -- names ---------------------------------------------------------------

def normalize_site(value):
    """The registrable domain of a host or URL the owner named; ``ValueError`` when it is not one."""
    text = str(value or '').strip()
    if '://' in text:
        text = urlsplit(text).hostname or ''
    elif '/' in text:
        text = urlsplit('https://' + text).hostname or ''
    text = text.strip().strip('.').lower()
    if not text or any(ch.isspace() for ch in text) or '|' in text:
        raise ValueError('공유할 사이트 주소를 주세요(예: example.com). 아무것도 바꾸지 않았어요.')
    site = registrable_domain(text)
    if not site or '.' not in site:
        raise ValueError('공유할 사이트 주소를 주세요(예: example.com). 아무것도 바꾸지 않았어요.')
    return site


def _peek_config(data_dir, key, default=None):
    """One config row of another instance's store, read-only; ``default`` when there is no store or no row.

    The store belongs to a running process of the same macOS user.  A
    read-only SQLite connection never creates, migrates or locks it the way
    opening a ``QuickStore`` would (#957).
    """
    path = Path(data_dir) / 'private' / 'quickstart.db'
    if not path.is_file():
        return default
    try:
        connection = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=2)
        try:
            row = connection.execute('SELECT value FROM config WHERE key=?', (key,)).fetchone()
        finally:
            connection.close()
        return json.loads(row[0]) if row else default
    except (sqlite3.Error, ValueError, OSError):
        return default


def _telegram_config(data_dir):
    cfg = _peek_config(data_dir, 'telegram', {})
    return cfg if isinstance(cfg, dict) else {}


def _clean_name(value):
    return ' '.join(str(value).split()) if isinstance(value, str) and value.strip() else None


def display_name(data_dir):
    """The instance's bot's Telegram display name (``telegram.bot_name``, #957), else the name it was set up with, or None."""
    name = _clean_name(_telegram_config(data_dir).get('bot_name'))
    if name:
        return name
    try:
        record = json.loads(setup_path(_Private(data_dir)).read_text())
    except (OSError, ValueError):
        return None
    return _clean_name(record.get('display_name')) if isinstance(record, dict) else None


def instance_state(data_dir, now=None):
    """``paired``, ``setting_up`` or ``not_connected``, from that instance's own store (#957).

    Paired means its Telegram config holds the member's user id; a live
    setup record alone means the setup is still open.  The one-time setup
    link's expiry says nothing once the instance is paired.
    """
    user_id = _telegram_config(data_dir).get('user_id')
    if isinstance(user_id, int) and not isinstance(user_id, bool):
        return 'paired'
    return 'setting_up' if read_setup(_Private(data_dir), now) else 'not_connected'


class _Private:
    """``setup_path`` wants ``store.private``: a data directory's private folder, without opening its database."""

    def __init__(self, data_dir):
        self.private = Path(data_dir) / 'private'


def locate_instance(instance, home=None, environ=None):
    """``(port, data_dir)`` of an installed instance; ``port`` is None when it was never installed.

    ``MAIN_INSTANCE`` is the owner's default service, resolved exactly as
    ``service_control`` does (the default label's plist, ``AGENTOS_DATA``,
    the default data directory; port 8787).
    """
    from .service_control import ServiceController
    controller = ServiceController(instance=None if instance == MAIN_INSTANCE else instance, home=home, environ=environ)
    return controller.port, controller.data_dir


def _has_store(data_dir):
    return (Path(data_dir) / 'private' / 'quickstart.db').is_file()


def _same_dir(left, right):
    try:
        return Path(left).expanduser().resolve() == Path(right).expanduser().resolve()
    except (OSError, TypeError, ValueError):
        return False


def instances(home=None, locate=locate_instance, own=None, now=None):
    """The other AgentOS instances on this Mac: ``{instance: {name, state, main}}`` (#957).

    The owner's default service and the launchd-named instances, minus the
    one whose data directory is ``own`` (this instance), so an assistant is
    never offered itself.  ``name`` is the bot's display name, else the
    setup name, else the instance id; ``state`` is ``instance_state``.
    """
    rows = {}
    for name in [MAIN_INSTANCE, *family_instances(home)]:
        try:
            _port, data_dir = locate(name)
        except Exception:
            continue
        if own is not None and _same_dir(data_dir, own):
            continue
        if name == MAIN_INSTANCE and not _has_store(data_dir):
            continue   # no default service was ever set up here
        rows[name] = {'name': display_name(data_dir) or name, 'state': instance_state(data_dir, now), 'main': name == MAIN_INSTANCE}
    return rows


def names(rows):
    """``{instance: display name}`` from ``instances`` rows (or an older plain ``{instance: name}``)."""
    return {name: (row.get('name') or name) if isinstance(row, dict) else (row or name) for name, row in (rows or {}).items()}


def describe(instance, row):
    """One target for a listing: ``name(instance, state)``; names only."""
    row = row if isinstance(row, dict) else {'name': row}
    label = row.get('name') or instance
    parts = ([] if label == instance else [instance]) + ([STATE_LABELS[row['state']]] if row.get('state') in STATE_LABELS else [])
    return f"{label}({', '.join(parts)})" if parts else label


def resolve_instance(value, rows):
    """The instance whose id or display name was given (case and spacing aside), or ``ValueError``."""
    labels = names(rows)
    wanted = ' '.join(str(value or '').split()).lower()
    if not wanted:
        raise ValueError('어느 비서인지 이름을 주세요. 아무것도 바꾸지 않았어요.')
    # Review P2-1: an instance id is exact and wins; a display name (chosen by whoever made that bot) must
    # name exactly one instance, or the candidates are listed with their ids.
    for name in labels:
        if wanted == name.lower():
            return name
    matches = [name for name, label in labels.items() if wanted == ' '.join(str(label).split()).lower()]
    if len(matches) == 1:
        return matches[0]
    if matches:
        listed = ', '.join(describe(name, (rows or {}).get(name)) for name in matches)
        raise ValueError(f"'{value}'라는 이름의 비서가 여럿이에요: {listed}. 어느 비서인지 괄호 안의 id로 말해 주세요. 아무것도 바꾸지 않았어요.")
    listed = ', '.join(describe(name, row) for name, row in (rows or {}).items()) or '없음'
    raise ValueError(f"'{value}'라는 비서를 찾지 못했어요. 이 Mac의 다른 비서: {listed}. 아무것도 바꾸지 않았어요.")


# -- the link secret ------------------------------------------------------

def link_secret_path(data_dir):
    return Path(data_dir) / 'private' / LINK_SECRET_FILE


def ensure_link_secret(data_dir):
    """The family instance's link secret, created owner-only (0600 in a 0700 folder) when absent.  Owner side."""
    path = link_secret_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return read_link_secret(data_dir)
    value = secrets.token_urlsafe(32)
    with os.fdopen(fd, 'w') as stream:
        stream.write(value)
    return value


def read_link_secret(data_dir):
    """The link secret, or '' when none was ever written.  Family side (and the owner side on reuse)."""
    try:
        return link_secret_path(data_dir).read_text().strip()
    except OSError:
        return ''


def link_ok(data_dir, value):
    """Constant-time check of a presented header value against this instance's link secret."""
    expected = read_link_secret(data_dir)
    return (bool(expected) and isinstance(value, str) and bool(value)
            and hmac.compare_digest(value.encode(), expected.encode()))


# -- the owner side ---------------------------------------------------------

def grants(store):
    rows = store.config(GRANTS_KEY, [])
    return [row for row in rows if isinstance(row, dict) and row.get('instance') and row.get('site')] if isinstance(rows, list) else []


def _put_grants(store, rows):
    store.put(GRANTS_KEY, rows)


def received(store):
    """The sites this instance holds from the owner (``{site: {from, since}}``)."""
    rows = store.config(SHARED_KEY, {})
    return {site: row for site, row in rows.items() if isinstance(row, dict)} if isinstance(rows, dict) else {}


def login_refusal(store, site):
    """Why no login window may open for ``site`` (a registrable domain) on this instance, or None (#940).

    A family member who received the owner's session must not sign in to
    that site again here, from the Mac window or from a phone link (#939);
    that would drive or replace the owner's shared session.
    """
    return LOGIN_REFUSED_TEXT if site and site in received(store) else None


def payment_refusal(store, host):
    """Why a guarded step on ``host`` may not be approved on this instance, or None (``BrowserSession.approvals.refuse``)."""
    if not host:
        return None
    try:
        site = registrable_domain(host)
    except Exception:
        return None
    return PAYMENT_REFUSED_TEXT if site in received(store) else None


def _rows_for(jar, site):
    try:
        return jar.site_rows(site)
    except JarError:
        raise ValueError(JAR_UNREADABLE_TEXT) from None


def _post(port, secret, body, opener=None, timeout=PUSH_TIMEOUT):
    """One loopback call to the family instance; never through a proxy or tunnel."""
    request = urllib.request.Request(f'http://127.0.0.1:{int(port)}{SHARE_PATH}', data=json.dumps(body).encode(),
                                     method='POST', headers={'Content-Type': 'application/json', LINK_HEADER: secret})
    try:
        with (opener or _LOOPBACK.open)(request, timeout=timeout) as response:
            return json.loads(response.read() or b'{}')
    except urllib.error.HTTPError as error:
        # Review P1-1: a refusal the receiver decided carries a code; anything else stays a transport failure.
        try:
            answer = json.loads(error.read() or b'{}')
        except ValueError:
            answer = {}
        code = answer.get('code') if isinstance(answer, dict) else None
        if error.code == 400 and code in REFUSALS:
            raise Refused(code, str(answer.get('error') or code)) from None
        raise


def push(port, secret, site, rows, opener=None):
    """Replace the family instance's rows for ``site`` (empty ``rows``: it holds none).  Values go only here."""
    return _post(port, secret, {'op': 'put', 'site': site, 'cookies': list(rows or ())}, opener)


def revoke(port, secret, site, opener=None):
    return _post(port, secret, {'op': 'remove', 'site': site}, opener)


def _grant_index(rows, instance, site):
    return next((index for index, row in enumerate(rows) if row.get('instance') == instance and row.get('site') == site), None)


def _deliver(row, jar, locate, opener, now):
    """Run the push (or the revocation) one grant row is waiting for; True when the family instance confirmed it.

    Content-free: the log names the instance, the site and a count or an
    error class, never a row.
    """
    try:
        port, data_dir = locate(row['instance'])
        if port is None and row.get('state') == 'revoking':
            # Review P3-2: the instance is gone (no launchd definition): nothing is left to revoke.
            LOG.info('family share: %s: instance %s is not installed; nothing left to revoke', row['site'], row['instance'])
            row['error'] = None
            return True
        if port is None:
            raise RuntimeError('not installed')
        secret = ensure_link_secret(data_dir)
        if row.get('state') == 'revoking':
            revoke(port, secret, row['site'], opener)
            LOG.info('family share: %s removed from %s', row['site'], row['instance'])
        else:
            rows = jar.site_rows(row['site'])
            push(port, secret, row['site'], rows, opener)
            LOG.info('family share: %s -> %s (%d cookies)', row['site'], row['instance'], len(rows))
    except Exception as exc:
        # Review P2-3: a failed delivery is due again (``synced`` cleared, ``error`` set) until it lands.
        row['error'] = exc.code if isinstance(exc, Refused) else type(exc).__name__
        row['attempted'] = now
        row['synced'] = None
        LOG.warning('family share: %s -> %s not delivered (%s)', row['site'], row['instance'], type(exc).__name__)
        return False
    row['error'] = None
    row['synced'] = now
    return True


def share(store, jar, instance, site, *, locate=locate_instance, opener=None, now=None, label=None):
    """Grant one other instance this instance's session for ``site`` and push it now; a content-free receipt.

    Refused (nothing recorded) when there is no stored session for the
    site, so a misresolved name is caught rather than granted.  A push the
    receiving instance did not confirm keeps the grant: ``sync`` retries it.
    ``label`` is the target's display name for the receipt (#957).
    """
    now = time.time() if now is None else now
    label = label or instance
    site = normalize_site(site)
    if site in received(store):
        # Review P1-1: a session received from the owner is not this instance's to pass on.
        raise ValueError(NOT_YOURS_TEXT.format(site=site))
    rows = _rows_for(jar, site)
    if not rows:
        stored = [row['site'] for row in jar.sites()]
        raise ValueError(NO_SESSION_TEXT.format(site=site, stored=f' 지금 로그인된 사이트: {", ".join(stored)}.' if stored else ''))
    port, data_dir = locate(instance)
    # Review P2-2: never itself, however ``main`` or this instance's ``--data`` resolved; and no main without a store.
    if _same_dir(data_dir, store.root):
        raise ValueError(SELF_TEXT)
    if port is None or (instance == MAIN_INSTANCE and not _has_store(data_dir)):
        raise ValueError(NOT_INSTALLED_TEXT.format(instance=label))
    with store_lock(store):
        current = grants(store)
        index = _grant_index(current, instance, site)
        row = current[index] if index is not None else {'instance': instance, 'site': site, 'since': now}
        row.update(state='shared', synced=None, error=None)
        if index is None:
            current.append(row)
        _put_grants(store, current)
        delivered = _deliver(row, jar, locate, opener, now)
        _put_grants(store, current)
    refused = row.get('error') if row.get('error') in REFUSALS else None
    text = (f"{label} 비서에 {site} 로그인 세션을 공유했어요(쿠키 {len(rows)}개). 내 세션이 갱신되면 따라가고, "
            f"결제는 계정 주인만 할 수 있어요." if delivered else
            RECEIVER_SIGNED_IN_RECEIPT.format(label=label, site=site) if refused == RECEIVER_SIGNED_IN else
            f"{label} 비서가 지금 응답하지 않아 {site} 로그인 세션은 비서가 켜지면 전달돼요. 공유는 기록해 두었어요.")
    return {'instance': instance, 'site': site, 'cookies': len(rows), 'delivered': delivered, 'refused': refused, 'response': text}


def unshare(store, instance, site, *, locate=locate_instance, opener=None, now=None, labels=None):
    """End the share: the receiver's jar, its running worker and its mark are cleared, then the grant is removed.

    ``instance`` None ends every grant for the site.  Idempotent: a site that
    is not shared is reported, not failed.  A receiving instance that does not
    confirm keeps the grant as ``revoking`` (no more pushes) until it does.
    ``labels`` maps instance ids to display names for the receipt (#957).
    """
    now = time.time() if now is None else now
    labels = labels or {}
    site = normalize_site(site)
    with store_lock(store):
        current = grants(store)
        targets = [row for row in current if row['site'] == site and instance in (None, row['instance'])]
        if not targets:
            return {'site': site, 'instances': [], 'removed': True, 'idempotent': True,
                    'response': f'{site} 로그인 세션은 공유하고 있지 않아요. 바꿀 것이 없어요.'}
        # Review P2-2: ``revoking`` is on disk before anything is sent, so no push is sent meanwhile.
        for row in targets:
            row.update(state='revoking', synced=None)
        _put_grants(store, current)
        done, pending = [], []
        for row in targets:
            if _deliver(row, jar=None, locate=locate, opener=opener, now=now):
                current.remove(row)
                done.append(row['instance'])
            else:
                pending.append(row['instance'])
        _put_grants(store, current)
    parts = []
    if done:
        parts.append(f"{', '.join(labels.get(name, name) for name in done)} 비서에서 {site} 로그인 세션을 지웠어요. 내 세션은 그대로예요.")
    if pending:
        parts.append(f"{', '.join(labels.get(name, name) for name in pending)} 비서가 지금 응답하지 않아 {site} 세션은 비서가 켜지면 지워져요. "
                     '그때까지 새 세션은 보내지 않아요.')
    return {'site': site, 'instances': done, 'pending': pending, 'removed': not pending, 'idempotent': False,
            'response': ' '.join(parts)}


def sync(store, jar, touched=None, *, locate=locate_instance, opener=None, now=None, retry_after=0):
    """Deliver what the grants are waiting for: pushes for touched (or pending) sites, pending revocations.

    ``touched`` is the set of sites whose stored rows may have changed
    (``BrowserProfile.on_saved``), or None for every grant (owner start).  A
    site this instance itself received from the owner is never pushed: a
    family instance's own browsing stays with it.  Returns how many grants
    were delivered.
    """
    now = time.time() if now is None else now
    if not grants(store):
        return 0
    with store_lock(store):
        current = grants(store)
        held = set(received(store))
        delivered = 0
        for row in list(current):
            if row['site'] in held:
                continue
            if row.get('error') in REFUSALS and not (touched is None or row['site'] in touched):
                continue   # review P1-1: the receiver decided; asked again only when these rows change or at start
            due = (row.get('state') == 'revoking' or row.get('synced') is None or row.get('error')
                   or touched is None or row['site'] in touched)
            if not due or (row.get('error') and now - float(row.get('attempted') or 0) < retry_after):
                continue
            if not _deliver(row, jar, locate, opener, now):
                continue
            delivered += 1
            if row.get('state') == 'revoking':
                current.remove(row)
                continue
            # Review P2-2: a push that another writer revoked meanwhile is undone at once.
            latest = grants(store)
            index = _grant_index(latest, row['instance'], row['site'])
            if index is None or latest[index].get('state') == 'revoking':
                row['state'] = 'revoking'
                if _deliver(row, None, locate, opener, now):
                    current.remove(row)
        _put_grants(store, current)
    return delivered


def pending(store):
    """Whether any grant still waits for a push or a revocation."""
    return any(row.get('state') == 'revoking' or (row.get('synced') is None and row.get('error') not in REFUSALS)
               or (row.get('error') and row.get('error') not in REFUSALS) for row in grants(store))


def listing(store, rows=None):
    """What the owner may see: ``[{instance, label, site, since, delivered, state}]``, names only."""
    labels = names(rows)
    return [{'instance': row['instance'], 'label': labels.get(row['instance'], row['instance']), 'site': row['site'],
             'since': row.get('since'), 'delivered': row.get('synced') is not None and not row.get('error'),
             'state': row.get('state') or 'shared'} for row in grants(store)]


# -- the family side ---------------------------------------------------------

def accept(service, body, now=None):
    """Handle one authenticated ``POST /api/family/shared-site``; a content-free receipt or ``ValueError``.

    ``put`` replaces the site's rows in this instance's jar and running
    worker and marks the site as received; ``remove`` deletes them (the
    #680 path) and the mark.  Only rows whose domain belongs to the site are
    kept: a push cannot smuggle another site's cookies.
    """
    now = time.time() if now is None else now
    if not isinstance(body, dict):
        raise ValueError('요청 본문을 확인하세요.')
    op = body.get('op')
    site = normalize_site(body.get('site'))
    if site != str(body.get('site') or '').strip().lower():
        raise ValueError('사이트 이름은 등록 가능한 도메인이어야 합니다.')
    store = service.store
    if op not in ('put', 'remove'):
        raise ValueError('지원하지 않는 요청입니다.')
    with store_lock(store):
        marks = received(store)
        if op == 'put':
            rows = body.get('cookies')
            if not isinstance(rows, list):
                raise ValueError('쿠키 목록을 확인하세요.')
            rows = [row for row in rows if isinstance(row, dict) and isinstance(row.get('name'), str)
                    and _belongs(row.get('domain'), site)]
            if site not in marks and _holds_own(service, site):
                # Review P1-1: this instance's own sign-in there stays, with every authority it has; the
                # giver is told so.  Nothing is set aside, nothing is marked.
                LOG.info('family share: %s refused; this instance holds its own session', site)
                raise Refused(RECEIVER_SIGNED_IN, RECEIVER_SIGNED_IN_TEXT)
            # Fail closed: the mark that refuses payment is durable before any cookie is usable here.  A
            # crash or a failed import leaves a mark without rows (harmless, and ``remove`` clears it),
            # never rows without a mark.
            mark = {'from': 'owner', 'since': (marks.get(site) or {}).get('since') or now, 'importing': now}
            marks[site] = mark
            store.put(SHARED_KEY, marks)
            try:
                result = service.browser_profile.import_site(site, rows)
            except Exception as exc:
                mark.update(error=type(exc).__name__, updated=now)
                mark.pop('importing', None)
                store.put(SHARED_KEY, marks)
                LOG.warning('family share: %s not imported (%s); the mark stays', site, type(exc).__name__)
                if isinstance(exc, JarError):
                    raise ValueError(f'이 비서의 로그인 세션 저장소를 쓸 수 없습니다({exc}).') from None
                raise ValueError('이 비서에 로그인 세션을 저장하지 못했습니다.') from None
            mark.update(updated=now, error=None)
            mark.pop('importing', None)
            store.put(SHARED_KEY, marks)
            LOG.info('family share: received %s (%d cookies)', site, result['cookies'])
            return {'ok': True, 'op': 'put', 'site': site, 'cookies': result['cookies'], 'running_browser': result['running_browser']}
        if site not in marks:
            # Review P3-1: a site never received here is the family member's own session; it stays.
            return {'ok': True, 'op': 'remove', 'site': site, 'deleted': False, 'received': False, 'running_browser': None}
        try:
            result = service.browser_profile.delete_site(site)
        except ValueError as exc:
            raise ValueError(str(exc)) from None
        marks.pop(site, None)
        store.put(SHARED_KEY, marks)
        LOG.info('family share: removed %s', site)
        return {'ok': True, 'op': 'remove', 'site': site, 'deleted': bool(result.get('deleted')), 'received': True,
                'running_browser': result.get('running_browser')}


def _holds_own(service, site):
    """Whether this instance's jar holds rows for ``site`` of its own; an unreadable jar refuses the push (content-free)."""
    jar = getattr(service.browser_profile, 'jar', None)
    if jar is None:
        return False
    try:
        return bool(jar.site_rows(site))
    except JarError as exc:
        raise ValueError(f'이 비서의 로그인 세션 저장소를 읽을 수 없습니다({exc}).') from None


def _belongs(domain, site):
    host = str(domain or '').lower().lstrip('.').rstrip('.')
    return bool(host) and (host == site or host.endswith('.' + site))
