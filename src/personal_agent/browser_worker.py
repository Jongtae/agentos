"""Embedded macOS system WebKit browser worker (SEC-BROWSER-02 #680).

Run as ``python -m personal_agent.browser_worker --profile <id>``.  The worker
owns the process's main thread and the Cocoa run loop (AppKit and WebKit
objects may only be created and used there); a reader thread hands every
command to the main thread with ``AppHelper.callAfter``.  It speaks JSON
lines: one request per stdin line, one response per stdout line.

Request:  ``{"id": 7, "op": "navigate", "timeout": 20, ...arguments}``
Response: ``{"id": 7, "ok": true, ...result}`` or ``{"id": 7, "ok": false, "error": "<code>"}``
Events:   ``{"event": "ready" | "hidden"}`` (no ``id``).

Ops: ``navigate``, ``snapshot``, ``click``, ``type``, ``show``, ``hide``,
``state``, ``cookies_export``, ``cookies_import``, ``cookies_delete``,
``cookies_clear``, ``quit``.  Every op carries a deadline; the worker answers
``timeout`` when it passes.  Errors are AgentOS codes, never library text.

Session material: the web view uses ``WKWebsiteDataStore.nonPersistentDataStore()``
so WebKit keeps cookies in memory only and never writes a cookie file.  The
parent exports cookies over the pipe and keeps them in the encrypted jar
(``browser_jar``); the worker writes nothing to disk and prints nothing but
protocol lines.  Input is native: mouse events and ``insertText:`` at the
element's rectangle, so pages see ``isTrusted`` events, and the element under
the pointer is verified to be the intended target before any click.

Reuse: Apple's WebKit (``WKWebView``) through PyObjC (MIT) is the adopted
engine; ``WKWebsiteDataRecord.displayName`` is WebKit's own per-site
(registrable domain) grouping.  No site, provider or category is named here.
"""
import argparse
import json
import os
import platform
import plistlib
import sys
import threading
import time
from urllib.parse import urlsplit

#: Elements the model can act on and the fields the guard reasons about.  Run
#: in the page; returns plain data only (no node handles, no HTML).  ``index``
#: is the element's position in ``document.querySelectorAll(SELECTOR)``, the
#: same list ``LOCATE_SCRIPT`` resolves a click or typing target in.
SELECTOR = ('a[href], button, input, select, textarea, summary, [role="button"], [role="link"], [role="textbox"], '
            '[role="checkbox"], [role="radio"], [role="combobox"], [role="menuitem"], [role="tab"]')
SNAPSHOT_SCRIPT = r"""
(() => {
  const SELECTOR = %(selector)s;
  const NO_VALUE = ['submit', 'button', 'image', 'reset', 'checkbox', 'radio', 'file', 'password', 'hidden'];
  const forms = new Map();
  const visible = (el) => {
    if (el.type === 'hidden') return false;
    const style = getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 || rect.height > 0;
  };
  const clean = (text) => String(text || '').replace(/\s+/g, ' ').trim().slice(0, 160);
  const nameOf = (el) => {
    const tag = el.tagName.toLowerCase();
    const label = el.getAttribute('aria-label') || (el.labels && el.labels[0] && el.labels[0].innerText) ||
      el.getAttribute('placeholder') || el.getAttribute('title') || el.getAttribute('alt') ||
      ((tag === 'input' && (el.type === 'submit' || el.type === 'button')) ? el.value : '') ||
      el.innerText || el.textContent || (tag === 'input' ? el.name : '') || '';
    return clean(label);
  };
  const roleOf = (el) => {
    const role = el.getAttribute('role');
    if (role) return role;
    const tag = el.tagName.toLowerCase();
    if (tag === 'a') return 'link';
    if (tag === 'button' || tag === 'summary') return 'button';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'input') {
      const type = (el.type || 'text').toLowerCase();
      if (['submit', 'button', 'image', 'reset'].includes(type)) return 'button';
      if (type === 'checkbox' || type === 'radio') return type;
      return 'textbox';
    }
    return tag;
  };
  const elements = [];
  Array.from(document.querySelectorAll(SELECTOR)).forEach((el, index) => {
    if (!visible(el)) return;
    const tag = el.tagName.toLowerCase();
    const form = el.form || el.closest('form');
    let formId = null;
    if (form) { if (!forms.has(form)) forms.set(form, forms.size + 1); formId = forms.get(form); }
    const type = tag === 'input' ? (el.type || 'text').toLowerCase() : (tag === 'button' ? (el.type || 'submit').toLowerCase() : '');
    const takesValue = (tag === 'input' && !NO_VALUE.includes(type)) || tag === 'textarea' || tag === 'select';
    elements.push({index, role: roleOf(el), name: nameOf(el), href: tag === 'a' ? el.href : null, tag, type,
      autocomplete: (el.getAttribute('autocomplete') || '').toLowerCase().trim(),
      value: takesValue ? String(el.value || '').slice(0, 200) : null, form: formId, disabled: !!el.disabled});
  });
  return JSON.stringify({url: location.href, title: document.title, text: (document.body ? document.body.innerText : '').slice(0, 20000),
    elements: elements.slice(0, 300),
    forms: Array.from(forms.entries()).map(([form, id]) => ({id, text: String(form.innerText || '').slice(0, 6000)}))});
})()
""" % {'selector': json.dumps(SELECTOR)}

#: Resolve one target: the element at ``index``, checked against the
#: descriptor the guard classified (tag, type, autocomplete), scrolled into
#: view, and hit-tested so the native pointer lands on that element and not on
#: an overlay.  Returns the viewport point to press, or an error code.
LOCATE_SCRIPT = r"""
((index, expect) => {
  const el = document.querySelectorAll(%(selector)s)[index];
  if (!el) return JSON.stringify({error: 'target_missing'});
  const tag = el.tagName.toLowerCase();
  const type = tag === 'input' ? (el.type || 'text').toLowerCase() : (tag === 'button' ? (el.type || 'submit').toLowerCase() : '');
  const autocomplete = (el.getAttribute('autocomplete') || '').toLowerCase().trim();
  if (expect && (expect.tag !== tag || (expect.type || '') !== type || (expect.autocomplete || '') !== autocomplete)) {
    return JSON.stringify({error: 'target_changed'});
  }
  el.scrollIntoView({block: 'center', inline: 'center'});
  const rect = el.getBoundingClientRect();
  const top = Math.max(rect.top, 0), bottom = Math.min(rect.bottom, window.innerHeight);
  const left = Math.max(rect.left, 0), right = Math.min(rect.right, window.innerWidth);
  if (right - left < 1 || bottom - top < 1) return JSON.stringify({error: 'target_hidden'});
  const x = (left + right) / 2, y = (top + bottom) / 2;
  const hit = document.elementFromPoint(x, y);
  if (!hit || !(hit === el || el.contains(hit) || hit.control === el)) return JSON.stringify({error: 'target_obscured'});
  return JSON.stringify({x, y, tag, editable: el.isContentEditable || tag === 'input' || tag === 'textarea'});
})(%(index)s, %(expect)s)
"""

#: After the trusted click focused the field: make sure the focus is on it and
#: select its current content so the inserted text replaces it (``fill``).
SELECT_SCRIPT = r"""
((index) => {
  const el = document.querySelectorAll(%(selector)s)[index];
  if (!el) return JSON.stringify({error: 'target_missing'});
  if (document.activeElement !== el && !el.contains(document.activeElement)) el.focus();
  if (document.activeElement !== el && !el.contains(document.activeElement)) return JSON.stringify({error: 'not_focusable'});
  if (typeof el.select === 'function') { el.select(); }
  else if (el.isContentEditable) { const range = document.createRange(); range.selectNodeContents(el);
    const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range); }
  return JSON.stringify({ok: true});
})(%(index)s)
"""

WIDTH, HEIGHT = 1280, 900
SETTLE_QUIET_SECONDS = 0.4
POLL_SECONDS = 0.05


def safari_application_name():
    """``Version/<n> Safari/605.1.15`` from this Mac's Safari, for a Safari-form user agent.

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
    return f'Version/{version} Safari/605.1.15'


def _host(url):
    try:
        return (urlsplit(str(url or '')).hostname or '').lower()
    except ValueError:
        return ''


def site_of(domain, sites):
    """The site (registrable domain from WebKit's data records) a cookie domain belongs to."""
    domain = str(domain or '').lower().lstrip('.')
    for site in sorted(sites, key=len, reverse=True):
        if domain == site or domain.endswith('.' + site):
            return site
    return domain


class Worker:
    """The main-thread state: one hidden window, one web view, one in-memory store."""

    def __init__(self, profile, emit):
        import AppKit
        import Foundation
        import WebKit
        from PyObjCTools import AppHelper
        self.AppKit, self.Foundation, self.WebKit, self.AppHelper = AppKit, Foundation, WebKit, AppHelper
        self.profile, self.emit = profile, emit
        self.pending = {}          # op id -> finisher, for ops that complete asynchronously
        self.navigation = None     # (id, WKNavigation) awaiting didFinish
        self.hosts = set()         # hosts of committed main-frame navigations in this worker's life
        self.app = AppKit.NSApplication.sharedApplication()
        self.app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)   # no Dock icon
        config = WebKit.WKWebViewConfiguration.alloc().init()
        # In-memory only: WebKit never writes a cookie or storage file.
        self.store = WebKit.WKWebsiteDataStore.nonPersistentDataStore()
        config.setWebsiteDataStore_(self.store)
        config.setApplicationNameForUserAgent_(safari_application_name())
        self.view = WebKit.WKWebView.alloc().initWithFrame_configuration_(Foundation.NSMakeRect(0, 0, WIDTH, HEIGHT), config)
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

    def evaluate(self, script, done):
        """Evaluate ``script`` (which returns a JSON string); ``done(value_or_None, error_code_or_None)``."""
        def handler(result, error):
            if error is not None:
                done(None, 'script_failed')
                return
            try:
                done(json.loads(str(result)) if result is not None else None, None)
            except (TypeError, ValueError):
                done(None, 'script_failed')
        self.view.evaluateJavaScript_completionHandler_(script, handler)

    def settle(self, ident, finish, started=None):
        """Wait until no navigation is loading for a short quiet period, then ``finish``."""
        started = started or time.monotonic()
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
            if ident in self.pending or ident is not None:
                self.fail(ident, 'worker_error')

    def op_navigate(self, ident, command, timeout):
        url = str(command.get('url') or '')
        if urlsplit(url).scheme not in ('http', 'https'):
            return self.fail(ident, 'bad_url')
        request = self.Foundation.NSURLRequest.requestWithURL_(self.Foundation.NSURL.URLWithString_(url))
        self.deadline(ident, timeout, on_timeout=self.view.stopLoading)
        navigation = self.view.loadRequest_(request)
        self.navigation = (ident, navigation)

    def navigation_finished(self, navigation, error=None):
        if self.navigation is None:
            return
        ident, _ = self.navigation
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
        self.evaluate(SNAPSHOT_SCRIPT, done)

    def _locate(self, ident, command, then):
        index = command.get('index')
        if not isinstance(index, int) or index < 0:
            return self.fail(ident, 'bad_target')
        expect = command.get('expect') if isinstance(command.get('expect'), dict) else None
        script = LOCATE_SCRIPT % {'selector': json.dumps(SELECTOR), 'index': index, 'expect': json.dumps(expect)}

        def located(value, error):
            if ident not in self.pending:
                return
            if error or not isinstance(value, dict):
                return self.fail(ident, error or 'script_failed')
            if value.get('error'):
                return self.fail(ident, value['error'])
            then(value)
        self.evaluate(script, located)

    def op_click(self, ident, command, timeout):
        self.deadline(ident, timeout)

        def click(point):
            started = time.monotonic()
            self.press(point['x'], point['y'])
            self.settle(ident, lambda: self.reply(ident), started)
        self._locate(ident, command, click)

    def op_type(self, ident, command, timeout):
        text = command.get('text')
        if not isinstance(text, str):
            return self.fail(ident, 'bad_text')
        self.deadline(ident, timeout)

        def focus(point):
            if not point.get('editable'):
                return self.fail(ident, 'not_typable')
            self.press(point['x'], point['y'])
            self.AppHelper.callLater(0.1, lambda: self.evaluate(SELECT_SCRIPT % {'selector': json.dumps(SELECTOR),
                                                                                  'index': command['index']}, insert))

        def insert(value, error):
            if ident not in self.pending:
                return
            if error or not isinstance(value, dict) or value.get('error'):
                return self.fail(ident, (value or {}).get('error') if isinstance(value, dict) else (error or 'script_failed'))
            self.window.makeFirstResponder_(self.view)
            if text:
                self.view.insertText_(text)
            else:
                self.view.doCommandBySelector_('deleteBackward:')
            self.settle(ident, lambda: self.reply(ident))
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

    def _records(self, done):
        types = self.Foundation.NSSet.setWithObject_(self.WebKit.WKWebsiteDataTypeCookies)
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
        self._records(with_records)

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
        """Remove one site's data record (WebKit's own per-site grouping) and any cookie of it."""
        site = str(command.get('site') or '').lower()
        if not site:
            return self.fail(ident, 'bad_site')
        self.deadline(ident, timeout)

        def with_records(records):
            matched = [record for record in records if str(record.displayName() or '').lower() == site]
            types = self.Foundation.NSSet.setWithObject_(self.WebKit.WKWebsiteDataTypeCookies)

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
        self._records(with_records)

    def op_cookies_clear(self, ident, command, timeout):
        self.deadline(ident, timeout)
        types = self.WebKit.WKWebsiteDataStore.allWebsiteDataTypes()
        self.store.removeDataOfTypes_modifiedSince_completionHandler_(
            types, self.Foundation.NSDate.distantPast(), lambda: self.reply(ident))

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
    import objc

    class AgentOSBrowserDelegate(Foundation.NSObject):
        worker = objc.ivar()

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
            # A link that asks for a new window opens in this one: one page, one session.
            request = action.request()
            if request is not None:
                view.loadRequest_(request)
            return None

        def windowShouldClose_(self, window):
            # Closing the login window hides it; the parent then exports the session.
            self.worker.window_closed_by_owner()
            return False

    _DELEGATE.append(AgentOSBrowserDelegate)
    return AgentOSBrowserDelegate


def main(argv=None):
    parser = argparse.ArgumentParser(prog='personal_agent.browser_worker')
    parser.add_argument('--profile', default='default')
    args = parser.parse_args(argv)
    if sys.platform != 'darwin':
        sys.stdout.write(json.dumps({'event': 'unavailable', 'error': 'unsupported_platform'}) + '\n')
        return 2
    try:
        from PyObjCTools import AppHelper
    except ImportError:
        sys.stdout.write(json.dumps({'event': 'unavailable', 'error': 'missing_dependency'}) + '\n')
        return 2
    out_lock = threading.Lock()
    stdout = sys.stdout

    def emit(message):
        with out_lock:
            stdout.write(json.dumps(message, ensure_ascii=False) + '\n')
            stdout.flush()

    state = {}

    def setup():
        try:
            state['worker'] = Worker(args.profile, emit)
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
