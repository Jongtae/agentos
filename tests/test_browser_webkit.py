"""SEC-BROWSER-02 (#680): the embedded macOS WebKit engine and the encrypted session jar.

Evidence classes, named separately:

* unit (any platform): the encrypted jar (Fernet file at 0600, per-site
  names/counts/times only, unreadable with another key), the Keychain key
  adapter with an injected ``security`` runner (the key never on a command
  line), the profile's save-on-close / per-site delete / delete-all over a
  fake driver, and backup/export exclusion of the jar;
* model-free process integration (any platform): ``WebKitWorkerDriver`` over
  ``tests/browser_fake_worker.py`` speaking the worker protocol (timeouts,
  crash restart with the jar's cookies imported again, typed target errors);
* macOS integration (real ``/usr/bin/security``, test-only service name,
  cleaned up): the Keychain round trip;
* macOS + PyObjC integration (the real worker process, real WebKit): the
  fixture site's product -> 장바구니 -> cart flow, the account page without
  secrets, the payment guard, login_required, trusted native input, cookies
  surviving a worker restart through the jar, per-site delete, and no
  plaintext fixture cookie value under the data directory,
  ``~/Library/WebKit`` or ``~/Library/HTTPStorages``.

No site, provider or category is named in ``src``; the fixture site is the test's own.
"""
import json
import os

import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from personal_agent import browser_session as bs
from personal_agent.agent_runtime import ToolError
from personal_agent.browser_jar import JAR_NAME, CookieJar, JarError, KeychainKey, MemoryKey, SERVICE, store_account
from personal_agent.portable_state import export_owner_state
from personal_agent.quickstart_store import QuickStore

from test_browser_session import OTP, PASSWORD, PASSPORT, TOKEN, Approvals, FixtureHandler, flat

ROOT = Path(__file__).resolve().parents[1]
FAKE_WORKER = Path(__file__).resolve().with_name('browser_fake_worker.py')


def cookie(domain, name='sid', value='v', expires=None):
    return {'name': name, 'value': value, 'domain': domain, 'path': '/', 'expires': expires, 'secure': False,
            'http_only': True, 'same_site': None}


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


# ---------------------------------------------------------------- the jar (unit)

class JarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = Clock()
        self.key = MemoryKey()
        self.jar = CookieJar(Path(self.tmp.name) / 'private' / 'browser-profile' / JAR_NAME, self.key, self.clock)

    def test_saved_cookies_are_encrypted_at_0600_and_listed_without_values(self):
        value = 'fixture-' + uuid.uuid4().hex
        self.jar.save_export({'shop.test': [cookie('.shop.test', value=value), cookie('www.shop.test', 'pref')],
                              'news.test': [cookie('news.test')]}, hosts=['www.shop.test'])
        raw = self.jar.path.read_bytes()
        self.assertNotIn(value.encode(), raw)
        self.assertNotIn(b'shop.test', raw, 'even site names are inside the ciphertext')
        self.assertEqual(stat.S_IMODE(self.jar.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.jar.path.parent.stat().st_mode), 0o700)
        self.assertEqual(self.jar.state(), 'stored')
        sites = self.jar.sites()
        self.assertEqual([(row['site'], row['cookies'], row['last_used']) for row in sites],
                         [('news.test', 1, 1000.0), ('shop.test', 2, 1000.0)])
        self.assertNotIn(value, flat(sites))
        self.assertIn(value, flat(self.jar.cookies()), 'the worker import gets the values back')

    def test_last_used_moves_only_for_sites_this_worker_opened(self):
        self.jar.save_export({'shop.test': [cookie('shop.test')], 'news.test': [cookie('news.test')]}, hosts=[])
        self.clock.now = 2000.0
        self.jar.save_export({'shop.test': [cookie('shop.test')], 'news.test': [cookie('news.test')]},
                             hosts=['m.shop.test'])
        used = {row['site']: row['last_used'] for row in self.jar.sites()}
        self.assertEqual(used, {'shop.test': 2000.0, 'news.test': 1000.0})

    def test_expired_rows_are_not_imported_and_remove_clear_work(self):
        self.jar.save_export({'shop.test': [cookie('shop.test', expires=500.0), cookie('shop.test', 'live', expires=5000.0)],
                              'news.test': [cookie('news.test')]})
        self.assertEqual(sorted(row['name'] for row in self.jar.cookies()), ['live', 'sid'])
        self.assertTrue(self.jar.remove('shop.test'))
        self.assertFalse(self.jar.remove('shop.test'))
        self.assertEqual([row['site'] for row in self.jar.sites()], ['news.test'])
        self.assertTrue(self.jar.clear())
        self.assertFalse(self.jar.path.exists())
        self.assertIsNone(self.key.get(), 'delete-all also deletes the key this jar owns')
        self.assertEqual(self.jar.state(), 'empty')

    def test_another_key_cannot_read_it_and_nothing_falls_back_to_plaintext(self):
        self.jar.save_export({'shop.test': [cookie('shop.test', value='secret-value')]})
        other = CookieJar(self.jar.path, MemoryKey(MemoryKey().create()), self.clock)
        self.assertEqual(other.state(), 'unreadable')
        self.assertEqual(other.sites(), [])
        self.assertEqual(other.cookies(), [])
        with self.assertRaises(JarError):
            other.remove('shop.test')
        missing = CookieJar(self.jar.path, MemoryKey(), self.clock)
        self.assertEqual(missing.state(), 'key_missing')
        # A key that cannot be stored means no jar at all, never a plaintext file.
        class NoKeychain(MemoryKey):
            def create(self):
                raise JarError('keychain_unavailable')
        broken = CookieJar(Path(self.tmp.name) / 'other' / JAR_NAME, NoKeychain(), self.clock)
        with self.assertRaises(JarError):
            broken.save_export({'shop.test': [cookie('shop.test', value='secret-value')]})
        self.assertFalse(broken.path.exists())

    def test_an_empty_export_does_not_create_a_file(self):
        self.jar.save_export({})
        self.assertFalse(self.jar.path.exists())
        self.assertIsNone(self.key.get(), 'no key is created before there is a session to protect')


class KeychainKeyTests(unittest.TestCase):
    def runner(self, results):
        calls = []

        def run(args, input=None, **kwargs):
            calls.append((list(args), input))
            code, out = results.pop(0)
            return subprocess.CompletedProcess(args, code, stdout=out, stderr='')
        return run, calls

    def test_the_key_goes_through_stdin_never_argv(self):
        stored = {}

        def run(args, input=None, **kwargs):
            run.calls.append((list(args), input))
            if args[1] == '-i':
                stored['hex'] = input.split(' -X ')[1].split()[0]
                return subprocess.CompletedProcess(args, 0, stdout='', stderr='')
            if args[1] == 'find-generic-password':
                if 'hex' not in stored:
                    return subprocess.CompletedProcess(args, 44, stdout='', stderr='')
                return subprocess.CompletedProcess(args, 0, stdout=bytes.fromhex(stored['hex']).decode() + '\n', stderr='')
            return subprocess.CompletedProcess(args, 0, stdout='', stderr='')
        run.calls = []
        key = KeychainKey('store-abc', runner=run)
        self.assertIsNone(key.get())
        created = key.create()
        self.assertEqual(key.get(), created)
        for args, stdin in run.calls:
            self.assertNotIn(created.decode(), ' '.join(args))
            self.assertNotIn(created.hex(), ' '.join(args))
        self.assertEqual(run.calls[1][0], ['/usr/bin/security', '-i'])
        self.assertIn(f'-s {SERVICE} ', run.calls[1][1])
        self.assertIn('-a store-abc ', run.calls[1][1])

    def test_errors_are_typed_and_tokens_are_plain(self):
        run, _ = self.runner([(1, '')])
        with self.assertRaises(JarError):
            KeychainKey('store-abc', runner=run).get()
        for bad in ('store abc', 'x;rm', '', 'a\nb'):
            with self.assertRaises(ValueError):
                KeychainKey(bad)
        self.assertRegex(store_account('/tmp/x'), r'^store-[0-9a-f]{24}$')
        self.assertEqual(store_account('/tmp/x'), store_account('/tmp/x/'))


@unittest.skipUnless(sys.platform == 'darwin' and Path('/usr/bin/security').exists(), 'macOS Keychain only')
class KeychainIntegrationTests(unittest.TestCase):
    """Real ``/usr/bin/security`` with a test-only service name that is deleted afterwards."""

    def test_create_read_delete_round_trip(self):
        key = KeychainKey('store-test-' + uuid.uuid4().hex[:12], service='personal-agentos.browser-jar.test-' + uuid.uuid4().hex[:12])
        self.addCleanup(key.delete)
        self.assertIsNone(key.get())
        created = key.create()
        self.assertEqual(key.get(), created)
        self.assertTrue(key.delete())
        self.assertIsNone(key.get())


# ---------------------------------------------------------------- the profile over a fake driver (unit)

class CookieDriver:
    """A driver that holds cookie rows like the worker's in-memory store."""

    def __init__(self, rows=(), fail_delete=False):
        self.rows = list(rows)
        self.fail_delete = fail_delete
        self.closed = False
        self.calls = []

    def cookies_export(self):
        grouped = {}
        for row in self.rows:
            grouped.setdefault(row['domain'].lstrip('.'), []).append(row)
        return grouped, ['shop.test']

    def cookies_delete(self, site):
        self.calls.append(('delete', site))
        if self.fail_delete:
            raise RuntimeError('worker gone')
        self.rows = [row for row in self.rows if row['domain'].lstrip('.') != site]

    def cookies_clear(self):
        self.calls.append(('clear',))
        self.rows = []

    def close(self):
        self.closed = True


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.jar = CookieJar(Path(self.tmp.name) / JAR_NAME, MemoryKey(), Clock())
        self.driver = CookieDriver([cookie('shop.test', value='shop-secret'), cookie('news.test', value='news-secret')])
        self.profile = bs.BrowserProfile(Path(self.tmp.name), launcher=lambda d, h: self.driver, jar=self.jar)

    def test_closing_a_session_saves_its_cookies_into_the_jar_only(self):
        session = self.profile.driver_factory('w1')()
        self.assertTrue(self.profile.status()['in_use'])
        session.close()
        self.assertTrue(self.driver.closed)
        self.assertEqual([row['site'] for row in self.profile.status()['sessions']], ['news.test', 'shop.test'])
        status = self.profile.status()
        self.assertFalse(status['in_use'])
        for secret in ('shop-secret', 'news-secret'):
            self.assertNotIn(secret, flat(status))

    def test_delete_one_site_reaches_the_running_worker_and_the_jar(self):
        self.jar.save_export({'shop.test': [cookie('shop.test')], 'news.test': [cookie('news.test')]})
        session = self.profile.driver_factory('w1')()
        self.assertEqual(self.profile.delete_site('SHOP.test '), {'deleted': True, 'site': 'shop.test'})
        self.assertIn(('delete', 'shop.test'), self.driver.calls)
        session.close()
        self.assertEqual([row['site'] for row in self.profile.status()['sessions']], ['news.test'],
                         'the running worker no longer had it, so closing did not save it back')
        with self.assertRaises(ValueError):
            self.profile.delete_site('  ')

    def test_a_worker_that_cannot_delete_never_saves_that_site_back(self):
        self.driver.fail_delete = True
        session = self.profile.driver_factory('w1')()
        self.profile.delete_site('shop.test')
        session.close()
        self.assertEqual([row['site'] for row in self.profile.status()['sessions']], ['news.test'])

    def test_delete_all_clears_the_worker_the_jar_and_the_key(self):
        self.jar.save_export({'shop.test': [cookie('shop.test')]})
        session = self.profile.driver_factory('w1')()
        self.assertEqual(self.profile.delete_all(), {'deleted': True, 'all': True})
        self.assertIn(('clear',), self.driver.calls)
        self.assertIsNone(self.jar.key.get())
        session.close()
        self.assertEqual(self.profile.status()['sessions'], [])

    def test_the_login_window_saves_when_the_owner_closes_it(self):
        class Window(CookieDriver):
            def __init__(self, rows):
                super().__init__(rows)
                self.shown = []

            def show(self, url, timeout):
                self.shown.append(url)

            def is_open(self):
                return False
        window = Window([cookie('shop.test', value='login-secret')])
        profile = bs.BrowserProfile(Path(self.tmp.name), launcher=lambda d, h: window, jar=self.jar)
        receipt = profile.open_for_login('https://shop.test/login?next=/', wait=True)
        self.assertEqual((receipt['state'], receipt['url']), ('closed', 'https://shop.test/login'))
        self.assertEqual(window.shown, ['https://shop.test/login?next=/'])
        self.assertTrue(window.closed)
        self.assertEqual([row['site'] for row in profile.status()['sessions']], ['shop.test'])
        self.assertNotIn('login-secret', flat(receipt))


# ---------------------------------------------------------------- backup / export exclusion (unit)

class BackupExclusionTests(unittest.TestCase):
    def test_export_and_backup_never_include_the_jar(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / 'data')
        value = 'fixture-' + uuid.uuid4().hex
        key = MemoryKey()
        jar = CookieJar(store.private / 'browser-profile' / JAR_NAME, key)
        jar.save_export({'shop.test': [cookie('shop.test', value=value)]})
        ciphertext = jar.path.read_bytes()
        self.assertNotIn(value.encode(), ciphertext)
        archives = [export_owner_state(store.root, Path(tmp.name) / 'export.tar.gz')]
        script = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'agentos-backup.py'), str(store.root),
                                 str(Path(tmp.name) / 'backup.tar.gz')], capture_output=True, text=True, check=True)
        archives.append(Path(script.stdout.strip()))
        for archive in archives:
            with tarfile.open(archive) as bundle:
                names = bundle.getnames()
                self.assertFalse([name for name in names if 'browser-profile' in name or JAR_NAME in name], names)
                for member in bundle.getmembers():
                    if member.isfile():
                        data = bundle.extractfile(member).read()
                        self.assertNotIn(value.encode(), data)
                        self.assertNotIn(ciphertext[:40], data)


# ---------------------------------------------------------------- the driver's process boundary (fake worker)

class DriverProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / 'commands.jsonl'
        self.seeded = [cookie('shop.test', value='seed-value')]

    def driver(self, **kwargs):
        driver = bs.WebKitWorkerDriver('p', seed=lambda: self.seeded,
                                       command=[sys.executable, str(FAKE_WORKER), str(self.log)], **kwargs)
        self.addCleanup(driver.close)
        return driver

    def commands(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_requests_carry_timeouts_and_targets_carry_the_classified_descriptor(self):
        driver = self.driver()
        self.assertEqual(self.commands()[0]['op'], 'cookies_import', 'the jar is imported on start')
        self.assertEqual(self.commands()[0]['cookies'], self.seeded)
        driver.goto('https://shop.test/p', 7)
        page = driver.snapshot()
        self.assertEqual(page['url'], 'https://shop.test/p')
        driver.click(3, 4)
        driver.type(3, 'hello', 4)
        ops = self.commands()
        self.assertEqual([c['op'] for c in ops], ['cookies_import', 'navigate', 'snapshot', 'click', 'type'])
        self.assertEqual(ops[1]['timeout'], 7.0)
        self.assertEqual(ops[3]['expect'], {'tag': 'button', 'type': 'submit', 'autocomplete': ''})
        with self.assertRaises(ToolError) as caught:
            driver.click(7, 4)
        self.assertEqual(caught.exception.code, 'target_unavailable')
        self.assertEqual(driver.cookies_export(), ({'shop.test': self.seeded}, []))

    def test_worker_timeout_hang_and_crash_are_typed_and_the_next_call_restarts(self):
        driver = self.driver(grace_seconds=0.5)
        with self.assertRaises(TimeoutError):
            driver.goto('https://shop.test/slow', 2)
        self.assertTrue(driver.alive(), 'a worker-side timeout keeps the worker')
        with self.assertRaises(TimeoutError):
            driver.goto('https://shop.test/hang', 1)
        self.assertFalse(driver.alive(), 'an unresponsive worker is killed')
        driver.goto('https://shop.test/ok', 3)
        self.assertEqual(driver.restarts, 1)
        with self.assertRaises(bs.WorkerError):
            driver.goto('https://shop.test/crash', 3)
        driver.goto('https://shop.test/again', 3)
        self.assertEqual(driver.restarts, 2)
        imports = [c for c in self.commands() if c['op'] == 'cookies_import']
        self.assertEqual(len(imports), 3, 'every (re)start imports the jar again')

    def test_a_session_maps_driver_failures_to_typed_tool_errors(self):
        driver = self.driver(grace_seconds=0.5)
        session = bs.BrowserSession(lambda: driver, work_id='w', action_seconds=1)
        page = session.open({'url': 'https://shop.test/p', 'effect': 'navigate'})
        self.assertEqual(page['state'], 'page')
        with self.assertRaises(ToolError) as caught:
            session.open({'url': 'https://shop.test/hang', 'effect': 'navigate'})
        self.assertEqual(caught.exception.code, 'browser_timeout')
        with self.assertRaises(ToolError) as caught:
            session.open({'url': 'https://shop.test/crash', 'effect': 'navigate'})
        self.assertEqual(caught.exception.code, 'browser_failed')
        self.assertNotIn('crash', str(caught.exception))

    def test_an_engine_that_cannot_start_is_a_typed_failure(self):
        env = dict(os.environ, AGENTOS_FAKE_WORKER_MODE='unavailable')
        original = subprocess.Popen

        def popen(*args, **kwargs):
            kwargs['env'] = env
            return original(*args, **kwargs)
        from unittest import mock
        with mock.patch.object(bs.subprocess, 'Popen', popen):
            with self.assertRaises(bs.WorkerError) as caught:
                bs.WebKitWorkerDriver('p', command=[sys.executable, str(FAKE_WORKER), str(self.log)])
        self.assertEqual(caught.exception.code, 'worker_unavailable')

    def test_the_login_window_state_follows_the_owner_closing_it(self):
        driver = self.driver()
        driver.show('https://shop.test/login', 5)
        self.assertTrue(driver.is_open())
        driver.show('https://shop.test/autoclose', 5)
        for _ in range(40):
            if not driver.is_open():
                break
            time.sleep(0.05)
        self.assertFalse(driver.is_open())


# ---------------------------------------------------------------- the real worker (macOS + PyObjC)

def _webkit_ready():
    return bs.webkit_unavailable_reason() is None and Path('/usr/bin/security').exists()


class SessionFixtureHandler(FixtureHandler):
    """The shared fixture site plus a session cookie and a trusted-input page."""

    def do_GET(self):
        path = urlsplit(self.path).path
        value = self.server.cookie_value
        if path == '/session-start':
            data = '<html><head><title>세션</title></head><body><h1>세션 시작</h1></body></html>'.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Set-Cookie', f'fixture_sid={value}; Path=/; HttpOnly; Max-Age=3600')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == '/whoami':
            present = value in (self.headers.get('Cookie') or '')
            return self._send(f'<html><head><title>계정 상태</title></head><body><p>{"세션 있음" if present else "세션 없음"}</p></body></html>')
        if path == '/windows':
            return self._send('''<html><head><title>새 창</title></head><body>
              <a href="/cart" target="_blank">새 창 장바구니</a>
              <a href="file:///etc/hosts" target="_blank">로컬 파일</a></body></html>''')
        if path == '/trusted':
            return self._send('''<html><head><title>입력</title></head><body>
              <button type="button" onclick="document.getElementById('r').textContent='click trusted='+event.isTrusted">누르기</button>
              <input aria-label="메모" oninput="document.getElementById('r2').textContent='input trusted='+event.isTrusted">
              <p id="r">대기</p><p id="r2">대기</p></body></html>''')
        return super().do_GET()


@unittest.skipUnless(_webkit_ready(), 'embedded WebKit needs macOS with pyobjc-framework-WebKit')
class WebKitIntegrationTests(unittest.TestCase):
    """Evidence class: model-free integration with the real worker process and system WebKit."""

    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), SessionFixtureHandler)
        self.server.posts = []
        self.server.cookie_value = 'agentos-fixture-' + uuid.uuid4().hex
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.origin = f'http://127.0.0.1:{self.server.server_address[1]}'
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = QuickStore(Path(self.tmp.name) / 'data')
        profile_dir = self.store.private / 'browser-profile'
        # The real Keychain, under a test-only service name this test deletes.
        self.key = KeychainKey(store_account(profile_dir), service='personal-agentos.browser-jar.test-' + uuid.uuid4().hex[:12])
        self.addCleanup(self.key.delete)
        self.jar = CookieJar(profile_dir / JAR_NAME, self.key)
        self.profile = bs.BrowserProfile(profile_dir, jar=self.jar)

    def session(self, work_id):
        return bs.BrowserSession(self.profile.driver_factory(work_id), work_id=work_id, approvals=Approvals(), steps=40,
                                 excluded=lambda: [PASSPORT])

    def test_product_to_cart_guard_login_and_trusted_input_through_the_real_worker(self):
        sess = self.session('work-int')
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
            account = sess.open({'url': self.origin + '/account', 'effect': 'read'})
            for secret in (PASSWORD, OTP, TOKEN):
                self.assertNotIn(secret, flat(account))
            sess.open({'url': self.origin + '/checkout', 'effect': 'navigate'})
            with self.assertRaises(ToolError) as caught:
                sess.type({'target': '카드번호', 'text': '4111', 'effect': 'navigate'})
            self.assertEqual(caught.exception.code, 'approval_required')
            with self.assertRaises(ToolError) as caught:
                sess.click({'target': '결제하기', 'effect': 'mutate'})
            self.assertEqual(caught.exception.code, 'approval_required')
            self.assertEqual(self.server.posts, ['/cart'], 'no payment form was submitted')
            compound = sess.open({'url': self.origin + '/checkout-compound', 'effect': 'navigate'})
            for secret in ('4242424242424242', '987', '246810'):
                self.assertNotIn(secret, flat(compound))
            reset = sess.open({'url': self.origin + '/reset/' + PASSPORT, 'effect': 'read'})
            for secret in (PASSPORT, 'hunter2', 'abcDEF123456secret'):
                self.assertNotIn(secret, flat(reset))
            login = sess.open({'url': self.origin + '/login', 'effect': 'navigate'})
            self.assertEqual(login['state'], 'login_required')
            sess.open({'url': self.origin + '/trusted', 'effect': 'navigate'})
            sess.click({'target': '누르기', 'effect': 'navigate'})
            typed = sess.type({'target': '메모', 'text': '안녕', 'effect': 'mutate'})
            self.assertIn('click trusted=true', typed['text'])
            self.assertIn('input trusted=true', typed['text'])
            self.assertIn('안녕', [row.get('value') for row in typed['elements']])
            # A new-window link opens in the same view; a page can never make it load a local file.
            sess.open({'url': self.origin + '/windows', 'effect': 'navigate'})
            local = sess.click({'target': '로컬 파일', 'effect': 'navigate'})
            self.assertEqual(local['title'], '새 창')
            self.assertTrue(local['url'].startswith(self.origin))
            opened = sess.click({'target': '새 창 장바구니', 'effect': 'navigate'})
            self.assertEqual(opened['title'], '장바구니')
        finally:
            sess.close()
        self.assertFalse(self.profile.status()['in_use'])

    def test_sessions_survive_a_restart_only_through_the_encrypted_jar(self):
        value = self.server.cookie_value
        first = self.session('work-1')
        try:
            first.open({'url': self.origin + '/session-start', 'effect': 'navigate'})
            self.assertEqual(first.open({'url': self.origin + '/whoami', 'effect': 'read'})['text'], '세션 있음')
        finally:
            first.close()
        self.assertEqual(stat.S_IMODE(self.jar.path.stat().st_mode), 0o600)
        self.assertIsNotNone(self.key.get(), 'the jar key is in the Keychain')
        self.assertNotIn(value.encode(), self.jar.path.read_bytes())
        sessions = self.profile.status()['sessions']
        self.assertEqual([row['site'] for row in sessions], ['127.0.0.1'])
        self.assertNotIn(value, flat(self.profile.status()))
        second = self.session('work-2')
        try:
            self.assertEqual(second.open({'url': self.origin + '/whoami', 'effect': 'read'})['text'], '세션 있음',
                             'a new worker process got the session from the jar')
        finally:
            second.close()
        self.assertEqual(self.profile.delete_site('127.0.0.1')['deleted'], True)
        third = self.session('work-3')
        try:
            self.assertEqual(third.open({'url': self.origin + '/whoami', 'effect': 'read'})['text'], '세션 없음')
        finally:
            third.close()
        self.assertEqual(self.scan_for(value), [], 'no plaintext copy of the fixture cookie anywhere')

    def scan_for(self, value):
        needle = value.encode()
        home = Path.home() / 'Library'
        hits = []
        for root in (Path(self.tmp.name), home / 'WebKit', home / 'HTTPStorages'):
            if not root.is_dir():
                continue
            for folder, _, files in os.walk(root, followlinks=False):
                for name in files:
                    path = Path(folder) / name
                    try:
                        if path.is_symlink() or path.stat().st_size > 64 * 1024 * 1024:
                            continue
                        if needle in path.read_bytes():
                            hits.append(str(path))
                    except OSError:
                        continue
        return hits


if __name__ == '__main__':
    unittest.main()
