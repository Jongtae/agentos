"""One-page family setup: from installing Telegram to a working bot (FAMILY-02 #897).

A family member's agent is a separate AgentOS instance on the owner's Mac
(FAMILY-01 #893).  Its first setup happens before any agent exists to talk
to, so it is a necessary input surface under the Presence *Pages* rule (#880).
It is reached through a temporary HTTPS link and runs without stops:

1. install Telegram (store buttons);
2. create the bot with Telegram's official Managed Bots deep link
   (Bot API 9.6): ``https://t.me/newbot/{owner_bot}/{username}?name={name}``.
   The family member confirms a pre-filled screen and owns the new bot;
3. the owner's instance - the manager bot - receives the ``managed_bot``
   update.  It fetches the token with ``getManagedBotToken``, restricts the
   bot to its owner with ``setManagedBotAccessSettings``, and hands the token
   to the family instance over loopback only;
4. the family member opens the pairing link, and the setup closes itself.

Boundaries:
- through the tunnel only ``PUBLIC_PATHS`` answer, and only with the one-time
  setup code, while a setup is pending;
- the token never enters a model prompt, log or Evidence, and never crosses
  the tunnel;
- the owner's bot accepts a ``managed_bot`` update only for a username it
  issued for a pending, unexpired setup.
"""
import hmac
import json
import logging
import queue
import re
import secrets
import subprocess
import threading
import time
import urllib.request
from html import escape
from pathlib import Path
from urllib.parse import quote

LOG = logging.getLogger('personal_agent.family_setup')

SETUP_FILE = 'family-setup.json'
SETUP_SECONDS = 30 * 60
RETRY_SECONDS = 10
MAX_ATTEMPTS = 20
# Loopback calls never go through an HTTP(S)_PROXY from the environment (review P3-1).
_LOOPBACK = urllib.request.build_opener(urllib.request.ProxyHandler({}))
PUBLIC_PATHS = frozenset({'/family-setup', '/api/family/status', '/api/family/pair'})
HANDOFF_HEADER = 'X-AgentOS-Family-Handoff'
PENDING_KEY = 'family_setups'
TELEGRAM_IOS = 'https://apps.apple.com/app/telegram-messenger/id686449807'
TELEGRAM_ANDROID = 'https://play.google.com/store/apps/details?id=org.telegram.messenger'
_BOT_USERNAME = re.compile(r'[A-Za-z][A-Za-z0-9_]{3,30}[Bb][Oo][Tt]\Z')


def handoff_secret_key(instance):
    return f'family_handoff.{instance}'


def suggested_username(instance, nonce=None):
    """A Telegram bot username for ``instance``: 5-32 characters ending in ``bot``."""
    stem = re.sub(r'[^a-z0-9]', '_', instance.lower()).strip('_') or 'family'
    # 32 random bits: the username is the binding a stranger would have to guess (review P2-5).
    nonce = nonce or secrets.token_hex(4)
    return f'{stem[:16]}_ag{nonce}_bot'


def create_link(owner_bot, username, display_name):
    return f'https://t.me/newbot/{quote(owner_bot)}/{quote(username)}?name={quote(display_name)}'


# -- the family instance's pending setup ----------------------------------

def setup_path(store):
    return Path(store.private) / SETUP_FILE


def write_setup(store, *, instance, display_name, owner_bot, now=None):
    """Create the family instance's one-time setup record; returns it."""
    now = time.time() if now is None else now
    record = {'instance': instance, 'display_name': display_name, 'owner_bot': owner_bot,
              'username': suggested_username(instance), 'code': secrets.token_urlsafe(18),
              'handoff': secrets.token_urlsafe(32), 'created': now, 'expires': now + SETUP_SECONDS}
    store.write_private(setup_path(store), json.dumps(record))
    return record


def setup_recorded(store):
    """Whether this instance was ever set up through a tunnel (review P2-2).

    Its tunnel gate stays closed for good: after the setup finishes or
    expires, a tunnel that is still up (a killed command) reaches nothing.
    """
    return setup_path(store).exists()


def read_setup(store, now=None):
    """The pending setup, or None when absent, finished or expired."""
    try:
        record = json.loads(setup_path(store).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict) or record.get('finished'):
        return None
    try:
        if (time.time() if now is None else now) >= float(record.get('expires', 0)):
            return None
    except (TypeError, ValueError):
        return None
    return record


def _update_setup(store, **fields):
    try:
        record = json.loads(setup_path(store).read_text())
    except (OSError, ValueError):
        return None
    record.update(fields)
    store.write_private(setup_path(store), json.dumps(record))
    return record


def finish_setup(store):
    """Close the setup: the tunnel paths stop answering at once."""
    return _update_setup(store, finished=time.time())


def _same(value, expected):
    # Bytes, so a non-ASCII value is a mismatch rather than a TypeError (review P2-1).
    return isinstance(value, str) and bool(value) and hmac.compare_digest(value.encode(), str(expected).encode())


def code_ok(record, code):
    return bool(record) and _same(code, record.get('code', ''))


def handoff_ok(record, value):
    return bool(record) and _same(value, record.get('handoff', ''))


def status(service, record, now=None):
    """What the wizard shows; closes the setup once the family member is paired."""
    now = time.time() if now is None else now
    cfg = service.store.config('telegram', {})
    out = {'name': record['display_name'], 'create_url': create_link(record['owner_bot'], record['username'], record['display_name']),
           'username': record['username'], 'ios': TELEGRAM_IOS, 'android': TELEGRAM_ANDROID,
           'expires_in': max(0, int(record['expires'] - now)), 'state': 'waiting_bot'}
    if cfg.get('enabled') and cfg.get('username'):
        out['state'] = 'bot_connected'
        out['bot_username'] = cfg['username']
        if record.get('pair_url') and float(record.get('pair_expires') or 0) > now:
            out['pair_url'] = record['pair_url']
    if isinstance(cfg.get('user_id'), int):
        out['state'] = 'paired'
        out.pop('pair_url', None)
        finish_setup(service.store)
    return out


def accept_token(service, record, token, creator_id=None):
    """Connect the handed-over bot token (loopback only) and keep its pairing link.

    ``creator_id`` is the Telegram user who created the bot; only that user
    can pair (review P2-5).
    """
    cfg = service.store.config('telegram', {})
    if cfg.get('enabled') and isinstance(token, str) and token and hmac.compare_digest(
            token.encode(), str(service.store.secret('telegram_token') or '').encode()):
        # The same bot arriving again never resets a pairing (re-review P2-6).
        return {'ok': True, 'already_connected': True}
    pairing = service.connect_telegram({'token': token})
    if isinstance(creator_id, int) and not isinstance(creator_id, bool):
        with service.lock:
            cfg = service.store.config('telegram', {})
            cfg['pair_user_id'] = creator_id
            service.store.put('telegram', cfg)
    _update_setup(service.store, pair_url=pairing['url'], pair_expires=time.time() + int(pairing.get('expires_in') or 600))
    describe_bot(service.telegram.call, (record or {}).get('display_name') or '가족 비서')
    return {'ok': True}


#: #928 review P3-2: seconds each best-effort description call may take.
DESCRIBE_TIMEOUT = 4


def bot_descriptions(display_name):
    """What the new bot's empty chat and profile say (#927): Telegram shows ``</>`` otherwise."""
    name = ' '.join(str(display_name or '').split())[:64] or '가족 비서'
    return {'description': f'{name}예요. 필요한 일을 편하게 말로 부탁하세요. 찾아보고, 정리하고, 대신 처리해 드려요.\n\n'
                           '아래 버튼을 누르면 바로 시작돼요.',
            'short_description': f'{name} · 필요한 일을 말로 부탁하세요'}


def describe_bot(call, display_name):
    """Set the bot's description and short description; best-effort, never blocks the hand-over."""
    texts = bot_descriptions(display_name)
    for method, key in (('setMyDescription', 'description'), ('setMyShortDescription', 'short_description')):
        try:
            # #928 review P3-2: short, so the hand-over answers well inside the owner side's wait.
            call(method, {key: texts[key]}, timeout=DESCRIBE_TIMEOUT)
        except Exception as exc:
            LOG.warning('family setup: %s failed (%s)', method, type(exc).__name__)


def pair_again(service, record):
    """A fresh pairing link when the first one expired before it was opened."""
    pairing = service.pair_telegram()
    _update_setup(service.store, pair_url=pairing['url'], pair_expires=time.time() + int(pairing.get('expires_in') or 600))
    return {'pair_url': pairing['url']}


# -- the owner's instance: the manager bot ---------------------------------

def register_pending(owner_store, record, port):
    """Tell the owner's instance which bot username belongs to which family instance."""
    rows = [row for row in owner_store.config(PENDING_KEY, []) if isinstance(row, dict) and row.get('instance') != record['instance']]
    rows.append({'instance': record['instance'], 'port': int(port), 'username': record['username'],
                 'expires': record['expires'], 'delivered': None})
    owner_store.secret(handoff_secret_key(record['instance']), record['handoff'])
    owner_store.put(PENDING_KEY, rows)


def record_tunnel(owner_store, instance, pid):
    """Remember the tunnel process of a pending setup, so a restart can end it (#929)."""
    rows = [dict(row, tunnel_pid=int(pid)) if isinstance(row, dict) and row.get('instance') == instance else row
            for row in owner_store.config(PENDING_KEY, []) or []]
    owner_store.put(PENDING_KEY, rows)


def _tunnel_command(pid, run=subprocess.run):
    """The command line of ``pid``, or '' when it is gone or unreadable."""
    try:
        result = run(['ps', '-o', 'command=', '-p', str(int(pid))], capture_output=True, text=True, timeout=5)
    except (OSError, ValueError, subprocess.SubprocessError):
        return ''
    return result.stdout.strip() if result.returncode == 0 else ''


def stop_stale_tunnel(row, *, run=subprocess.run, kill=None):
    """End the tunnel a setup left behind when its watcher died with the process (#929).

    Only a process whose command line is still this setup's own ``ngrok http
    127.0.0.1:<port>`` is signalled, so a reused pid is never touched.
    Returns True when a tunnel was signalled.
    """
    import os
    import signal
    pid, port = row.get('tunnel_pid'), row.get('port')
    if not isinstance(pid, int) or pid <= 1 or not isinstance(port, int):
        return False
    words = _tunnel_command(pid, run).split()
    if not (words and Path(words[0]).name == 'ngrok' and words[1:3] == ['http', f'127.0.0.1:{port}']):
        return False
    try:
        (kill or os.kill)(pid, signal.SIGTERM)
    except OSError:
        return False
    LOG.info('family setup: stopped the tunnel a restart left behind (instance=%s)', row.get('instance'))
    return True


def clear_pending(owner_store, instance):
    rows = [row for row in owner_store.config(PENDING_KEY, []) if isinstance(row, dict) and row.get('instance') != instance]
    owner_store.put(PENDING_KEY, rows)
    owner_store.remove_secret(handoff_secret_key(instance))


def deliver_token(port, handoff, token, creator_id=None, timeout=20):
    """POST the token to the family instance on loopback; never through a tunnel."""
    request = urllib.request.Request(f'http://127.0.0.1:{int(port)}/api/family/telegram-token',
                                     data=json.dumps({'token': token, 'creator_id': creator_id}).encode(), method='POST',
                                     headers={'Content-Type': 'application/json', HANDOFF_HEADER: handoff})
    with _LOOPBACK.open(request, timeout=timeout) as response:
        return json.loads(response.read() or b'{}')


def _hand_over(owner_store, telegram_call, row, deliver):
    """Run whichever of the two steps is still missing; True once both are done.

    Step one hands the token over; step two restricts the bot to its owner.
    Each is recorded on its own, so a retry never re-delivers a token that
    already arrived (re-review P2-6).
    """
    if not row.get('handed_over'):
        handoff = owner_store.secret(handoff_secret_key(row['instance']))
        if not handoff:
            return False
        token = telegram_call('getManagedBotToken', {'user_id': row['bot_id']})
        deliver(row['port'], handoff, token, row.get('creator_id'))
        row['handed_over'] = time.time()
    if not row.get('restricted'):
        # Only the family member who created the bot (its owner) can use it.
        telegram_call('setManagedBotAccessSettings', {'user_id': row['bot_id'], 'is_access_restricted': True})
        row['restricted'] = time.time()
    return True


def _attempt(owner_store, telegram_call, rows, row, deliver, now):
    try:
        done = _hand_over(owner_store, telegram_call, row, deliver)
    except Exception:
        done = False
    row['attempts'] = int(row.get('attempts') or 0) + 1
    if done:
        row['delivered'] = now
    else:
        row['next_attempt'] = now + RETRY_SECONDS
    owner_store.put(PENDING_KEY, rows)
    return done


def accept_managed_bot(owner_store, telegram_call, update, deliver=deliver_token, now=None):
    """Handle one ``managed_bot`` update on the owner's instance.

    Accepted only when the new bot's username is one this instance issued for
    a pending, unexpired family setup.  The bot and its creator are bound to
    that setup; a hand-over that fails is retried by ``retry_pending`` until
    the setup expires (review P2-3).  Returns a content-free receipt; the
    token is never returned, logged or stored here.
    """
    now = time.time() if now is None else now
    bot = update.get('bot') if isinstance(update, dict) else None
    creator = update.get('user') if isinstance(update, dict) else None
    username = bot.get('username') if isinstance(bot, dict) else None
    bot_id = bot.get('id') if isinstance(bot, dict) else None
    if not isinstance(username, str) or not _BOT_USERNAME.match(username) or not isinstance(bot_id, int):
        return {'accepted': False, 'reason': 'not a bot'}
    rows = [row for row in owner_store.config(PENDING_KEY, []) if isinstance(row, dict)]
    matches = [row for row in rows if str(row.get('username', '')).lower() == username.lower()
               and not row.get('delivered') and row.get('bot_id') in (None, bot_id) and float(row.get('expires') or 0) > now]
    if len(matches) != 1:
        return {'accepted': False, 'reason': 'no pending family setup for this bot'}
    row = matches[0]
    row['bot_id'] = bot_id
    creator_id = creator.get('id') if isinstance(creator, dict) else None
    row['creator_id'] = creator_id if isinstance(creator_id, int) and not isinstance(creator_id, bool) else None
    delivered = _attempt(owner_store, telegram_call, rows, row, deliver, now)
    return {'accepted': True, 'instance': row['instance'], 'delivered': delivered}


def retry_pending(owner_store, telegram_call, deliver=deliver_token, now=None):
    """Retry bound, undelivered hand-overs whose setup is still open; returns how many succeeded."""
    now = time.time() if now is None else now
    rows = [row for row in owner_store.config(PENDING_KEY, []) if isinstance(row, dict)]
    succeeded = 0
    for row in rows:
        if (isinstance(row.get('bot_id'), int) and not row.get('delivered') and float(row.get('expires') or 0) > now
                and float(row.get('next_attempt') or 0) <= now and int(row.get('attempts') or 0) < MAX_ATTEMPTS):
            succeeded += _attempt(owner_store, telegram_call, rows, row, deliver, now)
    return succeeded


# -- the temporary HTTPS link (ngrok, already installed on the owner's Mac) --

def start_tunnel(port, popen=subprocess.Popen, timeout=30):
    """Start ``ngrok http`` for one loopback port; returns ``(process, https_url)``.

    ``--host-header=rewrite`` makes the instance see ``localhost:<port>``.
    ngrok still adds forwarding headers, so every tunneled request is
    *relayed* and never local (#594).  ``--inspect=false`` keeps no request
    log in ngrok's local inspector (review P3-2).  Its output is drained in a
    daemon thread for the tunnel's life, so a full pipe never stalls it, and
    the address is awaited with a real deadline (review P2-4).
    """
    from .subscription_engines import find_cli
    # #932: under launchd PATH lacks Homebrew; the real launcher runs the found binary.
    binary = (find_cli('ngrok') or 'ngrok') if popen is subprocess.Popen else 'ngrok'
    process = popen([binary, 'http', f'127.0.0.1:{int(port)}', '--host-header=rewrite', '--inspect=false',
                     '--log', 'stdout', '--log-format', 'json'],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines = queue.Queue()

    found = threading.Event()

    def drain():
        # After the address is found the output is only drained, never kept (re-review P3-5).
        for line in process.stdout:
            if not found.is_set():
                lines.put(line)
        lines.put(None)
    threading.Thread(target=drain, daemon=True).start()
    deadline = time.monotonic() + timeout
    last_error = ''
    while True:
        try:
            line = lines.get(timeout=max(0.0, deadline - time.monotonic()))
        except queue.Empty:
            break
        if line is None:
            break
        try:
            entry = json.loads(line)
        except ValueError:
            entry = {}
        if not isinstance(entry, dict):
            continue
        url = entry.get('url')
        if isinstance(url, str) and url.startswith('https://'):
            found.set()
            return process, url
        if entry.get('lvl') in ('eror', 'error', 'crit') or entry.get('err'):
            last_error = str(entry.get('err') or entry.get('msg') or '')[:200]
    process.terminate()
    raise RuntimeError('ngrok did not report a public HTTPS address.' + (f' ({last_error})' if last_error else ''))


# -- the page --------------------------------------------------------------

def page(record, nonce):
    """The wizard: one mobile page, no external resources, polls its own status."""
    name = escape(record['display_name'])
    code = json.dumps(record['code'])
    nonce = escape(nonce)
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{name} 설정</title>
<style nonce="{nonce}">body{{font:17px/1.5 -apple-system,system-ui,sans-serif;margin:0;padding:20px;max-width:520px;margin:auto;color:#1c1c1e}}
h1{{font-size:22px}}section{{border:1px solid #d1d1d6;border-radius:14px;padding:16px;margin:14px 0}}
section.done{{opacity:.55}}a.button,button{{display:block;width:100%;box-sizing:border-box;text-align:center;padding:14px;margin:8px 0;
border-radius:12px;border:0;background:#0a84ff;color:#fff;font-size:17px;text-decoration:none}}a.secondary{{background:#e5e5ea;color:#1c1c1e}}
.note{{font-size:14px;color:#636366}}.hidden{{display:none}}</style></head><body>
<h1>{name} 만들기</h1>
<p class="note">이 비서는 가족의 Mac에서 동작하고, 그 Mac 주인의 AI 구독을 씁니다. Mac 주인은 기술적으로 이 비서의 대화와 봇에 접근할 수 있습니다.</p>
<section id="s1"><h2>1. 텔레그램 설치</h2><p>텔레그램을 설치하고 전화번호로 가입해 주세요.</p>
<a class="button secondary" href="{TELEGRAM_IOS}">iPhone에서 설치</a><a class="button secondary" href="{TELEGRAM_ANDROID}">Android에서 설치</a>
<button id="installed">설치하고 가입했어요</button></section>
<section id="s2" class="hidden"><h2>2. 내 비서 봇 만들기</h2><p>텔레그램에서 이름과 아이디가 채워진 화면이 열립니다. <b>아이디는 바꾸지 말고</b> 만들기를 눌러 주세요.</p>
<a class="button" id="create">텔레그램에서 봇 만들기</a><p class="note" id="wait2"></p></section>
<section id="s3" class="hidden"><h2>3. 비서와 대화 시작</h2><p>아래 버튼을 누르고 텔레그램에서 <b>시작</b>을 눌러 주세요.</p>
<a class="button" id="pair">비서와 대화 시작</a><button class="secondary hidden" id="repair">연결 링크 다시 받기</button></section>
<section id="s4" class="hidden"><h2>완료</h2><p>이제 텔레그램에서 비서에게 말을 걸면 됩니다. 이 페이지는 닫아도 됩니다.</p></section>
<p class="note" id="expire"></p>
<script nonce="{nonce}">
const code={code};const q='?code='+encodeURIComponent(code);const $=id=>document.getElementById(id);
function show(id){{$(id).classList.remove('hidden')}}
$('installed').onclick=()=>{{$('s1').classList.add('done');show('s2')}};
$('repair').onclick=async()=>{{const r=await fetch('/api/family/pair'+q,{{method:'POST'}});if(r.ok){{const d=await r.json();$('pair').href=d.pair_url;$('repair').classList.add('hidden')}}}};
async function tick(){{let d;try{{const r=await fetch('/api/family/status'+q,{{cache:'no-store'}});if(r.status===404){{$('expire').textContent='설정 링크가 만료되었거나 이미 끝났습니다.';return}}if(!r.ok){{setTimeout(tick,4000);return}}d=await r.json()}}catch(e){{setTimeout(tick,4000);return}}
$('create').href=d.create_url;$('expire').textContent='이 링크는 약 '+Math.ceil(d.expires_in/60)+'분 뒤에 닫힙니다.';
if(d.state==='waiting_bot'){{$('wait2').textContent='봇을 만들면 이 화면이 자동으로 다음 단계로 넘어갑니다.'}}
if(d.state==='bot_connected'){{['s1','s2'].forEach(i=>{{show(i);$(i).classList.add('done')}});show('s3');if(d.pair_url){{$('pair').href=d.pair_url}}else{{show('repair')}}}}
if(d.state==='paired'){{['s1','s2','s3'].forEach(i=>{{show(i);$(i).classList.add('done')}});show('s4');return}}
setTimeout(tick,3000)}}
tick();
</script></body></html>'''


def page_csp(nonce):
    return (f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; connect-src 'self'; "
            "img-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")


# -- the owner's one command: `agentos family add NAME` ---------------------

def _telegram_get(token, method, opener=urllib.request.urlopen, body=None):
    """One Bot API call with the owner's token; the token is never printed."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f'https://api.telegram.org/bot{token}/{method}', data=data,
                                     headers={'Content-Type': 'application/json'} if data else {})
    with opener(request, timeout=20) as response:
        payload = json.loads(response.read() or b'{}')
    if not payload.get('ok'):
        raise RuntimeError(f'Telegram refused {method}.')
    return payload['result']


def _port_free(port):
    import socket
    for candidate in (port, port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(('127.0.0.1', candidate))
            except OSError:
                return False
    return True


def choose_port(taken, first=8797, free=_port_free):
    """The first port p (stepping by 2) whose pair (p, p + 1) is neither recorded nor bound."""
    for port in range(first, 65534, 2):
        if not {port, port + 1} & taken and free(port):
            return port
    raise RuntimeError('No free port pair was found.')


def _local_status(port, code, opener=_LOOPBACK.open):
    with opener(f'http://127.0.0.1:{int(port)}/api/family/status?code={quote(code)}', timeout=10) as response:
        return json.loads(response.read() or b'{}')


#: The owner's AI route a family instance runs on (#893: the owner shares the
#: subscription).  Each configuration row travels with the rows it needs and the
#: secrets it consumes, and a secret only with its row (re-review P2-7).
SHARED_ROUTE_ROWS = {
    'subscription_engine': ((), ('claude_code_token',)),
    'model': (('model_test',), ('model_key',)),
    'decision_route': (('decision_route_checks',), ()),
    'decision_model': ((), ('decision_model_key',)),
    'decision_jev': ((), ('decision_jev_key',)),
}


def _has_route(store):
    engine = store.config('subscription_engine', {})
    model = store.config('model', {})
    return bool((isinstance(engine, dict) and engine.get('id')) or (isinstance(model, dict) and model.get('provider')))


def share_ai_route(owner_store, family_store):
    """Give a family instance the owner's AI route; returns the copied names (never values).

    Without a route a paired family member would only be told to connect a
    model (review P1).  Only the route rows, their companion rows and the
    secrets they consume are copied; the owner's memory, folders, Telegram bot
    and every other secret stay behind.  An instance that already has a route
    keeps it (re-review P3-9).  Returns None when the owner has no route.
    """
    if not _has_route(owner_store):
        return None
    if _has_route(family_store):
        return []
    copied = []
    for key, (companions, secret_keys) in SHARED_ROUTE_ROWS.items():
        value = owner_store.config(key, None)
        if not value:
            continue
        family_store.put(key, value)
        copied.append(key)
        for companion in companions:
            extra = owner_store.config(companion, None)
            if extra:
                family_store.put(companion, extra)
                copied.append(companion)
        for secret_key in secret_keys:
            secret = owner_store.secret(secret_key)
            if secret:
                family_store.secret(secret_key, secret)
                copied.append(secret_key)
    return copied


class SetupError(RuntimeError):
    """A family setup that could not start; the message is for the owner."""


STATE_TEXT = {'waiting_bot': '가족이 봇을 만들기를 기다리는 중이에요.',
              'bot_connected': '가족의 봇이 연결됐어요. 대화 시작을 기다리는 중이에요.',
              'paired': '가족 비서 연결이 끝났어요. 이제 가족이 텔레그램에서 비서와 대화할 수 있어요.'}
EXPIRED_TEXT = '가족 비서 설정 링크가 만료됐어요. 다시 만들어 달라고 하시면 새 링크를 드릴게요.'


def family_instances(home=None):
    """Names of the named AgentOS instances installed on this Mac (#897)."""
    from .service_control import LABEL
    folder = Path(home or Path.home()) / 'Library/LaunchAgents'
    return sorted(path.name[len(LABEL) + 1:-len('.plist')] for path in folder.glob(f'{LABEL}.*.plist'))


def _paired(data_dir):
    """Whether that instance's Telegram is paired; an instance with no store is never reused."""
    from .quickstart_store import QuickStore
    if not (Path(data_dir) / 'private' / 'quickstart.db').is_file():
        return True
    try:
        return isinstance(QuickStore(data_dir).config('telegram', {}).get('user_id'), int)
    except Exception:
        return True


def pick_instance_name(home=None):
    """An installed family instance nobody has paired yet, else the first free ``family-N`` (#913 review P2-3).

    A retried setup reuses the unpaired instance instead of adding another, and
    a folder left by an uninstalled instance counts as taken, so a new member
    never lands on someone else's data.
    """
    home = Path(home or Path.home())
    installed = family_instances(home)
    data_root = home / '.local/share/agentos-instances'
    for name in installed:
        if not _paired(data_root / name):
            return name
    folders = {path.name for path in data_root.iterdir() if path.is_dir()} if data_root.is_dir() else set()
    return next_instance_name(set(installed) | folders)


def reconcile_pending(owner_store, now=None, *, run=subprocess.run, kill=None):
    """At start: a setup whose watcher died with the process is closed (#913 review P3-2).

    #929: its tunnel process, which outlives the owner server, is ended too.
    """
    for row in list(owner_store.config(PENDING_KEY, []) or []):
        if isinstance(row, dict) and row.get('instance'):
            stop_stale_tunnel(row, run=run, kill=kill)
            clear_pending(owner_store, row['instance'])


def next_instance_name(existing):
    """``family-1``, ``family-2``, ... the first one not taken."""
    index = 1
    while f'family-{index}' in set(existing):
        index += 1
    return f'family-{index}'


def prepare_family_setup(owner_store, name, display_name, *, service_action, environ=None, opener=None,
                         popen=subprocess.Popen, free=_port_free, port=None):
    """Create (or reuse) the instance, open the temporary link; returns a handle, or raises ``SetupError``.

    Shared by ``agentos family add`` and the owner's conversation (#912).  The
    caller then runs ``watch_family_setup`` and closes everything.
    """
    import os
    from .quickstart_store import QuickStore
    from .service_control import DEFAULT_PORT, ServiceController, service_label
    environ = os.environ if environ is None else environ
    external = opener or urllib.request.urlopen
    try:
        service_label(name)
    except ValueError as exc:
        raise SetupError(str(exc)) from None
    display_name = ' '.join(str(display_name or '').split())[:64] or f'{name} 비서'
    import shutil
    from .subscription_engines import find_cli
    if popen is subprocess.Popen and not find_cli('ngrok'):
        # #913 review P2-2: checked before anything is created or copied.
        raise SetupError('가족에게 보낼 임시 링크를 만들 ngrok이 이 Mac에 없어 가족 비서를 만들지 않았습니다.')
    cfg = owner_store.config('telegram', {})
    owner_token = owner_store.secret('telegram_token')
    if not (cfg.get('enabled') and cfg.get('username') and owner_token):
        raise SetupError('먼저 내 AgentOS에 텔레그램 봇을 연결해 주세요. 가족 봇은 내 봇이 관리자로 만들어 줍니다.')
    me = _telegram_get(owner_token, 'getMe', external)
    if not me.get('can_manage_bots'):
        raise SetupError(f"BotFather 미니앱에서 @{cfg['username']} 봇의 'Bot Management Mode'를 한 번 켜 주세요.")
    # An instance already installed keeps the port recorded in its own definition.
    existing = ServiceController(instance=name, environ=environ)
    taken = {DEFAULT_PORT, DEFAULT_PORT + 1} | {value for _data, other in existing._other_definitions() for value in (other, other + 1)}
    port = port or existing.port or choose_port(taken, free=free)
    family_store = QuickStore(ServiceController(instance=name, port=port, environ=environ).data_dir)
    if share_ai_route(owner_store, family_store) is None:
        raise SetupError('내 AgentOS에 연결된 AI(구독 엔진이나 모델)가 없어 가족 비서를 만들지 않았습니다. 먼저 내 AI를 연결해 주세요.')
    record = write_setup(family_store, instance=name, display_name=display_name, owner_bot=cfg['username'])
    register_pending(owner_store, record, port)
    handle = {'name': name, 'display_name': display_name, 'port': port, 'record': record,
              'family_store': family_store, 'process': None, 'link': None}
    try:
        receipt = service_action('status', instance=name, port=port)
        if not receipt.get('background_available'):
            receipt = service_action('install', instance=name, port=port)
            if not receipt.get('ok'):
                raise SetupError('가족 비서를 이 Mac에서 시작하지 못했습니다. ' + str(receipt.get('next_action') or receipt.get('error') or ''))
        try:
            process, public = start_tunnel(port, popen=popen)
        except (OSError, RuntimeError) as exc:
            raise SetupError('가족에게 보낼 임시 링크를 열지 못했습니다. ' + str(exc)) from None
        handle['process'] = process
        if isinstance(getattr(process, 'pid', None), int):
            record_tunnel(owner_store, name, process.pid)
        handle['link'] = f"{public}/family-setup?code={quote(record['code'])}"
        return handle
    except BaseException:
        close_family_setup(handle, owner_store)
        raise


def close_family_setup(handle, owner_store):
    """Stop the tunnel and close the setup; the instance keeps running."""
    if handle.get('process') is not None:
        try:
            handle['process'].terminate()
        except Exception:
            pass
    finish_setup(handle['family_store'])
    clear_pending(owner_store, handle['name'])


def watch_family_setup(handle, owner_store, *, on_state, opener=None, sleep=time.sleep, clock=time.time):
    """Wait until the family member pairs or the setup expires, then close it; True when paired."""
    loopback = opener or _LOOPBACK.open
    record, last, paired = handle['record'], None, False
    try:
        # The tunnel ends a little before the setup does (review P2-2).
        while clock() < record['expires'] - 5:
            try:
                state = _local_status(handle['port'], record['code'], loopback).get('state')
            except Exception:
                state = None
            if state and state != last:
                on_state(state)
                last = state
            if state == 'paired':
                paired = True
                break
            sleep(3)
        if not paired:
            on_state('expired')
        return paired
    finally:
        close_family_setup(handle, owner_store)


def family_main(argv, *, service_action, owner_data=None, environ=None, opener=None,
                popen=subprocess.Popen, out=print, sleep=time.sleep, clock=time.time, free=_port_free):
    """``agentos family add NAME``: the same setup as asking the assistant, from a terminal."""
    import argparse
    import os
    from .quickstart_store import QuickStore
    environ = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(prog='agentos family', description="Create a family member's own agent on this Mac.")
    parser.add_argument('action', choices=('add',))
    parser.add_argument('name', help='Instance name: lowercase letters, digits and hyphens (e.g. spouse).')
    parser.add_argument('--display-name', default=None, help='The bot name shown in Telegram.')
    parser.add_argument('--port', type=int, default=None, help='Port for the instance (default: the next free pair from 8797).')
    parser.add_argument('--owner-data', default=None, help="The owner's data directory (default: AGENTOS_DATA or ~/.local/share/agentos).")
    args = parser.parse_args(argv)
    owner_root = Path(args.owner_data or owner_data or environ.get('AGENTOS_DATA') or Path.home() / '.local/share/agentos').expanduser()
    owner_store = QuickStore(owner_root)
    try:
        handle = prepare_family_setup(owner_store, args.name, args.display_name, service_action=service_action,
                                      environ=environ, opener=opener, popen=popen, free=free, port=args.port)
    except SetupError as exc:
        out(str(exc))
        return 2 if 'lowercase' in str(exc) or '1-32' in str(exc) else 1
    out(f"{handle['display_name']} 설정 링크 (약 {SETUP_SECONDS // 60}분 동안 열려 있습니다):\n{handle['link']}")
    cfg = owner_store.config('telegram', {})
    if isinstance(cfg.get('user_id'), int):
        try:
            _telegram_get(owner_store.secret('telegram_token'), 'sendMessage', opener or urllib.request.urlopen,
                          {'chat_id': cfg['user_id'], 'text': f"{handle['display_name']} 설정 링크입니다. 가족에게 보내 주세요.\n{handle['link']}"})
        except Exception:
            pass
    paired = watch_family_setup(handle, owner_store, on_state=lambda state: out(STATE_TEXT.get(state, EXPIRED_TEXT)),
                                opener=opener, sleep=sleep, clock=clock)
    return 0 if paired else 1
