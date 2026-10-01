"""Sign in to a site from the phone through a one-time link that drives the Mac's login window (BROWSE-07 #939).

An in-flow login (#709) or an explicit login request shows the AgentOS login
window on the Mac.  The owner who is not at the Mac gets a temporary HTTPS
link (ngrok, as the family setup's, #897) to a page that shows that window
as an image refreshed about twice a second; a tap on the image is pressed at
the same point in the window, text goes into the focused field, and [완료]
closes the window, which saves the session to the jar exactly as closing it
on the Mac does.  Nothing is proxied: the site talks to the Mac's WebKit
only, and the phone sees pixels.

Boundaries:
- the link carries a 32-byte random code and expires in ``SESSION_SECONDS``
  (10 minutes) or less; it is sent only to the paired owner's Telegram chat;
- the first client whose page calls the API with the cookie the page set is
  bound to the session (an HttpOnly, Secure, SameSite=Strict cookie); every
  later request must carry it, or it is answered 404;
- through the tunnel only ``PUBLIC_PATHS`` answer, and only with the code;
  every other route is refused (``quickstart.remote_login_gate``);
- typed text and taps go into the worker's ``remote_*`` ops and nowhere
  else: never logged, stored or shown to a model; image frames pass through
  once and are never stored;
- the log records only ``open``, ``bound``, ``done``, ``expired`` or
  ``closed`` with the site name;
- one session at a time; done, expiry, a Telegram skip and a Mac close each
  stop the tunnel and the window.
"""
import hashlib
import hmac
import json
import logging
import secrets
import subprocess
import threading
import time
from html import escape
from urllib.parse import quote

from .family_setup import start_tunnel

LOG = logging.getLogger('personal_agent.remote_login')

SESSION_SECONDS = 10 * 60
PAGE_PATH = '/remote-login'
FRAME_PATH = '/api/remote-login/frame'
INPUT_PATH = '/api/remote-login/input'
DONE_PATH = '/api/remote-login/done'
PUBLIC_PATHS = frozenset({PAGE_PATH, FRAME_PATH, INPUT_PATH, DONE_PATH})
COOKIE_NAME = 'agentos_remote_login'
INPUT_KINDS = ('tap', 'text', 'key', 'nav', 'dialog')
DIALOG_ANSWERS = ('ok', 'cancel')
KEYS = ('Enter', 'Backspace', 'Tab')
NAV_ACTIONS = ('back', 'reload')
#: Characters one text input may carry (a page's field, never a document).
TEXT_LIMIT = 512
#: How often the page refreshes the image, in milliseconds.
REFRESH_MS = 500

LINK_TEXT = ('휴대폰에서 로그인하는 링크예요 ({site}). 이 링크를 연 휴대폰 한 대만 쓸 수 있고, 약 {minutes}분 뒤에 닫혀요.\n'
             '화면을 누르면 Mac의 로그인 창에서 같은 자리가 눌리고, 입력한 글자는 선택한 칸에 들어가요. '
             '다 되면 [완료]를 눌러 주세요.\n{link}')
NO_NGROK_TEXT = '휴대폰에서 로그인할 임시 링크를 만들 ngrok이 이 Mac에 없어요. Mac의 로그인 창에서 로그인해 주세요.'
NO_PORT_TEXT = '이 Mac의 AgentOS 주소를 아직 알 수 없어 휴대폰 로그인 링크를 만들지 못했어요. Mac의 로그인 창에서 로그인해 주세요.'
BUSY_TEXT = '이미 휴대폰 로그인 링크가 열려 있어요. 그 링크가 닫힌 뒤에 다시 요청해 주세요.'
#: A link that could not open or be delivered leaves the Mac window and its prompt as they are (review P2-1).
TUNNEL_FAILED_TEXT = '휴대폰 링크를 열지 못했어요. Mac의 로그인 창에서 로그인해 주세요.'
#: Review P3-6: a family instance (one paired through a family setup) never opens a phone link to a window.
FAMILY_INSTANCE_TEXT = '가족 비서에서는 휴대폰 로그인 링크를 만들 수 없어요.'
#: How many unbound page cookies are kept at once (review P3-1): a later page open never invalidates an earlier one.
ISSUED_KEPT = 8
#: Review P3-3: how long after 완료's reply the tunnel is stopped, so the phone gets the answer first.
DONE_DELAY_SECONDS = 0.3


class RemoteLoginError(RuntimeError):
    """A session that could not start; the message is for the owner."""


def cookie_header(token):
    return f'{COOKIE_NAME}={token}; HttpOnly; Secure; SameSite=Strict; Path=/'


def _same(value, expected):
    return isinstance(value, str) and bool(value) and bool(expected) and hmac.compare_digest(value.encode(), str(expected).encode())


def validate_input(body):
    """``(kind, fields)`` of one phone input, or None when it is not one.

    ``tap`` carries ``x``/``y`` (numbers), ``text`` a bounded string, ``key``
    one of ``KEYS``, ``nav`` one of ``NAV_ACTIONS`` and ``dialog`` (the
    answer to a page's own dialog) one of ``DIALOG_ANSWERS``.  Nothing else passes.
    """
    if not isinstance(body, dict):
        return None
    kind = body.get('type')
    if kind == 'tap':
        x, y = body.get('x'), body.get('y')
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 for v in (x, y)):
            return 'tap', {'x': float(x), 'y': float(y)}
    elif kind == 'text':
        text = body.get('text')
        if isinstance(text, str) and 0 < len(text) <= TEXT_LIMIT and '\n' not in text and '\r' not in text:
            return 'text', {'text': text}
    elif kind == 'key':
        if body.get('key') in KEYS:
            return 'key', {'key': body['key']}
    elif kind == 'nav':
        if body.get('action') in NAV_ACTIONS:
            return 'nav', {'action': body['action']}
    elif kind == 'dialog':
        if body.get('answer') in DIALOG_ANSWERS:
            return 'dialog', {'answer': body['answer']}
    return None


class RemoteLogin:
    """One remote login session: its link, binding, tunnel and the login window it drives.

    ``profile`` is the ``BrowserProfile`` whose login window ``window`` is
    open; ``close(reason)`` closes that window the way its opener closes it
    (an in-flow login records a decision, an explicit one asks the window to
    close); ``on_end(reason)`` runs once after the session ended.  ``popen``
    and ``clock`` are injectable for tests.
    """

    def __init__(self, profile, window, site, close, *, on_end=None, popen=subprocess.Popen, clock=time.time,
                 seconds=SESSION_SECONDS):
        self.profile, self.window, self.site = profile, window, str(site or '')
        self._close, self._on_end = close, on_end
        self._popen, self.clock = popen, clock
        self.code = secrets.token_urlsafe(32)
        self.created = clock()
        self.expires = self.created + max(1.0, min(float(seconds), SESSION_SECONDS))
        #: The cookie value the bound client carries; None until a page's first API call binds it.
        self.bound_client = None
        #: The cookie values pages were given while unbound (newest last, at most ``ISSUED_KEPT``).
        self._issued = []
        #: The digest of the last frame sent (review P3-4); never the frame itself.
        self._last_frame = None
        self.process = None
        self.link = None
        self.reason = None
        self._lock = threading.Lock()
        self._ended = threading.Event()

    # -- lifecycle -------------------------------------------------------------
    def start(self, port):
        """Open the tunnel to ``port`` and return the one-time link; the watcher then runs until the end."""
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise RemoteLoginError(NO_PORT_TEXT)
        try:
            self.process, public = start_tunnel(port, popen=self._popen)
        except (OSError, RuntimeError) as exc:
            raise RemoteLoginError(TUNNEL_FAILED_TEXT + ' ' + str(exc)) from None
        self.link = f'{public}{PAGE_PATH}?code={quote(self.code)}'
        # Page dialogs (#936) are now held for the phone's answer and shown on the Mac as a sheet.
        self.profile.login_window_remote(self.window, True)
        LOG.info('remote login open site=%s', self.site)
        threading.Thread(target=self._watch, name='agentos-remote-login', daemon=True).start()
        return self.link

    def _watch(self):
        """End the session at its expiry, or as soon as its window closed on its own."""
        while not self._ended.wait(0.5):
            if self.clock() >= self.expires:
                self.finish('expired')
            elif self.profile.login_window_outcome(self.window) is not None:
                self.finish('closed')

    def alive(self):
        return not self._ended.is_set()

    def expired(self, now=None):
        return (self.clock() if now is None else now) >= self.expires

    def finish(self, reason):
        """End the session once: stop the tunnel, close the window its way, tell the owner's side.

        ``closed``: the window already closed on its own, nothing more to close.
        ``failed``: the link never opened or was never delivered (review P2-1):
        the tunnel stops but the window and its prompt stay exactly as they
        were, for the owner to use on the Mac.
        """
        with self._lock:
            if self._ended.is_set():
                return False
            self.reason = reason
            self._ended.set()
        process, self.process = self.process, None
        if process is not None:
            try:
                process.terminate()
            except Exception:
                pass
        LOG.info('remote login %s site=%s', reason, self.site)
        if reason != 'closed':
            self.profile.login_window_remote(self.window, False)
        if reason not in ('closed', 'failed'):
            try:
                self._close(reason)
            except Exception as exc:
                LOG.warning('remote login: window close failed (%s)', type(exc).__name__)
        if self._on_end is not None:
            try:
                self._on_end(reason)
            except Exception as exc:
                LOG.warning('remote login: end hook failed (%s)', type(exc).__name__)
        return True

    def finish_later(self, reason, delay=DONE_DELAY_SECONDS):
        """``finish`` after ``delay`` seconds, so a reply already written reaches the phone before the tunnel stops (review P3-3)."""
        timer = threading.Timer(delay, self.finish, args=(reason,))
        timer.daemon = True
        timer.start()
        return self.alive()

    # -- the link and its client -----------------------------------------------
    def code_ok(self, code):
        return self.alive() and not self.expired() and _same(code, self.code)

    def _issued_match(self, cookie):
        return next((issued for issued in self._issued if _same(cookie, issued)), None)

    def open_page(self, cookie):
        """The page was requested: the cookie to set (a fresh value while unbound, unless the request already
        carries one issued here, review P3-1), None when a known client reloads, or False when another
        client asked after binding."""
        with self._lock:
            if self.bound_client is None:
                if self._issued_match(cookie) is not None:
                    return None
                issued = secrets.token_urlsafe(32)
                self._issued = (self._issued + [issued])[-ISSUED_KEPT:]
                return issued
            return None if _same(cookie, self.bound_client) else False

    def client_ok(self, cookie):
        """Whether an API request's cookie is the bound client's; the first API call carrying any cookie a
        page was issued binds that client (a link preview fetcher never calls the API, so it never binds,
        and a later page open never invalidates an earlier one, review P3-1)."""
        with self._lock:
            if self.bound_client is None:
                issued = self._issued_match(cookie)
                if issued is None:
                    return False
                self.bound_client, self._issued = issued, []
                LOG.info('remote login bound site=%s', self.site)
                return True
            return _same(cookie, self.bound_client)

    # -- the window ----------------------------------------------------------------
    def frame(self, full=False):
        """The window's current image (``{'jpeg', 'width', 'height', 'dialog'}``), ``{'unchanged': True}``
        when nothing changed since the last one sent (review P3-4; ``full`` sends it anyway), or None when
        the window could not answer now."""
        if not self.alive():
            return None
        frame = self.profile.login_window_frame(self.window)
        if not isinstance(frame, dict):
            return None
        digest = hashlib.sha256(json.dumps([frame.get('jpeg'), frame.get('width'), frame.get('height'), frame.get('dialog')],
                                           sort_keys=True).encode()).hexdigest()
        if not full and digest == self._last_frame:
            return {'unchanged': True}
        self._last_frame = digest
        return frame

    def input(self, body):
        """One phone input (``validate_input``) into the window; True when the worker accepted it."""
        if not self.alive():
            return False
        checked = validate_input(body)
        if checked is None:
            return False
        kind, fields = checked
        return bool(self.profile.login_window_input(self.window, kind, **fields))

    def status(self):
        return {'site': self.site, 'state': self.reason or ('bound' if self.bound_client else 'open'),
                'expires_in': max(0, int(self.expires - self.clock()))}


# -- the page ----------------------------------------------------------------

def page(session, nonce):
    """The phone page: one mobile page, no external resources; it talks only to its own API."""
    site = escape(session.site or '로그인')
    code = json.dumps(session.code)
    nonce = escape(nonce)
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1"><title>{site} 로그인</title>
<style nonce="{nonce}">body{{font:16px/1.4 -apple-system,system-ui,sans-serif;margin:0;padding:10px;background:#1c1c1e;color:#f2f2f7}}
h1{{font-size:16px;margin:0 0 8px;font-weight:600}}.note{{font-size:13px;color:#aeaeb2;margin:6px 0}}
#shot{{display:block;width:100%;background:#000;border-radius:8px;touch-action:manipulation;-webkit-user-select:none;user-select:none}}
.row{{display:flex;gap:6px;margin:8px 0}}input{{flex:1;font-size:16px;padding:12px;border-radius:10px;border:1px solid #48484a;background:#2c2c2e;color:#fff}}
button{{font-size:15px;padding:12px 10px;border-radius:10px;border:0;background:#3a3a3c;color:#fff}}button.main{{background:#0a84ff}}
button.wide{{flex:1}}#done{{width:100%;font-size:19px;padding:16px;background:#30d158;color:#000;font-weight:600;margin-top:10px}}
#end{{display:none;text-align:center;padding:30px 0;font-size:18px}}.hidden{{display:none}}
#dialog{{background:#2c2c2e;border:1px solid #ffd60a;border-radius:10px;padding:12px;margin:8px 0}}#dialog p{{margin:0 0 8px;white-space:pre-wrap}}</style></head><body>
<h1>{site} 로그인</h1>
<div id="live"><div id="dialog" class="hidden"><p class="note">Mac의 로그인 창이 이 질문에 답하기를 기다리고 있어요.</p><p id="dialog-text"></p>
<div class="row"><button id="dialog-ok" class="main wide">확인</button><button id="dialog-cancel" class="wide">취소</button></div></div>
<img id="shot" alt="Mac의 로그인 창">
<p class="note">화면을 누르면 Mac의 로그인 창에서 같은 자리가 눌려요. 입력할 칸을 먼저 누른 뒤 아래에 글자를 넣고 [입력]을 누르세요.</p>
<div class="row"><input id="text" type="text" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" placeholder="선택한 칸에 넣을 글자" maxlength="{TEXT_LIMIT}"><button id="hide">가리기</button><button id="send" class="main">입력</button></div>
<div class="row"><button id="enter" class="wide">엔터</button><button id="back" class="wide">←지우기</button><button id="nav-back" class="wide">뒤로</button><button id="reload" class="wide">새로고침</button></div>
<button id="done">완료</button>
<p class="note" id="expire"></p></div>
<p id="end"></p>
<script nonce="{nonce}">
const code={code};const q='?code='+encodeURIComponent(code);const $=id=>document.getElementById(id);
let W=0,H=0,busy=false,ended=false,full=true;
function end(text){{ended=true;$('live').classList.add('hidden');$('end').style.display='block';$('end').textContent=text}}
async function post(path,body){{try{{const r=await fetch(path+q,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body||{{}}),credentials:'same-origin'}});
if(r.status===404){{end('이 링크는 닫혔어요.');return false}}if(!r.ok)return false;const d=await r.json();return d&&d.ok===true}}catch(e){{return false}}}}
async function frame(){{if(ended||busy)return;busy=true;try{{const r=await fetch('{FRAME_PATH}'+q+(full?'&full=1':''),{{cache:'no-store',credentials:'same-origin'}});
if(r.status===404){{end('이 링크는 닫혔어요.');return}}
if(r.status===204){{full=false;return}}
if(r.ok){{const d=await r.json();full=false;W=d.width;H=d.height;$('shot').src='data:image/jpeg;base64,'+d.jpeg;dialog(d.dialog)}}}}catch(e){{}}finally{{busy=false}}}}
function dialog(d){{const box=$('dialog');if(!d){{box.classList.add('hidden');return}}$('dialog-text').textContent=d.text||'';$('dialog-cancel').classList.toggle('hidden',d.kind!=='confirm');box.classList.remove('hidden')}}
$('dialog-ok').onclick=()=>post('{INPUT_PATH}',{{type:'dialog',answer:'ok'}}).then(()=>setTimeout(frame,150));
$('dialog-cancel').onclick=()=>post('{INPUT_PATH}',{{type:'dialog',answer:'cancel'}}).then(()=>setTimeout(frame,150));
setInterval(frame,{REFRESH_MS});frame();
$('shot').addEventListener('click',e=>{{if(!W||!H)return;const r=e.currentTarget.getBoundingClientRect();
const x=Math.max(0,Math.min(W,(e.clientX-r.left)/r.width*W)),y=Math.max(0,Math.min(H,(e.clientY-r.top)/r.height*H));post('{INPUT_PATH}',{{type:'tap',x:x,y:y}}).then(()=>setTimeout(frame,150))}});
$('send').onclick=async()=>{{const t=$('text').value;if(!t)return;if(await post('{INPUT_PATH}',{{type:'text',text:t}})){{$('text').value=''}}}};
$('text').addEventListener('keydown',e=>{{if(e.key==='Enter'){{e.preventDefault();$('send').click()}}}});
$('hide').onclick=()=>{{const t=$('text');t.type=t.type==='password'?'text':'password';$('hide').textContent=t.type==='password'?'보기':'가리기'}};
$('enter').onclick=()=>post('{INPUT_PATH}',{{type:'key',key:'Enter'}});
$('back').onclick=()=>post('{INPUT_PATH}',{{type:'key',key:'Backspace'}});
$('nav-back').onclick=()=>post('{INPUT_PATH}',{{type:'nav',action:'back'}});
$('reload').onclick=()=>post('{INPUT_PATH}',{{type:'nav',action:'reload'}});
$('done').onclick=async()=>{{if(await post('{DONE_PATH}')){{end('완료했어요. 로그인 창을 닫고 세션을 저장했어요. 이 페이지는 닫아도 돼요.')}}}};
$('expire').textContent='이 링크는 약 {max(1, int(round((session.expires - session.clock()) / 60)))}분 뒤에 닫혀요.';
</script></body></html>'''


def page_csp(nonce):
    return (f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; connect-src 'self'; "
            "img-src data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
