"""Browser action capability inside an owner-logged-in profile (SEC-BROWSER-01 #656).

The owner logs in once, by hand, in a browser window AgentOS opens on a
persistent Chromium profile that the execution environment owns.  The model
then opens, reads, finds, clicks and types on pages in that profile through
five generic tools.  Two boundaries are enforced here, deterministically and
independently of anything the model says (pilot posture, #653):

* **Output mediation.**  Nothing leaves ``PageDriver.snapshot`` before
  ``mediate_snapshot``: values of ``password`` inputs and of fields whose
  ``autocomplete`` names a credential, one-time code or card field are
  dropped; the existing saved-private-value matcher of public lookups
  (``lookup_text_violations``, #605) redacts page text; the raw DOM, cookies,
  ``localStorage`` and storage state have no accessor at all.
* **Payment guard.**  Typing into a card-number, CVC, card-expiry, one-time
  code or password field, and pressing a button of a form that contains such
  a field, need an owner approval bound to (Work, action, page URL digest,
  target element) and verified at execution.  The model's ``effect`` label can
  only add a requirement (``payment`` always needs approval), never remove one.

Reuse: Playwright (Apache-2.0, optional ``browser`` extra) is adopted for the
commodity browser mechanics behind ``PlaywrightDriver``; ``ToolError``, the
Work budget, the lookup redactor and the exact-approval binding are the
existing AgentOS symbols.  No site, provider or category is named anywhere in
this module.
"""
import hashlib
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .agent_runtime import BROWSER_ACTIONS, ToolError, lookup_norm, lookup_text_violations, lookup_words

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
LOGIN_REQUIRED_TEXT = '이 페이지는 로그인이 필요합니다. 설정의 "브라우저 열어 로그인"으로 먼저 로그인해 주세요. AgentOS는 비밀번호를 입력하지 않습니다.'
STEP_BUDGET_TEXT = f'이 작업의 브라우저 단계 한도({STEPS_PER_WORK}회)에 도달해 더 실행하지 않았습니다.'
TIMEOUT_TEXT = '브라우저 동작이 시간 안에 끝나지 않았습니다.'
FAILED_TEXT = '브라우저 동작을 실행하지 못했습니다.'
BUSY_TEXT = '브라우저 프로필을 다른 작업 또는 로그인 창이 사용하고 있어 지금은 실행하지 않았습니다.'
NO_PAGE_TEXT = '열린 페이지가 없습니다. 먼저 browser_open으로 페이지를 여세요.'
UNAVAILABLE_TEXT = '브라우저 기능이 설치되어 있지 않습니다. 설정의 브라우저 항목에서 설치 방법을 확인해 주세요.'
INSTALL_HINT = "pip install 'personal-agentos[browser]' && playwright install chromium"
LIMITATION_TEXT = ('카드번호·CVC·일회용 코드 입력과 그 양식의 버튼은 승인 없이 실행하지 않습니다. '
                   '저장된 결제수단으로 카드 입력 없이 결제되는 사이트의 결제 버튼은 감지하지 못하므로, '
                   '결제수단을 연결하지 않은 계정에서만 사용하세요.')


# --- element classification (deterministic, site-independent) ---------------

def _autocomplete(element):
    return str(element.get('autocomplete') or '').strip().lower()


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


def target_key(element):
    """The stable descriptor an approval is bound to (not the list number, which shifts)."""
    return '|'.join(str(element.get(key) or '') for key in ('role', 'name', 'tag', 'type', 'autocomplete', 'form'))


def digest(text):
    return hashlib.sha256(str(text or '').encode()).hexdigest()


def page_reference(url):
    """A URL without its query and fragment: what Evidence and approvals may carry."""
    try:
        parts = urlsplit(str(url or ''))
    except ValueError:
        return ''
    return urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))


def step_binding(work_id, action, url, element_key):
    """What one approval is bound to: Work, action, page URL digest and target element."""
    return {'work_id': work_id, 'action': action, 'page_digest': digest(page_reference(url)),
            'target_digest': digest(element_key)}


def binding_digest(binding):
    return digest('|'.join(str(binding.get(key) or '') for key in ('work_id', 'action', 'page_digest', 'target_digest')))


# --- output mediation --------------------------------------------------------

def redact_private_values(text, excluded=(), blocked=None):
    """Redact tokens of ``text`` that match a saved or withheld private value.

    The matcher is the existing #605 lookup check (``lookup_text_violations``):
    whole values, contained spans, jamo keys and digit runs.  Returns
    ``(text, redacted_count)``.  A page with nothing to compare against is
    returned unchanged.
    """
    text = str(text or '')
    excluded = [value for value in excluded if isinstance(value, str) and value.strip()]
    if not text or not (excluded or blocked):
        return text, 0
    bad, digits_joined = lookup_text_violations(text, excluded, blocked)
    if not bad and not digits_joined:
        return text, 0
    out = []
    removed = 0
    for token in re.split(r'(\s+)', text):
        if not token or token.isspace():
            out.append(token)
            continue
        words = lookup_words(token)
        if any(word in bad for word in words) or (digits_joined and re.search(r'\d', lookup_norm(token))):
            out.append(REDACTED)
            removed += 1
        else:
            out.append(token)
    return ''.join(out), removed


def mediate_snapshot(raw, excluded=(), blocked=None):
    """The only page state that may leave the driver.

    ``raw`` is a ``PageDriver.snapshot`` result.  Guarded field values are
    dropped, text and names are bounded and redacted, and the model sees a
    numbered element list ``{n, role, name, href?, value?}``.  The internal
    descriptor of each element stays in ``_elements`` for target resolution
    and the payment guard; it is never returned to the model.
    """
    raw = raw if isinstance(raw, dict) else {}
    elements = [element for element in (raw.get('elements') or []) if isinstance(element, dict)]
    text, redacted = redact_private_values(str(raw.get('text') or '')[:TEXT_LIMIT * 2], excluded, blocked)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    truncated = len(text) > TEXT_LIMIT
    text = text[:TEXT_LIMIT]
    login_required = any(element.get('type') == 'password' for element in elements)
    visible = []
    internal = []
    for element in elements:
        if element.get('disabled'):
            continue
        name, count = redact_private_values(str(element.get('name') or '')[:NAME_LIMIT], excluded, blocked)
        redacted += count
        row = {'n': len(visible) + 1, 'role': str(element.get('role') or element.get('tag') or 'element'), 'name': name}
        if element.get('href'):
            row['href'] = page_reference(element['href'])[:400]
        if not guarded_field(element) and isinstance(element.get('value'), str) and element['value']:
            value, count = redact_private_values(element['value'][:VALUE_LIMIT], excluded, blocked)
            redacted += count
            row['value'] = value
        visible.append(row)
        internal.append({**{key: element.get(key) for key in ('index', 'role', 'name', 'tag', 'type', 'autocomplete', 'form')},
                         'n': row['n'], 'guarded': guarded_field(element), 'payment': payment_field(element)})
        if len(visible) >= ELEMENT_LIMIT:
            break
    for row in internal:
        row['submit_guarded'] = guarded_submit(row, elements)
    snapshot = {'url': page_reference(raw.get('url')), 'title': str(raw.get('title') or '')[:200], 'text': text,
                'elements': visible, 'login_required': login_required, 'truncated': truncated,
                'redacted_values': redacted}
    snapshot['_elements'] = internal
    return snapshot


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

    ``driver_factory`` returns the driver on first use (Chromium is launched
    only when a browser tool actually runs); ``budget`` is the Work's shared
    ``WorkBudget``; ``excluded`` returns ``(values, blocked)`` for redaction;
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

    def _snapshot(self):
        excluded, blocked = (), None
        if self.excluded is not None:
            try:
                excluded, blocked = self.excluded()
            except Exception:
                excluded, blocked = (), None
        raw = self._call(lambda timeout: self._driver().snapshot())
        self.last = mediate_snapshot(raw, excluded, blocked)
        return self.last

    def _page_state(self):
        snapshot = self._snapshot()
        if snapshot['login_required']:
            # Generic: a password field on the page (or after a redirect) means
            # the profile holds no session for it.  Nothing else is returned.
            return {'state': 'login_required', 'url': snapshot['url'], 'title': snapshot['title'],
                    'needs_setup': True, 'requires': 'browser-login', 'next_step': LOGIN_REQUIRED_TEXT}
        return {'state': 'page', **public_view(snapshot)}

    @staticmethod
    def _effect(args):
        effect = str(args.get('effect') or '').strip().lower()
        if effect not in EFFECTS:
            raise ValueError('effect는 read, navigate, mutate, payment 중 하나여야 합니다.')
        return effect

    def _guard(self, action, url, element_key, description, effect, deterministic):
        """Refuse a guarded step unless an exact owner approval is consumed now.

        ``deterministic`` is AgentOS's own classification of the target; the
        model's ``effect`` label is consulted only to ADD the requirement.
        """
        if not (deterministic or effect == 'payment'):
            return
        binding = step_binding(self.work_id, action, url, element_key)
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
        self._guard('browser_open', url, url, f'{parts.netloc} 페이지 열기', effect, False)
        self._call(lambda timeout: self._driver().goto(url, timeout))
        return self._page_state()

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
        self._guard('browser_click', snapshot['url'], target_key(element),
                    f"'{element.get('name') or element.get('role')}' 버튼 누르기", effect, element['submit_guarded'])
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
        self._guard('browser_type', snapshot['url'], target_key(element),
                    f"'{element.get('name') or element.get('role')}' 입력란에 입력", effect, element['payment'])
        self._call(lambda timeout: self._driver().type(element['index'], text, timeout))
        return self._page_state()

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


# --- the profile the execution environment owns --------------------------------

def playwright_available():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return True


#: Elements the model can act on and the fields the guard reasons about.  Run
#: in the page; returns plain data only (no node handles, no HTML).
SNAPSHOT_SCRIPT = r"""
() => {
  const SELECTOR = 'a[href], button, input, select, textarea, summary, [role="button"], [role="link"], [role="textbox"], [role="checkbox"], [role="radio"], [role="combobox"], [role="menuitem"], [role="tab"]';
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
  return {url: location.href, title: document.title, text: (document.body ? document.body.innerText : '').slice(0, 20000),
    elements: elements.slice(0, 300)};
}
"""
INTERACTIVE_SELECTOR = ('a[href], button, input, select, textarea, summary, [role="button"], [role="link"], [role="textbox"], '
                        '[role="checkbox"], [role="radio"], [role="combobox"], [role="menuitem"], [role="tab"]')


class PlaywrightDriver:
    """The real ``PageDriver`` over Playwright's sync API and a persistent context.

    Every call happens on the thread that created the driver (Playwright's
    sync API is thread-bound).  Errors are re-raised as ``TimeoutError`` or
    ``RuntimeError`` with AgentOS's own text: the library's messages can quote
    selectors and URLs.  There is no method that returns HTML, cookies or
    storage state.
    """

    def __init__(self, profile_dir, headless=True):
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        try:
            self._context = self._playwright.chromium.launch_persistent_context(str(profile_dir), headless=headless)
        except Exception:
            self._playwright.stop()
            raise
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()

    @staticmethod
    def _wrap(exc):
        if 'Timeout' in type(exc).__name__:
            return TimeoutError('browser timeout')
        return RuntimeError(type(exc).__name__)

    def goto(self, url, timeout):
        try:
            self._page.goto(url, wait_until='domcontentloaded', timeout=timeout * 1000)
        except Exception as exc:
            raise self._wrap(exc) from None

    def snapshot(self):
        try:
            return self._page.evaluate(SNAPSHOT_SCRIPT)
        except Exception as exc:
            raise self._wrap(exc) from None

    def _settle(self, timeout):
        try:
            self._page.wait_for_load_state('domcontentloaded', timeout=timeout * 1000)
        except Exception:
            pass

    def click(self, index, timeout):
        try:
            self._page.locator(INTERACTIVE_SELECTOR).nth(index).click(timeout=timeout * 1000)
        except Exception as exc:
            raise self._wrap(exc) from None
        self._settle(timeout)

    def type(self, index, text, timeout):
        try:
            self._page.locator(INTERACTIVE_SELECTOR).nth(index).fill(text, timeout=timeout * 1000)
        except Exception as exc:
            raise self._wrap(exc) from None

    def is_open(self):
        try:
            return bool(self._context.pages)
        except Exception:
            return False

    def close(self):
        try:
            self._context.close()
        finally:
            self._playwright.stop()


def playwright_launcher(profile_dir, headless):
    return PlaywrightDriver(profile_dir, headless=headless)


class BrowserProfile:
    """The one persistent profile: who may hold it now, and the owner's login window.

    Chromium allows one process per profile directory, so a Work's session
    and the login window are serialized by one non-blocking lock.  ``launcher``
    is injectable (``(profile_dir, headless) -> PageDriver``); the default
    needs the optional Playwright extra and is imported lazily.
    """

    def __init__(self, profile_dir, *, launcher=None, headless=True, available=None, clock=time.time):
        self.profile_dir = Path(profile_dir)
        self.launcher = launcher or playwright_launcher
        self.headless = headless
        self._available = available if available is not None else (lambda: playwright_available()) if launcher is None else (lambda: True)
        self.clock = clock
        self._lock = threading.Lock()
        self._holder = None
        self._login_thread = None

    def available(self):
        try:
            return bool(self._available())
        except Exception:
            return False

    def status(self):
        available = self.available()
        return {'available': available, 'install_hint': None if available else INSTALL_HINT,
                'profile_exists': self.profile_dir.is_dir() and any(self.profile_dir.iterdir()),
                'login_window_open': self._holder == 'login', 'in_use': self._holder is not None and self._holder != 'login',
                'last_login_at': None, 'headless': self.headless, 'limitation': LIMITATION_TEXT}

    def _acquire(self, holder):
        if not self._lock.acquire(blocking=False):
            raise ToolError(BUSY_TEXT, 'browser_busy')
        self._holder = holder

    def _release(self):
        self._holder = None
        try:
            self._lock.release()
        except RuntimeError:
            pass

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
            return _ReleasingDriver(driver, self._release)
        return launch

    def open_for_login(self, url, wait=False):
        """Open a headed window on the profile for the owner to log in by hand.

        AgentOS navigates to ``url`` and does nothing else: no typing, no
        reading.  The window is the owner's; the profile is released when
        every page is closed (or after ``LOGIN_WINDOW_SECONDS``).
        """
        if not self.available():
            return {'state': 'unavailable', 'install_hint': INSTALL_HINT}
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
                driver.goto(url, ACTION_TIMEOUT_SECONDS)
                opened.set()
                deadline = self.clock() + LOGIN_WINDOW_SECONDS
                while driver.is_open() and self.clock() < deadline:
                    time.sleep(0.5)
            except Exception as exc:
                failure.append(type(exc).__name__)
            finally:
                if driver is not None:
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
            opened.wait(ACTION_TIMEOUT_SECONDS + 5)
        if failure:
            return {'state': 'failed', 'message': FAILED_TEXT}
        return {'state': 'closed' if wait else 'opened', 'url': page_reference(url),
                'message': '브라우저 창에서 직접 로그인한 뒤 창을 닫아 주세요. AgentOS는 입력 내용을 보지 않습니다.'}


class _ReleasingDriver:
    """A driver whose ``close`` also releases the profile lock (once)."""

    def __init__(self, driver, release):
        self._driver, self._release = driver, release

    def __getattr__(self, name):
        return getattr(self._driver, name)

    def close(self):
        try:
            self._driver.close()
        finally:
            release, self._release = self._release, lambda: None
            release()
