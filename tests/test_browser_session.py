"""SEC-BROWSER-01 (#656): browser action capability in the owner-logged-in profile.

Evidence classes, named separately:

* unit (model-free, fake driver): output mediation, the payment guard with and
  without an exact approval, the model's effect label never lifting the
  guard, generic login_required detection, budget/timeouts, tool schemas,
  the loop end to end with a scripted model, the service approval surfaces
  (Telegram buttons, web decision) and the secret-free durable records;
* integration (model-free, real Playwright driver, skipped cleanly when the
  optional extra or Chromium is absent): a local ``http.server`` fixture site
  driven product page -> 장바구니 -> cart page.

No site, provider or category is named in ``src``; the fixture below is the
test's own.
"""
import html
import json
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
        <label>카드번호 <input type="text" autocomplete="cc-number" name="card"></label>
        <label>CVC <input type="text" autocomplete="cc-csc" name="cvc"></label>
        <label>받는 사람 <input type="text" autocomplete="name" name="who"></label>
        <button type="submit">결제하기</button>
      </form>
      <form action="/coupon" method="post"><label>쿠폰 <input type="text" name="coupon"></label><button type="submit">쿠폰 적용</button></form>
      </body></html>''',
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
        self.pending, self.label, self.skip = [], None, 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form':
            self.form_count += 1
            self.form = {'id': self.form_count, 'action': attrs.get('action', ''), 'method': attrs.get('method', 'get')}
            self.forms.append(self.form)
        if tag == 'label':
            self.label = []
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
                       'disabled': 'disabled' in attrs, 'hidden': hidden or kind == 'hidden', 'action': dict(self.form) if self.form else None}
            self.elements.append(element)
            if not element['name'] and self.label is not None and self.label:
                element['name'] = ' '.join(self.label).strip()
            self.pending.append(element)

    def handle_endtag(self, tag):
        if tag == 'form':
            self.form = None
        if tag == 'label':
            self.label = None
        if tag in ('script', 'style', 'head'):
            self.skip -= 1
        if tag in INTERACTIVE and self.pending:
            self.pending.pop()

    def handle_data(self, data):
        text = ' '.join(data.split())
        if not text or self.skip:
            return
        self.text.append(text)
        if self.label is not None:
            self.label.append(text)
        for element in self.pending:
            if not element['name']:
                element['name'] = text

    def result(self, title):
        elements = [{k: v for k, v in e.items() if k not in ('hidden', 'action')} for e in self.elements if not e['hidden']]
        return {'url': self.url, 'title': title, 'text': '\n'.join(self.text), 'elements': elements}, self.elements


class FakeDriver:
    """A ``PageDriver`` over the fixture pages: links navigate, submit buttons post their form."""

    def __init__(self, pages=PAGES, origin=ORIGIN, log=None):
        self.pages, self.origin = pages, origin
        self.url, self.values, self.closed = None, {}, False
        self.log = log if log is not None else []
        self.posts = []

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
        return parser.result(title)

    def snapshot(self):
        self.log.append(('snapshot', self.url))
        return self._parse()[0]

    def click(self, index, timeout):
        self.log.append(('click', index, timeout))
        element = next(e for e in self._parse()[1] if e['index'] == index)
        if element['tag'] == 'a':
            return self.goto(element['href'], timeout)
        form = element.get('action')
        if form and element['type'] == 'submit':
            self.posts.append((form['method'], form['action']))
            return self.goto(urljoin(self.url, form['action']), timeout)

    def type(self, index, text, timeout):
        self.log.append(('type', index, text, timeout))
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

    def test_cli_profiles_declare_the_browser_unavailable(self):
        for profile in CLI_PROFILES:
            unavailable = route_unavailable(profile)
            self.assertTrue(BROWSER_ACTIONS <= set(unavailable), profile)

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
        self.assertEqual(binding, bs.step_binding('work-1', 'browser_type', ORIGIN + '/checkout',
                                                  bs.target_key({'role': 'textbox', 'name': '카드번호', 'tag': 'input', 'type': 'text',
                                                                 'autocomplete': 'cc-number', 'form': 1})))
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

    def test_an_exact_approval_is_consumed_once_and_only_for_its_binding(self):
        card = bs.target_key({'role': 'textbox', 'name': '카드번호', 'tag': 'input', 'type': 'text', 'autocomplete': 'cc-number', 'form': 1})
        approvals = Approvals(bs.step_binding('work-1', 'browser_type', ORIGIN + '/checkout', card))
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

    def test_product_to_cart_through_the_loop_with_repeated_reads(self):
        script = Script({'tool_calls': [call('1', 'browser_open', url=ORIGIN + '/product', effect='navigate')]},
                        {'tool_calls': [call('2', 'browser_find', text='세탁세제')]},
                        {'tool_calls': [call('3', 'browser_click', target='장바구니', effect='mutate')]},
                        {'tool_calls': [call('4', 'browser_read')]},
                        {'tool_calls': [call('5', 'browser_read')]},
                        {'content': '장바구니에 세탁세제 3L이 담겼습니다.'})
        driver = FakeDriver()
        caps = self.caps(script, driver)
        result = run_agent(caps.adapter, CFG, '', [{'role': 'user', 'content': '세탁세제 장바구니에 담아줘'}], '', caps, self.record)
        self.assertEqual(result.outcome, 'succeeded')
        self.assertEqual(driver.posts, [('post', '/cart')])
        cart = json.loads(script.bodies[-1]['messages'][-1]['content'])
        self.assertIn('세탁세제 3L × 1', cart['text'])
        self.assertIn('owner-browser-session', caps.private_provenance)
        failed = [json.loads(d) for t, s, d in self.events if s == 'failed']
        self.assertEqual(failed, [], 'a second browser_read is not a duplicate call')
        traces = [json.loads(d) for t, s, d in self.events if t.startswith('browser_') and s == 'succeeded']
        self.assertEqual(traces[0]['evidence']['url'], ORIGIN + '/product')
        self.assertNotIn('text', traces[0]['evidence'])
        caps.close_browser()
        self.assertTrue(driver.closed)

    def test_a_refused_payment_step_is_a_typed_failure_the_owner_can_read(self):
        script = Script({'tool_calls': [call('1', 'browser_open', url=ORIGIN + '/checkout', effect='navigate')]},
                        {'tool_calls': [call('2', 'browser_type', target='카드번호', text='4111111111111111', effect='mutate')]},
                        {'content': '결제 단계는 승인이 필요합니다.'})
        driver = FakeDriver()
        approvals = Approvals()
        caps = self.caps(script, driver, browser_approvals=approvals)
        result = run_agent(caps.adapter, CFG, '', [{'role': 'user', 'content': '결제해줘'}], '', caps, self.record)
        self.assertEqual(result.outcome, 'partial')
        observation = json.loads(script.bodies[2]['messages'][-1]['content'])
        self.assertEqual((observation['code'], observation['retry'], observation['requires']),
                         ('approval_required', 'permanent', 'browser-step-approval'))
        self.assertEqual(observation['error'], bs.APPROVAL_TEXT)
        self.assertEqual(len(approvals.requests), 1)
        self.assertEqual([e for e in driver.log if e[0] == 'type'], [])

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
        self.page, self.target = bs.digest('https://h.test/checkout'), bs.digest('textbox|카드번호')

    def test_issue_and_consume_exactly_once_for_the_exact_binding(self):
        issued = self.store.issue_browser_step_approval('local-owner', 'w1', 'browser_type', self.page, self.target, now=1000)
        token = issued['approval_token']
        for owner, work, action, page, target in (('other', 'w1', 'browser_type', self.page, self.target),
                                                  ('local-owner', 'w2', 'browser_type', self.page, self.target),
                                                  ('local-owner', 'w1', 'browser_click', self.page, self.target),
                                                  ('local-owner', 'w1', 'browser_type', bs.digest('other'), self.target),
                                                  ('local-owner', 'w1', 'browser_type', self.page, bs.digest('other'))):
            with self.assertRaises(ValueError):
                self.store.consume_browser_step_approval(owner, work, action, page, target, token, now=1001)
        with self.assertRaises(ValueError):
            self.store.consume_browser_step_approval('local-owner', 'w1', 'browser_type', self.page, self.target, 'not-the-token', now=1001)
        self.assertEqual(self.store.consume_browser_step_approval('local-owner', 'w1', 'browser_type', self.page, self.target, token, now=1001),
                         {'consumed': True, 'action': 'browser_type'})
        with self.assertRaises(ValueError):
            self.store.consume_browser_step_approval('local-owner', 'w1', 'browser_type', self.page, self.target, token, now=1002)

    def test_expired_and_replaced_approvals_are_refused(self):
        stale = self.store.issue_browser_step_approval('local-owner', 'w1', 'browser_type', self.page, self.target, ttl=10, now=1000)
        with self.assertRaises(ValueError):
            self.store.consume_browser_step_approval('local-owner', 'w1', 'browser_type', self.page, self.target, stale['approval_token'], now=1011)
        first = self.store.issue_browser_step_approval('local-owner', 'w1', 'browser_type', self.page, self.target, now=2000)
        second = self.store.issue_browser_step_approval('local-owner', 'w1', 'browser_type', self.page, self.target, now=2001)
        with self.assertRaises(ValueError):
            self.store.consume_browser_step_approval('local-owner', 'w1', 'browser_type', self.page, self.target, first['approval_token'], now=2002)
        self.store.consume_browser_step_approval('local-owner', 'w1', 'browser_type', self.page, self.target, second['approval_token'], now=2002)


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
        self.assertIsNone(status['install_hint'])
        self.assertFalse(status['profile_exists'])
        self.assertIsNone(status['last_login_at'])
        self.assertEqual(status['pending_steps'], [])
        with self.assertRaises(ValueError):
            self.service.open_browser_for_login({'url': ''})
        receipt = self.service.open_browser_for_login({'url': ORIGIN + '/login?next=x'})
        self.assertEqual(receipt['state'], 'opened')
        self.assertEqual(receipt['url'], ORIGIN + '/login')
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

    def test_unavailable_profile_offers_no_tools_and_an_install_hint(self):
        profile = bs.BrowserProfile(Path(self.tmp.name) / 'p2', launcher=None, available=lambda: False)
        service = AgentService(self.store, self.service.adapter, self.service.telegram_transport, browser_profile=profile)
        status = service.browser_status()
        self.assertFalse(status['available'])
        self.assertEqual(status['install_hint'], bs.INSTALL_HINT)
        self.assertIsNone(profile.driver_factory('w'))
        self.assertEqual(service.open_browser_for_login({'url': ORIGIN + '/x'})['state'], 'unavailable')

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
            self.assertEqual(receipt['state'], 'opened')
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

    def test_cli_login_refuses_without_the_extra_and_opens_with_it(self):
        from unittest import mock
        from personal_agent import quickstart
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with mock.patch.object(bs, 'playwright_available', lambda: False):
            with self.assertRaises(SystemExit) as caught:
                quickstart.browser_login_main(['--url', ORIGIN + '/login', '--data', tmp.name])
            self.assertEqual(caught.exception.code, 2)
        class ClosedByOwner(FakeDriver):
            def is_open(self):
                return False   # the owner closed the window at once
        with mock.patch.object(bs, 'playwright_launcher', lambda d, h: ClosedByOwner()), \
             mock.patch.object(bs, 'playwright_available', lambda: True), \
             mock.patch('sys.stdout') as out:
            code = quickstart.browser_login_main(['--url', ORIGIN + '/login', '--data', tmp.name])
        self.assertEqual(code, 0)
        printed = ''.join(str(c.args[0]) for c in out.write.call_args_list)
        self.assertIn('"state": "closed"', printed)


# ---------------------------------------------------------------- integration (real driver)

def _chromium_available():
    if not bs.playwright_available():
        return False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:
        return False


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


@unittest.skipUnless(_chromium_available(), 'Playwright with Chromium is not installed (optional browser extra)')
class PlaywrightIntegrationTests(unittest.TestCase):
    """Evidence class: model-free integration with the real driver against a local fixture site."""

    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
        self.server.posts = []
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.origin = f'http://127.0.0.1:{self.server.server_address[1]}'
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_product_page_cart_button_and_cart_page_through_the_real_driver(self):
        profile = bs.BrowserProfile(Path(self.tmp.name) / 'profile', headless=True)
        approvals = Approvals()
        sess = bs.BrowserSession(profile.driver_factory('work-int'), work_id='work-int', approvals=approvals,
                                 excluded=lambda: [PASSPORT])
        try:
            page = sess.open({'url': self.origin + '/product', 'effect': 'navigate'})
            self.assertEqual(page['state'], 'page')
            self.assertIn('세탁세제 3L', page['text'])
            self.assertIn(bs.REDACTED, page['text'], 'the saved value is redacted by the real snapshot too')
            self.assertNotIn('숨김 링크', [row['name'] for row in page['elements']])
            self.assertTrue(sess.find({'text': '12,900'})['found'])
            cart = sess.click({'target': '장바구니', 'effect': 'mutate'})
            self.assertEqual(cart['title'], '장바구니')
            self.assertIn('세탁세제 3L × 1', cart['text'])
            self.assertEqual(self.server.posts, ['/cart'])
            # The account page: rendered token, password and one-time code never leave the driver.
            account = sess.open({'url': self.origin + '/account', 'effect': 'read'})
            for secret in (PASSWORD, OTP, TOKEN):
                self.assertNotIn(secret, flat(account))
            # The checkout form: the guard holds against the real DOM as well.
            sess.open({'url': self.origin + '/checkout', 'effect': 'navigate'})
            with self.assertRaises(ToolError) as caught:
                sess.type({'target': '카드번호', 'text': '4111', 'effect': 'navigate'})
            self.assertEqual(caught.exception.code, 'approval_required')
            with self.assertRaises(ToolError):
                sess.click({'target': '결제하기', 'effect': 'mutate'})
            self.assertEqual(self.server.posts, ['/cart'], 'no payment form was submitted')
            login = sess.open({'url': self.origin + '/login', 'effect': 'navigate'})
            self.assertEqual(login['state'], 'login_required')
        finally:
            sess.close()
        self.assertTrue(any((Path(self.tmp.name) / 'profile').iterdir()), 'the persistent profile exists')
        self.assertEqual(profile.status()['in_use'], False)


if __name__ == '__main__':
    unittest.main()
