"""SEC-BROWSER-01 (#656): browser action capability in the owner-logged-in profile.

Evidence classes, named separately:

* unit (model-free, fake driver): output mediation, the payment guard with and
  without an exact approval, the model's effect label never lifting the
  guard, generic login_required detection, budget/timeouts, tool schemas,
  the loop end to end with a scripted model, the service approval surfaces
  (Telegram buttons, web decision) and the secret-free durable records;
* integration (model-free, the real embedded WebKit worker, #680): in
  ``tests/test_browser_webkit.py``, macOS with PyObjC only, against the
  ``http.server`` fixture site defined here (product page -> 장바구니 -> cart
  page).

No site, provider or category is named in ``src``; the fixture below is the
test's own.
"""
import html
import json
import re
import shutil
import tempfile
import threading
import time
import unittest
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

from personal_agent import browser_session as bs
from personal_agent.agent_runtime import (BROWSER_ACTIONS, DEFINITIONS, Capabilities, ToolError, WorkBudget,
                                          action_definitions, evidence_summary, run_agent, withheld_effect)
from personal_agent.bounded_execution import CLI_PROFILES, route_unavailable
from personal_agent.manifests import BUILTIN_MANIFEST, HOST_ACTIONS, WRITE_ACTIONS, validate
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService, BROWSER_REQUESTS_KEY
from personal_agent.quickstart_store import QuickStore

CFG = {'provider': 'compatible', 'endpoint': 'https://openrouter.ai/api/v1', 'model': 'test-model'}
PASSWORD = 'hunter2-password-value'
OTP = '915533'
TOKEN = 'sk-live-ABCDEFGHIJKLMNOP1234'
PASSPORT = 'M12345678'
ORIGIN = 'http://fixture.test'

#: The test's own fixture site: a product page whose form adds to the cart, the
#: cart, an account page rendering secrets, a checkout form with card fields, a
#: login page.  Paths are relative; the fake driver and the HTTP server both
#: serve them.
PAGES = {
    '/product': f'''<html><head><title>세탁세제 3L</title></head><body>
      <h1>세탁세제 3L</h1><p>가격 12,900원</p><p>보관 위치 {PASSPORT}</p>
      <form action="/cart" method="post"><button type="submit">장바구니</button></form>
      <form action="/search" method="get"><input name="q" aria-label="검색어"><button type="submit">검색</button></form>
      <a href="/account">내 계정</a> <a href="/checkout">결제</a> <a href="/login">로그인</a>
      <a href="/hidden" style="display:none">숨김 링크</a>
    </body></html>''',
    '/cart': '''<html><head><title>장바구니</title></head><body><h1>장바구니</h1>
      <ul><li>세탁세제 3L × 1</li></ul><a href="/product">계속 쇼핑</a></body></html>''',
    '/search': '''<html><head><title>검색 결과</title></head><body><h1>검색 결과</h1><p>결과 없음</p></body></html>''',
    '/account': f'''<html><head><title>내 계정</title></head><body><h1>내 계정</h1>
      <p>API key: {TOKEN}</p>
      <label>비밀번호 <input type="password" name="pw" value="{PASSWORD}"></label>
      <label>인증 코드 <input type="text" autocomplete="one-time-code" name="otp" value="{OTP}"></label>
      <label>이름 <input type="text" name="name" value="홍길동"></label>
      <button type="button">저장</button></body></html>''',
    '/checkout': '''<html><head><title>결제</title></head><body><h1>결제</h1>
      <form action="/pay" method="post">
        <p>결제 금액 12,900원</p>
        <label>카드번호 <input type="text" autocomplete="cc-number" name="card"></label>
        <label>CVC <input type="text" autocomplete="cc-csc" name="cvc"></label>
        <label>받는 사람 <input type="text" autocomplete="name" name="who"></label>
        <button type="submit">결제하기</button>
      </form>
      <form action="/coupon" method="post"><label>쿠폰 <input type="text" name="coupon"></label><button type="submit">쿠폰 적용</button></form>
      </body></html>''',
    '/checkout-compound': '''<html><head><title>결제</title></head><body><h1>결제</h1>
      <form action="/pay" method="post">
        <label>카드 <input type="text" autocomplete="section-checkout billing cc-number" name="card" value="4242424242424242"></label>
        <label>보안코드 <input type="text" autocomplete="shipping cc-csc" name="cvc" value="987"></label>
        <label>확인 코드 <input type="text" autocomplete="one-time-code webauthn" name="otp" value="246810"></label>
        <label>메모 <input type="text" autocomplete="section-a shipping street-address" name="addr" value="서울"></label>
        <button type="submit">주문하기</button>
      </form></body></html>''',
    # #698: controls outside the payment form that submit it through a label or a script.
    '/checkout-forwarded': '''<html><head><title>빠른 결제</title></head><body><h1>빠른 결제</h1>
      <form id="payForm" action="/pay" method="post">
        <p>결제 금액 12,900원</p>
        <label>카드번호 <input type="text" autocomplete="cc-number" name="card"></label>
        <label>받는 사람 <input type="text" autocomplete="name" name="who" id="who"></label>
        <button type="submit" id="paybtn">결제하기</button>
      </form>
      <form id="couponForm" action="/coupon" method="post"><label>쿠폰 <input type="text" name="coupon"></label>
        <button type="submit">쿠폰 적용</button></form>
      <label for="paybtn"><span role="button">빠른 구매</span></label>
      <div role="button" onclick="payForm.submit()">바로 진행</div>
      <div role="button" onclick="payForm.requestSubmit()">요청 진행</div>
      <div role="button" onclick="couponForm.submit()">쿠폰 바로 적용</div>
      <div role="button" onclick="setTimeout(() => payForm.submit(), 1500)">나중에 진행</div>
      <div role="button" onclick="fetch('/validate').then(() => new Promise((ok) => setTimeout(ok, 800))).then(() => payForm.requestSubmit())">확인 후 진행</div>
      <div role="button" onclick="setTimeout(() => couponForm.submit(), 1500)">나중에 쿠폰</div>
      <div role="button" onclick="document.getElementById('who').value = '처리 중'; this.textContent = '처리 중…'; payForm.submit()">메모 후 진행</div>
      </body></html>''',
    # #698 P1-2: two identical payment forms; the label points at the first ...
    '/checkout-twins': '''<html><head><title>빠른 결제</title></head><body><h1>빠른 결제</h1>
      <form action="/pay" method="post"><p>결제 금액 12,900원</p>
        <label>카드번호 <input type="text" autocomplete="cc-number" name="card"></label>
        <button type="submit" id="payA">결제하기</button></form>
      <form action="/pay" method="post"><p>결제 금액 12,900원</p>
        <label>카드번호 <input type="text" autocomplete="cc-number" name="card"></label>
        <button type="submit" id="payB">결제하기</button></form>
      <label for="payA"><span role="button">빠른 구매</span></label>
      </body></html>''',
    # #700 P2-1: the pay button of one payment form whose handler submits another payment form.
    '/checkout-cross': '''<html><head><title>교차 결제</title></head><body><h1>교차 결제</h1>
      <form id="payA" action="/pay" method="post"><p>결제 금액 12,900원</p>
        <label>카드번호 <input type="text" autocomplete="cc-number" name="card"></label>
        <button type="button" onclick="payB.submit()">결제하기</button></form>
      <form id="payB" action="/pay-other" method="post"><p>결제 금액 990,000원</p>
        <label>카드번호 <input type="text" autocomplete="cc-number" name="card"></label>
        <input type="hidden" name="amount" value="990000"></form>
      </body></html>''',
    # #758: a stored payment method (no card field anywhere) behind controls named for a purchase.
    '/one-click': '''<html><head><title>원클릭</title></head><body><h1>세제 3L</h1><p>12,900원</p>
      <form action="/add" method="post"><button type="submit">담기</button></form>
      <form action="/order" method="post"><button type="submit" id="buyBtn">Buy now</button></form>
      <a href="/order" role="button">바로구매</a>
      <div role="button" onclick="fetch('/charge', {method: 'POST'})">Pay ₩12,900</div>
      <label for="buyBtn"><span role="button">빠른 진행</span></label>
      <a href="/reviews">구매후기</a>
      </body></html>''',
    '/order': '<html><head><title>주문 완료</title></head><body><h1>주문 완료</h1></body></html>',
    '/add': '<html><head><title>담음</title></head><body><h1>담았습니다</h1></body></html>',
    '/reviews': '<html><head><title>후기</title></head><body><h1>후기</h1></body></html>',
    '/validate': '<html><head><title>확인</title></head><body>ok</body></html>',
    '/reset/' + PASSPORT:'''<html><head><title>Reset token=abcDEF123456secret</title></head><body><h1>재설정</h1>
      <a href="https://owner:hunter2@fixture.test/reset/''' + PASSPORT + '''?code=1#x">다시 열기</a>
      <a href="https://fixture.test/help">도움말</a></body></html>''',
    '/pay': '''<html><head><title>결제 완료</title></head><body><h1>결제 완료</h1></body></html>''',
    '/coupon': '''<html><head><title>쿠폰</title></head><body><h1>쿠폰 적용됨</h1></body></html>''',
    '/login': '''<html><head><title>로그인</title></head><body><form action="/session" method="post">
      <label>이메일 <input type="email" name="email"></label>
      <label>비밀번호 <input type="password" name="password"></label>
      <button type="submit">로그인</button></form></body></html>''',
}
INTERACTIVE = ('a', 'button', 'input', 'select', 'textarea', 'summary')


class _PageParser(HTMLParser):
    """Turns fixture HTML into the raw snapshot shape the page script returns."""

    def __init__(self, url, values):
        super().__init__()
        self.url, self.values = url, values
        self.text, self.elements, self.forms = [], [], []
        self.form, self.form_count, self.index = None, 0, -1
        self.pending, self.label, self.label_info, self.skip = [], None, None, 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form':
            self.form_count += 1
            self.form = {'id': self.form_count, 'action': attrs.get('action', ''), 'method': attrs.get('method', 'get'),
                         'html_id': attrs.get('id')}
            self.forms.append(self.form)
        if tag == 'label':
            self.label = []
            self.label_info = {'for': attrs.get('for'), 'elements': []}
        if tag in ('script', 'style', 'head'):
            self.skip += 1
        if tag in INTERACTIVE or attrs.get('role'):
            self.index += 1
            if tag == 'a' and not attrs.get('href'):
                return
            hidden = 'display:none' in (attrs.get('style') or '').replace(' ', '')
            kind = (attrs.get('type') or ('text' if tag == 'input' else 'submit' if tag == 'button' else '')).lower()
            role = attrs.get('role') or {'a': 'link', 'button': 'button', 'select': 'combobox', 'textarea': 'textbox',
                                        'summary': 'button'}.get(tag) or ('button' if kind in ('submit', 'button', 'image', 'reset')
                                                                          else kind if kind in ('checkbox', 'radio') else 'textbox')
            value = self.values.get(self.index, attrs.get('value', ''))
            takes_value = (tag == 'input' and kind not in ('submit', 'button', 'image', 'reset', 'checkbox', 'radio', 'file', 'hidden')) or tag in ('textarea', 'select')
            element = {'index': self.index, 'role': role, 'name': attrs.get('aria-label') or attrs.get('placeholder') or
                       (value if tag == 'input' and kind in ('submit', 'button') else ''), 'href': urljoin(self.url, attrs['href']) if tag == 'a' else None,
                       'tag': tag, 'type': kind, 'autocomplete': (attrs.get('autocomplete') or '').lower(),
                       'value': value if takes_value else None, 'form': self.form['id'] if self.form else None,
                       'disabled': 'disabled' in attrs, 'hidden': hidden or kind == 'hidden', 'action': dict(self.form) if self.form else None,
                       'html_id': attrs.get('id'), 'onclick': attrs.get('onclick') or '', 'label': self.label_info, 'sent': value}
            if self.label_info is not None:
                self.label_info['elements'].append(element)
            self.elements.append(element)
            if not element['name'] and self.label is not None and self.label:
                element['name'] = ' '.join(self.label).strip()
            self.pending.append(element)

    def handle_endtag(self, tag):
        if tag == 'form':
            self.form = None
        if tag == 'label':
            self.label = self.label_info = None
        if tag in ('script', 'style', 'head'):
            self.skip -= 1
        if tag in INTERACTIVE and self.pending:
            self.pending.pop()

    def handle_data(self, data):
        text = ' '.join(data.split())
        if not text or self.skip:
            return
        self.text.append(text)
        if self.form is not None:
            self.form.setdefault('texts', []).append(text)
        if self.label is not None:
            self.label.append(text)
        for element in self.pending:
            if not element['name']:
                element['name'] = text

    def control(self, element):
        """The control the element's <label> forwards a press to, when it is another element (as the page script)."""
        label = element.get('label')
        if label is None:
            return None
        if label['for'] is not None:
            control = next((e for e in self.elements if e['html_id'] == label['for']), None)
        else:
            control = next((e for e in label['elements'] if e['tag'] in ('input', 'button', 'select', 'textarea')
                            and e['type'] != 'hidden'), None)
        return control if control is not element else None

    def record(self, form):
        """As the page script's ``formRecord``: position, method and resolved action."""
        return {'dom': form['id'] - 1, 'method': form['method'].lower(), 'action': urljoin(self.url, form['action'])}

    def cancelled(self, form):
        """As the worker's report of a cancelled submit (#700): the record, its page and the
        digest of what it would send (non-credential values and the form's text)."""
        rows = [f"{e.get('html_id') or e['index']}={'<guarded>' if bs.guarded_field(e) else e.get('sent') or ''}"
                for e in self.elements if e['form'] == form['id'] and e['tag'] in ('input', 'select', 'textarea')]
        state = '\n'.join(rows) + '\n\x1e' + '\n'.join(form.get('texts', []))
        return {**self.record(form), 'page': self.url, 'state': bs.digest(state)}

    def result(self, title):
        for element in self.elements:
            control = self.control(element)
            element['label_form'] = control['form'] if control else None
            element['own_text'] = ' '.join(filter(None, [element['name'], element['sent'] if element['tag'] == 'input'
                                                         and element['type'] in ('submit', 'button') else '']))
            pressable = lambda e: e['role'] not in ('textbox', 'combobox', 'checkbox', 'radio') and e['tag'] not in ('select', 'textarea')
            element['label_name'] = (control['name'] + ' | ' + control['name']) if control and pressable(control) else ''
            element['ancestor_text'], element['pressable'], element['context'] = '', pressable(element), ''
        private = ('hidden', 'action', 'html_id', 'onclick', 'label', 'sent')
        elements = [{k: v for k, v in e.items() if k not in private} for e in self.elements if not e['hidden']]
        forms = [{'id': form['id'], 'text': '\n'.join(form.get('texts', [])), **self.record(form)} for form in self.forms]
        return {'url': self.url, 'title': title, 'text': '\n'.join(self.text), 'elements': elements, 'forms': forms}, self.elements


from test_agency_loop import judgments


class FakeDriver:
    """A ``PageDriver`` over the fixture pages: links navigate, submit buttons post their form."""

    def __init__(self, pages=PAGES, origin=ORIGIN, log=None):
        self.pages, self.origin = pages, origin
        self.url, self.values, self.closed = None, {}, False
        self.log = log if log is not None else []
        self.posts, self.approved = [], []
        #: A payment-form submit the page's guard cancelled between steps (a
        #: test sets it, as a timer would); the next snapshot reports it once.
        self.cancelled = None
        #: The last cancelled submit, which ``release_submit`` may release once (#700).
        self.held = None

    def _path(self, url):
        return urlsplit(url).path or '/'

    def goto(self, url, timeout):
        self.log.append(('goto', url, timeout))
        if self._path(url) not in self.pages:
            raise RuntimeError('not found')
        self.url = url

    def _parse(self):
        parser = _PageParser(self.url, self.values.get(self.url, {}))
        page = self.pages[self._path(self.url)]
        parser.feed(page)
        title = page.split('<title>')[1].split('</title>')[0] if '<title>' in page else ''
        return parser.result(title) + (parser,)

    def snapshot(self):
        self.log.append(('snapshot', self.url))
        page = self._parse()[0]
        if self.cancelled is not None:
            page['cancelled_submit'], self.cancelled = self.cancelled, None
        return page

    @staticmethod
    def _submitted(element, parser):
        """The form a press on ``element`` submits: its own, through its label, or by its onclick script."""
        if element['type'] == 'submit' and element.get('action'):
            return element['action']
        control = parser.control(element)
        if control is not None and control['type'] == 'submit' and control.get('action'):
            return control['action']
        called = re.search(r'(\w+)\.(?:submit|requestSubmit)\(\)', element.get('onclick') or '')
        if called:
            return next((form for form in parser.forms if form.get('html_id') == called.group(1)), None)
        return None

    def _run_script(self, element, parser):
        """The DOM changes an onclick handler makes before it submits: ``getElementById('x').value = 'v'``."""
        for html_id, value in re.findall(r"getElementById\('(\w+)'\)\.value = '([^']*)'", element.get('onclick') or ''):
            target = next((e for e in parser.elements if e['html_id'] == html_id), None)
            if target is not None:
                self.values.setdefault(self.url, {})[target['index']] = value

    def click(self, index, timeout, approved=False):
        """As the worker: a submit of a payment form is cancelled and held unless an approved
        step's allowance names that form (its own or its label's payment form, else any, #700)."""
        self.log.append(('click', index, timeout))
        self.approved.append(approved)
        _, elements, parser = self._parse()
        element = next(e for e in elements if e['index'] == index)
        if element['tag'] == 'a':
            return self.goto(element['href'], timeout)
        self._run_script(element, parser)
        _, elements, parser = self._parse()
        element = next(e for e in elements if e['index'] == index)
        form = self._submitted(element, parser)
        if form is None:
            return None
        holds = lambda form_id: any(e['form'] == form_id and bs.payment_field(e) for e in elements)
        if holds(form['id']):
            control = parser.control(element)
            own = [f for f in (element['form'], control['form'] if control else None) if f is not None and holds(f)]
            allowed = own or [f['id'] for f in parser.forms if holds(f['id'])]
            if not approved or form['id'] not in allowed:
                self.held = parser.cancelled(form)
                refusal = ToolError(bs.APPROVAL_TEXT, 'approval_required', requires='browser-step-approval')
                refusal.cancelled_form = dict(self.held)
                raise refusal
        return self._post(form, timeout)

    def _post(self, form, timeout):
        self.posts.append((form['method'], form['action']))
        return self.goto(urljoin(self.url, form['action']), timeout)

    def hold(self, form_id):
        """A payment-form submit the page's guard cancelled between steps (as a timer would): the next snapshot reports it."""
        _, _, parser = self._parse()
        self.held = self.cancelled = parser.cancelled(next(f for f in parser.forms if f['id'] == form_id))

    def release_submit(self, record, timeout):
        """As the worker (#700): only the held submit, and only while its form would send the same state."""
        self.log.append(('release', dict(record)))
        held, self.held = self.held, None
        _, _, parser = self._parse()
        form = next((f for f in parser.forms if held and parser.record(f)['dom'] == held['dom']), None)
        if held is None or record != held or form is None or parser.cancelled(form) != held:
            raise ToolError(bs.TARGET_TEXT, 'target_unavailable')
        self._post(form, timeout)
        return {'navigated': True}

    def type(self, index, text, timeout, approved=False):
        self.log.append(('type', index, text, timeout))
        self.approved.append(approved)
        self.values.setdefault(self.url, {})[index] = text

    def is_open(self):
        return not self.closed

    def close(self):
        self.closed = True


class Approvals:
    """A scripted owner: ``issued`` bindings are consumed once; every refusal is recorded."""

    def __init__(self, *issued):
        self.issued = [bs.binding_digest(b) for b in issued]
        self.requests = []

    def issue(self, binding):
        self.issued.append(bs.binding_digest(binding))

    def consume(self, binding):
        key = bs.binding_digest(binding)
        if key in self.issued:
            self.issued.remove(key)
            return True
        return False

    def request(self, binding, description):
        self.requests.append((binding, description))


def session(driver=None, **kwargs):
    driver = driver or FakeDriver()
    return bs.BrowserSession(lambda: driver, work_id='work-1', **kwargs), driver


def call(ident, name, **args):
    return {'id': ident, 'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}


class Script:
    def __init__(self, *messages):
        self.messages, self.bodies = list(messages), []

    def __call__(self, url, body, headers=None, timeout=60):
        self.bodies.append(json.loads(json.dumps(body)))
        message = self.messages.pop(0) if self.messages else {'content': '끝났습니다.'}
        return {'choices': [{'message': message}]}


def flat(value):
    return json.dumps(value, ensure_ascii=False)


# ---------------------------------------------------------------- schemas

class ToolSchemaTests(unittest.TestCase):
    def test_five_browser_tools_are_declared_once_with_the_effect_enum(self):
        tools = {d['function']['name']: d['function']['parameters'] for d in DEFINITIONS if d['function']['name'] in BROWSER_ACTIONS}
        self.assertEqual(set(tools), {'browser_open', 'browser_read', 'browser_find', 'browser_click', 'browser_type'})
        self.assertEqual(tools['browser_open']['required'], ['url', 'effect'])
        self.assertEqual(tools['browser_read']['properties'], {})
        self.assertEqual(tools['browser_find']['required'], ['text'])
        self.assertEqual(tools['browser_click']['required'], ['target', 'effect'])
        self.assertEqual(tools['browser_type']['required'], ['target', 'text', 'effect'])
        for name in ('browser_open', 'browser_click', 'browser_type'):
            self.assertEqual(tools[name]['properties']['effect']['enum'], ['read', 'navigate', 'mutate', 'payment'])
            self.assertFalse(tools[name]['additionalProperties'])
        self.assertTrue(BROWSER_ACTIONS <= HOST_ACTIONS)
        self.assertEqual(WRITE_ACTIONS & BROWSER_ACTIONS, {'browser_click', 'browser_type'})
        validate(BUILTIN_MANIFEST)
        modes = {t['id']: t['mode'] for t in BUILTIN_MANIFEST['tools']}
        self.assertEqual((modes['browser_click'], modes['browser_read']), ('bounded_write', 'read_only'))

    def test_only_the_trusted_local_cli_profile_offers_the_browser(self):
        # #701: trusted-local serves the browser through the service relay; the
        # strict and isolated profiles declare it unavailable.
        from personal_agent.bounded_execution import BOUNDED_PROFILE, profile_actions
        for profile in CLI_PROFILES:
            unavailable = route_unavailable(profile)
            if profile == BOUNDED_PROFILE:
                self.assertTrue(BROWSER_ACTIONS <= set(profile_actions(profile)), profile)
                self.assertFalse(BROWSER_ACTIONS & set(unavailable), profile)
            else:
                self.assertTrue(BROWSER_ACTIONS <= set(unavailable), profile)
                self.assertFalse(BROWSER_ACTIONS & set(profile_actions(profile)), profile)

    def test_tools_are_offered_only_when_a_profile_is_registered(self):
        store = QuickStore(tempfile.mkdtemp())
        without = Capabilities(store, None, {}, '', 'w', lambda *a: None)
        self.assertFalse({d['function']['name'] for d in without.definitions()} & BROWSER_ACTIONS)
        with self.assertRaises(ToolError) as caught:
            without.execute('browser_read', {})
        self.assertEqual(caught.exception.code, 'needs_setup')
        with_browser = Capabilities(store, None, {}, '', 'w', lambda *a: None, browser=lambda: FakeDriver())
        self.assertTrue(BROWSER_ACTIONS <= {d['function']['name'] for d in with_browser.definitions()})
        self.assertEqual(len(action_definitions(with_browser.tools, BROWSER_ACTIONS)), 5)


# ---------------------------------------------------------------- mediation

class MediationTests(unittest.TestCase):
    def test_password_otp_values_and_a_rendered_token_never_leave_the_driver(self):
        sess, driver = session(excluded=lambda: [PASSPORT])
        page = sess.open({'url': ORIGIN + '/account', 'effect': 'read'})
        self.assertEqual(page['state'], 'page')
        self.assertEqual(page['url'], ORIGIN + '/account')
        text = flat(page)
        for secret in (PASSWORD, OTP, TOKEN):
            self.assertNotIn(secret, text)
        self.assertNotIn('<', page['text'])
        self.assertNotIn('_elements', page)
        self.assertNotIn('cookies', text)
        rows = {row['name']: row for row in page['elements']}
        self.assertNotIn('value', rows['비밀번호'])
        self.assertNotIn('value', rows['인증 코드'])
        self.assertEqual(rows['이름']['value'], '홍길동', 'an ordinary field keeps its value')
        self.assertIn('API key: ' + bs.REDACTED, page['text'])
        self.assertGreaterEqual(page['redacted_values'], 1)

    def test_page_exclusions_drop_only_the_words_the_owner_said(self):
        """#889: each value keeps the words the owner did not say in this request; untouched values stay verbatim."""
        from personal_agent.agent_runtime import page_exclusions
        self.assertEqual(page_exclusions(['배민'], '배민'), [])
        self.assertEqual(page_exclusions(['카카오골프, 더블이글 비교해 가장 싼 티 선호'], '카카오골프, 더블이글에서 가장 싼 티를 찾아줘'),
                         ['비교해 싼 티 선호'])  # a one-character word is never left out: kept
        self.assertEqual(page_exclusions([PASSPORT, '010-1234-5678'], '세탁세제 찾아줘'), [PASSPORT, '010-1234-5678'])
        self.assertEqual(page_exclusions([PASSPORT], ''), [PASSPORT])
        self.assertEqual(page_exclusions(['보관함 비밀 4719'], '보관함 알려줘'), ['비밀 4719'])
        # A particle-bearing owner word covers the value word it starts with.
        self.assertEqual(page_exclusions(['배민'], '배민으로 시켜줘'), [])
        # #889 review P2: a shorter owner word never covers a longer value word.
        self.assertEqual(page_exclusions(['johnsmith'], 'john 에게 메일 보내줘'), ['johnsmith'])
        self.assertEqual(page_exclusions(['golfzonpassword'], 'golfzon 예약해줘'), ['golfzonpassword'])
        self.assertEqual(page_exclusions(['김치냉장고 모델 X100'], '김치 레시피'), ['김치냉장고 모델 X100'])
        # #889 review P3: digits need the owner's exact words in the owner's order.
        self.assertEqual(page_exclusions(['333333-222-110'], '110-222-333333'), ['333333-222-110'])
        self.assertEqual(page_exclusions(['110-222-333333'], '110-222-333333 계좌'), [])
        self.assertEqual(page_exclusions(['010-1234-5678'], '1234번'), ['010 5678'])

    def test_saved_private_values_are_redacted_from_page_text(self):
        sess, _ = session(excluded=lambda: [PASSPORT])
        page = sess.open({'url': ORIGIN + '/product', 'effect': 'read'})
        self.assertNotIn(PASSPORT, flat(page))
        self.assertIn('보관 위치 ' + bs.REDACTED, page['text'])
        self.assertIn('가격 12,900원', page['text'], 'ordinary text stays')
        plain, _ = session()
        self.assertIn(PASSPORT, plain.open({'url': ORIGIN + '/product', 'effect': 'read'})['text'], 'nothing saved, nothing redacted')

    def test_hidden_elements_are_not_listed_and_numbers_are_stable_targets(self):
        sess, _ = session()
        page = sess.open({'url': ORIGIN + '/product', 'effect': 'navigate'})
        names = [row['name'] for row in page['elements']]
        self.assertEqual(names, ['장바구니', '검색어', '검색', '내 계정', '결제', '로그인'])
        self.assertEqual([row['n'] for row in page['elements']], [1, 2, 3, 4, 5, 6])
        self.assertEqual(page['elements'][3]['href'], ORIGIN + '/account')
        self.assertEqual(page['title'], '세탁세제 3L')

    def test_find_reports_lines_and_elements(self):
        sess, _ = session()
        sess.open({'url': ORIGIN + '/product', 'effect': 'read'})
        found = sess.find({'text': '장바구니'})
        self.assertTrue(found['found'])
        self.assertEqual([row['n'] for row in found['elements']], [1])
        self.assertFalse(sess.find({'text': '없는 텍스트'})['found'])

    def test_open_requires_http_and_read_requires_a_page(self):
        sess, _ = session()
        with self.assertRaises(ToolError) as caught:
            sess.read()
        self.assertEqual(caught.exception.code, 'no_page')
        with self.assertRaises(ValueError):
            sess.open({'url': 'file:///etc/passwd', 'effect': 'read'})
        with self.assertRaises(ValueError):
            sess.open({'url': ORIGIN + '/product', 'effect': 'purchase'})

    def test_title_url_and_hrefs_are_mediated_and_userinfo_dropped(self):
        sess, _ = session(excluded=lambda: [PASSPORT])
        page = sess.open({'url': 'https://owner:hunter2@fixture.test/reset/' + PASSPORT + '?t=1', 'effect': 'read'})
        text = flat(page)
        for secret in (PASSPORT, 'hunter2', 'abcDEF123456secret', 'owner:', 'code=1'):
            self.assertNotIn(secret, text)
        self.assertEqual(page['url'], 'https://fixture.test/reset/' + bs.REDACTED)
        self.assertIn(bs.REDACTED, page['title'])
        rows = {row['name']: row for row in page['elements']}
        self.assertEqual(rows['다시 열기']['href'], 'https://fixture.test/reset/' + bs.REDACTED)
        self.assertEqual(rows['도움말']['href'], 'https://fixture.test/help', 'ordinary links are unchanged')
        self.assertEqual(bs.page_reference('https://u:p@h.test:8443/x?y#z'), 'https://h.test:8443/x')
        found = sess.find({'text': '재설정'})
        self.assertNotIn(PASSPORT, flat(found))

    def test_page_reference_drops_query_and_fragment(self):
        self.assertEqual(bs.page_reference('https://h.test/p?session=abc#x'), 'https://h.test/p')
        snapshot = evidence_summary('browser_open', {'state': 'page', 'url': 'https://h.test/p', 'title': 't', 'text': 'x' * 10,
                                                     'elements': [{'n': 1}], 'redacted_values': 2})
        self.assertEqual(snapshot, {'state': 'page', 'url': 'https://h.test/p', 'title': 't', 'element_count': 1,
                                    'characters': 10, 'redacted_values': 2, 'found': None})


# ---------------------------------------------------------------- payment guard

class PaymentGuardTests(unittest.TestCase):
    def setUp(self):
        self.approvals = Approvals()
        self.sess, self.driver = session(approvals=self.approvals, steps=40)
        self.sess.open({'url': ORIGIN + '/checkout', 'effect': 'navigate'})

    def refused(self, fn, *args):
        with self.assertRaises(ToolError) as caught:
            fn(*args)
        self.assertEqual(caught.exception.code, 'approval_required')
        self.assertEqual(caught.exception.requires, 'browser-step-approval')
        self.assertEqual(str(caught.exception), bs.APPROVAL_TEXT)
        return caught.exception

    def test_card_fields_and_their_form_button_need_approval_whatever_the_label_says(self):
        for effect in ('read', 'navigate', 'mutate', 'payment'):
            self.refused(self.sess.type, {'target': '카드번호', 'text': '4111', 'effect': effect})
            self.refused(self.sess.type, {'target': 'CVC', 'text': '123', 'effect': effect})
            self.refused(self.sess.click, {'target': '결제하기', 'effect': effect})
        self.assertEqual([entry for entry in self.driver.log if entry[0] in ('type', 'click')], [], 'nothing reached the page')
        self.assertEqual(len(self.approvals.requests), 12)
        binding, description = self.approvals.requests[0]
        self.assertEqual(set(binding), set(bs.BINDING_FIELDS))
        self.assertEqual((binding['work_id'], binding['action']), ('work-1', 'browser_type'))
        self.assertEqual(binding['page_digest'], bs.digest(ORIGIN + '/checkout'))
        self.assertEqual(binding['argument_digest'], bs.digest('4111'))
        self.assertNotIn('4111', repr(self.approvals.requests), 'the typed text is never carried, only its digest')
        self.assertIn('카드번호', description)

    def test_ordinary_fields_and_buttons_proceed_and_the_label_can_only_add(self):
        # A field of the payment form that is not a card field, and another form's button: no approval.
        self.sess.type({'target': '받는 사람', 'text': '홍길동', 'effect': 'mutate'})
        page = self.sess.click({'target': '쿠폰 적용', 'effect': 'mutate'})
        self.assertEqual(page['title'], '쿠폰')
        self.sess.open({'url': ORIGIN + '/checkout', 'effect': 'navigate'})
        # The model's own `payment` label adds the requirement on an ordinary control.
        self.refused(self.sess.click, {'target': '쿠폰 적용', 'effect': 'payment'})
        self.refused(self.sess.open, {'url': ORIGIN + '/pay', 'effect': 'payment'})

    def refused_binding(self, pages, action, args):
        """The binding a fresh session is refused on (what the owner then approves)."""
        probe = Approvals()
        sess, _ = session(FakeDriver(pages), approvals=probe)
        sess.open({'url': ORIGIN + '/checkout', 'effect': 'navigate'})
        with self.assertRaises(ToolError):
            getattr(sess, action)(args)
        return probe.requests[-1][0]

    def test_an_exact_approval_is_consumed_once_and_only_for_its_binding(self):
        approvals = Approvals(self.refused_binding(PAGES, 'type', {'target': '카드번호', 'text': '4111', 'effect': 'payment'}))
        sess, driver = session(approvals=approvals)
        sess.open({'url': ORIGIN + '/checkout', 'effect': 'navigate'})
        # Same page, different target (CVC): refused.  Same target on another page: refused.
        with self.assertRaises(ToolError):
            sess.type({'target': 'CVC', 'text': '1', 'effect': 'payment'})
        sess.type({'target': '카드번호', 'text': '4111', 'effect': 'payment'})
        self.assertIn(('type', 0, '4111'), [entry[:3] for entry in driver.log], 'the driver index of the card field')
        with self.assertRaises(ToolError) as caught:
            sess.type({'target': '카드번호', 'text': '4111', 'effect': 'payment'})
        self.assertEqual(caught.exception.code, 'approval_required', 'one approval, one step')

    def test_different_text_or_a_changed_form_does_not_consume_the_approval(self):
        approved = self.refused_binding(PAGES, 'type', {'target': '카드번호', 'text': '4111', 'effect': 'payment'})
        # The resumed run types different text: a new request, the approval is left unspent.
        approvals = Approvals(approved)
        sess, driver = session(approvals=approvals)
        sess.open({'url': ORIGIN + '/checkout', 'effect': 'navigate'})
        with self.assertRaises(ToolError) as caught:
            sess.type({'target': '카드번호', 'text': '5555', 'effect': 'payment'})
        self.assertEqual(caught.exception.code, 'approval_required')
        self.assertEqual(len(approvals.issued), 1, 'the old approval was not consumed')
        self.assertEqual(approvals.requests[-1][0]['argument_digest'], bs.digest('5555'))
        # The form's total changed on the same URL: also a new request.
        changed = dict(PAGES)
        changed['/checkout'] = PAGES['/checkout'].replace('결제 금액 12,900원', '결제 금액 129,000원')
        sess, driver = session(FakeDriver(changed), approvals=approvals)
        sess.open({'url': ORIGIN + '/checkout', 'effect': 'navigate'})
        with self.assertRaises(ToolError):
            sess.type({'target': '카드번호', 'text': '4111', 'effect': 'payment'})
        self.assertEqual(len(approvals.issued), 1)
        self.assertNotEqual(approvals.requests[-1][0]['state_digest'], approved['state_digest'])
        self.assertEqual([entry for entry in driver.log if entry[0] == 'type'], [])
        # A changed field value of the form (quantity, recipient) changes the state of the button too.
        click = self.refused_binding(PAGES, 'click', {'target': '결제하기', 'effect': 'navigate'})
        approvals = Approvals(click)
        sess, driver = session(approvals=approvals, steps=40)
        sess.open({'url': ORIGIN + '/checkout', 'effect': 'navigate'})
        sess.type({'target': '받는 사람', 'text': '다른 사람', 'effect': 'mutate'})
        with self.assertRaises(ToolError):
            sess.click({'target': '결제하기', 'effect': 'navigate'})
        self.assertEqual(len(approvals.issued), 1)
        # Unchanged page, same button: the approval is spent and the click runs.
        sess.open({'url': ORIGIN + '/checkout', 'effect': 'navigate'})
        driver.values.clear()
        sess.click({'target': '결제하기', 'effect': 'navigate'})
        self.assertEqual(driver.posts, [('post', '/pay')])
        self.assertEqual(approvals.issued, [])

    def test_compound_autocomplete_tokens_are_redacted_and_guarded(self):
        self.assertEqual(bs.autocomplete_field('section-checkout billing cc-number'), 'cc-number')
        self.assertEqual(bs.autocomplete_field('shipping cc-csc'), 'cc-csc')
        self.assertEqual(bs.autocomplete_field('one-time-code webauthn'), 'one-time-code')
        self.assertEqual(bs.autocomplete_field('  Section-A HOME tel  '), 'tel')
        self.assertEqual(bs.autocomplete_field(''), '')
        approvals = Approvals()
        sess, driver = session(approvals=approvals, steps=40)
        page = sess.open({'url': ORIGIN + '/checkout-compound', 'effect': 'navigate'})
        for secret in ('4242424242424242', '987', '246810'):
            self.assertNotIn(secret, flat(page))
        rows = {row['name']: row for row in page['elements']}
        self.assertEqual(rows['메모']['value'], '서울', 'a non-credential compound token keeps its value')
        for target in ('카드', '보안코드', '확인 코드'):
            with self.assertRaises(ToolError) as caught:
                sess.type({'target': target, 'text': '1', 'effect': 'mutate'})
            self.assertEqual(caught.exception.code, 'approval_required', target)
        with self.assertRaises(ToolError) as caught:
            sess.click({'target': '주문하기', 'effect': 'navigate'})
        self.assertEqual(caught.exception.code, 'approval_required', 'the submit of a form with those fields')
        self.assertEqual([entry for entry in driver.log if entry[0] in ('type', 'click')], [])

    def test_password_fields_are_guarded_too(self):
        sess, _ = session()
        sess.open({'url': ORIGIN + '/account', 'effect': 'read'})
        with self.assertRaises(ToolError) as caught:
            sess.type({'target': '비밀번호', 'text': 'x', 'effect': 'mutate'})
        self.assertEqual(caught.exception.code, 'approval_required')
        with self.assertRaises(ToolError) as caught:
            sess.type({'target': '인증 코드', 'text': '000000', 'effect': 'mutate'})
        self.assertEqual(caught.exception.code, 'approval_required')
        sess.type({'target': '이름', 'text': '김철수', 'effect': 'mutate'})


class ForwardedSubmitTests(unittest.TestCase):
    """#698: a label or a script outside the payment form that submits it needs the same approval."""

    def setUp(self):
        self.approvals = Approvals()
        self.sess, self.driver = session(approvals=self.approvals, steps=40)
        self.page = self.sess.open({'url': ORIGIN + '/checkout-forwarded', 'effect': 'navigate'})

    def refused(self, target):
        with self.assertRaises(ToolError) as caught:
            self.sess.click({'target': target, 'effect': 'mutate'})
        self.assertEqual((caught.exception.code, caught.exception.requires), ('approval_required', 'browser-step-approval'))
        return self.approvals.requests[-1][0]

    def test_a_label_forwarding_to_the_pay_button_is_classified_and_never_reaches_the_page(self):
        rows = {row['name']: row for row in self.sess.last['_elements']}
        self.assertTrue(rows['빠른 구매']['submit_guarded'], 'the span inside <label for=paybtn> presses the pay button')
        self.assertTrue(rows['빠른 구매']['forwards_payment'])
        self.assertFalse(rows['쿠폰 적용']['submit_guarded'])
        for name in ('카드번호', '쿠폰'):
            self.assertFalse(rows[name]['forwards_payment'], 'a field inside its own label forwards nothing')
        binding = self.refused('빠른 구매')
        self.assertEqual(binding['action'], 'browser_click')
        self.assertEqual([entry for entry in self.driver.log if entry[0] == 'click'], [], 'refused before the driver')
        self.assertEqual(self.driver.posts, [])

    def test_the_label_control_is_part_of_the_descriptor_the_worker_checks(self):
        elements = [{'index': 0, 'tag': 'input', 'autocomplete': 'cc-number', 'form': 1},
                    {'index': 1, 'tag': 'button', 'role': 'button', 'form': 1},
                    {'index': 2, 'tag': 'span', 'role': 'button', 'form': None, 'label_form': 1},
                    {'index': 3, 'tag': 'span', 'role': 'button', 'form': None, 'label_form': 2}]
        self.assertTrue(bs.guarded_submit(elements[2], elements))
        self.assertFalse(bs.guarded_submit(elements[3], elements), 'a label into an ordinary form')
        self.assertTrue(bs.forwards_to_payment_form(elements[2], bs.payment_forms(elements)))

    def test_a_scripted_submit_of_the_payment_form_is_refused_by_the_driver_and_asks_the_owner(self):
        for target in ('바로 진행', '요청 진행'):
            binding = self.refused(target)
            # #700: bound to the cancelled form and what it would send, not to the step.
            self.assertEqual((binding['action'], binding['page_digest'], binding['target_digest']),
                             ('browser_submit', bs.digest(ORIGIN + '/checkout-forwarded'),
                              bs.digest(f'form 0|post|{ORIGIN}/pay')))
            self.assertIn(target, self.approvals.requests[-1][1], 'the owner reads the step that caused it')
            self.assertIn(bs.CANCELLED_NOTE, self.approvals.requests[-1][1])
        self.assertEqual(self.driver.approved, [False, False], 'the driver was told the steps had no approval')
        self.assertEqual(self.driver.posts, [], 'no payment form was submitted')
        self.assertEqual(len(self.approvals.requests), 2)
        self.assertEqual(self.approvals.requests[0][0], self.approvals.requests[1][0], 'the same form in the same state')

    def test_a_scripted_submit_of_an_ordinary_form_still_runs(self):
        page = self.sess.click({'target': '쿠폰 바로 적용', 'effect': 'mutate'})
        self.assertEqual(page['title'], '쿠폰')
        self.sess.open({'url': ORIGIN + '/checkout-forwarded', 'effect': 'navigate'})
        self.sess.click({'target': '쿠폰 적용', 'effect': 'mutate'})
        self.assertEqual(self.driver.posts, [('post', '/coupon'), ('post', '/coupon')])
        self.assertEqual(self.approvals.requests, [])

    def test_an_approved_forwarded_submit_runs_once(self):
        # The label's span is refused before the page (a click binding): the approved click
        # carries the allowance.  The scripted div's submit is cancelled and held (a submit
        # binding): the approved form in that state is released by the worker (#700).
        for target, action, approved in (('바로 진행', 'browser_submit', False), ('빠른 구매', 'browser_click', True)):
            binding = self.refused(target)
            self.assertEqual(binding['action'], action)
            self.approvals.issued.append(bs.binding_digest(binding))
            self.sess.open({'url': ORIGIN + '/checkout-forwarded', 'effect': 'navigate'})
            page = self.sess.click({'target': target, 'effect': 'mutate'})
            self.assertEqual(page['title'], '결제 완료')
            self.assertTrue(page['navigated'])
            self.assertEqual(self.driver.approved[-1], approved)
            self.assertEqual(self.approvals.issued, [], 'one approval, one step')
            self.sess.open({'url': ORIGIN + '/checkout-forwarded', 'effect': 'navigate'})
            self.refused(target)
        self.assertEqual(self.driver.posts, [('post', '/pay'), ('post', '/pay')])
        self.assertEqual(len([entry for entry in self.driver.log if entry[0] == 'release']), 1)

    def test_an_approved_step_lets_only_its_own_payment_form_through(self):
        # #700 P2-1: the approved pay button of one form cannot carry a submit of another.
        approvals = Approvals()
        sess, driver = session(approvals=approvals, steps=40)
        sess.open({'url': ORIGIN + '/checkout-cross', 'effect': 'navigate'})
        with self.assertRaises(ToolError):
            sess.click({'target': '결제하기', 'effect': 'mutate'})
        click = approvals.requests[-1][0]
        self.assertEqual(click['action'], 'browser_click')
        approvals.issued.append(bs.binding_digest(click))
        with self.assertRaises(ToolError) as caught:
            sess.click({'target': '결제하기', 'effect': 'mutate'})
        self.assertEqual(caught.exception.code, 'approval_required')
        self.assertEqual(driver.approved[-1], True, 'the step was approved')
        submit = approvals.requests[-1][0]
        self.assertEqual((submit['action'], submit['target_digest']),
                         ('browser_submit', bs.digest(f'form 1|post|{ORIGIN}/pay-other')), 'the other form is asked for')
        self.assertEqual((approvals.issued, driver.posts), ([], []))

    def approved_binding(self, target, pages=PAGES, path='/checkout-forwarded'):
        """The binding a fresh session is refused on for ``target`` (what the owner then approves)."""
        probe = Approvals()
        sess, _ = session(FakeDriver(pages), approvals=probe, steps=40)
        sess.open({'url': ORIGIN + path, 'effect': 'navigate'})
        with self.assertRaises(ToolError):
            sess.click({'target': target, 'effect': 'mutate'})
        return probe.requests[-1][0]

    def test_a_changed_non_card_value_of_the_payment_form_asks_again(self):
        # Review P1-2: the label's span and the scripted div sit outside the form.
        for target in ('빠른 구매', '바로 진행'):
            approvals = Approvals(self.approved_binding(target))
            sess, driver = session(approvals=approvals, steps=40)
            sess.open({'url': ORIGIN + '/checkout-forwarded', 'effect': 'navigate'})
            sess.type({'target': '받는 사람', 'text': '다른 사람', 'effect': 'mutate'})
            with self.assertRaises(ToolError) as caught:
                sess.click({'target': target, 'effect': 'mutate'})
            self.assertEqual(caught.exception.code, 'approval_required', target)
            self.assertEqual(len(approvals.issued), 1, 'the approval of the unchanged form is not spent')
            self.assertEqual(driver.posts, [])
            driver.values.clear()
            sess.open({'url': ORIGIN + '/checkout-forwarded', 'effect': 'navigate'})
            self.assertEqual(sess.click({'target': target, 'effect': 'mutate'})['title'], '결제 완료')
            self.assertEqual((approvals.issued, driver.posts), ([], [('post', '/pay')]))

    def test_a_label_pointed_at_another_identical_payment_form_asks_again(self):
        retargeted = dict(PAGES)
        retargeted['/checkout-twins'] = PAGES['/checkout-twins'].replace('for="payA"', 'for="payB"')
        approved = self.approved_binding('빠른 구매', PAGES, '/checkout-twins')
        approvals = Approvals(approved)
        sess, driver = session(FakeDriver(retargeted), approvals=approvals)
        sess.open({'url': ORIGIN + '/checkout-twins', 'effect': 'navigate'})
        with self.assertRaises(ToolError):
            sess.click({'target': '빠른 구매', 'effect': 'mutate'})
        self.assertEqual(len(approvals.issued), 1)
        self.assertNotEqual(approvals.requests[-1][0]['state_digest'], approved['state_digest'])
        self.assertEqual(driver.posts, [])
        sess, driver = session(approvals=approvals)
        sess.open({'url': ORIGIN + '/checkout-twins', 'effect': 'navigate'})
        sess.click({'target': '빠른 구매', 'effect': 'mutate'})
        self.assertEqual((approvals.issued, driver.posts), ([], [('post', '/pay')]), 'the original label spends it')

    def test_a_submit_cancelled_after_the_step_answered_is_reported_by_the_next_snapshot(self):
        # Review P1-1: a timer or async callback submits the payment form after the step.
        self.sess.type({'target': '쿠폰', 'text': 'SAVE', 'effect': 'mutate'})
        self.driver.hold(1)
        with self.assertRaises(ToolError) as caught:
            self.sess.read()
        self.assertEqual(caught.exception.code, 'approval_required')
        binding, description = self.approvals.requests[-1]
        # #700: bound to the cancelled form's own submitted state; the owner reads the step.
        self.assertEqual((binding['action'], binding['target_digest']), ('browser_submit', bs.digest(f'form 0|post|{ORIGIN}/pay')))
        self.assertIn("'쿠폰' 입력란에 입력", description)
        self.assertIn(bs.CANCELLED_NOTE, description)
        self.assertIn('/pay', description)
        self.assertEqual(self.sess.read()['title'], '빠른 결제', 'reported once')
        # With no step of this session yet, the form's own submit is asked.
        approvals = Approvals()
        sess, driver = session(approvals=approvals)
        sess.open({'url': ORIGIN + '/checkout-forwarded', 'effect': 'navigate'})
        driver.hold(1)
        with self.assertRaises(ToolError):
            sess.read()
        self.assertEqual(approvals.requests[-1][0]['action'], 'browser_submit')
        self.assertTrue(approvals.requests[-1][1].startswith('결제 양식 제출'))
        self.assertEqual(driver.posts, [])

    def test_an_approved_deferred_submit_is_released_instead_of_asked_again(self):
        # #700 P2-2: async validation submits after the step; once the owner approved that
        # form in that state, the next cancelled submit of it is released, not asked again.
        self.sess.click({'target': '쿠폰 적용', 'effect': 'mutate'})
        self.sess.open({'url': ORIGIN + '/checkout-forwarded', 'effect': 'navigate'})
        self.driver.hold(1)
        with self.assertRaises(ToolError):
            self.sess.read()
        self.approvals.issued.append(bs.binding_digest(self.approvals.requests[-1][0]))
        asked = len(self.approvals.requests)
        # The resumed run repeats the step; its deferred submit is cancelled again and reported.
        sess, driver = session(self.driver, approvals=self.approvals, steps=40)
        sess.open({'url': ORIGIN + '/checkout-forwarded', 'effect': 'navigate'})
        driver.hold(1)
        page = sess.read()
        self.assertEqual(page['title'], '결제 완료', 'the released submit landed and that page is read')
        self.assertEqual((len(self.approvals.requests), self.approvals.issued), (asked, []), 'not asked again')
        self.assertEqual(driver.posts, [('post', '/coupon'), ('post', '/pay')])
        # A released submit is spent: the next one asks again.
        sess.open({'url': ORIGIN + '/checkout-forwarded', 'effect': 'navigate'})
        driver.hold(1)
        with self.assertRaises(ToolError):
            sess.read()
        self.assertEqual(driver.posts, [('post', '/coupon'), ('post', '/pay')])

    def test_a_handler_that_changes_the_form_before_submitting_matches_on_the_resumed_step(self):
        # #700 item 4: the unapproved click's handler changes the form (a recipient
        # value) and its own text, then submits.  The approval is bound to what the
        # submit sends, so the repeated step matches whether or not the page was reloaded.
        before = self.sess.last['_states']
        binding = self.refused('메모 후 진행')
        self.assertEqual(binding['action'], 'browser_submit')
        changed = self.sess.read()
        self.assertIn('처리 중', [row.get('value') for row in changed['elements']], 'the handler changed the form')
        self.assertNotEqual(self.sess.last['_states'], before, 'a binding to the pre-click page would no longer match')
        self.approvals.issued.append(bs.binding_digest(binding))
        # The same run repeats the step on the changed page: it matches.
        page = self.sess.click({'target': '메모 후 진행', 'effect': 'mutate'})
        self.assertEqual(page['title'], '결제 완료')
        self.assertEqual((self.approvals.issued, self.driver.posts), ([], [('post', '/pay')]))
        # A resumed run that opens the page again matches too.
        approvals = Approvals(binding)
        sess, driver = session(approvals=approvals, steps=40)
        sess.open({'url': ORIGIN + '/checkout-forwarded', 'effect': 'navigate'})
        self.assertEqual(sess.click({'target': '메모 후 진행', 'effect': 'mutate'})['title'], '결제 완료')
        self.assertEqual((approvals.issued, driver.posts), ([], [('post', '/pay')]))

    def test_a_hidden_amount_is_part_of_the_submitted_state(self):
        # #700 item 5: a hidden input the owner never sees (the amount) is bound too.
        approvals = Approvals()
        sess, driver = session(approvals=approvals, steps=40)
        sess.open({'url': ORIGIN + '/checkout-cross', 'effect': 'navigate'})
        driver.hold(2)
        with self.assertRaises(ToolError):
            sess.read()
        approvals.issued.append(bs.binding_digest(approvals.requests[-1][0]))
        cheaper = dict(PAGES)
        cheaper['/checkout-cross'] = PAGES['/checkout-cross'].replace('value="990000"', 'value="1"')
        driver.pages = cheaper
        driver.hold(2)
        with self.assertRaises(ToolError):
            sess.read()
        self.assertEqual(len(approvals.issued), 1, 'another amount is another approval')
        self.assertNotEqual(approvals.requests[-1][0]['state_digest'], approvals.requests[-2][0]['state_digest'])
        self.assertEqual(driver.posts, [])

    def test_an_issued_submit_approval_never_lifts_a_guarded_press(self):
        # #700 re-review P1: a press can pay by fetch with no submit to hold, so a guarded
        # press needs its own approval even while an approval of a cancelled submit is issued.
        # (A pay button whose submit comes after its window therefore asks again: fail closed.)
        self.driver.hold(1)
        with self.assertRaises(ToolError):
            self.sess.read()
        self.approvals.issue(self.approvals.requests[-1][0])
        pay = next(row for row in self.sess.last['_elements'] if row['tag'] == 'button' and row['submit_guarded'])
        binding = self.refused(str(pay['n']))
        self.assertEqual(binding['action'], 'browser_click')
        self.assertEqual(len(self.approvals.issued), 1, 'the submit approval is left unspent')
        self.assertEqual([entry for entry in self.driver.log if entry[0] == 'click'], [], 'refused before the page')
        self.assertEqual(self.driver.posts, [])

    def test_a_release_the_worker_refuses_fails_typed_and_spends_the_approval(self):
        binding = self.refused('바로 진행')
        self.approvals.issued.append(bs.binding_digest(binding))
        self.driver.hold(1)
        self.driver.held = dict(self.driver.held, state='changed')   # the page's held submit changed since
        with self.assertRaises(ToolError) as caught:
            self.sess.read()
        self.assertEqual(caught.exception.code, 'target_unavailable')
        self.assertEqual((self.approvals.issued, self.driver.posts), ([], []))


class CommitControlTests(unittest.TestCase):
    """#758: a press whose control commits a purchase needs approval with no card field on the page."""

    def test_commitment_signals_across_languages_and_what_they_leave_out(self):
        for name in ('Buy now', 'Pay ₩12,900', 'Pay with Apple Pay', 'Place your order', 'Complete purchase',
                     'Confirm order', 'Order now', 'Subscribe', 'Donate', 'Start your free trial', 'Send money',
                     'Top up', 'Express checkout', '결제하기', '바로구매', '주문하기', '구매 확정', '12,900원 결제',
                     '간편결제', '송금하기', '충전하기', '購入手続きへ', '注文を確定する', '支払う', '立即购买',
                     '提交订单', '付款'):
            self.assertTrue(bs.commit_name(name), name)
        # Review of #763: more phrasings, and text a page disguises with full-width or zero-width characters.
        for name in ('Order', 'Order • $23.50', 'Buy protection plan', 'Start subscription', 'Send $20', 'Upgrade now',
                     '결제 12,000원', '결제 (12,000원)', '구독 시작하기', '정기결제 시작', '立即订购', '立即訂購',
                     'Ｂｕｙ ｎｏｗ', 'Bu\u200by now', '결\u200b제하기'):
            self.assertTrue(bs.commit_name(name), name)
        for name in ('Purchase history', 'Payment methods', 'Add to wishlist', 'Buying guide', 'Checkout', 'Order history',
                     '구매후기', '주문내역', '결제수단 변경', '담기', '購入履歴', '支払い方法', '決済方法', '支付方式', '支付宝',
                     '', None, 'Continue'):
            self.assertFalse(bs.commit_name(name), name)
        # A bare verb in a long link title is an article, not a control; in a short one it counts.
        self.assertFalse(bs.commit_name('Best laptops to buy in 2026', link=True))
        self.assertTrue(bs.commit_name('Buy now', link=True))
        self.assertTrue(bs.commit_name('Place your order and track it later from your account', link=True))
        self.assertTrue(bs.commit_control({'role': 'button', 'tag': 'div', 'name': 'Pay now'}))
        self.assertTrue(bs.commit_control({'role': 'link', 'tag': 'a', 'name': '바로구매'}))
        self.assertFalse(bs.commit_control({'role': 'textbox', 'tag': 'input', 'name': 'Buy now', 'pressable': False}),
                         'a field commits nothing')
        self.assertTrue(bs.commit_control({'role': 'none', 'tag': 'input', 'type': 'submit', 'name': 'placeOrder1',
                                           'own_text': 'Place order', 'pressable': True}), 'any role: its own text')
        self.assertTrue(bs.commit_control({'role': 'button', 'tag': 'span', 'name': '빠른 진행',
                                           'label_name': 'Continue | Buy now'}), 'a label forwarding to it')
        self.assertTrue(bs.commit_control({'role': 'button', 'tag': 'span', 'name': 'Details',
                                           'ancestor_text': 'Card | Buy now ₩12,900'}), 'inside it: the press bubbles')
        self.assertFalse(bs.commit_control({'role': 'checkbox', 'tag': 'input', 'name': 'x', 'pressable': False,
                                            'label_name': ''}))
        # Review of 0008f29: a styled link that runs a script is a button; a wrapper's long text
        # is content (only a phrase there counts); a pay control a few wrappers up still counts.
        song = {'role': 'link', 'tag': 'a', 'name': 'Purchase this song for $0.99', 'pressable': True}
        self.assertTrue(bs.commit_control({**song, 'nav_link': False}))
        self.assertFalse(bs.commit_control({**song, 'nav_link': True}))
        wrapper = 'Our plans. ' + 'A long description of every plan and what it includes. ' * 4
        self.assertFalse(bs.commit_control({'role': 'button', 'tag': 'span', 'name': 'Read more',
                                            'ancestor_text': 'Subscribe now | ' + wrapper + 'Subscribe now'}),
                         'an app-root wrapper: its name is cut, its own text shows its length')
        self.assertTrue(bs.commit_control({'role': 'button', 'tag': 'span', 'name': 'i',
                                           'ancestor_text': 'Plan | Purchase annual plan for $99/yr'}), 'a control-sized parent')
        self.assertTrue(bs.commit_control({'role': 'button', 'tag': 'span', 'name': 'Details',
                                           'ancestor_text': 'Card | Card view || Buy now | Buy now'}))

    def test_one_click_controls_need_approval_before_the_page_and_ordinary_ones_run(self):
        approvals = Approvals()
        sess, driver = session(approvals=approvals, steps=40)
        sess.open({'url': ORIGIN + '/one-click', 'effect': 'navigate'})
        for target in ('Buy now', '바로구매', 'Pay ₩12,900', '빠른 진행'):
            with self.assertRaises(ToolError) as caught:
                sess.click({'target': target, 'effect': 'mutate'})
            self.assertEqual((caught.exception.code, caught.exception.requires), ('approval_required', 'browser-step-approval'))
        self.assertEqual([entry for entry in driver.log if entry[0] == 'click'], [], 'refused before the page')
        self.assertEqual(len(approvals.requests), 4)
        self.assertTrue(approvals.requests[3][1].startswith("결제 신호 'Buy now'"), 'the owner reads what the label forwards to')

    def test_a_changed_purchase_text_or_price_is_another_approval(self):
        # #763 review (Codex): a neutral name ("Continue") whose button value says "Buy $10":
        # the approval binds that text, so "Buy $1000" on the resumed run asks again.
        page = """<html><head><title>곡</title></head><body><form action="/order" method="post">
          <input type="submit" aria-label="Continue" value="Buy $10"></form></body></html>"""
        pages = {**PAGES, '/song': page}
        approvals = Approvals()
        sess, driver = session(FakeDriver(pages), approvals=approvals)
        sess.open({'url': ORIGIN + '/song', 'effect': 'navigate'})
        with self.assertRaises(ToolError):
            sess.click({'target': 'Continue', 'effect': 'mutate'})
        self.assertIn('Buy $10', approvals.requests[-1][1])
        approvals.issue(approvals.requests[-1][0])
        driver.pages = {**PAGES, '/song': page.replace('Buy $10', 'Buy $1000')}
        with self.assertRaises(ToolError):
            sess.click({'target': 'Continue', 'effect': 'mutate'})
        self.assertEqual((len(approvals.issued), driver.posts), (1, []), 'the approval of $10 is not spent on $1000')
        driver.pages = pages
        self.assertEqual(sess.click({'target': 'Continue', 'effect': 'mutate'})['title'], '주문 완료')

    def test_a_form_post_refused_between_steps_is_reported_to_the_model(self):
        sess, driver = session()
        sess.open({'url': ORIGIN + '/one-click', 'effect': 'navigate'})
        original = driver.snapshot
        driver.snapshot = lambda: {**original(), 'refused_submit': True}
        # The click's own first snapshot reads the report; the result the model sees carries it.
        page = sess.run('browser_click', {'target': '담기', 'effect': 'mutate'})
        self.assertEqual(page['submit_refused'], bs.SUBMIT_REFUSED_TEXT)
        driver.snapshot = original
        self.assertNotIn('submit_refused', sess.run('browser_read', {}))


# ---------------------------------------------------------------- login, budget, targets

class LoginAndBudgetTests(unittest.TestCase):
    def test_a_page_with_a_password_field_is_login_required_and_withheld(self):
        sess, _ = session()
        result = sess.open({'url': ORIGIN + '/login', 'effect': 'navigate'})
        self.assertEqual(result['state'], 'login_required')
        self.assertTrue(result['needs_setup'])
        self.assertEqual(result['requires'], 'browser-login')
        self.assertNotIn('text', result)
        self.assertNotIn('elements', result)
        self.assertEqual(withheld_effect('browser_open', result).advanced, False)
        self.assertIsNone(withheld_effect('browser_open', {'state': 'page', 'text': 'x'}))

    def test_step_cap_and_deadline_are_typed_failures(self):
        sess, _ = session(steps=2)
        sess.open({'url': ORIGIN + '/product', 'effect': 'read'})
        sess.read()
        with self.assertRaises(ToolError) as caught:
            sess.read()
        self.assertEqual(caught.exception.code, 'browser_step_budget')
        now = [100.0]
        budget = WorkBudget(seconds=30, clock=lambda: now[0])
        sess, driver = session(budget=budget)
        sess.open({'url': ORIGIN + '/product', 'effect': 'read'})
        self.assertEqual(driver.log[0][2], 20, 'per-action timeout is the browser cap while the Work has time')
        now[0] = 125.0
        sess.read()
        self.assertEqual(driver.log[-2][0], 'snapshot')
        now[0] = 131.0
        with self.assertRaises(ToolError) as caught:
            sess.read()
        self.assertEqual(caught.exception.code, 'deadline_exceeded')

    def test_timeout_is_bounded_by_the_remaining_budget(self):
        budget = WorkBudget(seconds=5, clock=lambda: 0.0)
        sess, driver = session(budget=budget)
        sess.open({'url': ORIGIN + '/product', 'effect': 'read'})
        self.assertEqual(driver.log[0][2], 5.0)

    def test_driver_failures_are_typed_and_carry_no_driver_text(self):
        class Failing(FakeDriver):
            def goto(self, url, timeout):
                raise TimeoutError('selector a[href=https://secret.example] not found')
        sess, _ = session(Failing())
        with self.assertRaises(ToolError) as caught:
            sess.open({'url': ORIGIN + '/product', 'effect': 'read'})
        self.assertEqual((caught.exception.code, str(caught.exception)), ('browser_timeout', bs.TIMEOUT_TEXT))

    def test_targets_resolve_by_number_or_name_and_refuse_ambiguity(self):
        pages = dict(PAGES)
        pages['/two'] = '<html><head><title>t</title></head><body><button>확인</button><button>확인</button><button>취소</button></body></html>'
        sess, _ = session(FakeDriver(pages))
        sess.open({'url': ORIGIN + '/two', 'effect': 'read'})
        with self.assertRaises(ToolError) as caught:
            sess.click({'target': '확인', 'effect': 'read'})
        self.assertEqual(caught.exception.code, 'ambiguous_target')
        with self.assertRaises(ToolError) as caught:
            sess.click({'target': '9', 'effect': 'read'})
        self.assertEqual(caught.exception.code, 'target_not_found')
        sess.click({'target': '취', 'effect': 'read'})
        sess.click({'target': '3', 'effect': 'read'})


# ---------------------------------------------------------------- the loop

class LoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = QuickStore(Path(self.tmp.name) / 'data')
        self.events = []

    def record(self, tool, status, detail):
        self.events.append((tool, status, detail))

    def caps(self, transport, driver, **kwargs):
        return Capabilities(self.store, ModelAdapter(transport), CFG, '', 'job', self.record, browser=lambda: driver, **kwargs)

    def owner_asked(self, message, typed=True):
        with self.store.db() as db:
            db.execute("INSERT INTO jobs(id,request_key,message,status,created,owner_typed) VALUES ('job','k-job',?,'running',?,?)",
                       (message, time.time(), 1 if typed else None))

    def test_only_an_owner_typed_request_of_this_worker_narrows_the_set(self):
        """#889 review P3: a preparation's goal and a delegated specialist keep the full set."""
        self.owner_asked('세탁세제 찾아줘', typed=False)
        caps = self.caps(Script(), FakeDriver())
        caps.written_private = ['세탁세제']
        self.assertEqual(caps._page_excluded(), ['세탁세제'])
        with self.store.db() as db:
            db.execute("UPDATE jobs SET owner_typed=1 WHERE id='job'")
        self.assertEqual(caps._page_excluded(), [])
        child = self.caps(Script(), FakeDriver(), delegated=True, inherited_excluded=['세탁세제'])
        self.assertEqual(child._page_excluded(), ['세탁세제'])

    def test_the_owners_own_words_in_this_request_do_not_mask_the_page(self):
        """#889: a value the Work saved from the owner's own words no longer blanks those words on public pages."""
        self.owner_asked('세탁세제 3L 찾아줘')
        caps = self.caps(Script(), FakeDriver())
        caps.written_private = ['세탁세제', PASSPORT]
        page = caps.browser_session().open({'url': ORIGIN + '/product', 'effect': 'read'})
        self.assertEqual(page['title'], '세탁세제 3L', 'the owner said it in this request')
        self.assertNotIn(PASSPORT, flat(page), 'a saved value the owner did not say here stays masked')
        self.assertIn('보관 위치 ' + bs.REDACTED, page['text'])
        # Outbound redaction (browser_type values, goals, records) keeps the full set.
        self.assertIn('세탁세제', caps._browser_excluded())
        caps.close_browser()

    def test_without_a_request_the_snapshot_set_is_unchanged(self):
        caps = self.caps(Script(), FakeDriver())
        caps.written_private = ['세탁세제']
        self.assertEqual(caps._page_excluded(), ['세탁세제'])

    def test_product_to_cart_through_the_loop_with_repeated_reads(self):
        script = Script({'tool_calls': [call('1', 'browser_open', url=ORIGIN + '/product', effect='navigate')]},
                        {'tool_calls': [call('2', 'browser_find', text='세탁세제')]},
                        {'tool_calls': [call('3', 'browser_click', target='장바구니', effect='mutate')]},
                        {'tool_calls': [call('4', 'browser_read')]},
                        {'tool_calls': [call('5', 'browser_read')]},
                        # #657: the cart page the model read is the claim's evidence.
                        {'tool_calls': [call('6', 'finish', status='done', evidence_refs=['5'],
                                             summary='장바구니에 세탁세제 3L이 담겼습니다.')]})
        driver = FakeDriver()
        caps = self.caps(script, driver, judgments=judgments(True))
        result = run_agent(caps.adapter, CFG, '', [{'role': 'user', 'content': '세탁세제 장바구니에 담아줘'}], '', caps, self.record)
        self.assertEqual(result.outcome, 'succeeded')
        self.assertEqual(driver.posts, [('post', '/cart')])
        cart = json.loads(script.bodies[-1]['messages'][-1]['content'])
        self.assertEqual(cart['ref'], '5')
        self.assertIn('세탁세제 3L × 1', cart['text'])
        self.assertIn('owner-browser-session', caps.private_provenance)
        failed = [json.loads(d) for t, s, d in self.events if s == 'failed']
        self.assertEqual(failed, [], 'a second browser_read is not a duplicate call')
        traces = [json.loads(d) for t, s, d in self.events if t.startswith('browser_') and s == 'succeeded']
        self.assertEqual(traces[0]['evidence']['url'], ORIGIN + '/product')
        self.assertNotIn('text', traces[0]['evidence'])
        caps.close_browser()
        self.assertTrue(driver.closed)

    def test_every_event_of_a_browser_call_keeps_its_declared_effect(self):
        """#787: the direct route records the model's declared effect on each event of a browser call."""
        script = Script({'tool_calls': [call('1', 'browser_open', url=ORIGIN + '/checkout', effect='read')]},
                        {'tool_calls': [call('2', 'browser_find', text='카드번호')]},
                        {'tool_calls': [call('3', 'browser_type', target='카드번호', text='4111111111111111', effect='mutate')]},
                        {'content': '결제 단계는 승인이 필요합니다.'})
        caps = self.caps(script, FakeDriver(), browser_approvals=Approvals())
        run_agent(caps.adapter, CFG, '', [{'role': 'user', 'content': '결제해줘'}], '', caps, self.record)
        declared = [(tool, status, json.loads(detail).get('declared_effect')) for tool, status, detail in self.events
                    if tool.startswith('browser_')]
        self.assertEqual(declared, [('browser_open', 'running', 'read'), ('browser_open', 'succeeded', 'read'),
                                    ('browser_find', 'running', None), ('browser_find', 'succeeded', None),
                                    ('browser_type', 'running', 'mutate'), ('browser_type', 'failed', 'mutate')])
        caps.close_browser()

    def test_the_same_step_on_the_same_page_is_refused_and_on_a_changed_page_runs(self):
        """#657: a browser repeat is keyed on (action, target, input, page digest), not on the memo."""
        script = Script({'tool_calls': [call('1', 'browser_open', url=ORIGIN + '/account', effect='navigate')]},
                        {'tool_calls': [call('2', 'browser_click', target='저장', effect='mutate')]},
                        # Nothing on the page changed: the same click is the same path.
                        {'tool_calls': [call('3', 'browser_click', target='저장', effect='read')]},
                        {'tool_calls': [call('4', 'browser_type', target='이름', text='김철수', effect='mutate')]},
                        # The page now differs (the field's value): the same target is a new step.
                        {'tool_calls': [call('5', 'browser_click', target='저장', effect='mutate')]},
                        {'tool_calls': [call('6', 'finish', status='done', evidence_refs=['5'], summary='저장했습니다.')]})
        driver = FakeDriver()
        caps = self.caps(script, driver, judgments=judgments(True))
        result = run_agent(caps.adapter, CFG, '', [{'role': 'user', 'content': '내 계정 이름을 바꿔서 저장해줘'}], '', caps, self.record)
        failed = [json.loads(d)['code'] for t, s, d in self.events if s == 'failed']
        self.assertEqual(failed, ['repeat_path'])
        self.assertEqual(len([entry for entry in driver.log if entry[0] == 'click']), 2)
        self.assertEqual(result.outcome, 'succeeded')
        # The typed text is never recorded: not in responded/running events,
        # the alternative or claim evidence, nor the concluded record.
        recorded = json.dumps(self.events, ensure_ascii=False)
        self.assertNotIn('김철수', recorded)
        self.assertIn('[가림: 3자]', recorded)
        self.assertNotIn('김철수', json.dumps(result.report, ensure_ascii=False))

    def test_a_refused_payment_step_is_a_typed_failure_the_owner_can_read(self):
        script = Script({'tool_calls': [call('1', 'browser_open', url=ORIGIN + '/checkout', effect='navigate')]},
                        {'tool_calls': [call('2', 'browser_type', target='카드번호', text='4111111111111111', effect='mutate')]},
                        {'content': '결제 단계는 승인이 필요합니다.'})
        driver = FakeDriver()
        approvals = Approvals()
        caps = self.caps(script, driver, browser_approvals=approvals)
        result = run_agent(caps.adapter, CFG, '', [{'role': 'user', 'content': '결제해줘'}], '', caps, self.record)
        self.assertEqual(result.outcome, 'partial')
        observation = json.loads(next(m['content'] for m in script.bodies[2]['messages'] if m.get('tool_call_id') == '2'))
        self.assertEqual((observation['code'], observation['retry'], observation['requires']),
                         ('approval_required', 'permanent', 'browser-step-approval'))
        self.assertEqual(observation['error'], bs.APPROVAL_TEXT)
        self.assertEqual(len(approvals.requests), 1)
        self.assertEqual([e for e in driver.log if e[0] == 'type'], [])

    def test_browser_type_text_is_never_recorded(self):
        card = '4111111111111111'
        script = Script({'tool_calls': [call('1', 'browser_open', url=ORIGIN + '/checkout', effect='navigate')]},
                        {'tool_calls': [call('2', 'browser_type', target='카드번호', text=card, effect='mutate'),
                                        call('3', 'browser_type', target='받는 사람', text='홍길동 010-1234-5678', effect='mutate')]},
                        {'content': '끝'})
        caps = self.caps(script, FakeDriver())
        run_agent(caps.adapter, CFG, '', [{'role': 'user', 'content': '입력해줘'}], '', caps, self.record)
        recorded = flat(self.events)
        self.assertNotIn(card, recorded)
        self.assertNotIn('010-1234-5678', recorded)
        running = [json.loads(d) for t, s, d in self.events if t == 'browser_type' and s == 'running']
        self.assertEqual([row['arguments']['text'] for row in running], ['[가림: 16자]', '[가림: 17자]'],
                         'both calls are recorded before the guard runs, each redacted')
        responded = [json.loads(d) for t, s, d in self.events if t == 'model' and s == 'responded']
        typed = [json.loads(c['function']['arguments']) for row in responded for c in row['tool_calls'] if c['function']['name'] == 'browser_type']
        self.assertEqual(sorted(row['text'] for row in typed), ['[가림: 16자]', '[가림: 17자]'])

    def test_login_required_keeps_the_turn_from_claiming_success(self):
        script = Script({'tool_calls': [call('1', 'browser_open', url=ORIGIN + '/login', effect='navigate')]},
                        {'content': '장바구니에 담았습니다.'})
        caps = self.caps(script, FakeDriver())
        result = run_agent(caps.adapter, CFG, '', [{'role': 'user', 'content': '담아줘'}], '', caps, self.record)
        self.assertEqual(result.outcome, 'failed')
        failed = [json.loads(d) for t, s, d in self.events if s == 'failed' and t == 'browser_open']
        self.assertEqual(failed[0]['error'], bs.LOGIN_REQUIRED_TEXT)
        self.assertNotIn('owner-browser-session', caps.private_provenance)

    def test_a_delegated_specialist_never_receives_the_browser(self):
        caps = self.caps(Script(), FakeDriver())
        child = Capabilities(self.store, caps.adapter, CFG, '', 'job', self.record, True, allowed_tools=set(caps.tools),
                             delegated=True)
        self.assertFalse({d['function']['name'] for d in child.definitions()} & BROWSER_ACTIONS)


# ---------------------------------------------------------------- store binding

class StoreApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = QuickStore(Path(self.tmp.name) / 'data')
        self.page, self.target, self.step = bs.digest('https://h.test/checkout'), bs.digest('textbox|카드번호'), bs.digest('4111|state')

    def test_issue_and_consume_exactly_once_for_the_exact_binding(self):
        issued = self.store.issue_browser_step_approval('local-owner', 'w1', 'browser_type', self.page, self.target, self.step, now=1000)
        token = issued['approval_token']
        for owner, work, action, page, target, step in (('other', 'w1', 'browser_type', self.page, self.target, self.step),
                                                        ('local-owner', 'w2', 'browser_type', self.page, self.target, self.step),
                                                        ('local-owner', 'w1', 'browser_click', self.page, self.target, self.step),
                                                        ('local-owner', 'w1', 'browser_type', bs.digest('other'), self.target, self.step),
                                                        ('local-owner', 'w1', 'browser_type', self.page, bs.digest('other'), self.step),
                                                        ('local-owner', 'w1', 'browser_type', self.page, self.target, bs.digest('5555|state'))):
            with self.assertRaises(ValueError):
                self.store.consume_browser_step_approval(owner, work, action, page, target, step, token, now=1001)
        with self.assertRaises(ValueError):
            self.store.consume_browser_step_approval('local-owner', 'w1', 'browser_type', self.page, self.target, self.step, 'not-the-token', now=1001)
        self.assertEqual(self.store.consume_browser_step_approval('local-owner', 'w1', 'browser_type', self.page, self.target, self.step, token, now=1001),
                         {'consumed': True, 'action': 'browser_type'})
        with self.assertRaises(ValueError):
            self.store.consume_browser_step_approval('local-owner', 'w1', 'browser_type', self.page, self.target, self.step, token, now=1002)

    def test_expired_and_replaced_approvals_are_refused(self):
        stale = self.store.issue_browser_step_approval('local-owner', 'w1', 'browser_type', self.page, self.target, self.step, ttl=10, now=1000)
        with self.assertRaises(ValueError):
            self.store.consume_browser_step_approval('local-owner', 'w1', 'browser_type', self.page, self.target, self.step, stale['approval_token'], now=1011)
        first = self.store.issue_browser_step_approval('local-owner', 'w1', 'browser_type', self.page, self.target, self.step, now=2000)
        second = self.store.issue_browser_step_approval('local-owner', 'w1', 'browser_type', self.page, self.target, self.step, now=2001)
        with self.assertRaises(ValueError):
            self.store.consume_browser_step_approval('local-owner', 'w1', 'browser_type', self.page, self.target, self.step, first['approval_token'], now=2002)
        self.store.consume_browser_step_approval('local-owner', 'w1', 'browser_type', self.page, self.target, self.step, second['approval_token'], now=2002)


# ---------------------------------------------------------------- service surfaces

CHAT, GENERATION = 42, 'gen-1'


class ServiceTests(unittest.TestCase):
    """The owner's approval surfaces around one Telegram Work, model-free."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = QuickStore(Path(self.tmp.name) / 'data')
        self.calls, self.scripts = [], []
        self.driver_log = []
        self.drivers = []

        def transport(url, body=None, headers=None, timeout=60):
            method = url.rsplit('/', 1)[-1]
            self.calls.append((method, body))
            if method == 'sendMessage':
                return {'ok': True, 'result': {'message_id': 9000 + len(self.calls)}}
            if method == 'getMe':
                return {'ok': True, 'result': {'username': 'owner_test_bot'}}
            return {'ok': True, 'result': True}

        def model(url, body, headers=None, timeout=60):
            tools = [t.get('function', {}).get('name') or t.get('name') for t in body.get('tools', [])]
            if 'agentos_connection_probe' in tools:
                return {'choices': [{'message': {'tool_calls': [{'id': 'probe', 'function': {'name': 'agentos_connection_probe', 'arguments': '{}'}}]}}]}
            if not self.scripts:
                return {'choices': [{'message': {'content': '끝났습니다.'}}]}
            return self.scripts[0](url, body, headers, timeout)

        def launcher(profile_dir, headless):
            driver = FakeDriver(log=self.driver_log)
            self.drivers.append(driver)
            return driver

        profile = bs.BrowserProfile(Path(self.tmp.name) / 'profile', launcher=launcher)
        self.service = AgentService(self.store, ModelAdapter(model), transport, browser_profile=profile)
        self.service.save_model({'provider': 'compatible', 'endpoint': 'https://example.test/v1', 'model': 'test-model', 'api_key': 'k'})
        self.assertTrue(self.service.test_model()['ok'])
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': GENERATION, 'cursor': 0})
        self.update_id, self.message_id = 100, 500

    def receive(self, text):
        self.update_id += 1
        self.message_id += 1
        self.service.ingest_update({'update_id': self.update_id, 'message': {'message_id': self.message_id, 'from': {'id': CHAT},
                                    'chat': {'id': CHAT, 'type': 'private'}, 'text': text}}, GENERATION)
        return self.store.jobs()[0]['id']

    def sends(self):
        return [body for method, body in self.calls if method == 'sendMessage']

    def tap(self, data, message_id, sender=CHAT):
        self.service.ingest_callback({'id': 'cb', 'from': {'id': sender}, 'data': data,
                                      'message': {'message_id': message_id, 'chat': {'id': sender, 'type': 'private'}}}, GENERATION)

    def payment_script(self):
        return Script({'tool_calls': [call('1', 'browser_open', url=ORIGIN + '/checkout', effect='navigate')]},
                      {'tool_calls': [call('2', 'browser_type', target='카드번호', text='4111111111111111', effect='mutate')]},
                      {'content': '카드번호를 입력했습니다.'})

    def refused_work(self):
        self.scripts = [self.payment_script()]
        job_id = self.receive('결제 페이지에서 카드번호 넣어줘')
        self.assertTrue(self.service.run_one())
        return job_id

    def test_refusal_reaches_the_owner_and_the_telegram_buttons_bind_the_step(self):
        job_id = self.refused_work()
        job = self.store.job(job_id)
        self.assertEqual(job['status'], 'partial')
        self.assertIn('결제 단계는 승인이 필요합니다', job['error'])
        self.assertIn('결제 단계는 승인이 필요합니다', job['owner_cause'])
        pending = self.service.browser_status()['pending_steps']
        self.assertEqual([(row['work_id'], row['action'], row['state']) for row in pending], [(job_id, 'browser_type', 'requested')])
        self.assertIn('카드번호', pending[0]['label'])
        self.assertTrue(self.drivers[0].closed, 'the session closes with the run')
        self.assertTrue(self.service.deliver_notification())
        prompt = [body for body in self.sends() if body.get('reply_markup') and 'p7w:' in flat(body['reply_markup'])][0]
        self.assertIn('결제 단계는 승인이 필요합니다', prompt['text'])
        self.assertIn('카드번호', prompt['text'])
        self.assertNotIn('4111', prompt['text'])
        buttons = prompt['reply_markup']['inline_keyboard'][0]
        self.assertEqual([b['text'] for b in buttons], ['이 단계 승인', '허용 안 함'])
        notification_id = buttons[0]['callback_data'].split(':')[1]
        row = self.store.notification(notification_id)
        # A foreign sender or a different message cannot approve.
        self.tap(f'p7w:{notification_id}:approve', row['message_id'], sender=99)
        self.tap(f'p7w:{notification_id}:approve', row['message_id'] + 1)
        self.assertEqual(self.store.job(job_id)['status'], 'partial')
        self.assertEqual(self.service.browser_status()['pending_steps'][0]['state'], 'requested')
        # The owner's tap issues the exact approval and re-queues this Work once.
        self.tap(f'p7w:{notification_id}:approve', row['message_id'])
        self.assertEqual(self.store.job(job_id)['status'], 'queued')
        self.assertEqual(self.store.notification(notification_id)['state'], 'browser_approved')
        pending = self.service._browser_request(job_id)
        self.assertEqual(pending['state'], 'issued')
        self.assertNotIn(pending['token'], flat(self.service.browser_status()), 'the token never reaches a read model')
        # The re-run consumes the approval at execution and the step runs; a further guarded step is refused again.
        self.scripts = [Script({'tool_calls': [call('1', 'browser_open', url=ORIGIN + '/checkout', effect='navigate')]},
                               {'tool_calls': [call('2', 'browser_type', target='카드번호', text='4111111111111111', effect='mutate')]},
                               {'tool_calls': [call('3', 'browser_click', target='결제하기', effect='navigate')]},
                               {'content': '카드번호를 입력했지만 결제 버튼은 승인이 필요합니다.'})]
        self.assertTrue(self.service.run_one())
        typed = [entry for entry in self.driver_log if entry[0] == 'type']
        self.assertEqual(len(typed), 1)
        self.assertEqual(self.store.job(job_id)['status'], 'partial')
        self.assertIsNone(self.service._browser_request(job_id).get('token'))
        self.assertEqual(self.service._browser_request(job_id)['action'], 'browser_click')
        with self.store.db() as db:
            rows = db.execute("SELECT state FROM memory_approvals WHERE action='browser-step'").fetchall()
        self.assertEqual([r['state'] for r in rows], ['consumed'])

    def scan_store(self, needle):
        """Every table row, config row and file under the data directory, searched for ``needle``."""
        hits = []
        with self.store.db() as db:
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for table in tables:
                for row in db.execute(f'SELECT * FROM "{table}"'):
                    if needle in flat([str(value) for value in tuple(row)]):
                        hits.append(table)
        for path in Path(self.store.root).rglob('*'):
            if path.is_file() and needle.encode() in path.read_bytes():
                hits.append(str(path.relative_to(self.store.root)))
        return hits

    def test_a_refused_card_number_leaves_no_trace_in_the_store(self):
        job_id = self.refused_work()
        self.assertTrue(self.service.deliver_notification())
        self.assertEqual(self.store.job(job_id)['status'], 'partial')
        self.assertEqual(self.scan_store('4111111111111111'), [])
        self.assertEqual(self.scan_store('41111111'), [])
        self.assertNotIn('4111111111111111', flat(self.calls), 'nor in anything sent to Telegram')
        self.assertNotIn('4111111111111111', flat(self.service.task_progress()))
        self.assertNotIn('4111111111111111', flat(self.service.settings()))
        row = self.service._browser_request(job_id)
        self.assertEqual(set(row) - {'work_id', 'action', 'label', 'state', 'requested_at'},
                         {'digest', 'page_digest', 'target_digest', 'step_digest'}, 'only keyed digests are kept')

    def test_a_resumed_run_typing_different_text_asks_again(self):
        job_id = self.refused_work()
        self.service.browser_step_decision({'work_id': job_id, 'decision': 'approve'})
        self.scripts = [Script({'tool_calls': [call('1', 'browser_open', url=ORIGIN + '/checkout', effect='navigate')]},
                               {'tool_calls': [call('2', 'browser_type', target='카드번호', text='5555555555554444', effect='mutate')]},
                               {'content': '다른 카드를 입력하려 했습니다.'})]
        self.assertTrue(self.service.run_one())
        self.assertEqual([e for e in self.driver_log if e[0] == 'type'], [], 'the approval did not cover different text')
        self.assertEqual(self.service._browser_request(job_id)['state'], 'requested', 'a new request for the new text')
        with self.store.db() as db:
            states = [r['state'] for r in db.execute("SELECT state FROM memory_approvals WHERE action='browser-step'")]
        self.assertEqual(states, ['issued'], 'the old approval stays unspent until it expires or is replaced')
        self.assertEqual(self.scan_store('5555555555554444'), [])

    def test_web_decision_deny_drops_the_request_and_approve_requeues(self):
        job_id = self.refused_work()
        with self.assertRaises(ValueError):
            self.service.browser_step_decision({'work_id': 'nope', 'decision': 'approve'})
        self.assertEqual(self.service.browser_step_decision({'work_id': job_id, 'decision': 'deny'}),
                         {'approved': False, 'resumed': False, 'work_id': job_id})
        self.assertEqual(self.service.browser_status()['pending_steps'], [])
        self.assertEqual(self.store.job(job_id)['status'], 'partial')
        job_id = self.refused_work()
        self.assertEqual(self.service.browser_step_decision({'work_id': job_id, 'decision': 'approve'}),
                         {'approved': True, 'resumed': True, 'work_id': job_id})
        self.assertEqual(self.store.job(job_id)['status'], 'queued')

    def test_settings_status_and_login_window(self):
        status = self.service.settings()['browser']
        self.assertTrue(status['available'])
        self.assertIsNone(status['unavailable_reason'])
        self.assertNotIn('install_hint', status, 'no browser install is ever suggested (#680)')
        self.assertEqual(status['sessions'], [])
        self.assertEqual(status['storage']['what'], 'site-sign-in-cookies')
        self.assertEqual(status['storage']['key_service'], 'personal-agentos.browser-jar')
        self.assertFalse(status['storage']['sent_to_ai'])
        self.assertEqual(status['storage']['state'], 'empty')
        self.assertEqual(status['google_note'], bs.GOOGLE_NOTE)
        self.assertEqual(status['pending_steps'], [])
        with self.assertRaises(ValueError):
            self.service.open_browser_for_login({'url': ''})
        receipt = self.service.open_browser_for_login({'url': ORIGIN + '/login?next=x'})
        # #749: the request never waits for the window; it shows on its own thread.
        self.assertEqual(receipt['state'], 'opening')
        self.assertEqual(receipt['url'], ORIGIN + '/login')
        for _ in range(100):
            if self.driver_log:
                break
            time.sleep(0.02)
        self.assertEqual(self.driver_log[0], ('goto', ORIGIN + '/login?next=x', bs.ACTION_TIMEOUT_SECONDS))
        self.assertEqual(self.service.browser_status()['login_window_open'], True)
        # While the owner's window is open a Work cannot take the profile: typed, not crashed.
        self.scripts = [Script({'tool_calls': [call('1', 'browser_open', url=ORIGIN + '/product', effect='navigate')]},
                               {'content': '바쁨'})]
        job_id = self.receive('상품 페이지 열어줘')
        self.service.run_one()
        self.assertIn(bs.BUSY_TEXT, self.store.job(job_id)['error'])
        self.drivers[0].closed = True
        for _ in range(40):
            if not self.service.browser_status()['login_window_open']:
                break
            time.sleep(0.05)
        self.assertFalse(self.service.browser_status()['login_window_open'])
        self.assertEqual(len([e for e in self.driver_log if e[0] in ('type', 'snapshot', 'click')]), 0,
                         'the login window is never read or typed into')

    def test_unavailable_platform_offers_no_tools_and_a_typed_refusal(self):
        from unittest import mock
        profile = bs.BrowserProfile(Path(self.tmp.name) / 'p2', launcher=None)
        with mock.patch.object(bs, 'webkit_unavailable_reason', lambda *a, **k: 'platform'):
            self.service.browser_profile = profile
            status = self.service.browser_status()
            self.assertFalse(status['available'])
            self.assertEqual(status['unavailable_reason'], 'platform')
            self.assertEqual(status['message'], bs.PLATFORM_TEXT)
            self.assertNotIn('install_hint', status)
            self.assertNotIn('storage', status, 'nothing is read from the jar where the engine cannot run')
            self.assertIsNone(profile.driver_factory('w'))
            receipt = self.service.open_browser_for_login({'url': ORIGIN + '/x'})
            self.assertEqual((receipt['state'], receipt['reason']), ('unavailable', 'platform'))
            # A Work is offered no browser tool, so a browser goal cannot claim success.
            script = Script({'tool_calls': [call('1', 'browser_open', url=ORIGIN + '/product', effect='navigate')]},
                            {'content': '브라우저를 쓸 수 없습니다.'})
            self.scripts = [script]
            job_id = self.receive('상품 페이지 열어줘')
            self.assertTrue(self.service.run_one())
            offered = {t.get('function', {}).get('name') for t in script.bodies[0].get('tools', [])}
            self.assertFalse(offered & BROWSER_ACTIONS)
            self.assertNotEqual(self.store.job(job_id)['status'], 'succeeded')
            self.assertEqual(self.drivers, [])
        with mock.patch.object(bs, 'webkit_unavailable_reason', lambda *a, **k: 'dependency'):
            self.assertEqual(profile.status()['message'], bs.DEPENDENCY_TEXT)
        # A browser call that reaches the runtime anyway is the typed refusal, not a setup hint.
        caps = Capabilities(self.store, None, {}, '', 'w', lambda *a: None, browser_unavailable=bs.PLATFORM_TEXT)
        with self.assertRaises(ToolError) as caught:
            caps.execute('browser_open', {'url': ORIGIN + '/product', 'effect': 'navigate'})
        self.assertEqual(caught.exception.code, 'browser_unavailable_platform')
        self.assertEqual(str(caught.exception), bs.PLATFORM_TEXT)
        self.assertEqual(bs.webkit_unavailable_reason(platform='linux'), 'platform')
        self.assertEqual(bs.webkit_unavailable_reason(platform='win32'), 'platform')
        self.assertEqual(bs.webkit_unavailable_reason(platform='darwin', find_spec=lambda name: None), 'dependency')
        self.assertIsNone(bs.webkit_unavailable_reason(platform='darwin', find_spec=lambda name: object()))

    def test_durable_records_never_carry_page_secrets(self):
        self.scripts = [Script({'tool_calls': [call('1', 'browser_open', url=ORIGIN + '/account', effect='read')]},
                               {'tool_calls': [call('2', 'browser_read')]},
                               {'content': '계정 페이지를 확인했습니다.'})]
        job_id = self.receive('내 계정 페이지 확인해줘')
        self.assertTrue(self.service.run_one())
        with self.store.db() as db:
            events = flat([dict(r) for r in db.execute('SELECT * FROM tool_events WHERE job_id=?', (job_id,))])
            provenance = flat(dict(db.execute('SELECT * FROM turn_provenance WHERE job_id=?', (job_id,)).fetchone()))
            messages = flat([dict(r) for r in db.execute('SELECT * FROM messages')])
        for record in (events, provenance, messages, flat(self.store.evidence_summary(job_id)), flat(self.service.task_progress())):
            for secret in (PASSWORD, OTP, TOKEN):
                self.assertNotIn(secret, record)
        self.assertNotIn('세탁세제', events, 'page text is not in the durable tool events')
        record = self.store.turn_provenance(job_id)
        self.assertIn('owner-browser-session', record.get('egress_taint', []))


# ---------------------------------------------------------------- HTTP and CLI surfaces

class HttpAndCliTests(unittest.TestCase):
    def test_routes_are_owner_session_bound_and_typed(self):
        from http.cookiejar import CookieJar
        from urllib.error import HTTPError
        from urllib.request import HTTPCookieProcessor, Request, build_opener
        from personal_agent.quickstart import make_handler
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = QuickStore(tmp.name)
        store.claim(store.bootstrap.read_text(), 'long-password-test')
        profile = bs.BrowserProfile(Path(tmp.name) / 'profile', launcher=lambda d, h: FakeDriver())
        service = AgentService(store, browser_profile=profile)
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = build_opener(HTTPCookieProcessor(CookieJar()))
        url = f'http://127.0.0.1:{server.server_port}'

        def request(path, body=None):
            headers = {'Content-Type': 'application/json'} if body is not None else {}
            req = Request(url + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
            with client.open(req, timeout=3) as response:
                return json.load(response)
        try:
            with self.assertRaises(HTTPError) as error:
                request('/api/browser/approval', {'work_id': 'x', 'decision': 'approve'})
            self.assertEqual(error.exception.code, 401, 'owner session required')
            request('/api/login', {'password': 'long-password-test'})
            state = request('/api/state')
            self.assertEqual(state['settings']['browser']['pending_steps'], [])
            self.assertTrue(state['settings']['browser']['available'])
            with self.assertRaises(HTTPError) as error:
                request('/api/browser/approval', {'work_id': 'x', 'decision': 'approve'})
            self.assertEqual(error.exception.code, 400)
            with self.assertRaises(HTTPError) as error:
                request('/api/browser/login', {'url': ''})
            self.assertEqual(error.exception.code, 400)
            receipt = request('/api/browser/login', {'url': ORIGIN + '/login'})
            self.assertEqual(receipt['state'], 'opening', '#749: the HTTP request never waits for the window')
            with self.assertRaises(HTTPError) as error:
                request('/api/browser/sessions/delete', {'site': ''})
            self.assertEqual(error.exception.code, 400)
            self.assertEqual(request('/api/browser/sessions/delete', {'site': 'fixture.test'}),
                             {'deleted': False, 'site': 'fixture.test'})
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

    def test_cli_login_refuses_off_macos_and_opens_the_window_on_it(self):
        from unittest import mock
        from personal_agent import quickstart
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with mock.patch.object(bs, 'webkit_unavailable_reason', lambda *a, **k: 'platform'), \
             mock.patch('sys.stderr') as err:
            with self.assertRaises(SystemExit) as caught:
                quickstart.browser_login_main(['--url', ORIGIN + '/login', '--data', tmp.name])
            self.assertEqual(caught.exception.code, 2)
        self.assertIn('macOS', ''.join(str(c.args[0]) for c in err.write.call_args_list))
        class ClosedByOwner(FakeDriver):
            def is_open(self):
                return False   # the owner closed the window at once
        with mock.patch.object(bs.BrowserProfile, '_launch_webkit', lambda self, d, h: ClosedByOwner()), \
             mock.patch.object(bs, 'webkit_unavailable_reason', lambda *a, **k: None), \
             mock.patch('sys.stdout') as out:
            code = quickstart.browser_login_main(['--url', ORIGIN + '/login', '--data', tmp.name])
        self.assertEqual(code, 0)
        printed = ''.join(str(c.args[0]) for c in out.write.call_args_list)
        self.assertIn('"state": "closed"', printed)


# ---------------------------------------------------------------- fixture site (served to the real WebKit worker, #680)

class FixtureHandler(BaseHTTPRequestHandler):
    def _send(self, body, status=200):
        data = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in PAGES:
            return self._send(PAGES[path])
        self._send('<html><body>없음</body></html>', 404)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', '0'))
        self.rfile.read(length)
        path = urlsplit(self.path).path
        self.server.posts.append(path)
        self._send(PAGES.get(path, '<html><body>없음</body></html>'))

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    unittest.main()
