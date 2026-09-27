"""Browser action capability inside an owner-logged-in profile (SEC-BROWSER-01 #656, SEC-BROWSER-02 #680).

The owner logs in once, by hand, in a window of the embedded macOS system
WebKit engine that AgentOS opens (no browser install, #680).  The model then
opens, reads, finds, clicks and types on pages in that profile through five
generic tools.  Two boundaries are enforced here, deterministically and
independently of anything the model says (pilot posture, #653):

* **Output mediation.**  Nothing leaves ``PageDriver.snapshot`` before
  ``mediate_snapshot``: values of ``password`` inputs and of fields whose
  ``autocomplete`` names a credential, one-time code or card field are
  dropped; the existing saved-private-value matcher of public lookups
  (``lookup_text_violations``, #605) and the CLI prompt secret pattern redact
  page text; the raw DOM, cookies,
  ``localStorage`` and storage state have no accessor at all.
* **Payment guard.**  Typing into a card-number, CVC, card-expiry, one-time
  code or password field, and pressing a button of a form that contains such
  a field, need an owner approval bound to (Work, action, page URL digest,
  target element) and verified at execution.  The model's ``effect`` label can
  only add a requirement (``payment`` always needs approval), never remove one.

Engine (#680): ``WebKitWorkerDriver`` drives ``personal_agent.browser_worker``,
a subprocess that owns the Cocoa run loop and a ``WKWebView`` with an
in-memory website data store.  Sign-in cookies live only in that memory and
in the encrypted jar (``browser_jar``) whose key is in the macOS Keychain.
The capability is macOS-only during the pilot; elsewhere, or without PyObjC,
it is reported unavailable (``browser_unavailable_platform``) with no
fallback engine.

Reuse: Apple's WebKit through PyObjC (MIT) for the commodity browser
mechanics; ``cryptography`` Fernet (as ``EncryptedCalendarSecretStore``) and
the macOS Keychain for the jar; ``ToolError``, the Work budget, the lookup
redactor and the exact-approval binding are the existing AgentOS symbols.  No
site, provider or category is named anywhere in this module.
"""
import hashlib
import importlib.util
import itertools
import json
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .agent_runtime import BROWSER_ACTIONS, ToolError, lookup_norm, lookup_text_violations, lookup_words
from .bounded_execution import SECRET_PATTERN
from .browser_jar import JAR_NAME, SERVICE as JAR_SERVICE, CookieJar, KeychainKey, store_account

#: The model's declared effect class of one action.
EFFECTS = ('read', 'navigate', 'mutate', 'payment')
#: Field ``autocomplete`` tokens whose values never reach the model or Evidence.
GUARDED_AUTOCOMPLETE = frozenset({'current-password', 'new-password', 'one-time-code', 'cc-number', 'cc-csc',
                                  'cc-exp', 'cc-exp-month', 'cc-exp-year', 'cc-name'})
#: Fields where typing (and any button of the enclosing form) needs approval.
PAYMENT_AUTOCOMPLETE = frozenset({'cc-number', 'cc-csc', 'cc-exp', 'cc-exp-month', 'cc-exp-year', 'one-time-code'})
#: Actions the loop never memoises or deduplicates: the page is state.
STATEFUL_ACTIONS = BROWSER_ACTIONS

TEXT_LIMIT = 6000
ELEMENT_LIMIT = 80
NAME_LIMIT = 120
VALUE_LIMIT = 200
FIND_LINES = 12
STEPS_PER_WORK = 12
ACTION_TIMEOUT_SECONDS = 20
LOGIN_WINDOW_SECONDS = 1800
REDACTED = '[가림]'

APPROVAL_TEXT = '결제 단계는 승인이 필요합니다. 소유자가 이 단계를 승인하면 이 요청을 한 번만 이어서 처리합니다.'
LOGIN_REQUIRED_TEXT = '이 페이지는 로그인이 필요합니다. 설정의 브라우저 로그인 세션에서 "로그인 창 열기"로 먼저 로그인해 주세요. AgentOS는 비밀번호를 입력하지 않습니다.'
STEP_BUDGET_TEXT = f'이 작업의 브라우저 단계 한도({STEPS_PER_WORK}회)에 도달해 더 실행하지 않았습니다.'
TIMEOUT_TEXT = '브라우저 동작이 시간 안에 끝나지 않았습니다.'
FAILED_TEXT = '브라우저 동작을 실행하지 못했습니다.'
BUSY_TEXT = '브라우저 프로필을 다른 작업 또는 로그인 창이 사용하고 있어 지금은 실행하지 않았습니다.'
NO_PAGE_TEXT = '열린 페이지가 없습니다. 먼저 browser_open으로 페이지를 여세요.'
UNAVAILABLE_TEXT = '이 작업 경로에는 브라우저 기능이 연결되어 있지 않습니다.'
LOGIN_WINDOW_TEXT = ('로그인 창에서 직접 로그인한 뒤 창을 닫아 주세요. AgentOS는 입력 내용을 보지 않으며, 창을 닫으면 '
                     '로그인 세션을 암호화해 저장합니다.')
LIMITATION_TEXT = ('카드번호·CVC·일회용 코드 입력과 그 양식의 버튼은 승인 없이 실행하지 않습니다. '
                   '저장된 결제수단으로 카드 입력 없이 결제되는 사이트의 결제 버튼은 감지하지 못하므로, '
                   '결제수단을 연결하지 않은 계정에서만 사용하세요.')


# --- element classification (deterministic, site-independent) ---------------

def autocomplete_field(value):
    """The field-name token of an HTML ``autocomplete`` attribute.

    The attribute is a token list (HTML Living Standard, "autofill detail
    tokens"): an optional ``section-*`` token, an optional ``shipping`` or
    ``billing`` token, an optional contact token (``home``/``work``/``mobile``/
    ``fax``/``pager``), the field name, and an optional trailing ``webauthn``.
    The field name is therefore the last token once ``webauthn`` is removed:
    ``section-checkout billing cc-number`` is ``cc-number``.
    """
    tokens = str(value or '').strip().lower().split()
    if tokens and tokens[-1] == 'webauthn':
        tokens = tokens[:-1]
    return tokens[-1] if tokens else ''


def _autocomplete(element):
    return autocomplete_field(element.get('autocomplete'))


def guarded_field(element):
    """A field whose value is session or credential material: never returned."""
    return element.get('type') == 'password' or _autocomplete(element) in GUARDED_AUTOCOMPLETE


def payment_field(element):
    """A field typing into which needs the owner's per-step approval."""
    return element.get('type') == 'password' or _autocomplete(element) in PAYMENT_AUTOCOMPLETE


def button_like(element):
    return element.get('role') == 'button' or element.get('tag') == 'button'


def payment_forms(elements):
    """Ids of the forms that contain a payment/credential field."""
    return {element.get('form') for element in elements if element.get('form') is not None and payment_field(element)}


def guarded_submit(element, elements):
    """A button of a form that contains a payment/credential field."""
    return button_like(element) and element.get('form') is not None and element['form'] in payment_forms(elements)


USERNAME_TYPES = frozenset({'text', 'email', 'tel', ''})


def login_form_present(elements, redirected=False):
    """Generic login detection: a password field asking for the current password.

    True when a ``password`` input (not ``new-password``) sits in a form that
    also has a username-like text/email/tel field, or when the navigation was
    redirected to a page with such a password field.  A change-password form
    or a lone password field on an account page is not a login wall.  No
    site, path or wording is consulted.
    """
    for element in elements:
        if element.get('type') != 'password' or _autocomplete(element) == 'new-password':
            continue
        if redirected:
            return True
        form = element.get('form')
        if form is None:
            continue
        if any(other is not element and other.get('form') == form and other.get('tag') == 'input'
               and str(other.get('type') or '').lower() in USERNAME_TYPES for other in elements):
            return True
    return False


def target_key(element):
    """The stable descriptor an approval is bound to (not the list number, which shifts)."""
    return '|'.join(str(element.get(key) or '') for key in ('role', 'name', 'tag', 'type', 'autocomplete', 'form'))


def digest(text):
    return hashlib.sha256(str(text or '').encode()).hexdigest()


def _host(parts):
    """``host[:port]`` of a split URL, without any userinfo."""
    try:
        host, port = parts.hostname or '', parts.port
    except ValueError:
        host, port = parts.hostname or '', None
    if ':' in host:
        host = f'[{host}]'
    return f'{host}:{port}' if port else host


def page_reference(url):
    """A URL without userinfo, query and fragment: what Evidence and approvals may carry."""
    try:
        parts = urlsplit(str(url or ''))
    except ValueError:
        return ''
    return urlunsplit((parts.scheme, _host(parts), parts.path, '', ''))


#: Binding fields, in order.  ``argument_digest`` is the normalized step
#: argument (the typed text, the clicked target, the opened URL) and
#: ``state_digest`` the relevant current page state, so an approval never
#: covers different text or a changed form (price, quantity, terms).
BINDING_FIELDS = ('work_id', 'action', 'page_digest', 'target_digest', 'argument_digest', 'state_digest')


def step_binding(work_id, action, url, element_key, argument='', state=''):
    """What one approval is bound to: Work, action, page, target, arguments and page state."""
    return {'work_id': work_id, 'action': action, 'page_digest': digest(page_reference(url)),
            'target_digest': digest(element_key), 'argument_digest': digest(argument), 'state_digest': digest(state)}


def binding_digest(binding):
    return digest('|'.join(str(binding.get(key) or '') for key in BINDING_FIELDS))


# --- output mediation --------------------------------------------------------

def redact_private_values(text, excluded=()):
    """Redact tokens of ``text`` that match a saved or withheld private value.

    The matcher is the existing #605 lookup check (``lookup_text_violations``,
    kept by #654): whole values, contained spans, jamo keys and digit runs.  It is applied
    per line, so its rule "a matching digit run withholds every digit-bearing
    token" stays on the line that carries the value instead of blanking every
    number on the page.  Returns ``(text, redacted_count)``.  A page with
    nothing to compare against is returned unchanged.
    """
    text = str(text or '')
    excluded = [value for value in excluded if isinstance(value, str) and value.strip()]
    if not text or not excluded:
        return text, 0
    lines = []
    removed = 0
    for line in text.split('\n'):
        bad, digits_joined = lookup_text_violations(line, excluded) if line.strip() else (set(), False)
        if not bad and not digits_joined:
            lines.append(line)
            continue
        out = []
        for token in re.split(r'(\s+)', line):
            if not token or token.isspace():
                out.append(token)
                continue
            if any(word in bad for word in lookup_words(token)) or (digits_joined and re.search(r'\d', lookup_norm(token))):
                out.append(REDACTED)
                removed += 1
            else:
                out.append(token)
        lines.append(''.join(out))
    return '\n'.join(lines), removed


def scrub(text, excluded=()):
    """Redact saved private values, then credential-shaped tokens (the CLI prompt pattern)."""
    text, removed = redact_private_values(text, excluded)
    text, count = SECRET_PATTERN.subn(REDACTED, text)
    return text, removed + count


def mediate_url(url, excluded=()):
    """A model-visible URL: no userinfo, query or fragment; each path segment scrubbed.

    Returns ``(url, redacted_count)``.  A path segment that carries a saved
    private value or a credential-shaped token is replaced as a whole.
    """
    try:
        parts = urlsplit(str(url or ''))
    except ValueError:
        return '', 0
    removed = 0
    host, count = scrub(_host(parts), excluded)
    removed += count
    segments = []
    for segment in parts.path.split('/'):
        cleaned, count = scrub(segment, excluded)
        if count:
            removed += count
            cleaned = REDACTED
        segments.append(cleaned)
    return urlunsplit((parts.scheme, host, '/'.join(segments), '', '')), removed


def mediate_snapshot(raw, excluded=(), requested_url=None):
    """The only page state that may leave the driver.

    ``raw`` is a ``PageDriver.snapshot`` result.  Guarded field values are
    dropped, text and names are bounded and redacted, and the model sees a
    numbered element list ``{n, role, name, href?, value?}``.  The internal
    descriptor of each element stays in ``_elements`` for target resolution
    and the payment guard; it is never returned to the model.
    """
    raw = raw if isinstance(raw, dict) else {}
    elements = [element for element in (raw.get('elements') or []) if isinstance(element, dict)]
    text, redacted = scrub(str(raw.get('text') or '')[:TEXT_LIMIT * 2], excluded)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    truncated = len(text) > TEXT_LIMIT
    text = text[:TEXT_LIMIT]
    redirected = bool(requested_url) and page_reference(requested_url) != page_reference(raw.get('url'))
    login_required = login_form_present(elements, redirected)
    visible = []
    internal = []
    for element in elements:
        if element.get('disabled'):
            continue
        name, count = scrub(str(element.get('name') or '')[:NAME_LIMIT], excluded)
        redacted += count
        row = {'n': len(visible) + 1, 'role': str(element.get('role') or element.get('tag') or 'element'), 'name': name}
        if element.get('href'):
            href, count = mediate_url(element['href'], excluded)
            redacted += count
            row['href'] = href[:400]
        if not guarded_field(element) and isinstance(element.get('value'), str) and element['value']:
            value, count = scrub(element['value'][:VALUE_LIMIT], excluded)
            redacted += count
            row['value'] = value
        visible.append(row)
        internal.append({**{key: element.get(key) for key in ('index', 'role', 'name', 'tag', 'type', 'autocomplete', 'form')},
                         'n': row['n'], 'guarded': guarded_field(element), 'payment': payment_field(element)})
        if len(visible) >= ELEMENT_LIMIT:
            break
    for row in internal:
        row['submit_guarded'] = guarded_submit(row, elements)
    url, count = mediate_url(raw.get('url'), excluded)
    redacted += count
    title, count = scrub(str(raw.get('title') or '')[:200], excluded)
    redacted += count
    snapshot = {'url': url, 'title': title, 'text': text,
                'elements': visible, 'login_required': login_required, 'truncated': truncated,
                'redacted_values': redacted}
    snapshot['_elements'] = internal
    # Internal only (never returned): the unmediated page reference the
    # approval binds to, and the page state a guarded step is bound to.
    snapshot['_page'] = page_reference(raw.get('url'))
    snapshot['_states'] = page_states(raw, elements, text, excluded)
    return snapshot


def page_states(raw, elements, text, excluded=()):
    """``{form id: state, None: page state}`` a guarded step's approval is bound to.

    A form's state is its mediated visible text (price, quantity, terms) and
    the mediated values of its non-guarded fields; guarded values (card, code,
    password) are never part of it.  A target outside any form is bound to the
    mediated page text.
    """
    forms = {}
    for form in raw.get('forms') or []:
        if isinstance(form, dict) and form.get('id') is not None:
            forms[form['id']] = scrub(str(form.get('text') or '')[:TEXT_LIMIT], excluded)[0]
    states = {None: text}
    for form_id in {element.get('form') for element in elements if element.get('form') is not None}:
        values = sorted((target_key(element), scrub(str(element.get('value') or ''), excluded)[0])
                        for element in elements if element.get('form') == form_id and not guarded_field(element))
        states[form_id] = forms.get(form_id, '') + '\n' + '\n'.join(f'{key}={value}' for key, value in values)
    return states


def public_view(snapshot):
    """The model-facing dict: everything but the internal element descriptors."""
    return {key: value for key, value in snapshot.items() if not key.startswith('_')}


def resolve_target(snapshot, target):
    """The internal element ``target`` names: its list number or a visible-name match."""
    rows = snapshot.get('_elements') or []
    wanted = ' '.join(str(target or '').split())
    if not wanted:
        raise ToolError('target을 입력하세요: 요소 번호 또는 보이는 이름입니다.', 'target_not_found')
    if wanted.isdigit():
        number = int(wanted)
        for row in rows:
            if row['n'] == number:
                return row
        raise ToolError(f'요소 번호 {number}은(는) 현재 페이지 목록에 없습니다. browser_read로 목록을 다시 확인하세요.', 'target_not_found')
    key = wanted.casefold()
    exact = [row for row in rows if ' '.join(str(row.get('name') or '').split()).casefold() == key]
    if len(exact) == 1:
        return exact[0]
    partial = exact or [row for row in rows if key in ' '.join(str(row.get('name') or '').split()).casefold()]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise ToolError('일치하는 요소가 없습니다. browser_read의 요소 목록에 있는 번호나 이름을 사용하세요.', 'target_not_found')
    raise ToolError('여러 요소가 일치합니다: ' + ', '.join(f"{row['n']}" for row in partial[:8]) + '. 요소 번호로 지정하세요.',
                    'ambiguous_target')


def find_in_snapshot(snapshot, text):
    """Visible-text lines and elements containing ``text`` (case-insensitive)."""
    wanted = ' '.join(str(text or '').split()).casefold()
    if not wanted:
        raise ValueError('찾을 텍스트를 입력하세요.')
    lines = [line.strip() for line in str(snapshot.get('text') or '').splitlines() if wanted in line.casefold()]
    elements = [row for row in snapshot.get('elements') or [] if wanted in str(row.get('name') or '').casefold()]
    return {'url': snapshot.get('url'), 'query': text, 'lines': lines[:FIND_LINES], 'elements': elements[:FIND_LINES],
            'found': bool(lines or elements)}


# --- the session one Work drives ---------------------------------------------

class NoApprovals:
    """No owner approval surface: every guarded step is refused."""

    def consume(self, binding):
        return False

    def request(self, binding, description):
        return None


class BrowserSession:
    """One Work's page state over an injectable ``PageDriver``.

    ``driver_factory`` returns the driver on first use (the engine is started
    only when a browser tool actually runs); ``budget`` is the Work's shared
    ``WorkBudget``; ``excluded`` returns the private values to redact;
    ``approvals`` has ``consume(binding)`` and ``request(binding, text)``.
    """

    def __init__(self, driver_factory, *, work_id, budget=None, excluded=None, approvals=None,
                 steps=STEPS_PER_WORK, action_seconds=ACTION_TIMEOUT_SECONDS):
        self._factory = driver_factory
        self.driver = None
        self.work_id = work_id
        self.budget = budget
        self.excluded = excluded
        self.approvals = approvals or NoApprovals()
        self.steps, self.steps_used = steps, 0
        self.action_seconds = action_seconds
        self.last = None

    # -- plumbing --
    def _driver(self):
        if self.driver is None:
            try:
                self.driver = self._factory()
            except ToolError:
                raise
            except Exception as exc:
                raise ToolError(FAILED_TEXT, 'browser_failed') from exc
            if self.driver is None:
                raise ToolError(UNAVAILABLE_TEXT, 'needs_setup', requires='browser-profile')
        return self.driver

    def _timeout(self):
        seconds = self.action_seconds
        if self.budget is not None:
            try:
                seconds = min(seconds, self.budget.remaining())
            except Exception:
                pass
        return max(1.0, float(seconds))

    def _spend_step(self):
        if self.budget is not None:
            self.budget.check()
        if self.steps_used >= self.steps:
            raise ToolError(STEP_BUDGET_TEXT, 'browser_step_budget')
        self.steps_used += 1

    def _call(self, operation, *args):
        try:
            return operation(*args, self._timeout())
        except ToolError:
            raise
        except TimeoutError as exc:
            raise ToolError(TIMEOUT_TEXT, 'browser_timeout') from exc
        except Exception as exc:
            raise ToolError(FAILED_TEXT, 'browser_failed') from exc

    def _snapshot(self, requested_url=None):
        excluded = ()
        if self.excluded is not None:
            try:
                excluded = list(self.excluded())
            except Exception:
                excluded = ()
        raw = self._call(lambda timeout: self._driver().snapshot())
        self.last = mediate_snapshot(raw, excluded, requested_url)
        return self.last

    def _page_state(self, requested_url=None):
        snapshot = self._snapshot(requested_url)
        if snapshot['login_required']:
            # Generic (`login_form_present`): the profile holds no session for
            # this page.  Nothing else of the page is returned.
            return {'state': 'login_required', 'url': snapshot['url'], 'title': snapshot['title'],
                    'needs_setup': True, 'requires': 'browser-login', 'next_step': LOGIN_REQUIRED_TEXT}
        return {'state': 'page', **public_view(snapshot)}

    @staticmethod
    def _effect(args):
        effect = str(args.get('effect') or '').strip().lower()
        if effect not in EFFECTS:
            raise ValueError('effect는 read, navigate, mutate, payment 중 하나여야 합니다.')
        return effect

    def _guard(self, action, url, element_key, description, effect, deterministic, argument='', state=''):
        """Refuse a guarded step unless an exact owner approval is consumed now.

        ``deterministic`` is AgentOS's own classification of the target; the
        model's ``effect`` label is consulted only to ADD the requirement.
        The approval is bound to the step's arguments and the current page
        state too, so different text or a changed form asks again.
        """
        if not (deterministic or effect == 'payment'):
            return
        binding = step_binding(self.work_id, action, url, element_key, argument, state)
        if self.approvals.consume(binding):
            return
        try:
            self.approvals.request(binding, description)
        except Exception:
            pass
        raise ToolError(APPROVAL_TEXT, 'approval_required', requires='browser-step-approval')

    # -- the tools --
    def run(self, action, args):
        if action == 'browser_open':
            return self.open(args)
        if action == 'browser_read':
            return self.read()
        if action == 'browser_find':
            return self.find(args)
        if action == 'browser_click':
            return self.click(args)
        if action == 'browser_type':
            return self.type(args)
        raise ValueError('허용하지 않은 도구입니다.')

    def open(self, args):
        effect = self._effect(args)
        url = str(args.get('url') or '').strip()
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.netloc:
            raise ValueError('http 또는 https 주소만 열 수 있습니다.')
        self._spend_step()
        self._guard('browser_open', url, url, f'{_host(parts)} 페이지 열기', effect, False, argument=url)
        self._call(lambda timeout: self._driver().goto(url, timeout))
        return self._page_state(requested_url=url)

    def read(self):
        self._require_page()
        self._spend_step()
        return self._page_state()

    def find(self, args):
        self._require_page()
        self._spend_step()
        snapshot = self._snapshot()
        return find_in_snapshot(snapshot, args.get('text'))

    def click(self, args):
        effect = self._effect(args)
        self._require_page()
        self._spend_step()
        snapshot = self._snapshot()
        element = resolve_target(snapshot, args.get('target'))
        key = target_key(element)
        self._guard('browser_click', snapshot['_page'], key,
                    f"'{element.get('name') or element.get('role')}' 버튼 누르기", effect, element['submit_guarded'],
                    argument=key, state=self._state_of(snapshot, element))
        self._call(lambda timeout: self._driver().click(element['index'], timeout))
        return self._page_state()

    def type(self, args):
        effect = self._effect(args)
        self._require_page()
        text = str(args.get('text') or '')
        if len(text) > 2000:
            raise ValueError('입력 텍스트는 2000자 이하여야 합니다.')
        self._spend_step()
        snapshot = self._snapshot()
        element = resolve_target(snapshot, args.get('target'))
        self._guard('browser_type', snapshot['_page'], target_key(element),
                    f"'{element.get('name') or element.get('role')}' 입력란에 입력", effect, element['payment'],
                    argument=text, state=self._state_of(snapshot, element))
        self._call(lambda timeout: self._driver().type(element['index'], text, timeout))
        return self._page_state()

    @staticmethod
    def _state_of(snapshot, element):
        states = snapshot.get('_states') or {}
        return states.get(element.get('form'), states.get(None, ''))

    def _require_page(self):
        if self.driver is None or self.last is None:
            raise ToolError(NO_PAGE_TEXT, 'no_page')

    def close(self):
        driver, self.driver = self.driver, None
        if driver is not None:
            try:
                driver.close()
            except Exception:
                pass


# --- the embedded engine (SEC-BROWSER-02 #680) ----------------------------------

#: The typed refusal when this computer cannot run the embedded engine.
UNAVAILABLE_CODE = 'browser_unavailable_platform'
PLATFORM_TEXT = ('브라우저 기능은 시범 기간 동안 macOS에서만 제공됩니다. 이 컴퓨터에서는 브라우저가 필요한 단계를 '
                 '실행하지 않습니다.')
DEPENDENCY_TEXT = ('macOS 시스템 WebKit 연결 구성요소(pyobjc-framework-WebKit)가 없어 브라우저 기능을 사용할 수 '
                   '없습니다. AgentOS를 다시 설치한 뒤 다시 시작하세요.')
GOOGLE_NOTE = 'Google 로그인은 내장 브라우저에서 지원되지 않습니다.'
TARGET_TEXT = ('대상 요소가 바뀌었거나 다른 요소에 가려져 있어 실행하지 않았습니다. browser_read로 페이지를 다시 '
               '확인하세요.')
#: Worker error codes that mean "the element the guard classified is not what the pointer would hit".
TARGET_ERRORS = frozenset({'target_missing', 'target_changed', 'target_hidden', 'target_obscured', 'not_typable',
                           'not_focusable', 'bad_target'})
WORKER_START_SECONDS = 30
WORKER_GRACE_SECONDS = 5
WORKER_QUIT_SECONDS = 5
LOGIN_OPEN_SECONDS = 45
LOGIN_SAVE_SECONDS = 15


def webkit_unavailable_reason(platform=None, find_spec=None):
    """None when the embedded macOS WebKit engine can run here, else ``platform`` or ``dependency``.

    Only the presence of the PyObjC modules is checked; nothing is imported
    into the server process (AppKit belongs to the worker's main thread).
    """
    platform = sys.platform if platform is None else platform
    find_spec = importlib.util.find_spec if find_spec is None else find_spec
    if platform != 'darwin':
        return 'platform'
    for module in ('objc', 'AppKit', 'WebKit', 'PyObjCTools'):
        try:
            if find_spec(module) is None:
                return 'dependency'
        except (ImportError, ValueError):
            return 'dependency'
    return None


def unavailable_text(reason):
    return DEPENDENCY_TEXT if reason == 'dependency' else PLATFORM_TEXT


class WorkerError(RuntimeError):
    """A worker op failed; ``code`` is the worker's AgentOS code, never library or page text."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


class WebKitWorkerDriver:
    """The real ``PageDriver``: the embedded WebKit worker process (``browser_worker``).

    The worker owns its own main thread and Cocoa run loop; this object owns
    the subprocess and speaks its JSON-lines protocol.  Every request carries
    a timeout the worker enforces, and this side waits that long plus a grace
    period before it kills an unresponsive worker.  A worker that exited or
    was killed is restarted on the next call, with the jar's cookies imported
    again (``seed``); the page it had open is gone, so the next target
    lookup fails typed rather than acting on a different page.

    Clicks and typing carry the descriptor (tag, type, autocomplete) of the
    element the last snapshot listed at that index, so the worker refuses to
    press a different element than the one the payment guard classified.
    Nothing here returns HTML, and cookie rows go only to the jar.  The
    worker's stderr is discarded so no library trace can carry page or
    session text into a log.
    """

    def __init__(self, profile_id='default', *, seed=None, command=None, start_seconds=WORKER_START_SECONDS,
                 grace_seconds=WORKER_GRACE_SECONDS):
        self.profile_id = str(profile_id)
        self._seed = seed
        self._command = list(command) if command else [sys.executable, '-m', 'personal_agent.browser_worker',
                                                       '--profile', self.profile_id]
        self.start_seconds, self.grace_seconds = start_seconds, grace_seconds
        self._lock = threading.RLock()
        self._proc = None
        self._queue = None
        self._ids = itertools.count(1)
        self._visible = False
        self._expect = {}
        self.starts = 0
        with self._lock:
            self._start()

    @property
    def restarts(self):
        return max(0, self.starts - 1)

    # -- process ---------------------------------------------------------------
    def _start(self):
        self.starts += 1
        proc = subprocess.Popen(self._command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, encoding='utf-8', bufsize=1, close_fds=True)
        messages = queue.Queue()

        def read():
            try:
                for line in proc.stdout:
                    try:
                        message = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(message, dict):
                        continue
                    if message.get('event') == 'hidden':
                        self._visible = False
                        continue
                    messages.put(message)
            except (OSError, ValueError):
                pass
            messages.put(None)
        threading.Thread(target=read, name='agentos-browser-worker-pipe', daemon=True).start()
        self._proc, self._queue, self._visible, self._expect = proc, messages, False, {}
        deadline = time.monotonic() + self.start_seconds
        while True:
            try:
                message = messages.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                message = None
            if message is None or message.get('event') == 'unavailable':
                self._kill()
                raise WorkerError('worker_unavailable')
            if message.get('event') == 'ready':
                break
        rows = []
        if self._seed is not None:
            try:
                rows = list(self._seed() or [])
            except Exception:
                rows = []
        if rows:
            self._send('cookies_import', ACTION_TIMEOUT_SECONDS, cookies=rows)

    def _kill(self):
        proc, self._proc = self._proc, None
        self._visible = False
        if proc is None:
            return
        try:
            proc.kill()
            proc.wait(WORKER_QUIT_SECONDS)
        except Exception:
            pass
        for stream in (proc.stdin, proc.stdout):
            try:
                stream.close()
            except Exception:
                pass

    def alive(self):
        return self._proc is not None and self._proc.poll() is None

    def _send(self, op, timeout, **arguments):
        proc, messages = self._proc, self._queue
        ident = next(self._ids)
        timeout = max(1.0, float(timeout))
        try:
            proc.stdin.write(json.dumps({'id': ident, 'op': op, 'timeout': timeout, **arguments}, ensure_ascii=False) + '\n')
            proc.stdin.flush()
        except (OSError, ValueError, AttributeError):
            self._kill()
            raise WorkerError('worker_exited') from None
        deadline = time.monotonic() + timeout + self.grace_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                # Unresponsive: kill it; the next call starts a fresh worker.
                self._kill()
                raise TimeoutError('browser timeout')
            try:
                message = messages.get(timeout=remaining)
            except queue.Empty:
                continue
            if message is None:
                self._kill()
                raise WorkerError('worker_exited')
            if message.get('id') != ident:
                continue
            if message.get('ok'):
                return message
            code = str(message.get('error') or 'worker_error')
            if code == 'timeout':
                raise TimeoutError('browser timeout')
            if code in TARGET_ERRORS:
                raise ToolError(TARGET_TEXT, 'target_unavailable')
            raise WorkerError(code)

    def _request(self, op, timeout, **arguments):
        with self._lock:
            if not self.alive():
                self._kill()
                self._start()   # restart after a crash, with the jar's cookies
            return self._send(op, timeout, **arguments)

    # -- PageDriver ------------------------------------------------------------
    def goto(self, url, timeout):
        self._request('navigate', timeout, url=url)

    def snapshot(self):
        page = self._request('snapshot', ACTION_TIMEOUT_SECONDS).get('page') or {}
        self._expect = {element['index']: {key: str(element.get(key) or '') for key in ('tag', 'type', 'autocomplete')}
                        for element in page.get('elements') or []
                        if isinstance(element, dict) and isinstance(element.get('index'), int)}
        return page

    def click(self, index, timeout):
        self._request('click', timeout, index=index, expect=self._expect.get(index))

    def type(self, index, text, timeout):
        self._request('type', timeout, index=index, text=text, expect=self._expect.get(index))

    # -- the owner's login window ---------------------------------------------------
    def show(self, url, timeout):
        self._request('show', timeout, url=url)
        self._visible = True

    def hide(self):
        self._request('hide', ACTION_TIMEOUT_SECONDS)
        self._visible = False

    def is_open(self):
        return self.alive() and self._visible

    # -- session material: to and from the encrypted jar only ------------------------
    def cookies_export(self):
        """``({site: [cookie rows]}, [hosts opened])``: for ``CookieJar.save_export`` only."""
        message = self._request('cookies_export', ACTION_TIMEOUT_SECONDS)
        sites = message.get('sites') if isinstance(message.get('sites'), dict) else {}
        return sites, [host for host in message.get('hosts') or [] if isinstance(host, str)]

    def cookies_import(self, rows):
        return self._request('cookies_import', ACTION_TIMEOUT_SECONDS, cookies=list(rows or [])).get('imported', 0)

    def cookies_delete(self, site):
        return self._request('cookies_delete', ACTION_TIMEOUT_SECONDS, site=site).get('deleted', 0)

    def cookies_clear(self):
        self._request('cookies_clear', ACTION_TIMEOUT_SECONDS)

    def close(self):
        with self._lock:
            if self.alive():
                try:
                    self._send('quit', WORKER_QUIT_SECONDS)
                    self._proc.wait(WORKER_QUIT_SECONDS)
                except Exception:
                    pass
            self._kill()


# --- the profile the execution environment owns --------------------------------

class BrowserProfile:
    """The one browser profile: who may hold it now, its encrypted sessions and the login window.

    One Work session or the owner's login window holds the profile at a time
    (one non-blocking lock), so two workers never race to save the jar.
    ``launcher`` is injectable (``(profile_dir, headless) -> PageDriver``);
    the default starts the embedded WebKit worker with the jar's cookies.
    When a driver closes, its cookies are exported into the jar first.
    ``profile_dir`` (under ``store.private``) holds only the encrypted jar.
    """

    def __init__(self, profile_dir, *, launcher=None, headless=True, available=None, clock=time.time, jar=None):
        self.profile_dir = Path(profile_dir)
        self.jar = jar if jar is not None else CookieJar(self.profile_dir / JAR_NAME,
                                                         KeychainKey(store_account(self.profile_dir)), clock)
        self.launcher = launcher or self._launch_webkit
        self.headless = headless
        self._available = available if available is not None else (
            (lambda: webkit_unavailable_reason() is None) if launcher is None else (lambda: True))
        self.clock = clock
        self._lock = threading.Lock()
        self._jar_lock = threading.RLock()
        self._holder = None
        self._live = None
        self._suppressed = set()
        self._login_thread = None

    def _launch_webkit(self, profile_dir, headless):
        return WebKitWorkerDriver(self.profile_dir.name, seed=self.jar.cookies)

    def available(self):
        try:
            return bool(self._available())
        except Exception:
            return False

    def unavailable_reason(self):
        """None, or ``platform`` / ``dependency`` (the typed refusal ``browser_unavailable_platform``)."""
        if self.available():
            return None
        return webkit_unavailable_reason() or 'platform'

    def unavailable_message(self):
        reason = self.unavailable_reason()
        return unavailable_text(reason) if reason else None

    def status(self):
        reason = self.unavailable_reason()
        status = {'available': reason is None, 'unavailable_reason': reason, 'engine': 'macos-webkit',
                  'message': unavailable_text(reason) if reason else None,
                  'login_window_open': self._holder == 'login', 'in_use': self._holder is not None and self._holder != 'login',
                  'limitation': LIMITATION_TEXT, 'google_note': GOOGLE_NOTE, 'sessions': []}
        if reason is None:
            status['storage'] = {'what': 'site-sign-in-cookies', 'path': str(self.jar.path),
                                 'key': getattr(self.jar.key, 'location', 'macos-keychain'), 'key_service': JAR_SERVICE,
                                 'sent_to_ai': False, 'state': self.jar.state()}
            status['sessions'] = self.jar.sites()
        return status

    # -- holding the profile ---------------------------------------------------
    def _acquire(self, holder):
        if not self._lock.acquire(blocking=False):
            raise ToolError(BUSY_TEXT, 'browser_busy')
        self._holder = holder
        self._suppressed = set()

    def _release(self):
        self._holder = None
        self._live = None
        try:
            self._lock.release()
        except RuntimeError:
            pass

    def _save(self, driver):
        """Export the driver's cookies into the jar (never elsewhere).  A failure keeps the old jar."""
        if not hasattr(driver, 'cookies_export'):
            return False
        with self._jar_lock:
            try:
                sites, hosts = driver.cookies_export()
            except Exception:
                return False
            sites = {site: rows for site, rows in sites.items() if site not in self._suppressed}
            try:
                self.jar.save_export(sites, hosts)
            except Exception:
                return False
            return True

    def driver_factory(self, work_id):
        """A zero-argument factory a ``BrowserSession`` calls on first use, or None when unavailable."""
        if not self.available():
            return None
        def launch():
            self._acquire(work_id)
            try:
                self.profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                driver = self.launcher(self.profile_dir, self.headless)
            except Exception:
                self._release()
                raise
            self._live = driver
            return _ReleasingDriver(driver, self._save, self._release)
        return launch

    # -- the owner's sessions (Settings) -------------------------------------------
    def delete_site(self, site):
        """Remove one site's sign-in cookies from the jar and from a running worker."""
        site = str(site or '').strip().lower()
        if not site:
            raise ValueError('삭제할 사이트를 지정하세요.')
        with self._jar_lock:
            live = self._live
            if live is not None and hasattr(live, 'cookies_delete'):
                try:
                    live.cookies_delete(site)
                except Exception:
                    # The running worker could not drop it: never save it back from this session.
                    self._suppressed.add(site)
            try:
                removed = self.jar.remove(site)
            except Exception:
                raise ValueError('저장된 로그인 세션을 읽지 못했습니다. "모두 삭제"로 초기화할 수 있습니다.') from None
        return {'deleted': bool(removed), 'site': site}

    def delete_all(self):
        """Delete the jar file and its Keychain key, and clear a running worker's store."""
        with self._jar_lock:
            live = self._live
            if live is not None and hasattr(live, 'cookies_clear'):
                try:
                    live.cookies_clear()
                except Exception:
                    self._suppressed |= {row['site'] for row in self.jar.sites()}
            existed = self.jar.clear()
        return {'deleted': existed, 'all': True}

    # -- the owner's login window ------------------------------------------------------
    def open_for_login(self, url, wait=False):
        """Show the worker window at ``url`` for the owner to log in by hand.

        AgentOS navigates to ``url`` and does nothing else: no typing, no
        reading.  The window's title shows the host it is on.  Cookies are
        exported into the encrypted jar while it is open and when the owner
        closes it (or after ``LOGIN_WINDOW_SECONDS``).
        """
        if not self.available():
            return {'state': 'unavailable', 'reason': self.unavailable_reason(), 'message': self.unavailable_message()}
        parts = urlsplit(str(url or ''))
        if parts.scheme not in ('http', 'https') or not parts.netloc:
            raise ValueError('http 또는 https 주소를 입력하세요.')
        try:
            self._acquire('login')
        except ToolError:
            return {'state': 'busy', 'message': BUSY_TEXT}
        opened = threading.Event()
        failure = []
        def window():
            driver = None
            try:
                self.profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                driver = self.launcher(self.profile_dir, False)
                self._live = driver
                show = getattr(driver, 'show', None)
                if show is not None:
                    show(url, LOGIN_OPEN_SECONDS)
                else:
                    driver.goto(url, ACTION_TIMEOUT_SECONDS)
                opened.set()
                deadline = self.clock() + LOGIN_WINDOW_SECONDS
                saved = self.clock()
                while driver.is_open() and self.clock() < deadline:
                    time.sleep(0.5)
                    if self.clock() - saved >= LOGIN_SAVE_SECONDS:
                        self._save(driver)
                        saved = self.clock()
            except Exception as exc:
                failure.append(type(exc).__name__)
            finally:
                if driver is not None:
                    self._save(driver)
                    try:
                        driver.close()
                    except Exception:
                        pass
                self._release()
                opened.set()
        self._login_thread = threading.Thread(target=window, name='agentos-browser-login', daemon=True)
        self._login_thread.start()
        if wait:
            self._login_thread.join()
        else:
            opened.wait(LOGIN_OPEN_SECONDS + WORKER_START_SECONDS + 5)
        if failure:
            return {'state': 'failed', 'message': FAILED_TEXT}
        return {'state': 'closed' if wait else 'opened', 'url': page_reference(url), 'message': LOGIN_WINDOW_TEXT}


class _ReleasingDriver:
    """A driver whose ``close`` saves its cookies to the jar, closes it, and releases the profile (once)."""

    def __init__(self, driver, save, release):
        self._driver, self._save, self._release = driver, save, release

    def __getattr__(self, name):
        return getattr(self._driver, name)

    def close(self):
        save, self._save = self._save, lambda driver: None
        try:
            save(self._driver)
        finally:
            try:
                self._driver.close()
            finally:
                release, self._release = self._release, lambda: None
                release()
