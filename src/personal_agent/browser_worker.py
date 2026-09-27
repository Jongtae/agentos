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

Submit guard (#698): a click or type the parent sends without ``approved``
arms, from ``LOCATE`` to the step's answer, a capture-phase ``submit``
listener (registered at document start in the client world) that cancels a
submit of any form holding a card, CVC, card-expiry, one-time-code or password
field, whatever triggered it (a label forwarding a press, a scripted click,
``requestSubmit``).  ``form.submit()`` fires no ``submit`` event, so for the
step ``HTMLFormElement.prototype.submit`` is wrapped in the page world to
signal the same listener; a page script holding the original function is not
covered (see ``SUBMIT_WRAP_SCRIPT``).  A cancelled submit answers
``approval_required``.

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
  submit: null, submitListening: false});
// The submit guard (#698): while a step without an approval runs (``state().submit``),
// a submit of a form holding a payment field (any field, shown or not) is cancelled
// whatever triggered it: a trusted or scripted click, a label, ``requestSubmit``,
// Enter, or ``form.submit()`` through the page-world signal (``SUBMIT_WRAP_SCRIPT``).
const holdsPayment = (form, tokens) => [...Array.from(form.elements || []), ...Array.from(form.querySelectorAll(SELECTOR))]
  .some((field) => paymentField(field, tokens));
const armSubmitGuard = () => { const s = state(); if (s.submitListening) return; s.submitListening = true;
  const cancel = (event) => { const g = state().submit; if (!g) return;
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !holdsPayment(form, g.tokens)) return;
    g.hit = true; event.preventDefault(); event.stopImmediatePropagation(); };
  window.addEventListener('submit', cancel, true);
  window.addEventListener(%(signal)s, cancel, true); };
""" % {'selector': json.dumps(SELECTOR), 'signal': json.dumps(SUBMIT_SIGNAL)}

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
  forms: Array.from(forms.entries()).map(([form, id]) => ({id, text: cut(form.innerText || '', 6000)}))});
"""

#: Arguments: index, expect, tokens, nonce, approved.  Resolve once, check,
#: hit-test, keep the handle and arm the click guard for it; without an
#: approval, also arm the submit guard until ``DISARM_SCRIPT`` (#698).
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
s.submit = approved === true ? null : {tokens, hit: false};
const tag = el.tagName.toLowerCase();
return JSON.stringify({x, y, editable: el.isContentEditable || tag === 'textarea' ||
  (tag === 'input' && !['submit', 'button', 'image', 'reset', 'checkbox', 'radio', 'file', 'hidden', 'range', 'color'].includes(typeOf(el)))});
"""

#: Arguments: nonce.  Did the press land on the held element?  (The submit
#: guard stays armed; ``submit`` reports a submit it cancelled so far.)
VERIFY_CLICK_SCRIPT = PRELUDE + r"""
const s = state(), g = s.guard, submit = !!(s.submit && s.submit.hit);
s.guard = null;
if (!g || g.nonce !== nonce) return JSON.stringify({error: 'target_changed', submit});
return JSON.stringify(g.bad ? {error: 'target_changed', submit} : {ok: true, submit});
"""

#: The end of a click/type step: disarm the submit guard and report whether it
#: cancelled a submit of a payment form (#698).
DISARM_SCRIPT = PRELUDE + r"""
const s = state(), g = s.submit;
s.submit = null;
return JSON.stringify({submit: !!(g && g.hit)});
"""

#: Page world, for one unapproved step (#698).  ``form.submit()`` fires no
#: ``submit`` event (HTML: the submit() method skips it), and the client world
#: cannot wrap the page's own prototype, so ``HTMLFormElement.prototype.submit``
#: is wrapped in the page world for the step: it dispatches ``signal`` on the
#: form, and the client-world guard cancels it for a payment form.  Limits: a
#: page script that kept the original function before the step, or that
#: replaces ``dispatchEvent``/``CustomEvent``, is not covered; submits through
#: ``requestSubmit``, clicks and labels fire the real ``submit`` event instead.
SUBMIT_WRAP_SCRIPT = r"""
const MARK = Symbol.for('agentos.guarded-submit');
const proto = HTMLFormElement.prototype, current = proto.submit;
if (typeof current !== 'function') return JSON.stringify({error: 'script_failed'});
if (!current[MARK]) {
  const original = current;
  const submit = function submit() {
    const event = new CustomEvent(signal, {cancelable: true});
    this.dispatchEvent(event);
    if (event.defaultPrevented) return undefined;
    return original.apply(this, arguments);
  };
  Object.defineProperty(submit, MARK, {value: original});
  Object.defineProperty(proto, 'submit', {value: submit, writable: true, enumerable: true, configurable: true});
}
return JSON.stringify({ok: true});
"""

#: Page world: put the page's own ``form.submit`` back after the step.
SUBMIT_RESTORE_SCRIPT = r"""
const MARK = Symbol.for('agentos.guarded-submit');
const proto = HTMLFormElement.prototype, current = proto.submit;
if (typeof current === 'function' && current[MARK]) {
  Object.defineProperty(proto, 'submit', {value: current[MARK], writable: true, enumerable: true, configurable: true});
}
return JSON.stringify({ok: true});
"""

#: Client world, at document start of every main-frame page: the submit guard's
#: listeners are registered before any page script can register its own
#: capture listener on ``window`` (they do nothing until a step arms them).
SUBMIT_GUARD_USER_SCRIPT = '(() => {\n' + PRELUDE + '\narmSubmitGuard();\n})();'

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
        # Only the step's ``form.submit()`` wrapper runs in the page world (#698).
        self.page_world = WebKit.WKContentWorld.pageWorld()
        config.userContentController().addUserScript_(
            WebKit.WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_inContentWorld_(
                SUBMIT_GUARD_USER_SCRIPT, WebKit.WKUserScriptInjectionTimeAtDocumentStart, True, self.world))
        self.view =WebKit.WKWebView.alloc().initWithFrame_configuration_(Foundation.NSMakeRect(0, 0, WIDTH, HEIGHT), config)
        delegate_class = _delegate_class()
        self.delegate = delegate_class.alloc().init()
        self.delegate.worker = self
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

    def disarm(self, done=None):
        """End a click/type step: disarm the submit guard, put the page's ``form.submit`` back.

        ``done(submit_cancelled)``.  A script error (the page navigated away)
        reports nothing cancelled: that page and its guard are gone.
        """
        def disarmed(value, error):
            cancelled = error is None and isinstance(value, dict) and value.get('submit') is True
            self.run(SUBMIT_RESTORE_SCRIPT, {}, lambda *_: done and done(cancelled), world=self.page_world)
        self.run(DISARM_SCRIPT, {}, disarmed)

    def finish_input(self, ident, blocked_before=None, error=None, submitted=False):
        """Answer a click/type after disarming its submit guard.

        A payment-form submit the guard cancelled answers ``approval_required``
        (#698), before any other error; then ``error``; then a navigation the
        step caused that was blocked.
        """
        def answer(cancelled):
            if ident not in self.pending:
                return
            if submitted or cancelled:
                return self.fail(ident, 'approval_required')
            if error:
                return self.fail(ident, error)
            if blocked_before is not None and self.blocked > blocked_before:
                return self.fail(ident, 'blocked_destination')
            self.reply(ident)
        self.disarm(answer)

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
        # Only a step the parent consumed an owner approval for may submit a payment form (#698).
        approved = command.get('approved') is True

        def located(value, error):
            if ident not in self.pending:
                return
            if error or not isinstance(value, dict):
                return self.finish_input(ident, error=error or 'script_failed')
            if value.get('error'):
                return self.finish_input(ident, error=value['error'])
            then(value, nonce, expect, tokens)

        def locate():
            self.run(LOCATE_SCRIPT, {'index': index, 'expect': expect, 'tokens': tokens, 'nonce': nonce,
                                     'approved': approved}, located)
        if approved:
            return locate()

        def wrapped(value, error):
            if ident not in self.pending:
                return
            if error or not isinstance(value, dict) or not value.get('ok'):
                # Never press without the guard in place.
                return self.finish_input(ident, error='script_failed')
            locate()
        self.run(SUBMIT_WRAP_SCRIPT, {'signal': SUBMIT_SIGNAL}, wrapped, world=self.page_world)

    def op_click(self, ident, command, timeout):
        self.deadline(ident, timeout, on_timeout=self.disarm)

        def click(point, nonce, expect, tokens):
            blocked_before = self.blocked
            self.press(point['x'], point['y'])

            def verified(value, error):
                if ident not in self.pending:
                    return
                submitted = error is None and isinstance(value, dict) and value.get('submit') is True
                if error is None and isinstance(value, dict) and value.get('error'):
                    return self.finish_input(ident, blocked_before, value['error'], submitted)
                # A script error here means the click already navigated away (the
                # page and its guards are gone), which the guards allowed.
                self.settle(ident, lambda: self.finish_input(ident, blocked_before, submitted=submitted))
            self.run(VERIFY_CLICK_SCRIPT, {'nonce': nonce}, verified)
        self._locate(ident, command, click)

    def op_type(self, ident, command, timeout):
        text = command.get('text')
        if not isinstance(text, str):
            return self.fail(ident, 'bad_text')
        self.deadline(ident, timeout, on_timeout=self.disarm)

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
        self.window.center()
        self.window.makeKeyAndOrderFront_(None)
        self.app.activateIgnoringOtherApps_(True)
        if url:
            return self.op_navigate(ident, command, timeout)
        self.reply(ident)

    def op_hide(self, ident, command, timeout):
        self.window.orderOut_(None)
        self.reply(ident)

    def window_closed_by_owner(self):
        self.window.orderOut_(None)
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

    class AgentOSBrowserDelegate(Foundation.NSObject):
        worker = objc.ivar()

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
