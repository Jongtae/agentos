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
  code or password field, pressing a button of a form that contains such a
  field, and pressing an element whose ``<label>`` forwards the press to a
  control of such a form, need an owner approval bound to (Work, action, page
  URL digest, target element) and verified at execution.  The model's
  ``effect`` label can only add a requirement (``payment`` always needs
  approval), never remove one.  Every step's approval is bound to the
  target's own form or page state, the state of the form its label forwards
  to, and the state of every payment form on the page, each with that form's
  identity (position, method, action).  The worker also cancels, for a page's
  whole life, any submit of such a form that no approval lets through,
  whatever element, script, timer, callback or native ``submit`` triggered it
  (#698, #700).  An approved step lets only its target's payment form through,
  briefly past the step for that form's deferred submit.  A cancelled submit
  is asked of the owner bound to that form and the digest of what it would
  send (hidden amounts included); once exactly that is approved, the worker
  releases the held submit (``release_submit``).

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
import os
import queue
import shutil
import re
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .agent_runtime import BROWSER_ACTIONS, ToolError, lookup_norm, lookup_text_violations, lookup_words
from .bounded_execution import SECRET_PATTERN
from .browser_jar import JAR_NAME, SERVICE as JAR_SERVICE, CookieJar, JarError, KeychainKey, store_account
from .browser_worker import PAYMENT_TOKENS, SECRET_TOKENS

#: The model's declared effect class of one action.
EFFECTS = ('read', 'navigate', 'mutate', 'payment')
#: Field ``autocomplete`` tokens whose values never reach the model or Evidence.
GUARDED_AUTOCOMPLETE = frozenset(SECRET_TOKENS)   # one set, shared with the worker's submitted-state digest
#: Fields where typing (and any button of the enclosing form) needs approval.
PAYMENT_AUTOCOMPLETE = frozenset(PAYMENT_TOKENS)   # one set, shared with the worker's page-lifetime guard
#: Actions the loop never memoises or deduplicates: the page is state.
STATEFUL_ACTIONS = BROWSER_ACTIONS

TEXT_LIMIT = 6000
ELEMENT_LIMIT = 80
NAME_LIMIT = 120
VALUE_LIMIT = 200
FIND_LINES = 12
STEPS_PER_WORK = 40
ACTION_TIMEOUT_SECONDS = 20
LOGIN_WINDOW_SECONDS = 1800
REDACTED = '[가림]'

CANCELLED_NOTE = '승인 없이 시도된 결제 양식 제출을 멈췄습니다'
APPROVAL_TEXT = '결제 단계는 승인이 필요합니다. 소유자가 이 단계를 승인하면 이 요청을 한 번만 이어서 처리합니다.'
LOGIN_REQUIRED_TEXT = '이 페이지는 로그인이 필요합니다. 설정의 브라우저 로그인 세션에서 "로그인 창 열기"로 먼저 로그인해 주세요. AgentOS는 비밀번호를 입력하지 않습니다.'
STEP_BUDGET_TEXT = f'이 작업의 브라우저 단계 한도({STEPS_PER_WORK}회)에 도달해 더 실행하지 않았습니다.'
TIMEOUT_TEXT = '브라우저 동작이 시간 안에 끝나지 않았습니다.'
FAILED_TEXT = '브라우저 동작을 실행하지 못했습니다.'
BUSY_TEXT = '브라우저 프로필을 다른 작업 또는 로그인 창이 사용하고 있어 지금은 실행하지 않았습니다.'
NO_PAGE_TEXT = '열린 페이지가 없습니다. 먼저 browser_open으로 페이지를 여세요.'
WORKER_DELETE_FAILED_TEXT = ('저장된 로그인 세션은 지웠지만 실행 중인 브라우저에서 지우지 못했습니다. 그 브라우저를 멈췄고 '
                             '그 안의 내용은 저장하지 않습니다.')
KEY_DELETE_FAILED_TEXT = ('로그인 세션은 삭제했지만 macOS 키체인의 암호화 키는 지우지 못했습니다. 키체인 접근 앱에서 '
                          '"personal-agentos.browser-jar" 항목을 직접 삭제할 수 있습니다.')
BLOCKED_TEXT = ('이 컴퓨터나 내부 네트워크(루프백·사설·링크 로컬·.local) 주소는 브라우저로 열지 않습니다. '
                '공개 웹 주소만 열 수 있습니다.')
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


def cancelled_note(record):
    """The owner-facing note naming the form whose submit was cancelled (its page, no query)."""
    if not isinstance(record, dict):
        return ''
    where, _ = mediate_url(page_reference(record.get('action')))
    return f' · {CANCELLED_NOTE}: {where[:200]}' if where else f' · {CANCELLED_NOTE}'


def forwards_to_payment_form(element, forms):
    """Its ``<label>`` forwards a press to a control of one of ``forms`` (#698).

    ``label_form`` is the form of the labeled control of the ``<label>`` the
    element is, or sits inside, when that control is another element: the
    ``for`` target, else the first labelable descendant (HTML's
    ``label.control``).  A click there activates that control, so a span inside
    ``<label for=pay>`` presses the pay button even outside the pay form.
    """
    return element.get('label_form') is not None and element['label_form'] in forms


def guarded_submit(element, elements):
    """A button of a form that contains a payment/credential field, or an element forwarding to one."""
    forms = payment_forms(elements)
    return ((button_like(element) and element.get('form') is not None and element['form'] in forms)
            or forwards_to_payment_form(element, forms))


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
        internal.append({**{key: element.get(key) for key in ('index', 'role', 'name', 'tag', 'type', 'autocomplete', 'form',
                                                             'label_form')},
                         'n': row['n'], 'guarded': guarded_field(element), 'payment': payment_field(element)})
        if len(visible) >= ELEMENT_LIMIT:
            break
    forms = payment_forms(elements)
    for row in internal:
        row['submit_guarded'] = guarded_submit(row, elements)
        row['forwards_payment'] = forwards_to_payment_form(row, forms)
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
    states, identities = page_states(raw, elements, text, excluded)
    snapshot['_states'] = states
    # Every payment form's identity and state (#698): part of every step's binding.
    snapshot['_payment_states'] = {identities[form_id]: states[form_id]
                                   for form_id in payment_forms(elements) if form_id in identities}
    return snapshot


def form_identity(form):
    """Which form: its position among the document's forms, its method and action page (no query)."""
    form = form if isinstance(form, dict) else {}
    return f"form {form.get('dom', '')}|{str(form.get('method') or '').lower()}|{page_reference(form.get('action'))}"


def page_states(raw, elements, text, excluded=()):
    """``({form id: state, None: page state}, {form id: identity})`` approvals are bound to.

    A form's state is its identity (``form_identity``), its mediated visible
    text (price, quantity, terms) and the mediated values of its non-guarded
    fields; guarded values (card, code, password) are never part of it.  A
    target outside any form is bound to the mediated page text.
    """
    forms, identities = {}, {}
    for form in raw.get('forms') or []:
        if isinstance(form, dict) and form.get('id') is not None:
            forms[form['id']] = scrub(str(form.get('text') or '')[:TEXT_LIMIT], excluded)[0]
            identities[form['id']] = form_identity(form)
    states = {None: text}
    referenced = {element.get(key) for element in elements for key in ('form', 'label_form')}
    for form_id in referenced - {None}:
        identities.setdefault(form_id, f'form ?{form_id}')
        values = sorted((target_key(element), scrub(str(element.get('value') or ''), excluded)[0])
                        for element in elements if element.get('form') == form_id and not guarded_field(element))
        states[form_id] = (identities[form_id] + '\n' + forms.get(form_id, '') + '\n'
                           + '\n'.join(f'{key}={value}' for key, value in values))
    return states, identities


def public_view(snapshot):
    """The model-facing dict: everything but the internal element descriptors."""
    return {key: value for key, value in snapshot.items() if not key.startswith('_')}


#: #736: how many of the current page's elements a ``target_not_found`` names, and how long each name may be.
TARGET_HINT_ELEMENTS = 15
TARGET_HINT_NAME = 40


def element_hint(snapshot):
    """The current page's first elements as ``number name`` (mediated names, bounded), or ''.

    #736: returned with ``target_not_found`` so the model can pick a real
    element in one step instead of reading the page again.
    """
    rows = [row for row in snapshot.get('elements') or [] if isinstance(row, dict) and row.get('n') is not None]
    parts = []
    for row in rows[:TARGET_HINT_ELEMENTS]:
        name = ' '.join(str(row.get('name') or row.get('role') or '').split())[:TARGET_HINT_NAME]
        parts.append(f"{row['n']} {name}".strip())
    if not parts:
        return ''
    more = f' 외 {len(rows) - len(parts)}개' if len(rows) > len(parts) else ''
    return ' 현재 페이지의 요소: ' + ' · '.join(parts) + more + '.'


def resolve_target(snapshot, target):
    """The internal element ``target`` names: its list number or a visible-name match."""
    rows = snapshot.get('_elements') or []
    wanted = ' '.join(str(target or '').split())
    if not wanted:
        raise ToolError('target을 입력하세요: 요소 번호 또는 보이는 이름입니다.' + element_hint(snapshot), 'target_not_found')
    if wanted.isdigit():
        number = int(wanted)
        for row in rows:
            if row['n'] == number:
                return row
        raise ToolError(f'요소 번호 {number}은(는) 현재 페이지 목록에 없습니다.' + element_hint(snapshot), 'target_not_found')
    key = wanted.casefold()
    exact = [row for row in rows if ' '.join(str(row.get('name') or '').split()).casefold() == key]
    if len(exact) == 1:
        return exact[0]
    partial = exact or [row for row in rows if key in ' '.join(str(row.get('name') or '').split()).casefold()]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise ToolError('일치하는 요소가 없습니다. 요소 목록에 있는 번호나 이름을 사용하세요.' + element_hint(snapshot),
                        'target_not_found')
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
                 steps=STEPS_PER_WORK, action_seconds=ACTION_TIMEOUT_SECONDS, allowed_origins_for_tests=()):
        self._factory = driver_factory
        # Test-only exact ``host:port`` allowance for a local fixture site; only
        # a test constructor sets it (never config or environment).
        self._allowed_origins = frozenset(allowed_origins_for_tests)
        self.driver = None
        self.work_id = work_id
        self.budget = budget
        self.excluded = excluded
        self.approvals = approvals or NoApprovals()
        self.steps, self.steps_used = steps, 0
        self.action_seconds = action_seconds
        self.last = None
        # The description of the last click/type sent to the current page: the
        # owner reads it with a payment-form submit cancelled after it answered
        # (#698).  Cleared by browser_open and a navigation (#700).
        self._last_input = None

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
        cancelled = raw.get('cancelled_submit') if isinstance(raw, dict) else None
        if cancelled:
            # A payment-form submit the worker cancelled after a step answered (a
            # timer, an async callback).  Released only when the owner approved
            # exactly it; the page it led to is then read instead.
            self._cancelled_submit(cancelled, self._last_input or '결제 양식 제출')
            self._last_input = None
            self._settle()
            return self._snapshot(requested_url)
        return self.last

    def _submit_binding(self, record):
        """What the approval of a cancelled payment-form submit is bound to (#700).

        That form (position, method, action page) on its page, and the digest
        of what its submit would send (every submitted control's name and
        value, hidden amounts included, card/code/password values excluded,
        and the form's visible text), read when the worker cancelled it.
        """
        page = record.get('page') or (self.last or {}).get('_page')
        return step_binding(self.work_id, 'browser_submit', page, form_identity(record), '', str(record.get('state') or ''))

    def _cancelled_submit(self, record, description, depth=0):
        """A payment-form submit the worker cancelled and holds (#698, #700).

        When the owner already approved exactly that form in that state, the
        worker releases the held submit and the step goes on (the answer is
        the release's); otherwise the owner is asked, bound to that form's
        submitted state rather than to the step that caused it, so the
        resumed run matches however the page changed on the way to the submit.
        """
        record = record if isinstance(record, dict) else {}
        binding = self._submit_binding(record)
        if depth < 2 and self.approvals.consume(binding):
            release = getattr(self._driver(), 'release_submit', None)
            if not callable(release):
                raise ToolError(FAILED_TEXT, 'browser_failed')
            try:
                return self._call(lambda timeout: release(record, timeout))
            except ToolError as exc:
                if exc.code != 'approval_required':
                    raise
                return self._cancelled_submit(getattr(exc, 'cancelled_form', None), description, depth + 1)
        self._refuse(binding, description + cancelled_note(record))

    def _settle(self):
        """Let a page that renders its content after load finish rendering, bounded (#709).

        Best effort and generic: a driver without ``settle`` (a test driver)
        skips it, and a settle that fails or times out is not a failed step;
        the snapshot reads whatever the page shows by then.
        """
        settle = getattr(self._driver(), 'settle', None)
        if not callable(settle):
            return
        seconds = RENDER_SETTLE_SECONDS
        if self.budget is not None:
            try:
                seconds = min(seconds, max(0.0, self.budget.remaining() - 1.0))
            except Exception:
                pass
        if seconds <= 0:
            return
        try:
            settle(seconds, self._timeout())
        except ToolError:
            raise
        except Exception:
            pass

    def _page_state(self, requested_url=None):
        snapshot = self._snapshot(requested_url)
        if snapshot['login_required']:
            # Generic (`login_form_present`): the profile holds no session for
            # this page.  Nothing else of the page is returned.
            return {'state': 'login_required', 'url': snapshot['url'], 'title': snapshot['title'],
                    'needs_setup': True, 'requires': 'browser-login',
                    'next_step': self._offer_login(snapshot['url']) or LOGIN_REQUIRED_TEXT}
        return {'state': 'page', **public_view(snapshot)}

    def _offer_login(self, url):
        """Ask the owner to log in during this Work (#709), when the approvals surface can.

        ``approvals.login_required(url)`` records the request; the service
        shows the login window and asks the owner once this Work's run has
        released the profile.  It returns the text the model reads instead
        of the Settings pointer, or None.  Nothing is typed and nothing is
        read from the login page.
        """
        offer = getattr(self.approvals, 'login_required', None)
        if not callable(offer):
            return None
        try:
            text = offer(url)
        except Exception:
            return None
        return text if isinstance(text, str) and text else None

    @staticmethod
    def _effect(args):
        effect = str(args.get('effect') or '').strip().lower()
        if effect not in EFFECTS:
            raise ValueError('effect는 read, navigate, mutate, payment 중 하나여야 합니다.')
        return effect

    def _submit_approval_issued(self):
        """The owner approved a cancelled payment-form submit of this Work that is not yet released (#700)."""
        issued = getattr(self.approvals, 'issued_action', None)
        try:
            return callable(issued) and issued() == 'browser_submit'
        except Exception:
            return False

    def _guard(self, binding, description, required, holdable=False):
        """Refuse a guarded step unless an exact owner approval is consumed now.

        ``required`` is AgentOS's own classification of the target, or the
        model's ``payment`` label (which can only ADD the requirement).  The
        binding covers the step's arguments and the current page state too, so
        different text or a changed form asks again.  Returns True when an
        approval was consumed: only then does the worker let a submit of the
        target's payment form through (#700).  An unguarded step still spends
        an approval the owner gave for exactly it.

        ``holdable``: the step is guarded only because it presses a control of
        a payment form, so the only guarded effect it can have is that form's
        submit, which the worker cancels and holds.  While the owner's approval
        of a cancelled submit is issued and unspent, such a step runs without
        an allowance instead of asking for itself (which would replace that
        approval): the submit it makes is held and released only when it is
        exactly the approved form in the approved state (#700 review).
        """
        if self.approvals.consume(binding):
            return True
        if required and not (holdable and self._submit_approval_issued()):
            self._refuse(binding, description)
        return False

    def _refuse(self, binding, description):
        try:
            self.approvals.request(binding, description)
        except Exception:
            pass
        raise ToolError(APPROVAL_TEXT, 'approval_required', requires='browser-step-approval')

    def _input(self, operation, description):
        """Run one click or type; a payment-form submit the worker cancelled asks the owner (#698).

        An approved step lets a submit of its target's payment form through;
        any other one is cancelled and handled by ``_cancelled_submit`` (#700).
        """
        self._last_input = description
        try:
            return self._call(operation)
        except ToolError as exc:
            if exc.code != 'approval_required':
                raise
            return self._cancelled_submit(getattr(exc, 'cancelled_form', None), description)

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
        # #680 review P1-2: never this computer or its private network (the
        # AgentOS UI included).  Name and literal here; the worker checks every
        # navigation again after DNS resolution (redirects, forms, new windows).
        if local_destination(url, self._allowed_origins):
            raise ToolError(BLOCKED_TEXT, 'blocked_destination')
        self._spend_step()
        self._guard(step_binding(self.work_id, 'browser_open', url, url, url), f'{_host(parts)} 페이지 열기',
                    effect == 'payment')
        self._last_input = None   # a submit cancelled on the new page is not that step's (#700)
        self._call(lambda timeout: self._driver().goto(url, timeout))
        self._settle()
        return self._page_state(requested_url=url)

    def read(self):
        self._require_page()
        self._spend_step()
        self._settle()
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
        binding = step_binding(self.work_id, 'browser_click', snapshot['_page'], key, key, self._state_of(snapshot, element))
        description = f"'{element.get('name') or element.get('role')}' 버튼 누르기"
        approved = self._guard(binding, description, element['submit_guarded'] or effect == 'payment',
                               holdable=element['submit_guarded'])
        before = page_reference(snapshot.get('url'))
        answer = self._input(lambda timeout: self._driver().click(element['index'], timeout, approved=approved),
                             description)
        if isinstance(answer, dict) and answer.get('navigated'):
            self._last_input = None   # #700: the page it was sent to is gone
        # #736: the worker answers once any navigation the click started has
        # committed; the content of the page it landed on is then settled too.
        self._settle()
        page = self._page_state()
        if (isinstance(answer, dict) and answer.get('navigated')) or page_reference(page.get('url')) != before:
            page['navigated'] = True
            self._last_input = None
        return page

    def type(self, args):
        effect = self._effect(args)
        self._require_page()
        text = str(args.get('text') or '')
        if len(text) > 2000:
            raise ValueError('입력 텍스트는 2000자 이하여야 합니다.')
        self._spend_step()
        snapshot = self._snapshot()
        element = resolve_target(snapshot, args.get('target'))
        binding = step_binding(self.work_id, 'browser_type', snapshot['_page'], target_key(element), text,
                               self._state_of(snapshot, element))
        description = f"'{element.get('name') or element.get('role')}' 입력란에 입력"
        # Typing presses the field first, so a label forwarding that press is guarded too.
        required = element['payment'] or element.get('forwards_payment') or effect == 'payment'
        approved = self._guard(binding, description, required)
        self._input(lambda timeout: self._driver().type(element['index'], text, timeout, approved=approved),
                    description)
        return self._page_state()

    @staticmethod
    def _state_of(snapshot, element):
        """The state a step on ``element`` is bound to (#698).

        Its own form's state (else the page text), the state of the form its
        label forwards a press to, and every payment form's state, each with
        the form's identity: a changed non-card value of the payment form, or
        a label pointed at another identical form, asks again.
        """
        states = snapshot.get('_states') or {}
        parts = [states.get(element.get('form'), states.get(None, ''))]
        if element.get('label_form') is not None:
            parts.append('label -> ' + states.get(element['label_form'], ''))
        payment = snapshot.get('_payment_states') or {}
        parts.extend(payment[identity] for identity in sorted(payment))
        return '\n\x1e'.join(parts)

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
def local_destination(url, allowed_origins=()):
    """True when ``url`` names this computer or a private network by name or literal address.

    ``browser_worker.local_url`` over the public-page guard's tables
    (``local_tools``): localhost, ``.local``/``.localhost``/``.internal``/
    ``.home.arpa``, loopback, private, link-local, reserved and multicast.  No
    DNS here; the worker resolves every navigation it performs.
    ``allowed_origins`` is the test-only exact ``host:port`` allowance.
    """
    from .browser_worker import local_url
    return local_url(url, allowed_origins)


#: Environment names a worker inherits: nothing else (no provider keys, tokens
#: or AgentOS settings).  ``PYTHONPATH`` lets a source checkout find the package.
WORKER_ENVIRONMENT = ('PATH', 'HOME', 'USER', 'LOGNAME', 'TMPDIR', 'LANG', 'LC_ALL', 'LC_CTYPE', 'PYTHONPATH')


def worker_environment(base=None):
    base = os.environ if base is None else base
    env = {name: base[name] for name in WORKER_ENVIRONMENT if base.get(name)}
    env.setdefault('PATH', '/usr/bin:/bin')
    if env.get('PYTHONPATH'):
        # The worker runs in the profile's folder: a relative entry would name another directory (#709 review).
        env['PYTHONPATH'] = os.pathsep.join(os.path.abspath(entry) for entry in env['PYTHONPATH'].split(os.pathsep) if entry)
    return env


#: Worker error codes that mean "the element the guard classified is not what the pointer would hit".
TARGET_ERRORS = frozenset({'target_missing', 'target_changed', 'target_hidden', 'target_obscured', 'not_typable',
                           'not_focusable', 'bad_target', 'submit_changed'})
WORKER_START_SECONDS = 30
WORKER_GRACE_SECONDS = 5
WORKER_QUIT_SECONDS = 5
LOGIN_OPEN_SECONDS = 45
#: #709: how long closing a login window waits for its save and release.
LOGIN_CLOSE_SECONDS = 20
#: #709: how many closed login windows' outcomes a profile remembers.
LOGIN_WINDOWS_KEPT = 16
#: #709: the longest a ``browser_open``/``browser_read`` waits for a
#: client-rendered page's content to settle (``browser_worker.op_settle``).
RENDER_SETTLE_SECONDS = 4.0
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
                 grace_seconds=WORKER_GRACE_SECONDS, cwd=None, allowed_origins_for_tests=()):
        self.profile_id = str(profile_id)
        self._seed = seed
        # ``-P``: the working directory is never on the worker's import path.
        self._command = list(command) if command else [sys.executable, '-P', '-m', 'personal_agent.browser_worker',
                                                       '--profile', self.profile_id]
        if not command:
            for origin in allowed_origins_for_tests:
                self._command += ['--test-allow-origin', str(origin)]
        # A fixed working directory (the profile's private folder) and a minimal environment.
        self._cwd = str(cwd) if cwd else os.path.expanduser('~')
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
                                text=True, encoding='utf-8', bufsize=1, close_fds=True, cwd=self._cwd,
                                env=worker_environment())
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
            if code == 'blocked_destination':
                raise ToolError(BLOCKED_TEXT, 'blocked_destination')
            if code == 'approval_required':
                # The worker cancelled a payment-form submit no approval let through (#698).
                refusal = ToolError(APPROVAL_TEXT, 'approval_required', requires='browser-step-approval')
                refusal.cancelled_form = message.get('form') if isinstance(message.get('form'), dict) else None
                raise refusal
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

    def settle(self, seconds, timeout):
        """Wait, bounded by ``seconds``, until a client-rendered page's content stops changing (#709)."""
        self._request('settle', timeout, seconds=seconds)

    def snapshot(self):
        page = self._request('snapshot', ACTION_TIMEOUT_SECONDS).get('page') or {}
        elements = [element for element in page.get('elements') or [] if isinstance(element, dict)]
        guarded_forms = payment_forms(elements)
        # The full descriptor the payment guard classified: the worker refuses
        # to press or type into an element that no longer matches it.
        self._expect = {element['index']: {'tag': str(element.get('tag') or ''), 'type': str(element.get('type') or ''),
                                           'autocomplete': str(element.get('autocomplete') or ''),
                                           'name': str(element.get('name') or ''),
                                           'in_form': element.get('form') is not None,
                                           'payment_form': (element.get('form') is not None and element.get('form') in guarded_forms)
                                           or forwards_to_payment_form(element, guarded_forms)}
                        for element in elements if isinstance(element.get('index'), int) and not isinstance(element.get('index'), bool)}
        return page

    def _target(self, index):
        expect = self._expect.get(index)
        if expect is None:
            raise ToolError(TARGET_TEXT, 'target_unavailable')   # never an element nobody classified
        return {'index': index, 'expect': expect, 'tokens': sorted(PAYMENT_AUTOCOMPLETE)}

    def click(self, index, timeout, approved=False):
        """``approved``: the session consumed an owner approval for this step.

        Only then does the worker let a submit of the target's payment form
        through, during the step and briefly after it (#700); otherwise a
        cancelled one answers ``approval_required`` with its form record.
        Returns ``{'navigated': bool}``: whether the click started a main-frame
        navigation (a same-view new-window load included) that the worker
        waited for (#736).  No URL crosses here; the next snapshot is mediated.
        """
        message = self._request('click', timeout, approved=approved is True, **self._target(index))
        return {'navigated': bool(message.get('navigated'))}

    def type(self, index, text, timeout, approved=False):
        self._request('type', timeout, text=text, approved=approved is True, **self._target(index))

    def release_submit(self, record, timeout):
        """Release the cancelled payment-form submit ``record`` names, which the owner approved (#700).

        ``record`` is the ``cancelled_form``/``cancelled_submit`` the worker
        reported (form position, method, action, page, state digest); the
        worker releases only that held submit, and only when the same form
        would still send the same state.  Answers like ``click``.
        """
        record = record if isinstance(record, dict) else {}
        form = {key: record.get(key) for key in ('dom', 'method', 'action', 'page', 'state')}
        message = self._request('release_submit', timeout, form=form)
        return {'navigated': bool(message.get('navigated'))}

    # -- the owner's login window ---------------------------------------------------
    def show(self, url, timeout):
        # Visible before the request: a ``hidden`` event that arrives while the
        # request is pending (the owner closed the window at once) must win.
        self._visible = True
        try:
            self._request('show', timeout, url=url)
        except Exception:
            self._visible = False
            raise

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

    def discard(self):
        """Stop the worker without exporting anything; the next call starts a fresh one from the jar."""
        with self._lock:
            self._kill()

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
        # Login windows this process opened: id -> stop flag, closed event,
        # close reason and whether the final save succeeded (#709).
        self._login_windows = {}
        # What the running worker was given from the jar (#680 review P2-3):
        # sites imported, or why the import failed (then nothing is saved).
        self._imported = set()
        self._import_error = None
        self.save_error = None
        # #680 review (Codex P1): after a delete/clear the running worker could
        # not perform, nothing that worker instance holds is ever saved.
        self._unsavable = None
        # Settings reads the jar through this cache so a locked Keychain never
        # blocks a poll (#680 review P2-7).
        self._view = None
        self._view_refreshing = False
        self._allowed_origins = ()

    def allow_origins_for_tests(self, *origins):
        """Test-only: exact ``host:port`` fixture origins the worker may load.  Never set by config."""
        self._allowed_origins = tuple(origins)

    def _seed(self):
        """The jar's rows for a (re)starting worker; records what was imported or why it failed."""
        try:
            sites, rows = self.jar.import_rows()
        except JarError as exc:
            self._import_error = str(exc)
            return []
        self._imported |= sites
        return rows

    def _launch_webkit(self, profile_dir, headless):
        return WebKitWorkerDriver(self.profile_dir.name, seed=self._seed, cwd=self.profile_dir,
                                  allowed_origins_for_tests=self._allowed_origins)

    def remove_legacy_profile(self):
        """Delete the pre-#680 Playwright Chromium profile (plaintext cookies) from ``profile_dir``.

        Everything in that folder except the encrypted jar is the old profile.
        Returns True when something was removed.
        """
        removed = False
        try:
            entries = list(self.profile_dir.iterdir()) if self.profile_dir.is_dir() else []
        except OSError:
            return False
        for entry in entries:
            if entry.name == JAR_NAME or entry.name.startswith(JAR_NAME + '.tmp-'):
                continue
            try:
                if entry.is_dir() and not entry.is_symlink():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
                removed = True
            except OSError:
                continue
        return removed

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
            state, sessions = self._jar_view()
            status['storage'] = {'what': 'site-sign-in-cookies', 'path': str(self.jar.path),
                                 'key': getattr(self.jar.key, 'location', 'macos-keychain'), 'key_service': JAR_SERVICE,
                                 'sent_to_ai': False, 'state': state, 'save_error': self.save_error}
            status['sessions'] = sessions
        return status

    def _jar_view(self):
        """``(state, sessions)`` for Settings without blocking on the Keychain.

        No file or a jar this process already read: answered at once.  Otherwise
        the jar is decrypted on a background thread and Settings shows
        ``checking`` until it finishes; a failure is shown for a minute before
        the next attempt.
        """
        cached = self.jar.cached_sites()
        if cached is not None:
            self._view = None
            return cached
        view = self._view
        if view is not None and view[0] != 'checking' and self.clock() - view[2] < 60:
            return view[0], view[1]
        if not self._view_refreshing:
            self._view_refreshing = True
            self._view = ('checking', [], self.clock())

            def refresh():
                try:
                    state = self.jar.state()
                    self._view = (state, self.jar.sites() if state == 'stored' else [], self.clock())
                except Exception:
                    self._view = ('unreadable', [], self.clock())
                finally:
                    self._view_refreshing = False
            threading.Thread(target=refresh, name='agentos-browser-jar-view', daemon=True).start()
        view = self._view or ('checking', [], self.clock())
        return view[0], view[1]

    # -- holding the profile ---------------------------------------------------
    def _acquire(self, holder):
        if not self._lock.acquire(blocking=False):
            raise ToolError(BUSY_TEXT, 'browser_busy')
        self._holder = holder
        self._suppressed = set()
        self._imported = set()
        self._import_error = None
        self._unsavable = None

    def _release(self):
        self._holder = None
        self._live = None
        try:
            self._lock.release()
        except RuntimeError:
            pass

    def _save(self, driver):
        """Export the driver's cookies into the jar (never elsewhere).  A failure keeps the old jar."""
        if not hasattr(driver, 'cookies_export') or not _alive(driver):
            return False   # a crashed worker has nothing new; never restart one just to export
        with self._jar_lock:
            if self._unsavable is not None and self._unsavable == _generation(driver):
                self.save_error = 'worker_delete_failed'
                return False
            if self._import_error:
                # The jar could not be read when this worker started (e.g. a
                # locked Keychain): saving could replace sessions it never
                # held.  Keep the jar as it is and tell the owner why.
                self.save_error = self._import_error
                return False
            try:
                sites, hosts = driver.cookies_export()
            except Exception:
                return False
            sites = {site: rows for site, rows in sites.items() if site not in self._suppressed}
            try:
                self.jar.save_export(sites, hosts, imported=self._imported)
            except JarError as exc:
                self.save_error = str(exc)
                return False
            except Exception:
                return False
            self.save_error = None
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
    def _worker_failed(self, live):
        """A running worker could not drop sessions: never save from it, and stop it.

        The worker is discarded (no export), so the Work's next step starts a
        fresh worker from the jar, which no longer holds the deleted sessions.
        """
        self._unsavable = _generation(live)
        discard = getattr(live, 'discard', None)
        if callable(discard):
            try:
                discard()
            except Exception:
                pass

    def delete_site(self, site):
        """Remove one site's sign-in data from the jar and from a running worker.

        ``deleted`` is True only when both succeeded.  When the running worker
        could not delete it, the jar entry is still removed, that worker is
        stopped without saving, and the reply says so (``running_browser``).
        """
        site = str(site or '').strip().lower()
        if not site:
            raise ValueError('삭제할 사이트를 지정하세요.')
        with self._jar_lock:
            live = self._live
            worker = None
            if live is not None and hasattr(live, 'cookies_delete') and _alive(live):
                try:
                    live.cookies_delete(site)
                    worker = 'deleted'
                except Exception:
                    self._suppressed.add(site)
                    self._worker_failed(live)
                    worker = 'failed'
            try:
                removed = self.jar.remove(site)
            except Exception:
                raise ValueError('저장된 로그인 세션을 읽지 못했습니다. "모두 삭제"로 초기화할 수 있습니다.') from None
        if worker == 'failed':
            return {'deleted': False, 'site': site, 'removed_from_jar': bool(removed), 'running_browser': 'failed',
                    'message': WORKER_DELETE_FAILED_TEXT}
        return {'deleted': bool(removed) or worker == 'deleted', 'site': site}

    def delete_all(self):
        """Delete the jar file, its Keychain key and the legacy profile, and clear a running worker.

        Every part is reported: a running worker that could not clear, or a
        Keychain key that could not be removed, makes ``deleted`` False with
        the reason; nothing is acknowledged that did not happen.
        """
        with self._jar_lock:
            live = self._live
            worker = None
            if live is not None and hasattr(live, 'cookies_clear') and _alive(live):
                try:
                    live.cookies_clear()
                    worker = 'cleared'
                except Exception:
                    self._worker_failed(live)
                    worker = 'failed'
            cleared = self.jar.clear()
            legacy = self.remove_legacy_profile()
            self.save_error = None
        result = {'all': True, 'jar_deleted': cleared['jar_deleted'] or legacy, 'key_deleted': cleared['key_deleted'],
                  'key_error': cleared['key_error'], 'running_browser': worker}
        result['deleted'] = cleared['key_error'] is None and worker != 'failed'
        if cleared['key_error']:
            result['message'] = KEY_DELETE_FAILED_TEXT
        elif worker == 'failed':
            result['message'] = WORKER_DELETE_FAILED_TEXT
        return result

    # -- the owner's login window ------------------------------------------------------
    def open_for_login(self, url, wait=False, seconds=None, on_closed=None):
        """Show the worker window at ``url`` for the owner to log in by hand.

        AgentOS navigates to ``url`` and does nothing else: no typing, no
        reading.  The window's title shows the host it is on.  Cookies are
        exported into the encrypted jar while it is open and when the owner
        closes it (or after ``seconds``, by default ``LOGIN_WINDOW_SECONDS``,
        or when ``close_login_window`` is called with the returned ``window``).

        #709: once the window has closed, its cookies were saved and the
        profile was released, ``on_closed(window, reason, saved)`` is called
        on the window's thread.  ``reason`` is ``owner`` (the owner closed the
        window), ``closed`` (``close_login_window``), ``timeout`` or
        ``failed``; ``saved`` is whether the final save into the jar succeeded.
        """
        if not self.available():
            return {'state': 'unavailable', 'reason': self.unavailable_reason(), 'message': self.unavailable_message()}
        parts = urlsplit(str(url or ''))
        if parts.scheme not in ('http', 'https') or not parts.netloc:
            raise ValueError('http 또는 https 주소를 입력하세요.')
        if local_destination(url, self._allowed_origins):
            raise ValueError(BLOCKED_TEXT)
        try:
            self._acquire('login')
        except ToolError:
            return {'state': 'busy', 'message': BUSY_TEXT}
        opened = threading.Event()
        window_id = secrets.token_hex(8)
        # The flag a programmatic close sets before it stops the loop, so an
        # owner's close is never confused with it (#709).
        record = {'stop': threading.Event(), 'done': threading.Event(), 'reason': None, 'saved': False}
        self._login_windows[window_id] = record
        for stale in list(self._login_windows)[:-LOGIN_WINDOWS_KEPT]:
            self._login_windows.pop(stale, None)
        stop = record['stop']
        lifetime = LOGIN_WINDOW_SECONDS if seconds is None else max(1.0, min(float(seconds), LOGIN_WINDOW_SECONDS))
        failure = []
        def window():
            driver = None
            reason = 'failed'
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
                deadline = self.clock() + lifetime
                saved = self.clock()
                while driver.is_open() and self.clock() < deadline and not stop.is_set():
                    stop.wait(0.5)
                    if self.clock() - saved >= LOGIN_SAVE_SECONDS:
                        self._save(driver)
                        saved = self.clock()
                reason = 'closed' if stop.is_set() else 'timeout' if self.clock() >= deadline else 'owner'
            except Exception as exc:
                failure.append(type(exc).__name__)
            finally:
                stored = False
                if driver is not None:
                    stored = bool(self._save(driver))
                    try:
                        driver.close()
                    except Exception:
                        pass
                self._release()
                record['reason'], record['saved'] = reason, stored and not failure
                record['done'].set()
                opened.set()
                if on_closed is not None:
                    try:
                        on_closed(window_id, reason, record['saved'])
                    except Exception:
                        pass
        self._login_thread = threading.Thread(target=window, name='agentos-browser-login', daemon=True)
        self._login_thread.start()
        if wait:
            self._login_thread.join()
        else:
            opened.wait(LOGIN_OPEN_SECONDS + WORKER_START_SECONDS + 5)
        if failure:
            return {'state': 'failed', 'message': FAILED_TEXT}
        return {'state': 'closed' if wait else 'opened', 'url': page_reference(url), 'message': LOGIN_WINDOW_TEXT,
                'window': window_id}

    def site_cookie_marks(self, host):
        """``(marks, now)`` of ``host``'s stored sign-in cookies (``CookieJar.site_cookie_marks``), or None when unreadable (#709)."""
        try:
            with self._jar_lock:
                return self.jar.site_cookie_marks(host)
        except Exception:
            return None

    def login_window_known(self, window):
        """Whether ``window`` is a login window this process opened (a restart forgets every one)."""
        return bool(window) and window in self._login_windows

    def login_window_outcome(self, window):
        """``(reason, saved)`` once ``window`` has closed, saved and released; None while it is open or unknown."""
        record = self._login_windows.get(window) if window else None
        if record is None or not record['done'].is_set():
            return None
        return record['reason'], bool(record['saved'])

    def close_login_window(self, window, timeout=LOGIN_CLOSE_SECONDS):
        """Close the login window ``open_for_login`` returned as ``window``, and wait for it (#709).

        Only that window: another login window is left alone.  Returns True
        only when that window has closed (now, or earlier by the owner), its
        final cookie save into the jar succeeded and the profile was
        released.  False when this process never opened it (a restart), it
        did not finish closing in ``timeout`` seconds, or the save failed.
        """
        record = self._login_windows.get(window) if window else None
        if record is None:
            return False
        record['stop'].set()
        if not record['done'].wait(timeout):
            return False
        return bool(record['saved'])


def _generation(driver):
    """Which worker process a driver runs now (a restart is a new generation)."""
    return (id(driver), getattr(driver, 'starts', 0))


def _alive(driver):
    alive = getattr(driver, 'alive', None)
    try:
        return bool(alive()) if callable(alive) else True
    except Exception:
        return False


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
