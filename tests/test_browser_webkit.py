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
        self.assertEqual(self.jar.clear(), {'jar_deleted': True, 'key_deleted': True, 'key_error': None})
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

    def test_a_key_that_cannot_be_removed_is_reported_not_hidden(self):
        class Stuck(MemoryKey):
            def delete(self):
                raise JarError('keychain_delete_failed')
        jar = CookieJar(Path(self.tmp.name) / 'stuck' / JAR_NAME, Stuck(), self.clock)
        jar.save_export({'shop.test': [cookie('shop.test')]})
        self.assertEqual(jar.clear(), {'jar_deleted': True, 'key_deleted': False, 'key_error': 'keychain_delete_failed'})
        self.assertFalse(jar.path.exists(), 'the sessions themselves are gone')

    def test_saving_merges_and_never_drops_sites_that_were_not_imported(self):
        self.jar.save_export({'shop.test': [cookie('shop.test')], 'news.test': [cookie('news.test')],
                              'mail.test': [cookie('mail.test')]})
        sites, rows = self.jar.import_rows()
        self.assertEqual(sites, {'shop.test', 'news.test', 'mail.test'})
        # This worker was given shop and news only; it signed out of news and signed in to docs.
        self.jar.save_export({'shop.test': [cookie('shop.test', value='new')], 'docs.test': [cookie('docs.test')]},
                             imported={'shop.test', 'news.test'})
        self.assertEqual(sorted(row['site'] for row in self.jar.sites()), ['docs.test', 'mail.test', 'shop.test'])
        # With a set, an unreadable jar is never overwritten.
        other = CookieJar(self.jar.path, MemoryKey(MemoryKey().create()), self.clock)
        with self.assertRaises(JarError):
            other.import_rows()
        before = self.jar.path.read_bytes()
        with self.assertRaises(JarError):
            other.save_export({'x.test': [cookie('x.test')]}, imported=set())
        self.assertEqual(self.jar.path.read_bytes(), before)

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
        run, _ = self.runner([(1, ''), (0, ''), (44, ''), (51, '')])
        key = KeychainKey('store-abc', runner=run)
        with self.assertRaises(JarError):
            key.get()
        self.assertTrue(key.delete())
        self.assertFalse(key.delete(), 'no item: nothing to delete')
        with self.assertRaises(JarError) as caught:
            key.delete()
        self.assertEqual(str(caught.exception), 'keychain_delete_failed')
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
        if self.fail_delete:
            raise RuntimeError('worker gone')
        self.rows = []

    def discard(self):
        self.calls.append(('discard',))

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

    def test_a_worker_that_cannot_delete_is_stopped_and_nothing_it_holds_is_saved(self):
        self.jar.save_export({'shop.test': [cookie('shop.test')]})
        self.driver.fail_delete = True
        session = self.profile.driver_factory('w1')()
        reply = self.profile.delete_site('shop.test')
        self.assertEqual((reply['deleted'], reply['running_browser'], reply['removed_from_jar']), (False, 'failed', True),
                         'the deletion is not acknowledged')
        self.assertEqual(reply['message'], bs.WORKER_DELETE_FAILED_TEXT)
        self.assertIn(('discard',), self.driver.calls, 'the worker is stopped without an export')
        self.driver.rows.append(cookie('late.test'))   # acquired after the failed delete
        session.close()
        self.assertEqual(self.profile.status()['sessions'], [], 'no site of that worker was saved, the late one included')
        self.assertEqual(self.profile.status()['storage']['save_error'], 'worker_delete_failed')

    def test_a_failed_clear_in_the_running_worker_is_reported_and_blocks_its_export(self):
        self.jar.save_export({'shop.test': [cookie('shop.test')]})
        self.driver.fail_delete = True
        session = self.profile.driver_factory('w1')()
        reply = self.profile.delete_all()
        self.assertFalse(reply['deleted'])
        self.assertEqual((reply['running_browser'], reply['jar_deleted'], reply['key_error']), ('failed', True, None))
        self.assertEqual(reply['message'], bs.WORKER_DELETE_FAILED_TEXT)
        self.driver.rows.append(cookie('late.test', value='late-secret'))
        session.close()
        self.assertFalse(self.jar.path.exists(), 'nothing from that worker was saved after the clear')

    def test_delete_all_reports_a_key_that_could_not_be_removed(self):
        class Stuck(MemoryKey):
            def delete(self):
                raise JarError('keychain_delete_failed')
        jar = CookieJar(Path(self.tmp.name) / 'stuck' / JAR_NAME, Stuck(), Clock())
        jar.save_export({'shop.test': [cookie('shop.test')]})
        profile = bs.BrowserProfile(Path(self.tmp.name) / 'stuck', launcher=lambda d, h: self.driver, jar=jar)
        reply = profile.delete_all()
        self.assertEqual((reply['deleted'], reply['jar_deleted'], reply['key_deleted'], reply['key_error']),
                         (False, True, False, 'keychain_delete_failed'))
        self.assertEqual(reply['message'], bs.KEY_DELETE_FAILED_TEXT)

    def test_a_jar_that_cannot_be_read_at_start_is_never_saved_over(self):
        from unittest import mock
        self.jar.save_export({'shop.test': [cookie('shop.test')], 'news.test': [cookie('news.test')]})
        before = self.jar.path.read_bytes()
        locked = CookieJar(self.jar.path, MemoryKey(), Clock())   # the Keychain key cannot be read

        class Worker(CookieDriver):
            def __init__(self, profile_id, seed=None, **kwargs):
                super().__init__([cookie('only.test')])
                self.seeded = seed()
        with mock.patch.object(bs, 'WebKitWorkerDriver', Worker):
            profile = bs.BrowserProfile(Path(self.tmp.name), jar=locked, available=lambda: True)
            session = profile.driver_factory('w1')()
            self.assertEqual(session.seeded, [])
            session.close()
        self.assertEqual(self.jar.path.read_bytes(), before, 'the jar was left as it was')
        self.assertEqual(profile.save_error, 'key_missing')
        # With a readable jar the import is recorded and the save merges.
        with mock.patch.object(bs, 'WebKitWorkerDriver', Worker):
            profile = bs.BrowserProfile(Path(self.tmp.name), jar=self.jar, available=lambda: True)
            session = profile.driver_factory('w2')()
            self.assertEqual(len(session.seeded), 2)
            session.close()
        self.assertEqual([row['site'] for row in self.jar.sites()], ['only.test'],
                         'imported sites the worker no longer had were dropped, the new one kept')

    def test_the_legacy_playwright_profile_is_deleted_once_and_by_delete_all(self):
        from personal_agent.quickstart_service import AgentService
        store = QuickStore(Path(self.tmp.name) / 'data')
        legacy = store.private / 'browser-profile'
        (legacy / 'Default').mkdir(parents=True)
        (legacy / 'Default' / 'Cookies').write_bytes(b'plaintext-legacy-cookie')
        (legacy / 'Local State').write_text('{}')
        jar = CookieJar(legacy / JAR_NAME, MemoryKey(), Clock())
        jar.save_export({'shop.test': [cookie('shop.test')]})
        profile = bs.BrowserProfile(legacy, launcher=lambda d, h: self.driver, jar=jar)
        service = AgentService(store, browser_profile=profile)
        self.assertEqual(sorted(path.name for path in legacy.iterdir()), [JAR_NAME], 'only the encrypted jar is left')
        self.assertIsNotNone(service.browser_status()['legacy_profile_removed_at'])
        (legacy / 'Default').mkdir()
        service.delete_browser_sessions({'all': True})
        self.assertFalse(any(legacy.iterdir()))
        self.assertIsNone(service.browser_status()['legacy_profile_removed_at'])

    def test_settings_never_waits_on_the_keychain(self):
        import threading as _threading
        gate = _threading.Event()

        class Slow(MemoryKey):
            def get(self):
                gate.wait(5)
                return super().get()
        key = Slow(MemoryKey().create())
        writer = CookieJar(self.jar.path, MemoryKey(key.key), Clock())
        writer.save_export({'shop.test': [cookie('shop.test')]})
        profile = bs.BrowserProfile(Path(self.tmp.name), launcher=lambda d, h: self.driver,
                                    jar=CookieJar(self.jar.path, key, Clock()))
        started = time.monotonic()
        self.assertEqual(profile.status()['storage']['state'], 'checking')
        self.assertLess(time.monotonic() - started, 1.0)
        gate.set()
        for _ in range(100):
            if profile.status()['storage']['state'] != 'checking':
                break
            time.sleep(0.02)
        self.assertEqual(profile.status()['storage']['state'], 'stored')
        self.assertEqual([row['site'] for row in profile.status()['sessions']], ['shop.test'])

    def test_delete_all_clears_the_worker_the_jar_and_the_key(self):
        self.jar.save_export({'shop.test': [cookie('shop.test')]})
        session = self.profile.driver_factory('w1')()
        reply = self.profile.delete_all()
        self.assertEqual((reply['deleted'], reply['all'], reply['key_deleted'], reply['running_browser']),
                         (True, True, True, 'cleared'))
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
        # The full descriptor the guard classified, and the guard's payment tokens.
        self.assertEqual(ops[3]['expect'], {'tag': 'button', 'type': 'submit', 'autocomplete': '', 'name': 'Go',
                                            'in_form': False, 'payment_form': False})
        self.assertEqual(ops[3]['tokens'], sorted(bs.PAYMENT_AUTOCOMPLETE))
        self.assertEqual(ops[4]['expect'], ops[3]['expect'])
        with self.assertRaises(ToolError) as caught:
            driver.click(7, 4)   # the fake worker answers target_obscured for it
        self.assertEqual(caught.exception.code, 'target_unavailable')
        self.assertEqual(self.commands()[-1]['expect']['payment_form'], True, "the pay button's form holds a card field")
        sent = len(self.commands())
        with self.assertRaises(ToolError) as caught:
            driver.type(5, 'x', 4)   # index 5 was never in a snapshot: nothing is sent
        self.assertEqual(caught.exception.code, 'target_unavailable')
        self.assertEqual(len(self.commands()), sent)
        with self.assertRaises(ToolError) as caught:
            driver.goto('https://shop.test/blocked', 3)
        self.assertEqual(caught.exception.code, 'blocked_destination')
        self.assertEqual(driver.cookies_export(), ({'shop.test': self.seeded}, []))

    def test_the_worker_runs_with_a_minimal_environment_a_fixed_cwd_and_no_cwd_on_its_path(self):
        from unittest import mock
        seen = {}

        class Stop(Exception):
            pass

        def popen(command, **kwargs):
            seen['command'], seen['kwargs'] = command, kwargs
            raise Stop()
        planted = {'OPENAI_API_KEY': 'sk-planted', 'ANTHROPIC_API_KEY': 'planted', 'GITHUB_API_KEY': 'planted',
                   'GH_TOKEN': 'planted', 'AGENTOS_DATA': '/planted', 'TELEGRAM_BOT_TOKEN': 'planted',
                   'AWS_SECRET_ACCESS_KEY': 'planted', 'HOME': '/Users/owner', 'PATH': '/usr/bin:/bin', 'LANG': 'ko_KR.UTF-8'}
        with mock.patch.dict(os.environ, planted), mock.patch.object(bs.subprocess, 'Popen', popen):
            with self.assertRaises(Stop):
                bs.WebKitWorkerDriver('p', cwd=self.tmp.name)
        env = seen['kwargs']['env']
        self.assertLessEqual(set(env), set(bs.WORKER_ENVIRONMENT))
        self.assertNotIn('planted', json.dumps(env))
        self.assertEqual((env['HOME'], env['LANG']), ('/Users/owner', 'ko_KR.UTF-8'))
        self.assertEqual(seen['kwargs']['cwd'], self.tmp.name)
        self.assertEqual(seen['command'][:4], [sys.executable, '-P', '-m', 'personal_agent.browser_worker'])
        self.assertNotIn('--test-allow-origin', seen['command'], 'production never allows a local origin')

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

    def test_a_close_that_arrives_while_show_is_pending_is_not_lost(self):
        driver = self.driver()
        driver.show('https://shop.test/closefirst', 5)   # the worker reports 'hidden' before answering
        self.assertFalse(driver.is_open())

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


# ---------------------------------------------------------------- destinations, output encoding, the UI marker (unit)

class DestinationTests(unittest.TestCase):
    def test_local_and_private_destinations_are_refused_by_name_literal_and_dns(self):
        from personal_agent import browser_worker as bw
        for url in ('http://127.0.0.1:8765/', 'http://localhost:8765/api/state', 'http://agentos.localhost:8765/',
                    'http://[::1]:8765/', 'http://10.0.0.2/', 'http://192.168.1.1/', 'http://169.254.169.254/latest',
                    'http://printer.local/', 'http://0.0.0.0/', 'file:///etc/hosts', 'ftp://shop.test/'):
            self.assertTrue(bw.local_url(url), url)
            self.assertEqual(bw.destination_refusal(url, resolver=lambda *a, **k: []), 'blocked_destination', url)
        public = lambda *a, **k: [(2, 1, 6, '', ('93.184.215.14', 443))]
        loop = lambda *a, **k: [(2, 1, 6, '', ('93.184.215.14', 443)), (2, 1, 6, '', ('127.0.0.1', 443))]
        self.assertIsNone(bw.destination_refusal('https://shop.example/', resolver=public))
        self.assertEqual(bw.destination_refusal('https://rebind.example/', resolver=loop), 'blocked_destination',
                         'a public name that resolves to loopback is refused')
        def fails(*a, **k):
            raise OSError('nxdomain')
        self.assertIsNone(bw.destination_refusal('https://missing.example/', resolver=fails))
        # The test-only allowance is one exact origin.
        self.assertIsNone(bw.destination_refusal('http://127.0.0.1:5000/x', ('127.0.0.1:5000',)))
        self.assertEqual(bw.destination_refusal('http://127.0.0.1:5001/x', ('127.0.0.1:5000',)), 'blocked_destination')

    def test_a_session_refuses_this_computer_before_any_driver_runs(self):
        from test_browser_session import FakeDriver
        driver = FakeDriver()
        sess = bs.BrowserSession(lambda: driver, work_id='w')
        for url in ('http://127.0.0.1:8765/', 'http://localhost:8765/', 'http://[::1]/', 'http://192.168.0.10/admin'):
            with self.assertRaises(ToolError) as caught:
                sess.open({'url': url, 'effect': 'read'})
            self.assertEqual(caught.exception.code, 'blocked_destination')
        self.assertEqual(driver.log, [])
        self.assertEqual(sess.steps_used, 0)
        allowed = bs.BrowserSession(lambda: driver, work_id='w', allowed_origins_for_tests=('127.0.0.1:9',))
        with self.assertRaises(ToolError) as caught:
            allowed.open({'url': 'http://127.0.0.1:10/', 'effect': 'read'})
        self.assertEqual(caught.exception.code, 'blocked_destination')
        profile = bs.BrowserProfile(Path(tempfile.mkdtemp()), launcher=lambda d, h: driver, jar=CookieJar(Path(tempfile.mkdtemp()) / JAR_NAME, MemoryKey()))
        with self.assertRaises(ValueError):
            profile.open_for_login('http://127.0.0.1:8765/')

    def test_worker_lines_are_ascii_and_emit_never_raises(self):
        import io
        from personal_agent.browser_worker import make_emit
        out = io.StringIO()
        emit = make_emit(out)
        emit({'id': 1, 'ok': True, 'page': {'title': 'a\ud800b', 'name': 'a' * 159 + '\U0001F600'}})
        emit({'id': 2, 'ok': True, 'bad': object()})
        lines = out.getvalue().splitlines()
        self.assertTrue(all(line.isascii() for line in lines))
        self.assertEqual(json.loads(lines[0])['page']['name'], 'a' * 159 + '\U0001F600')
        self.assertEqual(json.loads(lines[1]), {'id': 2, 'ok': False, 'error': 'encode_failed'})

        class Broken:
            def write(self, text):
                raise OSError('pipe closed')
            flush = write
        make_emit(Broken())({'id': 3, 'ok': True})   # does not raise

    def test_the_owner_ui_and_api_refuse_the_embedded_browser(self):
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen
        from personal_agent.browser_worker import EMBEDDED_UA_TOKEN, safari_application_name
        from personal_agent.quickstart import make_handler
        from personal_agent.quickstart_service import AgentService
        self.assertIn(EMBEDDED_UA_TOKEN, safari_application_name())
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = QuickStore(tmp.name)
        service = AgentService(store, browser_profile=bs.BrowserProfile(Path(tmp.name) / 'p', launcher=lambda d, h: None))
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(service))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f'http://127.0.0.1:{server.server_port}'
        agent = 'Mozilla/5.0 (Macintosh) AppleWebKit/605.1.15 (KHTML, like Gecko) ' + safari_application_name()
        for path, body in (('/', None), ('/api/state', None), ('/api/browser/approval', b'{"work_id":"x","decision":"approve"}'),
                           ('/api/local-login', b'{}')):
            request = Request(base + path, data=body, headers={'User-Agent': agent, 'Content-Type': 'application/json',
                                                                 'Origin': base})
            with self.assertRaises(HTTPError) as caught:
                urlopen(request, timeout=3)
            self.assertEqual(caught.exception.code, 403, path)
        try:
            with urlopen(Request(base + '/healthz', headers={'User-Agent': 'Mozilla/5.0 Safari/605.1.15'}), timeout=3) as response:
                status = response.status
        except HTTPError as error:
            status = error.code
        self.assertNotEqual(status, 403, 'an ordinary browser is unaffected')


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
        if path == '/memo-trap':
            # Review P1-1 repro: focusing the memo inserts a card field at the top of <body>.
            return self._send('''<html><head><title>메모</title></head><body>
              <p id="leak">없음</p>
              <label>메모 <input id="memo" type="text" onfocus="if(!window.armed){window.armed=1;var c=document.createElement('input');
                c.setAttribute('autocomplete','cc-number');c.setAttribute('aria-label','카드');
                c.oninput=function(){document.getElementById('leak').textContent='카드 입력됨:'+c.value;};document.body.prepend(c);}"></label>
              </body></html>''')
        if path == '/wide':
            # Review P2-1 repro: a surrogate pair at the label cut and a lone surrogate in the title.
            return self._send('<html><head><title>넓은 글자</title></head><body><button type="button" aria-label="'
                              + '가' * 159 + '\U0001F600' + '">버튼</button><script>document.title = "x\\uD800y";</script></body></html>')
        if path == '/to-agentos':
            self.send_response(302)
            self.send_header('Location', self.server.agentos_origin + '/api/state')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        if path == '/open-agentos':
            return self._send('<html><head><title>열기</title></head><body><button type="button" onclick="window.open(\''
                              + self.server.agentos_origin + '/\')">AgentOS 열기</button>'
                              + '<form action="' + self.server.agentos_origin + '/api/browser/approval" method="post">'
                              + '<button type="submit">승인 보내기</button></form></body></html>')
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
        # A stand-in for the owner's AgentOS on another loopback port: it must never be reached.
        self.agentos = ThreadingHTTPServer(('127.0.0.1', 0), SessionFixtureHandler)
        self.agentos.posts, self.agentos.cookie_value, self.agentos.hits = [], 'unused', []
        self.agentos.agentos_origin = ''
        threading.Thread(target=self.agentos.serve_forever, daemon=True).start()
        self.addCleanup(self.agentos.server_close)
        self.addCleanup(self.agentos.shutdown)
        self.agentos_origin = f'http://127.0.0.1:{self.agentos.server_address[1]}'
        self.server.agentos_origin = self.agentos_origin
        self.fixture = f'127.0.0.1:{self.server.server_address[1]}'
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = QuickStore(Path(self.tmp.name) / 'data')
        profile_dir = self.store.private / 'browser-profile'
        # The real Keychain, under a test-only service name this test deletes.
        self.key = KeychainKey(store_account(profile_dir), service='personal-agentos.browser-jar.test-' + uuid.uuid4().hex[:12])
        self.addCleanup(self.key.delete)
        self.jar = CookieJar(profile_dir / JAR_NAME, self.key)
        self.profile = bs.BrowserProfile(profile_dir, jar=self.jar)
        # Test-only: the fixture origin (and only it) may be loaded from loopback.
        self.profile.allow_origins_for_tests(self.fixture)

    def session(self, work_id):
        return bs.BrowserSession(self.profile.driver_factory(work_id), work_id=work_id, approvals=Approvals(), steps=40,
                                 excluded=lambda: [PASSPORT], allowed_origins_for_tests=(self.fixture,))

    def test_typing_never_lands_in_a_field_the_page_inserts_on_focus(self):
        sess = self.session('work-trap')
        try:
            sess.open({'url': self.origin + '/memo-trap', 'effect': 'navigate'})
            try:
                page = sess.type({'target': '메모', 'text': '장보기 목록', 'effect': 'mutate'})
            except ToolError as refused:
                self.assertEqual(refused.code, 'target_unavailable')
                page = sess.read()
            self.assertNotIn('카드 입력됨', page['text'], 'nothing was typed into the inserted card field')
            self.assertIn('없음', page['text'])
            values = {row['name']: row.get('value') for row in page['elements']}
            # Either the text is in the memo, or the step was refused because the
            # page moved the pointer's target (the click guard): never elsewhere.
            self.assertIn(values.get('메모'), ('장보기 목록', None), page['elements'])
            if values.get('메모') is None:
                self.assertNotIn('장보기', flat(page))
        finally:
            sess.close()

    def test_emoji_at_the_cut_and_a_lone_surrogate_do_not_break_the_worker(self):
        sess = self.session('work-wide')
        try:
            page = sess.open({'url': self.origin + '/wide', 'effect': 'read'})
            self.assertEqual(page['state'], 'page')
            self.assertIn('\ufffd', page['title'], 'the lone surrogate is replaced, not passed on')
            json.dumps(page, ensure_ascii=False).encode('utf-8')
            names = [row['name'] for row in page['elements']]
            self.assertTrue(any(name.startswith('가' * bs.NAME_LIMIT) for name in names), names)
            again = sess.open({'url': self.origin + '/product', 'effect': 'read'})
            self.assertIn('세탁세제 3L', again['text'], 'the same worker keeps working')
        finally:
            sess.close()

    def test_the_production_policy_refuses_the_agentos_port_by_redirect_and_window_open(self):
        agentos_port = self.agentos.server_address[1]
        plain = bs.BrowserSession(lambda: None, work_id='w')   # no test allowance at all
        with self.assertRaises(ToolError) as caught:
            plain.open({'url': f'http://127.0.0.1:{agentos_port}/', 'effect': 'read'})
        self.assertEqual(caught.exception.code, 'blocked_destination')
        sess = self.session('work-policy')
        try:
            with self.assertRaises(ToolError) as caught:
                sess.open({'url': self.origin + '/to-agentos', 'effect': 'read'})
            self.assertEqual(caught.exception.code, 'blocked_destination', 'a redirect to the AgentOS port is refused')
            sess.open({'url': self.origin + '/open-agentos', 'effect': 'read'})
            with self.assertRaises(ToolError) as caught:
                sess.click({'target': 'AgentOS 열기', 'effect': 'navigate'})
            self.assertEqual(caught.exception.code, 'blocked_destination', 'window.open to the AgentOS port is refused')
            sess.read()
            with self.assertRaises(ToolError) as caught:
                sess.click({'target': '승인 보내기', 'effect': 'navigate'})
            self.assertEqual(caught.exception.code, 'blocked_destination', 'a form posting to it is refused')
            page = sess.read()
            self.assertEqual(page['title'], '열기', 'the page stayed on the fixture site')
        finally:
            sess.close()
        self.assertEqual(self.agentos.posts, [], 'the stand-in AgentOS received no request')
        # Only the exact test origin was allowed; the worker in production has no allowance at all.
        worker = bs.WebKitWorkerDriver('p', cwd=self.tmp.name)
        try:
            with self.assertRaises(ToolError) as caught:
                worker.goto(self.origin + '/product', 10)
            self.assertEqual(caught.exception.code, 'blocked_destination')
        finally:
            worker.close()

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
