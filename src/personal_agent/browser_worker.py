"""Embedded macOS system WebKit browser worker (SEC-BROWSER-02 #680).

Run as ``python -P -m personal_agent.browser_worker --profile <id>``.  The
worker owns the process's main thread and the Cocoa run loop (AppKit and
WebKit objects may only be created and used there); a reader thread hands
every command to the main thread with ``AppHelper.callAfter``.  It speaks JSON
lines: one request per stdin line, one response per stdout line.

Request:  ``{"id": 7, "op": "navigate", "timeout": 20, ...arguments}``
Response: ``{"id": 7, "ok": true, ...result}`` or ``{"id": 7, "ok": false, "error": "<code>"}``
Events:   ``{"event": "ready" | "hidden" | "unavailable"}`` (no ``id``).

Ops: ``navigate``, ``snapshot``, ``click``, ``type``, ``show``, ``hide``,
``state``, ``cookies_export``, ``cookies_import``, ``cookies_delete``,
``cookies_clear``, ``quit``.  Every op carries a deadline; the worker answers
``timeout`` when it passes.  Errors are AgentOS codes, never library text,
and every line is ASCII JSON (a page's lone surrogate cannot break the pipe).

Session material: the web view uses ``WKWebsiteDataStore.nonPersistentDataStore()``
so WebKit keeps cookies in memory only and never writes a cookie file.  The
parent exports cookies over the pipe and keeps them in the encrypted jar
(``browser_jar``); the worker writes nothing to disk.

Page scripts run in ``WKContentWorld.defaultClientWorld()`` (the page cannot replace
the DOM functions they call).  Input is native and bound to one element:
``LOCATE`` resolves the element by index, checks the descriptor the payment
guard classified (tag, type, autocomplete, name, form membership, whether its
form holds a payment field), hit-tests it and keeps a handle; the native
press is followed by ``VERIFY_CLICK`` (a capture-phase guard in the same
world cancels a trusted click that lands elsewhere) or ``INSERT`` (the held
element must be the focused one and still match, then ``insertText`` runs in
that same script turn).  The element is never resolved a second time.

Submit guard (#698): for a page's whole life, from document start, a
capture-phase ``submit`` listener in the client world cancels a submit of any
form holding a card, CVC, card-expiry, one-time-code or password field,
whatever triggered it and whenever: a label forwarding a press, a scripted
click, ``requestSubmit``, a timer or an async-validation callback after the
step answered.  ``form.submit()`` fires no ``submit`` event, so a page-world
user script wraps ``HTMLFormElement.prototype.submit`` at document start to
signal the same listener (see ``PAGE_WRAP_USER_SCRIPT`` for its limits).  Only
a step the parent sends with ``approved`` lets one such submit through, until
the step answers; the owner's login window turns the guard off while shown.
A cancelled submit is recorded with its form (method, action, position): a
step answers ``approval_required``, and one cancelled between steps is
reported by the next snapshot (``cancelled_submit``) or step.

Destinations: every navigation (typed, redirect, form, ``window.open``, frame)
passes ``decidePolicyForNavigationAction``: only http(s) to public addresses,
after DNS resolution, reusing ``local_tools``' denied names and its
private-network table (``local_host``).  Loopback, private, link-local and ``.local`` hosts
(the AgentOS UI included) are refused.  Tests may allow one exact fixture
origin with ``--test-allow-origin``, an argument only a test constructor sets.

Reuse: Apple's WebKit (``WKWebView``) through PyObjC (MIT) is the adopted
engine; ``WKWebsiteDataRecord.displayName`` is WebKit's own per-site
(registrable domain) grouping.  No site, provider or category is named here.
"""
import argparse
import ipaddress
import json
import os
import platform
import plistlib
import socket
import sys
import threading
import time
import uuid
from urllib.parse import urlsplit

#: Appended to the user agent.  AgentOS's own HTTP server refuses every
#: request that carries it, so a page in the embedded browser can never use
#: the owner's AgentOS UI or API (#680 review P1-2).
EMBEDDED_UA_TOKEN = 'AgentOS-Embedded/1'

#: ``index`` is an element's position in ``document.querySelectorAll(SELECTOR)``.
SELECTOR = ('a[href], button, input, select, textarea, summary, [role="button"], [role="link"], [role="textbox"], '
            '[role="checkbox"], [role="radio"], [role="combobox"], [role="menuitem"], [role="tab"]')

#: The cancelable event the page-world ``form.submit()`` wrapper dispatches on
#: the form so the client-world submit guard can refuse it (#698).
SUBMIT_SIGNAL = 'agentos-guarded-submit'
#: The client-world message handler a cancelled submit is reported through.
GUARD_HANDLER = 'agentosGuard'
#: ``autocomplete`` field names of a payment form (with ``password`` inputs).
#: ``browser_session.PAYMENT_AUTOCOMPLETE`` is this same set.
PAYMENT_TOKENS = ('cc-csc', 'cc-exp', 'cc-exp-month', 'cc-exp-year', 'cc-number', 'one-time-code')

#: Helpers every page script shares.  Strings leaving the page are well-formed
#: UTF-16 and cut at code-point boundaries.  ``describe`` mirrors the guard's
#: classification in ``browser_session`` (the payment tokens are passed in).
PRELUDE = r"""
const SELECTOR = %(selector)s;
const well = (value) => { const s = String(value == null ? '' : value);
  return typeof s.toWellFormed === 'function' ? s.toWellFormed()
    : s.replace(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/g, '�'); };
const cut = (value, n) => { let s = well(value); if (s.length <= n) return s; s = s.slice(0, n);
  return /[\uD800-\uDBFF]$/.test(s) ? s.slice(0, -1) : s; };
const visible = (el) => {
  if (el.type === 'hidden') return false;
  const style = getComputedStyle(el);
  if (style.visibility === 'hidden' || style.display === 'none') return false;
  const rect = el.getBoundingClientRect();
  return rect.width > 0 || rect.height > 0;
};
const clean = (text) => cut(String(text || '').replace(/\s+/g, ' ').trim(), 160);
// The element's <label> without touching ``el.labels``: reading a label through
// that list on password-form pages left WebKit (macOS 26) unable to evaluate any
// further script in the document.
const labelOf = (el) => { const wrapping = el.closest('label');
  if (wrapping) return wrapping.innerText;
  const id = el.getAttribute('id');
  const target = id ? document.querySelector('label[for="' + CSS.escape(id) + '"]') : null;
  return target ? target.innerText : ''; };
const nameOf = (el) => {
  const tag = el.tagName.toLowerCase();
  const label = el.getAttribute('aria-label') || labelOf(el) ||
    el.getAttribute('placeholder') || el.getAttribute('title') || el.getAttribute('alt') ||
    ((tag === 'input' && (el.type === 'submit' || el.type === 'button')) ? el.value : '') ||
    el.innerText || el.textContent || (tag === 'input' ? el.name : '') || '';
  return clean(label);
};
const typeOf = (el) => { const tag = el.tagName.toLowerCase();
  return tag === 'input' ? (el.type || 'text').toLowerCase() : (tag === 'button' ? (el.type || 'submit').toLowerCase() : ''); };
const autocompleteOf = (el) => (el.getAttribute('autocomplete') || '').toLowerCase().trim();
const fieldToken = (el) => { const tokens = autocompleteOf(el).split(/\s+/).filter(Boolean);
  if (tokens.length && tokens[tokens.length - 1] === 'webauthn') tokens.pop(); return tokens.length ? tokens[tokens.length - 1] : ''; };
const formOf = (el) => el.form || el.closest('form');
// The control a <label> forwards a press to, for the label ``el`` is or sits in,
// when that control is another element (#698): HTML's ``label.control`` (the
// ``for`` target, else the first labelable descendant), resolved without ``el.labels``.
const LABELABLE = 'button, input:not([type="hidden"]), meter, output, progress, select, textarea';
const labelControl = (el) => { const label = el.closest('label'); if (!label) return null;
  const id = label.getAttribute('for');
  const control = id !== null ? document.getElementById(id) : label.querySelector(LABELABLE);
  return control && control !== el ? control : null; };
const paymentField = (el, tokens) => typeOf(el) === 'password' || tokens.includes(fieldToken(el));
const formHolds = (form, tokens) => !!form &&
  Array.from(document.querySelectorAll(SELECTOR)).some((other) => formOf(other) === form && visible(other) && paymentField(other, tokens));
const paymentForm = (el, tokens) => { if (formHolds(formOf(el), tokens)) return true;
  const control = labelControl(el); return !!control && formHolds(formOf(control), tokens); };
const describe = (el, tokens) => ({tag: el.tagName.toLowerCase(), type: typeOf(el), autocomplete: autocompleteOf(el), name: nameOf(el),
  in_form: !!formOf(el), payment_form: paymentForm(el, tokens)});
const same = (actual, expect) => !!expect && ['tag', 'type', 'autocomplete', 'name', 'in_form', 'payment_form']
  .every((key) => key in expect && actual[key] === expect[key]);
const state = () => (window.__agentos = window.__agentos || {targets: new Map(), guard: null, listening: false,
  off: false, allow: null, cancelled: null, submitListening: false});
// The submit guard (#698), armed for the page's whole life: a submit of a form holding
// a payment field (any field, shown or not) is cancelled whatever triggered it and
// whenever -- a trusted or scripted click, a label, ``requestSubmit``, Enter, a timer,
// an async callback, or ``form.submit()`` through the page-world signal.  Only an
// approved step lets ONE through (``allow``); the owner's login window sets ``off``.
const GUARD_TOKENS = %(tokens)s;
const formFields = (form) => { const own = Array.from(form.querySelectorAll('input, select, textarea, ' + SELECTOR));
  const id = form.getAttribute('id');
  return id ? own.concat(Array.from(document.querySelectorAll('[form="' + CSS.escape(id) + '"]'))) : own; };
const holdsPayment = (form) => formFields(form).some((field) => paymentField(field, GUARD_TOKENS));
// Which form: its position among the document's forms, its method and resolved action.
const formRecord = (form) => { const action = form.getAttribute('action'); let url = location.href;
  try { url = new URL(action === null ? '' : action, location.href).href; } catch (error) { url = location.href; }
  return {dom: Array.prototype.indexOf.call(document.forms, form),
    method: String(form.getAttribute('method') || 'get').toLowerCase().slice(0, 16), action: cut(url, 2000)}; };
const armSubmitGuard = () => { const s = state(); if (s.submitListening) return; s.submitListening = true;
  const cancel = (event) => { const g = state(); if (g.off) return;
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !holdsPayment(form)) return;
    if (g.allow && g.allow.left > 0) { g.allow.left -= 1; return; }
    event.preventDefault(); event.stopImmediatePropagation();
    const record = {...formRecord(form), id: Math.random().toString(36).slice(2) + Date.now().toString(36)};
    g.cancelled = record;
    try { window.webkit.messageHandlers[%(handler)s].postMessage(record); } catch (error) { /* read by the next script */ } };
  window.addEventListener('submit', cancel, true);
  window.addEventListener(%(signal)s, cancel, true); };
const takeCancelled = () => { const s = state(), c = s.cancelled; s.cancelled = null; return c; };
""" % {'selector': json.dumps(SELECTOR), 'signal': json.dumps(SUBMIT_SIGNAL), 'handler': json.dumps(GUARD_HANDLER),
       'tokens': json.dumps(list(PAYMENT_TOKENS))}

#: The snapshot: elements the model can act on and the fields the guard
#: reasons about.  Plain data only (no node handles, no HTML).
SNAPSHOT_SCRIPT = PRELUDE + r"""
const roleOf = (el) => {
  const role = el.getAttribute('role');
  if (role) return role;
  const tag = el.tagName.toLowerCase();
  if (tag === 'a') return 'link';
  if (tag === 'button' || tag === 'summary') return 'button';
  if (tag === 'select') return 'combobox';
  if (tag === 'textarea') return 'textbox';
  if (tag === 'input') {
    const type = typeOf(el);
    if (['submit', 'button', 'image', 'reset'].includes(type)) return 'button';
    if (type === 'checkbox' || type === 'radio') return type;
    return 'textbox';
  }
  return tag;
};
const NO_VALUE = ['submit', 'button', 'image', 'reset', 'checkbox', 'radio', 'file', 'password', 'hidden'];
const forms = new Map();
const idOf = (f) => { if (!f) return null; if (!forms.has(f)) forms.set(f, forms.size + 1); return forms.get(f); };
const elements = [];
Array.from(document.querySelectorAll(SELECTOR)).forEach((el, index) => {
  if (!visible(el)) return;
  const tag = el.tagName.toLowerCase();
  const form = formOf(el);
  const formId = idOf(form);
  const control = labelControl(el);
  const type = typeOf(el);
  const takesValue = (tag === 'input' && !NO_VALUE.includes(type)) || tag === 'textarea' || tag === 'select';
  elements.push({index, role: well(roleOf(el)), name: nameOf(el), href: tag === 'a' ? cut(el.href, 2000) : null, tag, type: well(type),
    autocomplete: well(autocompleteOf(el)), value: takesValue ? cut(el.value || '', 200) : null, form: formId,
    label_form: idOf(control ? formOf(control) : null), disabled: !!el.disabled});
});
return JSON.stringify({url: cut(location.href, 4000), title: cut(document.title, 400),
  text: cut(document.body ? document.body.innerText : '', 20000), elements: elements.slice(0, 300),
  forms: Array.from(forms.entries()).map(([form, id]) => ({id, text: cut(form.innerText || '', 6000), ...formRecord(form)})),
  cancelled: takeCancelled()});
"""

#: Arguments: index, expect, tokens, nonce, approved.  Resolve once, check,
#: hit-test, keep the handle and arm the click guard for it; an approved step
#: may let one payment-form submit through until ``STEP_END_SCRIPT`` (#698).
LOCATE_SCRIPT = PRELUDE + r"""
const el = document.querySelectorAll(SELECTOR)[index];
if (!el) return JSON.stringify({error: 'target_missing'});
if (!same(describe(el, tokens), expect)) return JSON.stringify({error: 'target_changed'});
el.scrollIntoView({block: 'center', inline: 'center'});
const rect = el.getBoundingClientRect();
const top = Math.max(rect.top, 0), bottom = Math.min(rect.bottom, window.innerHeight);
const left = Math.max(rect.left, 0), right = Math.min(rect.right, window.innerWidth);
if (right - left < 1 || bottom - top < 1) return JSON.stringify({error: 'target_hidden'});
const x = (left + right) / 2, y = (top + bottom) / 2;
const hit = document.elementFromPoint(x, y);
if (!hit || !(hit === el || el.contains(hit) || hit.control === el)) return JSON.stringify({error: 'target_obscured'});
const s = state();
s.targets.clear();
s.targets.set(nonce, new WeakRef(el));
s.guard = {nonce, bad: false};
if (!s.listening) {
  // A trusted click that lands anywhere but the held element is cancelled.
  window.addEventListener('click', (event) => {
    const g = state().guard; if (!g || !event.isTrusted) return;
    const ref = state().targets.get(g.nonce), target = ref && ref.deref();
    if (!target || !(event.target === target || target.contains(event.target) || event.target.control === target)) {
      g.bad = true; event.preventDefault(); event.stopImmediatePropagation();
    }
  }, true);
  s.listening = true;
}
armSubmitGuard();
s.allow = approved === true ? {left: 1} : null;
const tag = el.tagName.toLowerCase();
return JSON.stringify({x, y, editable: el.isContentEditable || tag === 'textarea' ||
  (tag === 'input' && !['submit', 'button', 'image', 'reset', 'checkbox', 'radio', 'file', 'hidden', 'range', 'color'].includes(typeOf(el)))});
"""

#: Arguments: nonce.  Did the press land on the held element?
VERIFY_CLICK_SCRIPT = PRELUDE + r"""
const s = state(), g = s.guard;
s.guard = null;
if (!g || g.nonce !== nonce) return JSON.stringify({error: 'target_changed'});
return JSON.stringify(g.bad ? {error: 'target_changed'} : {ok: true});
"""

#: The end of a click/type step: an approval's allowance ends (the guard is
#: whole again) and a submit the guard cancelled is reported (#698).
STEP_END_SCRIPT = PRELUDE + r"""
state().allow = null;
return JSON.stringify({cancelled: takeCancelled()});
"""

#: Arguments: off.  The owner's login window turns the guard off, and back on.
GUARD_SWITCH_SCRIPT = PRELUDE + r"""
armSubmitGuard();
const s = state();
s.off = off === true;
s.allow = null;
return JSON.stringify({ok: true});
"""


def client_guard_user_script(off=False):
    """Client world, at document start of every main-frame page: the guard is
    registered before any page script can add its own capture listener on
    ``window``, armed (or off while the owner's login window shows)."""
    return ('(() => {\n' + PRELUDE + '\nstate().off = ' + ('true' if off else 'false') +
            ';\narmSubmitGuard();\n})();')


#: Page world, at document start of every main-frame page (#698).
#: ``form.submit()`` fires no ``submit`` event (HTML: the method skips it) and
#: the client world cannot wrap the page's own prototype, so the page's
#: ``HTMLFormElement.prototype.submit`` is wrapped before any page script runs:
#: it dispatches the signal on the form with the ``dispatchEvent``,
#: ``CustomEvent`` and ``defaultPrevented`` captured at that moment, and the
#: client-world guard cancels it for a payment form.  Limits: the prototype of
#: another realm (a new iframe's ``HTMLFormElement.prototype.submit`` called on
#: this page's form) is not wrapped, and a page can detect the wrapper
#: (``toString``); ``fetch``/XHR posts are not form submits at all.
PAGE_WRAP_USER_SCRIPT = r"""(() => {
  const proto = HTMLFormElement.prototype, original = proto.submit;
  if (typeof original !== 'function') return;
  const dispatch = EventTarget.prototype.dispatchEvent, Signal = CustomEvent, apply = Reflect.apply;
  const prevented = Object.getOwnPropertyDescriptor(Event.prototype, 'defaultPrevented').get;
  const submit = function submit() {
    const event = new Signal(%s, {cancelable: true});
    apply(dispatch, this, [event]);
    if (apply(prevented, event, [])) return undefined;
    return apply(original, this, arguments);
  };
  Object.defineProperty(proto, 'submit', {value: submit, writable: true, enumerable: true, configurable: true});
})();""" % json.dumps(SUBMIT_SIGNAL)

#: Arguments: nonce, expect, tokens, text.  The held element must be the
#: focused one and still match the classified descriptor; the text is then
#: inserted in this same turn (no page script runs in between).
INSERT_SCRIPT = PRELUDE + r"""
const s = state(), g = s.guard, ref = s.targets.get(nonce), el = ref && ref.deref();
s.guard = null;
if (!g || g.nonce !== nonce || g.bad) return JSON.stringify({error: 'target_changed'});
if (!el || !el.isConnected || document.activeElement !== el) return JSON.stringify({error: 'target_changed'});
if (!same(describe(el, tokens), expect)) return JSON.stringify({error: 'target_changed'});
if (typeof el.select === 'function') { el.select(); }
else { const range = document.createRange(); range.selectNodeContents(el);
  const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range); }
const done = text ? document.execCommand('insertText', false, text) : document.execCommand('delete', false);
if (!done) return JSON.stringify({error: 'not_typable'});
return JSON.stringify({ok: true});
"""

WIDTH, HEIGHT = 1280, 900
SETTLE_QUIET_SECONDS = 0.4
POLL_SECONDS = 0.05
FOCUS_SECONDS = 0.1
RESOLVE_SECONDS = 3.0


def safari_application_name():
    """``Version/<n> Safari/605.1.15`` from this Mac's Safari, plus the embedded marker.

    WebKit's default user agent lacks the ``Version/... Safari/...`` part and
    some sites refuse it.  The version is read from the installed Safari's
    bundle (a platform fact); without it, the macOS major version (Safari's
    version follows it from macOS 26) or a conservative default is used.
    """
    version = ''
    try:
        with open('/Applications/Safari.app/Contents/Info.plist', 'rb') as handle:
            version = str(plistlib.load(handle).get('CFBundleShortVersionString') or '')
    except (OSError, ValueError, plistlib.InvalidFileException):
        version = ''
    if not version:
        major = (platform.mac_ver()[0] or '').split('.')[0]
        version = f'{major}.0' if major.isdigit() and int(major) >= 26 else '17.0'
    return f'Version/{version} Safari/605.1.15 {EMBEDDED_UA_TOKEN}'


def _host(url):
    try:
        return (urlsplit(str(url or '')).hostname or '').lower()
    except ValueError:
        return ''


def origin_key(url):
    """``host:port`` of an http(s) URL (default ports filled), or ''."""
    try:
        parts = urlsplit(str(url or ''))
        port = parts.port or (443 if parts.scheme == 'https' else 80)
    except ValueError:
        return ''
    host = (parts.hostname or '').lower()
    return f'{host}:{port}' if host and parts.scheme in ('http', 'https') else ''


def local_host(host):
    """True when ``host`` names this computer or a private network by name or literal address.

    Reuses the public-page guard's tables (``local_tools``): the denied names
    (localhost, metadata hosts), suffixes (``.localhost``, ``.local``,
    ``.internal``, ``.home.arpa``) and the private/loopback/link-local/
    reserved/multicast address check.
    """
    from .local_tools import DENIED_PUBLIC_HOST_SUFFIXES, DENIED_PUBLIC_HOSTS, _denied_address
    host = str(host or '').strip('[]').casefold().rstrip('.')
    if not host or host in DENIED_PUBLIC_HOSTS or host.endswith(DENIED_PUBLIC_HOST_SUFFIXES):
        return True
    try:
        return _denied_address(ipaddress.ip_address(host.split('%')[0]))
    except ValueError:
        return False


def local_url(url, allowed_origins=()):
    """True when an http(s) ``url`` names a local/private host (no DNS); False for anything allowed."""
    key = origin_key(url)
    if key and key in set(allowed_origins or ()):
        return False
    try:
        parts = urlsplit(str(url or ''))
        host = parts.hostname or ''
    except ValueError:
        return True
    return parts.scheme not in ('http', 'https') or local_host(host)


def destination_refusal(url, allowed_origins=(), resolver=None):
    """None when ``url`` may be loaded, else ``blocked_destination``.

    Only http(s).  The name or literal is checked with ``local_host``; a name
    is then resolved and refused when any address it resolves to is local or
    private (a public name pointing at 127.0.0.1 included).  A resolution
    error is not a refusal (WebKit cannot load it either).
    ``allowed_origins`` is a test-only exact ``host:port`` allowance.
    """
    from .local_tools import _denied_address
    key = origin_key(url)
    if key and key in set(allowed_origins or ()):
        return None
    if local_url(url):
        return 'blocked_destination'
    parts = urlsplit(str(url))
    host = (parts.hostname or '').rstrip('.')
    try:
        ipaddress.ip_address(host)
        return None   # a literal was already checked
    except ValueError:
        pass
    resolver = resolver or socket.getaddrinfo
    try:
        records = resolver(host, parts.port or (443 if parts.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    except (OSError, UnicodeError, ValueError):
        return None
    for record in records or []:
        try:
            address = ipaddress.ip_address(str(record[4][0]).split('%')[0])
        except (ValueError, IndexError, TypeError):
            continue
        if _denied_address(address):
            return 'blocked_destination'
    return None


def site_of(domain, sites):
    """The site (registrable domain from WebKit's data records) a cookie domain belongs to."""
    domain = str(domain or '').lower().lstrip('.')
    for site in sorted(sites, key=len, reverse=True):
        if domain == site or domain.endswith('.' + site):
            return site
    return domain


class Worker:
    """The main-thread state: one hidden window, one web view, one in-memory store."""

    def __init__(self, profile, emit, allowed_origins=()):
        import AppKit
        import Foundation
        import WebKit
        from PyObjCTools import AppHelper
        self.AppKit, self.Foundation, self.WebKit, self.AppHelper = AppKit, Foundation, WebKit, AppHelper
        self.profile, self.emit = profile, emit
        self.allowed_origins = frozenset(allowed_origins)
        self.pending = {}          # op id -> True while the op has not answered
        self.navigation = None     # (id, WKNavigation) the navigate op waits for
        self.blocked = 0           # main-frame navigations refused so far
        self.hosts = set()         # hosts of committed main-frame navigations in this worker's life
        self.resolved = {}         # url origin -> refusal code or None (this worker's life)
        self.app = AppKit.NSApplication.sharedApplication()
        self.app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)   # no Dock icon
        config = WebKit.WKWebViewConfiguration.alloc().init()
        # In-memory only: WebKit never writes a cookie or storage file.
        self.store = WebKit.WKWebsiteDataStore.nonPersistentDataStore()
        config.setWebsiteDataStore_(self.store)
        config.setApplicationNameForUserAgent_(safari_application_name())
        # The client world: shares the DOM, not the page's JavaScript globals, so a
        # page cannot replace the functions these scripts call.  (A named world
        # stopped answering after repeated password-form pages on macOS 26.)
        self.world = WebKit.WKContentWorld.defaultClientWorld()
        # Only the ``form.submit()`` wrapper runs in the page world (#698).
        self.page_world = WebKit.WKContentWorld.pageWorld()
        delegate_class = _delegate_class()
        self.delegate = delegate_class.alloc().init()
        self.delegate.worker = self
        # The submit guard (#698): document-start scripts, and the client-world
        # handler a cancelled submit is reported through (never the page world).
        self.guard_off = False
        self.cancelled = None      # the last cancelled submit not yet reported
        self.reported = []         # ids of cancelled submits already reported
        self.controller = config.userContentController()
        self._install_guard_scripts()
        self.controller.addScriptMessageHandler_contentWorld_name_(self.delegate, self.world, GUARD_HANDLER)
        self.view = WebKit.WKWebView.alloc().initWithFrame_configuration_(Foundation.NSMakeRect(0, 0, WIDTH, HEIGHT), config)
        self.view.setNavigationDelegate_(self.delegate)
        self.view.setUIDelegate_(self.delegate)
        style = (AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable |
                 AppKit.NSWindowStyleMaskMiniaturizable | AppKit.NSWindowStyleMaskResizable)
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            Foundation.NSMakeRect(0, 0, WIDTH, HEIGHT), style, AppKit.NSBackingStoreBuffered, False)
        self.window.setContentView_(self.view)
        self.window.setReleasedWhenClosed_(False)
        self.window.setDelegate_(self.delegate)
        self.window.setTitle_('AgentOS')

    # -- plumbing ------------------------------------------------------------
    def reply(self, ident, ok=True, **fields):
        self.pending.pop(ident, None)
        self.emit({'id': ident, 'ok': ok, **fields})

    def fail(self, ident, code):
        self.reply(ident, False, error=code)

    def deadline(self, ident, seconds, on_timeout=None):
        """Answer ``timeout`` if the op is still pending when its deadline passes."""
        def expire():
            if ident in self.pending:
                if on_timeout is not None:
                    try:
                        on_timeout()
                    except Exception:
                        pass
                self.fail(ident, 'timeout')
        self.pending[ident] = True
        self.AppHelper.callLater(max(0.5, float(seconds)), expire)

    def run(self, body, arguments, done, world=None):
        """Run ``body`` (returns a JSON string) in the client world (or ``world``); ``done(value_or_None, error_or_None)``."""
        def handler(result, error):
            if error is not None:
                done(None, 'script_failed')
                return
            try:
                done(json.loads(str(result)) if result is not None else None, None)
            except (TypeError, ValueError, UnicodeError):
                done(None, 'script_failed')
        self.view.callAsyncJavaScript_arguments_inFrame_inContentWorld_completionHandler_(
            body, arguments or {}, None, world or self.world, handler)

    def settle(self, ident, finish):
        """Wait until no navigation is loading for a short quiet period, then ``finish``."""
        quiet_since = [None]

        def poll():
            if ident not in self.pending:
                return
            if self.view.isLoading():
                quiet_since[0] = None
            elif quiet_since[0] is None:
                quiet_since[0] = time.monotonic()
            elif time.monotonic() - quiet_since[0] >= SETTLE_QUIET_SECONDS:
                finish()
                return
            self.AppHelper.callLater(POLL_SECONDS, poll)
        self.AppHelper.callLater(POLL_SECONDS, poll)

    # -- the submit guard (#698) ----------------------------------------------
    def _install_guard_scripts(self):
        """The document-start scripts: the client-world guard (armed, or off while
        the owner's login window shows) and the page-world ``form.submit`` wrapper."""
        WebKit = self.WebKit
        start = WebKit.WKUserScriptInjectionTimeAtDocumentStart
        self.controller.removeAllUserScripts()
        for source, world in ((client_guard_user_script(self.guard_off), self.world),
                              (PAGE_WRAP_USER_SCRIPT, self.page_world)):
            self.controller.addUserScript_(
                WebKit.WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_inContentWorld_(
                    source, start, True, world))

    def set_guard_off(self, off):
        """The owner's login window: the guard is off while it shows, for this page and the next ones."""
        self.guard_off = bool(off)
        self._install_guard_scripts()
        self.run(GUARD_SWITCH_SCRIPT, {'off': self.guard_off}, lambda *_: None)

    def receive_cancelled(self, record):
        """A cancelled submit, reported by the client-world guard (message handler or a script result)."""
        record = _form_record(record)
        if record is not None and record['id'] not in self.reported:
            self.cancelled = record

    def take_cancelled(self, record=None):
        """The cancelled submit not yet reported, once; ``record`` is one a script just read."""
        if record is not None:
            self.receive_cancelled(record)
        found, self.cancelled = self.cancelled, None
        if found is None:
            return None
        self.reported = (self.reported + [found['id']])[-64:]
        return {key: found[key] for key in ('dom', 'method', 'action')}

    def end_step(self, done=None):
        """End a click/type step: the approval's allowance ends; ``done(cancelled record or None)``.

        A script error (the page navigated away) reads nothing from the page;
        a submit that page's guard cancelled still arrived through the handler.
        """
        def ended(value, error):
            record = value.get('cancelled') if error is None and isinstance(value, dict) else None
            if record is not None:
                self.receive_cancelled(record)
            if done is not None:
                done(self.take_cancelled())
        self.run(STEP_END_SCRIPT, {}, ended)

    def finish_input(self, ident, blocked_before=None, error=None):
        """Answer a click/type once its approval's allowance ended.

        A payment-form submit the guard cancelled answers ``approval_required``
        with its form (#698), before any other error; then ``error``; then a
        navigation the step caused that was blocked.
        """
        def answer(cancelled):
            if ident not in self.pending:
                if cancelled is not None:
                    self.cancelled = {**cancelled, 'id': uuid.uuid4().hex}   # reported by the next snapshot
                return
            if cancelled is not None:
                return self.reply(ident, False, error='approval_required', form=cancelled)
            if error:
                return self.fail(ident, error)
            if blocked_before is not None and self.blocked > blocked_before:
                return self.fail(ident, 'blocked_destination')
            self.reply(ident)
        self.end_step(answer)

    # -- destinations ----------------------------------------------------------
    def decide(self, url, main_frame, decision):
        """Allow or refuse one navigation; ``decision(bool)`` may be called later (after DNS)."""
        scheme = str(urlsplit(url).scheme or '').lower() if url else ''
        if scheme == 'about' and url in ('about:blank', 'about:srcdoc'):
            return decision(True)
        if scheme in ('data', 'blob') and not main_frame:
            return decision(True)
        if scheme not in ('http', 'https'):
            return decision(False)
        key = origin_key(url)
        if key in self.resolved:
            return decision(self.resolved[key] is None)
        answered = []

        def answer(refusal):
            if answered:
                return
            answered.append(True)
            self.resolved[key] = refusal
            decision(refusal is None)

        def resolve():
            try:
                refusal = destination_refusal(url, self.allowed_origins)
            except Exception:
                refusal = 'blocked_destination'
            self.AppHelper.callAfter(answer, refusal)
        threading.Thread(target=resolve, name='agentos-browser-resolve', daemon=True).start()
        # A resolver that does not answer in time is a refusal (never a guess).
        self.AppHelper.callLater(RESOLVE_SECONDS, lambda: answered or answer('blocked_destination'))

    def navigation_refused(self, main_frame):
        if not main_frame:
            return
        self.blocked += 1
        if self.navigation is not None:
            ident, _ = self.navigation
            self.navigation = None
            if ident in self.pending:
                self.fail(ident, 'blocked_destination')

    # -- native input --------------------------------------------------------
    def press(self, x, y):
        """A native left click at viewport point (x, y): trusted, never needs the window shown."""
        AppKit, Foundation = self.AppKit, self.Foundation
        height = self.view.frame().size.height
        point = Foundation.NSMakePoint(float(x), float(height) - float(y))
        for kind, send in ((AppKit.NSEventTypeLeftMouseDown, self.view.mouseDown_),
                           (AppKit.NSEventTypeLeftMouseUp, self.view.mouseUp_)):
            event = AppKit.NSEvent.mouseEventWithType_location_modifierFlags_timestamp_windowNumber_context_eventNumber_clickCount_pressure_(
                kind, point, 0, AppKit.NSProcessInfo.processInfo().systemUptime(), self.window.windowNumber(), None, 0, 1, 1.0)
            send(event)

    # -- ops -----------------------------------------------------------------
    def handle(self, command):
        ident = command.get('id')
        op = command.get('op')
        timeout = command.get('timeout') or 20
        try:
            method = getattr(self, 'op_' + str(op), None)
            if method is None:
                return self.fail(ident, 'unknown_op')
            method(ident, command, timeout)
        except Exception:
            self.fail(ident, 'worker_error')

    def op_navigate(self, ident, command, timeout):
        url = str(command.get('url') or '')
        if urlsplit(url).scheme not in ('http', 'https'):
            return self.fail(ident, 'bad_url')
        request = self.Foundation.NSURLRequest.requestWithURL_(self.Foundation.NSURL.URLWithString_(url))
        self.deadline(ident, timeout, on_timeout=self.view.stopLoading)
        self.navigation = (ident, None)
        navigation = self.view.loadRequest_(request)
        if self.navigation is not None and self.navigation[0] == ident:
            self.navigation = (ident, navigation)

    def navigation_finished(self, navigation, error=None):
        """Answer the navigate op only for the navigation it started (P3)."""
        if self.navigation is None:
            return
        ident, expected = self.navigation
        if expected is None or navigation is None or not (navigation is expected or navigation.isEqual_(expected)):
            return
        self.navigation = None
        if ident not in self.pending:
            return
        if error is not None:
            return self.fail(ident, 'navigation_failed')
        self.reply(ident, url=str(self.view.URL().absoluteString()) if self.view.URL() else '')

    def op_snapshot(self, ident, command, timeout):
        self.deadline(ident, timeout)

        def done(value, error):
            if ident not in self.pending:
                return
            if error or not isinstance(value, dict):
                return self.fail(ident, error or 'script_failed')
            # A payment-form submit cancelled since the last report (#698).
            cancelled = self.take_cancelled(value.pop('cancelled', None))
            if cancelled is not None:
                value['cancelled_submit'] = cancelled
            self.reply(ident, page=value)
        self.run(SNAPSHOT_SCRIPT, {}, done)

    def _locate(self, ident, command, then):
        index = command.get('index')
        expect = command.get('expect')
        tokens = [str(token) for token in command.get('tokens') or [] if isinstance(token, str)]
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            return self.fail(ident, 'bad_target')
        if not isinstance(expect, dict):
            return self.fail(ident, 'target_changed')   # never press an element nobody classified
        nonce = uuid.uuid4().hex
        # Only a step the parent consumed an owner approval for may let one
        # payment-form submit through (#698).
        approved = command.get('approved') is True

        def located(value, error):
            if ident not in self.pending:
                return
            if error or not isinstance(value, dict):
                return self.finish_input(ident, error=error or 'script_failed')
            if value.get('error'):
                return self.finish_input(ident, error=value['error'])
            then(value, nonce, expect, tokens)
        self.run(LOCATE_SCRIPT, {'index': index, 'expect': expect, 'tokens': tokens, 'nonce': nonce,
                                 'approved': approved}, located)

    def op_click(self, ident, command, timeout):
        self.deadline(ident, timeout, on_timeout=self.end_step)

        def click(point, nonce, expect, tokens):
            blocked_before = self.blocked
            self.press(point['x'], point['y'])

            def verified(value, error):
                if ident not in self.pending:
                    return
                if error is None and isinstance(value, dict) and value.get('error'):
                    return self.finish_input(ident, blocked_before, value['error'])
                # A script error here means the click already navigated away (the
                # page and its guards are gone), which the guards allowed.
                self.settle(ident, lambda: self.finish_input(ident, blocked_before))
            self.run(VERIFY_CLICK_SCRIPT, {'nonce': nonce}, verified)
        self._locate(ident, command, click)

    def op_type(self, ident, command, timeout):
        text = command.get('text')
        if not isinstance(text, str):
            return self.fail(ident, 'bad_text')
        self.deadline(ident, timeout, on_timeout=self.end_step)

        def focus(point, nonce, expect, tokens):
            if not point.get('editable'):
                return self.finish_input(ident, error='not_typable')
            blocked_before = self.blocked
            self.press(point['x'], point['y'])

            def inserted(value, error):
                if ident not in self.pending:
                    return
                if error or not isinstance(value, dict):
                    return self.finish_input(ident, blocked_before, error or 'script_failed')
                if value.get('error'):
                    return self.finish_input(ident, blocked_before, value['error'])
                self.settle(ident, lambda: self.finish_input(ident, blocked_before))
            self.AppHelper.callLater(FOCUS_SECONDS, lambda: self.run(
                INSERT_SCRIPT, {'nonce': nonce, 'expect': expect, 'tokens': tokens, 'text': text}, inserted))
        self._locate(ident, command, focus)

    def op_show(self, ident, command, timeout):
        url = command.get('url')
        # The owner signs in by hand: the guard is off while the window shows (#698).
        self.set_guard_off(True)
        self.window.center()
        self.window.makeKeyAndOrderFront_(None)
        self.app.activateIgnoringOtherApps_(True)
        if url:
            return self.op_navigate(ident, command, timeout)
        self.reply(ident)

    def op_hide(self, ident, command, timeout):
        self.window.orderOut_(None)
        self.set_guard_off(False)
        self.reply(ident)

    def window_closed_by_owner(self):
        self.window.orderOut_(None)
        self.set_guard_off(False)
        self.emit({'event': 'hidden'})

    def op_state(self, ident, command, timeout):
        self.reply(ident, visible=bool(self.window.isVisible()))

    def _all_types(self):
        return self.WebKit.WKWebsiteDataStore.allWebsiteDataTypes()

    def _records(self, types, done):
        self.store.fetchDataRecordsOfTypes_completionHandler_(types, lambda records: done(list(records or [])))

    def op_cookies_export(self, ident, command, timeout):
        """Every cookie of the in-memory store, grouped by WebKit's per-site record name."""
        self.deadline(ident, timeout)

        def with_records(records):
            sites = {str(record.displayName()).lower() for record in records if record.displayName()}

            def with_cookies(cookies):
                if ident not in self.pending:
                    return
                grouped = {}
                for cookie in cookies or []:
                    row = _cookie_row(cookie)
                    grouped.setdefault(site_of(row['domain'], sites), []).append(row)
                self.reply(ident, sites=grouped, hosts=sorted(self.hosts))
            self.store.httpCookieStore().getAllCookies_(with_cookies)
        self._records(self.Foundation.NSSet.setWithObject_(self.WebKit.WKWebsiteDataTypeCookies), with_records)

    def op_cookies_import(self, ident, command, timeout):
        rows = [row for row in command.get('cookies') or [] if isinstance(row, dict)]
        self.deadline(ident, timeout)
        cookies = [cookie for cookie in (_cookie_object(self.Foundation, row) for row in rows) if cookie is not None]
        if not cookies:
            return self.reply(ident, imported=0)
        remaining = [len(cookies)]

        def one_done():
            remaining[0] -= 1
            if remaining[0] == 0 and ident in self.pending:
                self.reply(ident, imported=len(cookies))
        store = self.store.httpCookieStore()
        for cookie in cookies:
            store.setCookie_completionHandler_(cookie, one_done)

    def op_cookies_delete(self, ident, command, timeout):
        """Remove every kind of website data of one site (WebKit's own per-site records), then any cookie of it."""
        site = str(command.get('site') or '').lower()
        if not site:
            return self.fail(ident, 'bad_site')
        self.deadline(ident, timeout)
        types = self._all_types()

        def with_records(records):
            matched = [record for record in records if str(record.displayName() or '').lower() == site]

            def then_cookies():
                def with_cookies(cookies):
                    hits = [cookie for cookie in cookies or [] if site_of(str(cookie.domain()), {site}) == site]
                    if not hits:
                        return self.reply(ident, deleted=len(matched))
                    remaining = [len(hits)]

                    def one_done():
                        remaining[0] -= 1
                        if remaining[0] == 0 and ident in self.pending:
                            self.reply(ident, deleted=len(matched) + len(hits))
                    for cookie in hits:
                        self.store.httpCookieStore().deleteCookie_completionHandler_(cookie, one_done)
                self.store.httpCookieStore().getAllCookies_(with_cookies)
            if matched:
                self.store.removeDataOfTypes_forDataRecords_completionHandler_(types, matched, then_cookies)
            else:
                then_cookies()
        self._records(types, with_records)

    def op_cookies_clear(self, ident, command, timeout):
        self.deadline(ident, timeout)
        self.store.removeDataOfTypes_modifiedSince_completionHandler_(
            self._all_types(), self.Foundation.NSDate.distantPast(), lambda: self.reply(ident))

    def op_quit(self, ident, command, timeout):
        self.reply(ident)
        self.AppHelper.stopEventLoop()


def _form_record(value):
    """A cancelled submit's form, from page data: ``{id, dom, method, action}`` of bounded plain values, or None."""
    try:
        get = value.get if isinstance(value, dict) else value.objectForKey_
        dom, method, action, ident = get('dom'), get('method'), get('action'), get('id')
        return {'id': str(ident or '')[:64] or uuid.uuid4().hex, 'dom': int(dom) if dom is not None else -1,
                'method': str(method or '')[:16], 'action': str(action or '')[:2000]}
    except Exception:
        return None


def _cookie_row(cookie):
    expires = cookie.expiresDate()
    same_site = None
    try:
        same_site = cookie.sameSitePolicy()
    except AttributeError:
        same_site = None
    return {'name': str(cookie.name()), 'value': str(cookie.value()), 'domain': str(cookie.domain()),
            'path': str(cookie.path() or '/'), 'expires': float(expires.timeIntervalSince1970()) if expires is not None else None,
            'secure': bool(cookie.isSecure()), 'http_only': bool(cookie.isHTTPOnly()),
            'same_site': str(same_site) if same_site else None}


def _cookie_object(Foundation, row):
    """An ``NSHTTPCookie`` from a jar row, or None when the row is unusable or expired."""
    try:
        name, value, domain = str(row['name']), str(row['value']), str(row['domain'])
    except (KeyError, TypeError):
        return None
    expires = row.get('expires')
    if isinstance(expires, (int, float)) and expires <= time.time():
        return None
    properties = {Foundation.NSHTTPCookieName: name, Foundation.NSHTTPCookieValue: value,
                  Foundation.NSHTTPCookieDomain: domain, Foundation.NSHTTPCookiePath: str(row.get('path') or '/')}
    if isinstance(expires, (int, float)):
        properties[Foundation.NSHTTPCookieExpires] = Foundation.NSDate.dateWithTimeIntervalSince1970_(float(expires))
    if row.get('secure'):
        properties[Foundation.NSHTTPCookieSecure] = 'TRUE'
    if row.get('http_only'):
        properties['HttpOnly'] = 'TRUE'
    if row.get('same_site') and hasattr(Foundation, 'NSHTTPCookieSameSitePolicy'):
        properties[Foundation.NSHTTPCookieSameSitePolicy] = str(row['same_site'])
    return Foundation.NSHTTPCookie.cookieWithProperties_(properties)


_DELEGATE = []


def _delegate_class():
    """The navigation/UI/window delegate, defined once per process (Objective-C classes are global)."""
    if _DELEGATE:
        return _DELEGATE[0]
    import Foundation
    import WebKit
    import objc

    class AgentOSBrowserDelegate(Foundation.NSObject, protocols=[objc.protocolNamed('WKScriptMessageHandler')]):
        worker = objc.ivar()

        def userContentController_didReceiveScriptMessage_(self, controller, message):
            # Registered for the client world only: the page world cannot post here (#698).
            try:
                self.worker.receive_cancelled(message.body())
            except Exception:
                pass

        def webView_decidePolicyForNavigationAction_decisionHandler_(self, view, action, handler):
            # Every navigation: typed, redirect, form, window.open, frame.
            worker = self.worker
            request = action.request()
            url = str(request.URL().absoluteString()) if request is not None and request.URL() is not None else ''
            frame = action.targetFrame()
            main_frame = frame is None or bool(frame.isMainFrame())

            def decision(allowed):
                handler(WebKit.WKNavigationActionPolicyAllow if allowed else WebKit.WKNavigationActionPolicyCancel)
                if not allowed:
                    worker.navigation_refused(main_frame)
            worker.decide(url, main_frame, decision)

        def webView_didCommitNavigation_(self, view, navigation):
            url = view.URL()
            host = _host(url.absoluteString()) if url is not None else ''
            if host:
                self.worker.hosts.add(host)
                # The owner sees which host a login window shows (no address bar).
                scheme = str(url.scheme() or '')
                self.worker.window.setTitle_(f'AgentOS · {scheme}://{host}')

        def webView_didFinishNavigation_(self, view, navigation):
            self.worker.navigation_finished(navigation)

        def webView_didFailNavigation_withError_(self, view, navigation, error):
            self.worker.navigation_finished(navigation, error)

        def webView_didFailProvisionalNavigation_withError_(self, view, navigation, error):
            self.worker.navigation_finished(navigation, error)

        def webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_(self, view, config, action, features):
            # A link that asks for a new window opens in this one: one page, one
            # session.  The load still passes the navigation policy above; only
            # http(s) is handed to it at all.
            request = action.request()
            url = request.URL() if request is not None else None
            if url is not None and str(url.scheme() or '').lower() in ('http', 'https'):
                view.loadRequest_(request)
            return None

        def windowShouldClose_(self, window):
            # Closing the login window hides it; the parent then exports the session.
            self.worker.window_closed_by_owner()
            return False

    _DELEGATE.append(AgentOSBrowserDelegate)
    return AgentOSBrowserDelegate


def make_emit(stream):
    """A line writer that can never raise: ASCII JSON, and an encoding failure becomes an error reply."""
    lock = threading.Lock()

    def emit(message):
        try:
            line = json.dumps(message, ensure_ascii=True)
        except (TypeError, ValueError):
            line = json.dumps({'id': message.get('id') if isinstance(message, dict) else None, 'ok': False,
                               'error': 'encode_failed'}) if isinstance(message, dict) and 'id' in message else None
        if line is None:
            return
        with lock:
            try:
                stream.write(line + '\n')
                stream.flush()
            except (OSError, ValueError):
                pass
    return emit


def main(argv=None):
    parser = argparse.ArgumentParser(prog='personal_agent.browser_worker')
    parser.add_argument('--profile', default='default')
    # Test-only: an exact fixture origin (host:port) the destination policy
    # allows.  Only a test constructor passes it; no config or environment does.
    parser.add_argument('--test-allow-origin', action='append', default=[])
    args = parser.parse_args(argv)
    emit = make_emit(sys.stdout)
    if sys.platform != 'darwin':
        emit({'event': 'unavailable', 'error': 'unsupported_platform'})
        return 2
    try:
        from PyObjCTools import AppHelper
    except ImportError:
        emit({'event': 'unavailable', 'error': 'missing_dependency'})
        return 2
    state = {}

    def setup():
        try:
            state['worker'] = Worker(args.profile, emit, allowed_origins=args.test_allow_origin)
        except Exception:
            emit({'event': 'unavailable', 'error': 'webkit_failed'})
            AppHelper.stopEventLoop()
            return
        emit({'event': 'ready', 'profile': args.profile, 'pid': os.getpid()})

    def dispatch(command):
        worker = state.get('worker')
        if worker is None:
            emit({'id': command.get('id'), 'ok': False, 'error': 'not_ready'})
            return
        worker.handle(command)

    def reader():
        for line in sys.stdin:
            try:
                command = json.loads(line)
            except ValueError:
                continue
            if isinstance(command, dict):
                AppHelper.callAfter(dispatch, command)   # every WebKit call hops to the main thread
        # The parent went away: never outlive it.
        AppHelper.callAfter(AppHelper.stopEventLoop)

    AppHelper.callAfter(setup)
    threading.Thread(target=reader, name='agentos-browser-worker-reader', daemon=True).start()
    AppHelper.runEventLoop(installInterrupt=False)
    return 0


if __name__ == '__main__':
    sys.exit(main())
