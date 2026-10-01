"""BROWSE-07 (#939): sign in from the phone through a one-time link that drives the Mac's login window.

Evidence classes, named separately:

* unit (any platform): the worker's remote ops refuse ``not_shown`` while the
  window is parked (the ``Worker`` methods over a bare instance, no PyObjC);
  input validation; the session's code, binding and expiry rules;
* model-free local HTTP integration (fake login-window driver, fake ngrok
  process, temporary stores): the routes through a tunnel (forwarding
  headers), the cookie binding, 완료 saving the jar and closing, expiry
  closing, every other route refused through the tunnel, typed text reaching
  the driver and no log, and the Telegram button sending the link to the
  paired owner's chat only;
* not here: the real WebKit snapshot, native press/key and ``insertText``
  paths (macOS + PyObjC, opt-in real-browser tests), and a live ngrok tunnel.
"""
import io
import json
import logging
import tempfile
import threading
import time
import unittest
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from personal_agent import browser_session as bs
from personal_agent import browser_worker
from personal_agent import remote_login
from personal_agent.browser_jar import JAR_NAME, CookieJar, MemoryKey
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart import make_handler
from personal_agent.quickstart_service import AgentService, BROWSER_LOGIN_PHONE_LABEL
from personal_agent.quickstart_store import QuickStore

CHAT, GENERATION = 42, 'gen-939'
SECRET_TEXT = 'hunter2-never-logged'


def wait_until(condition, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


class WindowDriver:
    """A fake login-window driver: shows, answers frames, records remote inputs, exports a cookie once 'signed in'."""

    def __init__(self, log):
        self.log = log
        self.open = False
        self.sites = {}
        self.navigated = 0
        self.frames = 0
        self.remote = False
        #: A page dialog waiting for an answer, as the worker reports it in a frame.
        self.dialog = None

    def alive(self):
        return True

    def remote_begin(self):
        if not self.open:
            raise bs.WorkerError('not_shown')
        self.remote = True
        self.log.append(('remote_begin',))

    def remote_end(self):
        self.remote = False
        self.dialog = None
        self.log.append(('remote_end',))

    def show(self, url, timeout):
        self.open = True
        self.log.append(('show', url))
        return url

    def is_open(self):
        return self.open

    def navigations(self):
        return self.navigated

    def frame(self):
        if not self.open:
            raise bs.WorkerError('not_shown')
        self.frames += 1
        return {'jpeg': 'AAAA', 'width': 1280.0, 'height': 900.0, 'dialog': self.dialog}

    def remote_input(self, kind, **fields):
        if not self.open:
            raise bs.WorkerError('not_shown')
        self.log.append(('remote_' + kind, fields))
        if kind == 'dialog':
            self.dialog = None
        if kind == 'key' and fields.get('key') == 'Enter':
            # The sign-in: the site now holds a session cookie.
            self.navigated += 1
            self.sites = {'fixture.test': [{'name': 'sid', 'value': 'session-' + str(time.time_ns()), 'domain': 'fixture.test',
                                            'path': '/', 'expires': None, 'secure': True, 'http_only': True, 'same_site': None}]}

    def cookies_export(self):
        return dict(self.sites), []

    def close(self):
        self.open = False
        self.log.append(('close',))


class FakeTunnel:
    """``subprocess.Popen`` for ngrok: reports one public address, records ``terminate``."""

    def __init__(self):
        self.processes = []

    def __call__(self, argv, **kwargs):
        tunnel = self

        class Process:
            stdout = iter([json.dumps({'msg': 'started tunnel', 'url': 'https://abc123.ngrok-free.app'}) + '\n'])
            terminated = False

            def terminate(inner):
                inner.terminated = True
        process = Process()
        process.argv = argv
        tunnel.processes.append(process)
        return process


def telegram_transport(calls):
    def transport(url, body=None, headers=None, timeout=60):
        method = url.rsplit('/', 1)[-1]
        calls.append((method, body))
        if method == 'sendMessage':
            return {'ok': True, 'result': {'message_id': 9000 + len(calls)}}
        if method == 'getMe':
            return {'ok': True, 'result': {'username': 'owner_test_bot'}}
        return {'ok': True, 'result': True}
    return transport


# ---------------------------------------------------------------- unit: the worker refuses while parked

class WorkerOpsWhileParked(unittest.TestCase):
    """The remote ops never touch WebKit while the window is parked: ``not_shown`` before anything else."""

    def worker(self):
        worker = browser_worker.Worker.__new__(browser_worker.Worker)
        worker.owner_visible = False
        worker.pending = {}
        worker.popups = []
        worker.replies = []
        worker.emit = worker.replies.append
        return worker

    def test_every_remote_op_answers_not_shown_while_the_window_is_parked(self):
        worker = self.worker()
        for op, command in (('frame', {}), ('remote_tap', {'x': 1, 'y': 1}), ('remote_text', {'text': 'x'}),
                            ('remote_key', {'key': 'Enter'}), ('remote_nav', {'action': 'back'}),
                            ('remote_begin', {}), ('remote_dialog', {'answer': 'ok'})):
            with self.subTest(op=op):
                worker.handle({'id': 7, 'op': op, **command})
                self.assertEqual(worker.replies[-1], {'id': 7, 'ok': False, 'error': 'not_shown'})

    def test_a_frame_while_a_dialog_is_held_is_the_last_frame_without_a_snapshot(self):
        """Live 2026-10-01: a page waiting on its own confirm() renders nothing, so a snapshot never completes."""
        worker = self.worker()
        worker.owner_visible = True
        worker.held_dialog = {'kind': 'confirm', 'text': 'delete?', 'handler': None, 'sheet': None}
        worker.last_frame = ('AAAA', 1280.0, 900.0)
        worker.front_view = lambda: self.fail('no snapshot while a dialog is held')
        worker.handle({'id': 9, 'op': 'frame'})
        self.assertEqual(worker.replies[-1], {'id': 9, 'ok': True, 'jpeg': 'AAAA', 'width': 1280.0, 'height': 900.0,
                                              'dialog': {'kind': 'confirm', 'text': 'delete?'}})

    def test_a_page_dialog_is_held_for_the_phone_only_during_a_phone_session(self):
        """#936's rule stays in force without a phone session; with one, the phone (or the Mac's sheet) answers."""
        worker = self.worker()
        worker.owner_visible = True
        worker.dialog_step = None
        worker.held_dialog = None
        worker.remote = False
        worker.show_dialog_sheet = lambda kind, text: None   # the Mac's sheet needs AppKit; not here
        answers = []
        self.assertFalse(worker.hold_dialog('confirm', 'Sure?', answers.append), 'no phone session: #936 applies')
        worker.handle({'id': 1, 'op': 'remote_begin'})
        self.assertEqual(worker.replies[-1], {'id': 1, 'ok': True})
        self.assertTrue(worker.hold_dialog('confirm', '  삭제  하시겠습니까?  ', answers.append))
        self.assertEqual(worker.held_dialog['text'], '삭제 하시겠습니까?')
        self.assertEqual(answers, [], 'held, not answered')
        # A second dialog while one is held is cancelled at once.
        second = []
        self.assertTrue(worker.hold_dialog('alert', 'again', lambda: second.append('shown')))
        self.assertEqual(second, ['shown'])
        # The phone answers 확인: the page's confirm gets true, once.
        worker.handle({'id': 2, 'op': 'remote_dialog', 'answer': 'ok'})
        self.assertEqual(worker.replies[-1], {'id': 2, 'ok': True, 'answered': True})
        self.assertEqual(answers, [True])
        worker.handle({'id': 3, 'op': 'remote_dialog', 'answer': 'ok'})
        self.assertEqual(worker.replies[-1], {'id': 3, 'ok': True, 'answered': False}, 'nothing held now')
        worker.handle({'id': 4, 'op': 'remote_dialog', 'answer': 'maybe'})
        self.assertEqual(worker.replies[-1], {'id': 4, 'ok': False, 'error': 'bad_answer'})
        # Ending the session cancels a held dialog and stops holding.
        prompts = []
        self.assertTrue(worker.hold_dialog('prompt', 'name?', prompts.append))
        worker.handle({'id': 5, 'op': 'remote_end'})
        self.assertEqual(prompts, [None])
        self.assertFalse(worker.remote)
        self.assertFalse(worker.hold_dialog('confirm', 'Sure?', answers.append))
        self.assertEqual(answers, [True], 'back to the #936 path: not held, not answered here')

    def test_the_keys_and_actions_the_phone_offers_are_the_ones_the_worker_knows(self):
        self.assertEqual(set(remote_login.KEYS), set(browser_worker.REMOTE_KEYS))
        self.assertEqual(set(remote_login.NAV_ACTIONS), set(browser_worker.REMOTE_NAV_ACTIONS))
        self.assertEqual(set(remote_login.INPUT_KINDS), set(bs.REMOTE_INPUT_KINDS))


class InputValidation(unittest.TestCase):
    def test_only_the_four_shapes_pass_and_bounded(self):
        self.assertEqual(remote_login.validate_input({'type': 'tap', 'x': 10, 'y': 20.5}), ('tap', {'x': 10.0, 'y': 20.5}))
        self.assertEqual(remote_login.validate_input({'type': 'text', 'text': 'abc'}), ('text', {'text': 'abc'}))
        self.assertEqual(remote_login.validate_input({'type': 'key', 'key': 'Backspace'}), ('key', {'key': 'Backspace'}))
        self.assertEqual(remote_login.validate_input({'type': 'nav', 'action': 'reload'}), ('nav', {'action': 'reload'}))
        self.assertEqual(remote_login.validate_input({'type': 'dialog', 'answer': 'cancel'}), ('dialog', {'answer': 'cancel'}))
        for bad in ({'type': 'dialog', 'answer': 'yes'}, {'type': 'dialog', 'answer': True},{'type': 'tap', 'x': -1, 'y': 0}, {'type': 'tap', 'x': True, 'y': 1}, {'type': 'text', 'text': ''},
                    {'type': 'text', 'text': 'a\nb'}, {'type': 'text', 'text': 'x' * (remote_login.TEXT_LIMIT + 1)},
                    {'type': 'key', 'key': 'F5'}, {'type': 'nav', 'action': 'forward'}, {'type': 'script'}, [], None):
            with self.subTest(bad=bad):
                self.assertIsNone(remote_login.validate_input(bad))


# ---------------------------------------------------------------- the routes over a local server

class RemoteLoginSurface(unittest.TestCase):
    """The owner's instance with an explicit login window open and a remote session for it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = QuickStore(Path(self.tmp.name) / 'data')
        self.calls, self.driver_log, self.drivers = [], [], []

        def launcher(profile_dir, headless):
            driver = WindowDriver(self.driver_log)
            self.drivers.append(driver)
            return driver
        profile_dir = Path(self.tmp.name) / 'profile'
        self.jar = CookieJar(profile_dir / JAR_NAME, MemoryKey())
        self.profile = bs.BrowserProfile(profile_dir, launcher=launcher, jar=self.jar)
        self.service = AgentService(self.store, ModelAdapter(lambda *a, **k: {}), telegram_transport(self.calls),
                                    browser_profile=self.profile)
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': GENERATION, 'cursor': 0})
        self.tunnel = FakeTunnel()
        self.service.remote_login_popen = self.tunnel
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.service))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.close_windows)
        self.service.local_server_port = self.server.server_port
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def close_windows(self):
        """End the session and every login window, and wait for their threads: the window's final save and
        ``on_closed`` write under the data directory, which the temporary directory removes right after."""
        session = self.service.remote_login_session()
        if session is not None:
            session.finish('closed')
        for driver in self.drivers:
            driver.open = False
        for record in list(self.profile._login_windows.values()):
            record['done'].wait(5)
        thread = self.profile._login_thread
        if thread is not None:
            thread.join(5)

    def request(self, path, method='GET', body=None, tunneled=True, cookie=None):
        headers = {}
        if tunneled:
            headers.update({'X-Forwarded-For': '203.0.113.9', 'X-Forwarded-Proto': 'https'})
        if cookie:
            headers['Cookie'] = f'{remote_login.COOKIE_NAME}={cookie}'
        data = json.dumps(body).encode() if body is not None else (b'' if method == 'POST' else None)
        if body is not None:
            headers['Content-Type'] = 'application/json'
        try:
            with urlopen(Request(self.base + path, data=data, method=method, headers=headers), timeout=10) as response:
                return response.status, response.read(), dict(response.headers)
        except HTTPError as error:
            return error.code, error.read(), dict(error.headers)

    def open_window(self, phone=True):
        """An explicit login request (the Settings path) with ``phone``: the window shows, the link is sent."""
        receipt = self.service.open_browser_for_login({'url': 'https://fixture.test/login', 'phone': phone})
        self.assertEqual(receipt['state'], 'opening')
        self.assertTrue(wait_until(lambda: self.service.remote_login_session() is not None and
                                   self.service.remote_login_session().link is not None
                                   and any(method == 'sendMessage' for method, _ in self.calls)), 'the session started and the link was sent')
        return self.service.remote_login_session()

    def code(self, session):
        return '?code=' + session.code

    def frame_url(self, session, full=True):
        """The frame route; ``full`` asks for the frame even when it did not change (as the page's first fetch does)."""
        return remote_login.FRAME_PATH + self.code(session) + ('&full=1' if full else '')

    def bound_cookie(self, session):
        """Open the page as the phone and make its first API call: the cookie the page set is now bound."""
        status, body, headers = self.request(remote_login.PAGE_PATH + self.code(session))
        self.assertEqual(status, 200)
        jar = SimpleCookie()
        jar.load(headers['Set-Cookie'])
        morsel = jar[remote_login.COOKIE_NAME]
        self.assertTrue(morsel['httponly'])
        self.assertTrue(morsel['secure'])
        self.assertEqual(morsel['samesite'], 'Strict')
        cookie = morsel.value
        self.assertEqual(self.request(self.frame_url(session), cookie=cookie)[0], 200)
        return cookie

    # -- the link ---------------------------------------------------------------
    def test_the_link_goes_to_the_owner_chat_only_without_a_preview_and_carries_the_code(self):
        session = self.open_window()
        sends = [body for method, body in self.calls if method == 'sendMessage']
        self.assertEqual(len(sends), 1)
        self.assertEqual(sends[0]['chat_id'], CHAT)
        self.assertIn(session.link, sends[0]['text'])
        self.assertEqual(sends[0]['link_preview_options'], {'is_disabled': True})
        self.assertTrue(session.link.startswith('https://abc123.ngrok-free.app/remote-login?code='))
        self.assertGreaterEqual(len(session.code), 43, 'a 32-byte urlsafe code')
        self.assertIn('--host-header=rewrite', self.tunnel.processes[0].argv)
        self.assertIn('--inspect=false', self.tunnel.processes[0].argv)
        self.assertLessEqual(session.expires - session.created, remote_login.SESSION_SECONDS)

    def test_a_wrong_or_missing_code_is_404_on_every_route(self):
        session = self.open_window()
        cookie = self.bound_cookie(session)
        for path, method in ((remote_login.PAGE_PATH, 'GET'), (remote_login.FRAME_PATH, 'GET'),
                             (remote_login.INPUT_PATH, 'POST'), (remote_login.DONE_PATH, 'POST')):
            for query in ('', '?code=', '?code=wrong', '?code=' + session.code[:-1] + 'x', '?code=%C3%A9'):
                with self.subTest(path=path, query=query):
                    body = {'type': 'key', 'key': 'Enter'} if method == 'POST' else None
                    self.assertEqual(self.request(path + query, method, body, cookie=cookie)[0], 404)
        self.assertTrue(session.alive(), 'guessing never closes the session')
        self.assertFalse([entry for entry in self.driver_log if entry[0].startswith('remote_') and entry[0] != 'remote_begin'],
                         'nothing reached the window')

    def test_a_second_client_without_the_bound_cookie_is_404(self):
        session = self.open_window()
        cookie = self.bound_cookie(session)
        for path, method in ((remote_login.PAGE_PATH, 'GET'), (remote_login.FRAME_PATH, 'GET'),
                             (remote_login.INPUT_PATH, 'POST'), (remote_login.DONE_PATH, 'POST')):
            with self.subTest(path=path, who='no cookie'):
                self.assertEqual(self.request(path + self.code(session), method, {} if method == 'POST' else None)[0], 404)
            with self.subTest(path=path, who='another cookie'):
                self.assertEqual(self.request(path + self.code(session), method, {} if method == 'POST' else None, cookie='x' * 43)[0], 404)
        # The bound phone still works, and reloading its page sets no new cookie.
        status, _body, headers = self.request(remote_login.PAGE_PATH + self.code(session), cookie=cookie)
        self.assertEqual(status, 200)
        self.assertNotIn('Set-Cookie', headers)
        self.assertEqual(self.request(self.frame_url(session), cookie=cookie)[0], 200)
        self.assertTrue(session.alive())

    def test_a_link_preview_fetch_before_the_owner_opens_the_page_does_not_bind(self):
        """Telegram's preview fetcher (or any GET that never runs the page) must not lock the owner out."""
        session = self.open_window()
        status, _body, headers = self.request(remote_login.PAGE_PATH + self.code(session))
        self.assertEqual(status, 200)
        preview = SimpleCookie()
        preview.load(headers['Set-Cookie'])
        preview_cookie = preview[remote_login.COOKIE_NAME].value
        cookie = self.bound_cookie(session)   # the owner's page, opened later, binds on its first API call
        self.assertNotEqual(cookie, preview_cookie)
        self.assertEqual(self.request(self.frame_url(session), cookie=preview_cookie)[0], 404)
        self.assertEqual(self.request(remote_login.PAGE_PATH + self.code(session), cookie=preview_cookie)[0], 404)

    # -- the page -----------------------------------------------------------------
    def test_the_page_is_self_contained_korean_and_talks_only_to_its_own_api(self):
        session = self.open_window()
        status, body, headers = self.request(remote_login.PAGE_PATH + self.code(session))
        self.assertEqual(status, 200)
        page = body.decode()
        csp = headers['Content-Security-Policy']
        self.assertIn("default-src 'none'", csp)
        self.assertIn("connect-src 'self'", csp)
        self.assertIn("form-action 'none'", csp)
        self.assertIn('nonce-', csp)
        for label in ('입력', '엔터', '←지우기', '뒤로', '새로고침', '완료'):
            self.assertIn(label, page)
        self.assertIn('fixture.test', page)
        self.assertNotIn('http://', page.split('<script')[1], 'no external resource')
        self.assertNotIn('https://', page.split('<script')[1])
        self.assertIn(remote_login.INPUT_PATH, page)
        self.assertIn('setInterval(frame,500)', page)
        self.assertNotIn('<link', page)

    # -- driving the window ----------------------------------------------------------
    def test_the_page_clears_text_or_claims_done_only_when_the_operation_said_ok(self):
        """Codex P2: a 200 with ``{ok: false}`` (focus lost, worker refused) must not clear the typed text or show 완료."""
        session = self.open_window()
        cookie = self.bound_cookie(session)
        page = self.request(remote_login.PAGE_PATH + self.code(session), cookie=cookie)[1].decode()
        post = page.split('async function post')[1].split('\n')[1]
        self.assertIn('if(!r.ok)return false;const d=await r.json();return d&&d.ok===true', post)
        self.assertNotRegex(post, r'return r\.ok\}', 'the HTTP status alone never counts as success')
        self.assertIn("if(await post('/api/remote-login/input',{type:'text',text:t})){$('text').value=''}", page)
        self.assertIn("if(await post('/api/remote-login/done')){end(", page)
        # The server side of that contract: a refused input is a 200 whose ok is false.
        self.drivers[-1].open = False
        self.drivers[-1].remote_input = lambda kind, **fields: (_ for _ in ()).throw(bs.WorkerError('not_typable'))
        self.drivers[-1].open = True
        status, answer, _ = self.request(remote_login.INPUT_PATH + self.code(session), 'POST', {'type': 'text', 'text': 'x'}, cookie=cookie)
        self.assertEqual((status, json.loads(answer)), (200, {'ok': False}))

    def test_frames_come_from_the_window_each_time_and_inputs_reach_it_with_no_log(self):
        session = self.open_window()
        cookie = self.bound_cookie(session)
        driver = self.drivers[-1]
        frames_before = driver.frames
        with self.assertLogs('personal_agent', level='DEBUG') as logs:
            status, body, _ = self.request(self.frame_url(session), cookie=cookie)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body), {'jpeg': 'AAAA', 'width': 1280.0, 'height': 900.0, 'dialog': None})
            self.assertEqual(driver.frames, frames_before + 1, 'read from the window now, never cached')
            for body in ({'type': 'tap', 'x': 640, 'y': 300}, {'type': 'text', 'text': SECRET_TEXT},
                         {'type': 'key', 'key': 'Backspace'}, {'type': 'nav', 'action': 'reload'}):
                status, answer, _ = self.request(remote_login.INPUT_PATH + self.code(session), 'POST', body, cookie=cookie)
                self.assertEqual((status, json.loads(answer)), (200, {'ok': True}))
            self.assertEqual(self.request(remote_login.INPUT_PATH + self.code(session), 'POST', {'type': 'key', 'key': 'F5'}, cookie=cookie)[1],
                             b'{"ok": false}')
            self.assertEqual(self.request(remote_login.INPUT_PATH + self.code(session), 'POST', {'type': 'text', 'text': ''}, cookie=cookie)[1],
                             b'{"ok": false}')
            # A log line exists (content-free), so assertLogs has something to inspect.
            logging.getLogger('personal_agent.remote_login').info('remote login probe site=%s', session.site)
        remote = [entry for entry in self.driver_log if entry[0].startswith('remote_') and entry[0] != 'remote_begin']
        self.assertEqual(remote, [('remote_tap', {'x': 640.0, 'y': 300.0}), ('remote_text', {'text': SECRET_TEXT}),
                                  ('remote_key', {'key': 'Backspace'}), ('remote_nav', {'action': 'reload'})])
        self.assertNotIn(SECRET_TEXT, '\n'.join(logs.output))
        self.assertNotIn('640', '\n'.join(logs.output))
        self.assertFalse([line for line in logs.output if 'AAAA' in line], 'no frame in a log')
        for line in logs.output:
            if 'remote login' in line:
                self.assertRegex(line, r'remote login \w+ site=fixture\.test$')
        # Nothing of the input is in the store either.
        with self.store.db() as db:
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for table in tables:
                for row in db.execute(f'SELECT * FROM {table}'):
                    self.assertNotIn(SECRET_TEXT, json.dumps([str(value) for value in row]))
        self.assertFalse(hasattr(session, 'frames') or hasattr(session, 'last_frame'), 'a session keeps no frame')

    def test_a_page_dialog_reaches_the_phone_and_its_answer_reaches_the_window(self):
        session = self.open_window()
        cookie = self.bound_cookie(session)
        driver = self.drivers[-1]
        self.assertTrue(driver.remote, 'the session told the worker to hold dialogs for the phone')
        driver.dialog = {'kind': 'confirm', 'text': '삭제하시겠습니까?'}
        status, body, _ = self.request(self.frame_url(session), cookie=cookie)
        self.assertEqual(json.loads(body)['dialog'], {'kind': 'confirm', 'text': '삭제하시겠습니까?'})
        page = self.request(remote_login.PAGE_PATH + self.code(session), cookie=cookie)[1].decode()
        self.assertIn('기다리고 있어요', page)
        self.assertIn('dialog-ok', page)
        status, answer, _ = self.request(remote_login.INPUT_PATH + self.code(session), 'POST', {'type': 'dialog', 'answer': 'ok'}, cookie=cookie)
        self.assertEqual((status, json.loads(answer)), (200, {'ok': True}))
        self.assertIn(('remote_dialog', {'answer': 'ok'}), self.driver_log)
        self.assertIsNone(json.loads(self.request(self.frame_url(session), cookie=cookie)[1])['dialog'])
        session.finish('done')
        self.assertIn(('remote_end',), self.driver_log, 'ending the session ends the hold')

    def test_a_received_share_refuses_the_window_and_the_phone(self):
        """#940 hook: a site this instance received (family share, #935) never gets a login window here."""
        refusals = []

        def refuse(site):
            refusals.append(site)
            return '이 사이트는 공유받은 로그인이라 여기서 다시 로그인할 수 없어요' if site == 'fixture.test' else None
        self.service.refuse_login = refuse
        for body in ({'url': 'https://www.fixture.test/login'}, {'url': 'https://fixture.test/login', 'phone': True}):
            with self.assertRaises(ValueError) as caught:
                self.service.open_browser_for_login(body)
            self.assertEqual(str(caught.exception), '이 사이트는 공유받은 로그인이라 여기서 다시 로그인할 수 없어요')
        self.assertEqual(refusals, ['fixture.test', 'fixture.test'], 'asked by registrable site')
        self.assertEqual(self.drivers, [], 'no window opened')
        self.assertEqual(self.tunnel.processes, [], 'no tunnel opened')
        with self.assertRaises(remote_login.RemoteLoginError):
            self.service.start_remote_login('w', 'fixture.test', lambda reason: None)
        # Another site is unaffected.
        receipt = self.service.open_browser_for_login({'url': 'https://other.test/login'})
        self.assertEqual(receipt['state'], 'opening')
        self.assertTrue(wait_until(lambda: self.drivers))

    def test_done_closes_the_window_saves_the_jar_and_stops_the_tunnel(self):
        session = self.open_window()
        cookie = self.bound_cookie(session)
        driver = self.drivers[-1]
        self.request(remote_login.INPUT_PATH + self.code(session), 'POST', {'type': 'key', 'key': 'Enter'}, cookie=cookie)
        self.assertTrue(driver.sites, 'the fake sign-in set a session cookie')
        status, body, _ = self.request(remote_login.DONE_PATH + self.code(session), 'POST', {}, cookie=cookie)
        self.assertEqual((status, json.loads(body)), (200, {'ok': True}))
        self.assertTrue(session.alive(), 'review P3-3: the answer left before the tunnel stops')
        self.assertFalse(self.tunnel.processes[0].terminated)
        self.assertTrue(wait_until(lambda: not session.alive()), 'then the session ends')
        self.assertTrue(wait_until(lambda: self.profile.login_window_outcome(session.window) is not None), 'the window closed')
        self.assertEqual(self.profile.login_window_outcome(session.window), ('closed', True), 'closed by request and saved')
        self.assertIn('fixture.test', {site for site in self.jar.import_rows()[0]}, 'the session is in the jar')
        self.assertTrue(self.tunnel.processes[0].terminated, 'the tunnel stopped')
        self.assertFalse(session.alive())
        self.assertEqual(session.reason, 'done')
        self.assertIsNone(self.service.remote_login_session())
        # Afterwards the link is dead on every route, and a second 완료 does nothing.
        for path, method in ((remote_login.PAGE_PATH, 'GET'), (remote_login.FRAME_PATH, 'GET'),
                             (remote_login.INPUT_PATH, 'POST'), (remote_login.DONE_PATH, 'POST')):
            self.assertEqual(self.request(path + self.code(session), method, {} if method == 'POST' else None, cookie=cookie)[0], 404)
        self.assertFalse(session.finish('done'))

    def test_expiry_closes_the_window_and_the_tunnel(self):
        session = self.open_window()
        cookie = self.bound_cookie(session)
        session.expires = session.clock() - 1   # the fake clock moves: the watcher sees it within half a second
        self.assertTrue(wait_until(lambda: not session.alive()), 'the session ended')
        self.assertEqual(session.reason, 'expired')
        self.assertTrue(self.tunnel.processes[0].terminated)
        self.assertTrue(wait_until(lambda: self.profile.login_window_outcome(session.window) is not None), 'the window closed')
        self.assertEqual(self.profile.login_window_outcome(session.window)[0], 'closed')
        self.assertEqual(self.request(self.frame_url(session), cookie=cookie)[0], 404)
        self.assertEqual(self.request(remote_login.PAGE_PATH + self.code(session), cookie=cookie)[0], 404)

    def test_a_mac_close_ends_the_session_and_stops_the_tunnel(self):
        session = self.open_window()
        cookie = self.bound_cookie(session)
        self.drivers[-1].open = False   # the owner closed the window on the Mac
        self.assertTrue(wait_until(lambda: not session.alive()))
        self.assertEqual(session.reason, 'closed')
        self.assertTrue(self.tunnel.processes[0].terminated)
        self.assertEqual(self.request(self.frame_url(session), cookie=cookie)[0], 404)

    def test_one_session_at_a_time(self):
        self.open_window()
        with self.assertRaises(ValueError) as caught:
            self.service.open_browser_for_login({'url': 'https://fixture.test/login', 'phone': True})
        self.assertEqual(str(caught.exception), remote_login.BUSY_TEXT)
        self.assertEqual(len(self.tunnel.processes), 1)

    # -- the tunnel gate ---------------------------------------------------------------
    def test_through_the_tunnel_every_other_route_is_refused_while_and_after_the_session(self):
        session = self.open_window()
        others = ('/', '/api/status', '/api/settings', '/healthz', '/api/claim', '/family-setup', '/api/browser/login')
        for path in others:
            with self.subTest(path=path, when='open'):
                self.assertEqual(self.request(path)[0], 404)
                self.assertEqual(self.request(path, 'POST', {})[0], 404)
                self.assertEqual(self.request(path, 'DELETE')[0], 404)
        self.assertEqual(self.request(remote_login.PAGE_PATH + self.code(session))[0], 200)
        session.finish('done')
        for path in others:
            with self.subTest(path=path, when='after'):
                self.assertEqual(self.request(path)[0], 404, 'a tunnel left up reaches nothing')
        self.assertNotEqual(self.request('/healthz', tunneled=False)[0], 404, 'this Mac itself is unaffected')

    def test_before_any_session_the_tunnel_gate_is_open_as_today(self):
        self.assertFalse(self.service.remote_login_started())
        self.assertNotEqual(self.request('/healthz')[0], 404)
        self.assertEqual(self.request(remote_login.PAGE_PATH + '?code=x')[0], 404)

    # -- the explicit request's preconditions ------------------------------------------
    def test_phone_needs_a_paired_telegram(self):
        self.store.put('telegram', {})
        with self.assertRaises(ValueError):
            self.service.open_browser_for_login({'url': 'https://fixture.test/login', 'phone': True})
        self.assertEqual(self.drivers, [], 'no window was opened')

    def test_a_link_that_cannot_be_sent_closes_the_tunnel_and_keeps_the_window(self):
        """Review P2-1: nothing was wrong with the login itself; the Mac window stays for the owner."""
        self.calls.clear()
        failing = []

        def transport(url, body=None, headers=None, timeout=60):
            if url.endswith('/sendMessage'):
                failing.append(body)
                raise OSError('telegram down')
            return {'ok': True, 'result': True}
        self.service.telegram_transport = transport
        receipt = self.service.open_browser_for_login({'url': 'https://fixture.test/login', 'phone': True})
        self.assertEqual(receipt['state'], 'opening')
        self.assertTrue(wait_until(lambda: failing and self.tunnel.processes and self.tunnel.processes[0].terminated), 'closed')
        self.assertIsNone(self.service.remote_login_session())
        time.sleep(0.3)
        self.assertTrue(self.profile.status()['login_window_open'], 'the window stays open')
        self.assertTrue(self.drivers[-1].open)
        self.assertIn(('remote_end',), self.driver_log, 'dialogs go back to the Mac alone')

    def test_a_tunnel_that_does_not_open_keeps_the_window_and_tells_the_owner(self):
        """Review P2-1: a second ngrok session that exits with an error."""
        tunnel = self.tunnel

        def broken_popen(argv, **kwargs):
            class Process:
                stdout = iter([json.dumps({'lvl': 'eror', 'err': 'ERR_NGROK_108 limited to 1 simultaneous session'}) + '\n'])
                terminated = False

                def terminate(inner):
                    inner.terminated = True
            process = Process()
            tunnel.processes.append(process)
            return process
        self.service.remote_login_popen = broken_popen
        receipt = self.service.open_browser_for_login({'url': 'https://fixture.test/login', 'phone': True})
        self.assertEqual(receipt['state'], 'opening')
        self.assertTrue(wait_until(lambda: [body for method, body in self.calls if method == 'sendMessage']), 'the owner was told')
        notice = [body for method, body in self.calls if method == 'sendMessage'][-1]
        self.assertEqual(notice['chat_id'], CHAT)
        self.assertIn('Mac의 로그인 창에서 로그인해 주세요', notice['text'])
        self.assertIsNone(self.service.remote_login_session())
        self.assertTrue(self.drivers[-1].open, 'the window stays open')
        self.assertTrue(self.profile.status()['login_window_open'])

    def test_a_transient_frame_failure_is_retryable_not_the_end(self):
        """Review P3-2: only a dead session is 404; the page keeps polling on 503."""
        session = self.open_window()
        cookie = self.bound_cookie(session)
        driver = self.drivers[-1]
        original = driver.frame
        driver.frame = lambda: (_ for _ in ()).throw(bs.WorkerError('frame_failed'))
        status, body, _ = self.request(self.frame_url(session), cookie=cookie)
        self.assertEqual((status, json.loads(body)), (503, {'retry': True}))
        self.assertTrue(session.alive())
        driver.frame = original
        self.assertEqual(self.request(self.frame_url(session), cookie=cookie)[0], 200)
        page = self.request(remote_login.PAGE_PATH + self.code(session), cookie=cookie)[1].decode()
        self.assertIn("if(r.status===404){end('이 링크는 닫혔어요.');return}", page)
        self.assertNotIn('세션이 저장됐어요', page.split('r.status===404')[1].split(';')[0], 'the closed text never claims a save')

    def test_an_unchanged_frame_is_204_and_a_changed_one_is_sent(self):
        """Review P3-4: the same image is not sent twice; a page dialog or a changed image is."""
        session = self.open_window()
        cookie = self.bound_cookie(session)   # one full frame already went out
        self.assertEqual(self.request(self.frame_url(session, full=False), cookie=cookie)[0], 204)
        self.assertEqual(self.request(self.frame_url(session, full=False), cookie=cookie)[0], 204)
        self.assertEqual(self.request(self.frame_url(session), cookie=cookie)[0], 200, 'a page load asks for it anyway')
        self.drivers[-1].dialog = {'kind': 'alert', 'text': '안내'}
        status, body, _ = self.request(self.frame_url(session, full=False), cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['dialog'], {'kind': 'alert', 'text': '안내'})
        self.assertEqual(self.request(self.frame_url(session, full=False), cookie=cookie)[0], 204)
        self.assertFalse(hasattr(session, 'last_frame') or getattr(session, '_last_frame', None) == 'AAAA', 'a digest, never the frame')

    def test_two_pages_opened_before_binding_both_keep_their_cookie(self):
        """Review P3-1: a later page open never invalidates an earlier one; whichever calls the API first binds."""
        session = self.open_window()
        cookies = []
        for _ in range(2):
            status, _body, headers = self.request(remote_login.PAGE_PATH + self.code(session))
            self.assertEqual(status, 200)
            jar = SimpleCookie()
            jar.load(headers['Set-Cookie'])
            cookies.append(jar[remote_login.COOKIE_NAME].value)
        first, second = cookies
        self.assertNotEqual(first, second)
        status, _body, headers = self.request(remote_login.PAGE_PATH + self.code(session), cookie=first)
        self.assertEqual(status, 200)
        self.assertNotIn('Set-Cookie', headers, 'a reload with a pending cookie keeps it')
        self.assertEqual(self.request(self.frame_url(session), cookie=first)[0], 200, 'the earlier page binds')
        self.assertEqual(self.request(self.frame_url(session), cookie=second)[0], 404)
        self.assertEqual(self.request(remote_login.PAGE_PATH + self.code(session), cookie=second)[0], 404)
        self.assertEqual(self.request(remote_login.PAGE_PATH + self.code(session))[0], 404)

    def test_a_family_instance_opens_a_phone_link_for_its_own_sign_in(self):
        """#949: a family member signs in to their own account from their phone (only a received
        share is refused, #940); the link goes to that instance's own paired chat."""
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': GENERATION, 'cursor': 0, 'pair_user_id': CHAT})
        receipt = self.service.open_browser_for_login({'url': 'https://fixture.test/login', 'phone': True})
        self.assertEqual(receipt['state'], 'opening')
        self.assertTrue(wait_until(lambda: self.tunnel.processes), 'the tunnel opens')

    def test_a_received_share_site_is_refused_by_default(self):
        """#940: the family-share rule applies without any hook set."""
        from personal_agent import family_share
        self.store.put(family_share.SHARED_KEY, {'fixture.test': {'from': 'owner', 'since': time.time()}})
        self.assertIsNone(self.service.refuse_login)
        for body in ({'url': 'https://www.fixture.test/login'}, {'url': 'https://fixture.test/login', 'phone': True}):
            with self.assertRaises(ValueError) as caught:
                self.service.open_browser_for_login(body)
            self.assertEqual(str(caught.exception), '이 사이트는 공유받은 로그인이라 여기서 다시 로그인할 수 없어요')
        with self.assertRaises(remote_login.RemoteLoginError) as caught:
            self.service.start_remote_login('w', 'fixture.test', lambda reason: None)
        self.assertEqual(str(caught.exception), family_share.LOGIN_REFUSED_TEXT)
        self.assertEqual(self.drivers, [])
        self.assertEqual(self.tunnel.processes, [])
        self.assertEqual(self.service.open_browser_for_login({'url': 'https://other.test/login'})['state'], 'opening')


# ---------------------------------------------------------------- the in-flow prompt's button (#709 + #939)

def _flow_harness():
    from test_flow_login import LoginHarness
    return LoginHarness


class PhoneButton(_flow_harness()):
    """The Telegram login prompt's 휴대폰에서 로그인 starts the session for that Work's window."""

    def setUp(self):
        super().setUp()
        self.tunnel = FakeTunnel()
        self.service.remote_login_popen = self.tunnel
        self.service.local_server_port = 8787
        self.addCleanup(self.end_session)

    def end_session(self):
        session = self.service.remote_login_session()
        if session is not None:
            session.finish('closed')

    def link_messages(self):
        return [body for method, body in self.calls if method == 'sendMessage' and 'remote-login?code=' in str(body.get('text'))]

    def test_the_prompt_offers_the_phone_and_the_link_goes_to_the_owner_chat_only(self):
        from test_flow_login import CHAT as FLOW_CHAT
        job_id, prompt, buttons, notification = self.login_work()
        rows = prompt['reply_markup']['inline_keyboard']
        self.assertEqual(rows[1], [{'text': BROWSER_LOGIN_PHONE_LABEL, 'callback_data': f"p7l:{notification['id']}:phone"}])
        # A stranger's tap, and a tap on another message: nothing starts, nothing is sent.
        self.tap(f"p7l:{notification['id']}:phone", notification['message_id'], sender=777)
        self.tap(f"p7l:{notification['id']}:phone", notification['message_id'] + 1)
        self.assertEqual(self.link_messages(), [])
        self.assertIsNone(self.service.remote_login_session())
        self.assertEqual(self.tunnel.processes, [])
        # The owner's tap on the prompt itself.
        self.tap(f"p7l:{notification['id']}:phone", notification['message_id'])
        self.assertTrue(wait_until(lambda: self.link_messages()), 'the link was sent')
        links = self.link_messages()
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]['chat_id'], FLOW_CHAT)
        self.assertEqual({body['chat_id'] for method, body in self.calls if method == 'sendMessage'}, {FLOW_CHAT},
                         'every message of this flow went to the paired owner chat')
        session = self.service.remote_login_session()
        self.assertIsNotNone(session)
        self.assertEqual(session.window, (self.service._browser_login(job_id) or {}).get('window'))
        self.assertEqual(session.site, 'fixture.test')
        self.assertEqual(self.state(job_id), 'offered', 'the login is still offered; the phone drives its window')
        # A second tap while the session runs: refused, no second tunnel.
        self.tap(f"p7l:{notification['id']}:phone", notification['message_id'])
        self.assertEqual(len(self.tunnel.processes), 1)
        self.assertEqual(len(self.link_messages()), 1)

    def test_done_from_the_phone_settles_the_login_as_login_complete(self):
        job_id, prompt, buttons, notification = self.login_work()
        self.tap(f"p7l:{notification['id']}:phone", notification['message_id'])
        self.assertTrue(wait_until(lambda: self.service.remote_login_session() is not None and self.service.remote_login_session().link))
        session = self.service.remote_login_session()
        self.window().login()   # the owner signed in through the phone
        self.assertTrue(session.finish('done'))
        self.assertEqual(self.settle(job_id), 'resumed')
        self.assertTrue(self.tunnel.processes[0].terminated)
        self.assertEqual(self.store.job(job_id)['status'], 'queued', 'the Work continues once')

    def test_an_in_flow_login_for_a_received_share_shows_no_window_and_no_prompt(self):
        """#940 hook on the in-flow path: the row is unavailable; no window, no Telegram prompt."""
        self.service.refuse_login = lambda site: '이 사이트는 공유받은 로그인이라 여기서 다시 로그인할 수 없어요' if site == 'fixture.test' else None
        self.scripts = self.login_script()
        job_id = self.receive('계정 페이지 확인해줘')
        self.assertTrue(self.service.run_one())
        self.assertTrue(wait_until(lambda: self.state(job_id) == 'unavailable'), self.state(job_id))
        self.assertEqual((self.service._browser_login(job_id) or {}).get('cause'), 'refused')
        self.assertEqual(len(self.drivers), 1, 'only the Work\'s own driver; no login window')
        self.service.deliver_one()
        self.assertEqual(self.prompts(), [])

    def test_an_in_flow_login_for_a_received_share_is_refused_by_default(self):
        """#940 on the in-flow path without a hook: the received site gets no window and no prompt."""
        from personal_agent import family_share
        self.store.put(family_share.SHARED_KEY, {'fixture.test': {'from': 'owner', 'since': time.time()}})
        self.scripts = self.login_script()
        job_id = self.receive('계정 페이지 확인해줘')
        self.assertTrue(self.service.run_one())
        self.assertTrue(wait_until(lambda: self.state(job_id) == 'unavailable'), self.state(job_id))
        self.assertEqual((self.service._browser_login(job_id) or {}).get('cause'), 'refused')
        self.service.deliver_one()
        self.assertEqual(self.prompts(), [])

    def test_a_tunnel_failure_keeps_the_in_flow_window_and_prompt(self):
        """Review P2-1: the login is still offered; the owner is told to use the Mac window."""
        job_id, prompt, buttons, notification = self.login_work()

        def broken_popen(argv, **kwargs):
            class Process:
                stdout = iter([json.dumps({'lvl': 'eror', 'err': 'limited to 1 simultaneous session'}) + '\n'])

                def terminate(inner):
                    pass
            self.tunnel.processes.append(Process())
            return Process()
        self.service.remote_login_popen = broken_popen
        self.tap(f"p7l:{notification['id']}:phone", notification['message_id'])
        self.assertTrue(wait_until(lambda: [b for m, b in self.calls if m == 'sendMessage' and 'Mac의 로그인 창에서' in b.get('text', '')]),
                        'the owner was told')
        time.sleep(0.3)
        self.assertEqual(self.state(job_id), 'offered', 'the login is still offered')
        self.assertTrue(self.window().is_open(), 'the window stays')
        self.assertIsNone(self.service.remote_login_session())
        self.assertEqual([m for m, b in self.calls if m == 'editMessageText'], [], 'the prompt was not edited')
        # The owner can still finish on the Mac.
        self.owner_closes(job_id)
        self.assertEqual(self.settle(job_id), 'resumed')

    def test_a_skip_on_telegram_ends_the_phone_session(self):
        job_id, prompt, buttons, notification = self.login_work()
        self.tap(f"p7l:{notification['id']}:phone", notification['message_id'])
        self.assertTrue(wait_until(lambda: self.service.remote_login_session() is not None and self.service.remote_login_session().link))
        session = self.service.remote_login_session()
        self.tap(f"p7l:{notification['id']}:skip", notification['message_id'])
        self.assertEqual(self.settle(job_id), 'skipped')
        self.assertTrue(wait_until(lambda: not session.alive()))
        self.assertEqual(session.reason, 'closed')
        self.assertTrue(self.tunnel.processes[0].terminated)


if __name__ == '__main__':
    unittest.main()


class MobileUserAgent(unittest.TestCase):
    """#955: the phone session's user agent is a phone browser's and keeps AgentOS's embedded marker."""

    def test_the_mobile_agent_is_a_phone_browser_with_the_marker(self):
        from personal_agent.browser_worker import EMBEDDED_UA_TOKEN, MOBILE_SIZE, mobile_user_agent
        agent = mobile_user_agent()
        self.assertIn('iPhone', agent)
        self.assertIn('Mobile/', agent)
        self.assertTrue(agent.endswith(EMBEDDED_UA_TOKEN), 'AgentOS still refuses its own pages to this browser (#680)')
        self.assertEqual(MOBILE_SIZE, (390.0, 844.0))
