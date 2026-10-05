"""SESSION-KEEP-01 (#990): a login window writes the jar only when cookies changed, and a site the
owner signed in to through AgentOS is kept signed in by loading one of its pages, where it is held."""

import tempfile
import threading
import time
import unittest
from pathlib import Path

from personal_agent import browser_session as bs
from personal_agent import family_share
from personal_agent.agent_runtime import ToolError
from personal_agent.browser_jar import JAR_NAME, CookieJar, MemoryKey
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import BROWSER_OWNER_SIGNINS_KEY, AgentService
from personal_agent.quickstart_store import QuickStore

NOW = 1_000_000.0


def cookie(domain, name='sid', value='v1', expires=None):
    return {'name': name, 'value': value, 'domain': domain, 'path': '/', 'expires': expires, 'secure': True,
            'http_only': True, 'same_site': None}


class ExportDriver:
    """A worker whose cookies are ``self.sites``; it records navigations and closes."""

    def __init__(self, sites=None):
        self.sites = sites if sites is not None else {'shop.test': [cookie('.shop.test')]}
        self.log, self.closed = [], False

    def goto(self, url, timeout):
        self.log.append(('goto', url))

    def cookies_export(self):
        return {site: [dict(row) for row in rows] for site, rows in self.sites.items()}, {}

    def close(self):
        self.closed = True


class CountingJar(CookieJar):
    def __init__(self, path):
        super().__init__(path, MemoryKey(), lambda: NOW)
        self.writes = 0

    def save_export(self, *args, **kwargs):
        self.writes += 1
        return super().save_export(*args, **kwargs)


class DueTimeTests(unittest.TestCase):
    def test_the_interval_bounds_a_site_without_expiring_cookies(self):
        self.assertEqual(bs.keepalive_due_at([None], NOW, NOW), NOW + bs.KEEPALIVE_SECONDS)
        self.assertEqual(bs.keepalive_due_at([], 0, NOW), max(bs.KEEPALIVE_SECONDS, bs.KEEPALIVE_MIN_GAP_SECONDS))

    def test_a_cookie_expiring_sooner_brings_the_refresh_ahead_of_it(self):
        expires = NOW + 2 * 3600
        self.assertEqual(bs.keepalive_due_at([expires, None], NOW - 3600, NOW), expires - bs.KEEPALIVE_LEAD_SECONDS)

    def test_short_lived_cookies_never_refresh_more_often_than_the_minimum_gap(self):
        self.assertEqual(bs.keepalive_due_at([NOW + 900], NOW, NOW), NOW + bs.KEEPALIVE_MIN_GAP_SECONDS)
        self.assertEqual(bs.keepalive_due_at([NOW + 60], NOW, NOW), NOW + bs.KEEPALIVE_SECONDS,
                         'a cookie about to expire anyway sets no earlier time')


class LearnedIntervalTests(unittest.TestCase):
    """#1011: a site's interval comes from its observed logouts only."""

    def test_half_the_shortest_lifetime_clamped(self):
        self.assertEqual(bs.keepalive_interval(None), bs.KEEPALIVE_SECONDS)
        self.assertEqual(bs.keepalive_interval(43 * 60), 43 * 60 / 2)
        self.assertEqual(bs.keepalive_interval(5 * 60), bs.KEEPALIVE_FLOOR_SECONDS)
        self.assertEqual(bs.keepalive_interval(30 * 3600), bs.KEEPALIVE_SECONDS)

    def test_the_due_time_follows_the_learned_interval_below_the_default_gap(self):
        interval = bs.keepalive_interval(43 * 60)
        self.assertEqual(bs.keepalive_due_at([None], NOW, NOW, interval), NOW + interval)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.jar = CountingJar(Path(self.tmp.name) / JAR_NAME)
        self.drivers = []

        def launcher(profile_dir, headless):
            driver = ExportDriver()
            self.drivers.append(driver)
            return driver
        self.profile = bs.BrowserProfile(Path(self.tmp.name), launcher=launcher, jar=self.jar)
        self.touched = []
        self.profile.on_saved = self.touched.append

    def test_an_unchanged_export_is_not_written_again_and_a_change_is(self):
        self.profile._acquire('login')
        self.addCleanup(self.profile._release)
        driver = ExportDriver()
        for _ in range(3):
            self.assertTrue(self.profile._save(driver))
        self.assertEqual((self.jar.writes, len(self.touched)), (1, 1), 'one write and one push for three equal saves')
        driver.sites = {'shop.test': [cookie('.shop.test', value='v2')]}
        self.assertTrue(self.profile._save(driver))
        self.assertEqual((self.jar.writes, len(self.touched)), (2, 2))

    def test_a_new_holder_or_a_jar_change_always_writes(self):
        driver = ExportDriver()
        self.profile._acquire('a')
        self.profile._save(driver)
        self.profile._release()
        self.profile._acquire('b')
        self.profile._save(driver)
        self.assertEqual(self.jar.writes, 2, 'a new holder writes its first save')
        self.profile.import_site('shop.test', [cookie('.shop.test', value='pushed')])
        self.profile._save(driver)
        self.profile._release()
        self.assertEqual(self.jar.writes, 4, 'after an import the jar differs from the last write')

    def test_a_refresh_loads_the_page_once_saves_and_releases(self):
        self.assertEqual(self.profile.refresh_session('https://www.shop.test/'), {'state': 'refreshed'})
        [driver] = self.drivers
        self.assertEqual(driver.log, [('goto', 'https://www.shop.test/')])
        self.assertTrue(driver.closed)
        self.assertEqual(self.jar.writes, 1)
        self.assertTrue(self.profile._lock.acquire(blocking=False), 'the profile was released')
        self.profile._lock.release()

    def test_a_refresh_never_goes_to_this_computer_and_reports_a_busy_profile(self):
        self.assertEqual(self.profile.refresh_session('http://127.0.0.1:8787/')['state'], 'failed')
        self.assertEqual(self.profile.refresh_session('file:///etc/passwd')['state'], 'failed')
        self.assertEqual(self.drivers, [])
        self.profile._acquire('work-1')
        self.addCleanup(self.profile._release)
        self.assertEqual(self.profile.refresh_session('https://www.shop.test/'), {'state': 'busy'})

    def test_an_http_refresh_rewrites_only_that_site_and_pushes_it(self):
        self.jar.save_export({'shop.test': [cookie('.shop.test', 'FSID', 'old')], 'news.test': [cookie('.news.test')]})
        writes = self.jar.writes
        build, _ = HttpRefreshTests().opener(set_cookie='FSID=new; Domain=.shop.test; Path=/')
        self.assertEqual(self.profile.refresh_session_http('https://www.shop.test/', opener=build), {'state': 'refreshed'})
        self.assertEqual(self.drivers, [], 'no browser was started')
        self.assertEqual(self.jar.writes, writes + 1)
        self.assertEqual([row['value'] for row in self.jar.site_rows('shop.test')], ['new'])
        self.assertEqual(len(self.jar.site_rows('news.test')), 1, 'another site is untouched')
        self.assertEqual(self.touched[-1], {'shop.test'})
        self.assertTrue(self.profile._lock.acquire(blocking=False))
        self.profile._lock.release()

    def test_a_work_waits_for_a_running_keepalive_instead_of_failing(self):
        self.profile._acquire(bs.KEEPALIVE_HOLDER)
        threading.Timer(0.2, self.profile._release).start()
        started = time.monotonic()
        self.profile._acquire('work-1')
        self.addCleanup(self.profile._release)
        self.assertLess(time.monotonic() - started, 5)
        with self.assertRaises(ToolError):
            self.profile._acquire('work-2')  # any other holder is still refused at once


class HttpRefreshTests(unittest.TestCase):
    """#1015: the request itself (an injected opener; nothing leaves this machine)."""

    def opener(self, set_cookie=None, status=200, error=None):
        seen = {}

        def build(*handlers):
            processor = next(h for h in handlers if hasattr(h, 'cookiejar'))

            class Client:
                def open(self, request, timeout=None):
                    processor.cookiejar.add_cookie_header(request)
                    seen['cookie'] = request.get_header('Cookie')
                    seen['agent'] = request.get_header('User-agent')
                    if error is not None:
                        raise error
                    if set_cookie:
                        import email.message, io, urllib.response
                        headers = email.message.Message()
                        headers['Set-Cookie'] = set_cookie
                        response = urllib.response.addinfourl(io.BytesIO(b'ok'), headers, request.full_url, status)
                        processor.cookiejar.extract_cookies(response, request)
                    import io, urllib.response, email.message
                    return urllib.response.addinfourl(io.BytesIO(b'ok'), email.message.Message(), request.full_url, status)
            return Client()
        return build, seen

    def rows(self):
        return [cookie('.shop.test', 'FSID', 'old'), cookie('pay.shop.test', 'JSESSIONID', 'pay-only')]

    def test_only_the_hosts_cookies_go_out_and_a_rotated_value_comes_back(self):
        build, seen = self.opener(set_cookie='FSID=new; Domain=.shop.test; Path=/; HttpOnly')
        state, after = bs.http_refresh('https://www.shop.test/', self.rows(), opener=build, refusal=lambda url, allowed: None)
        self.assertEqual(state, 'refreshed')
        self.assertEqual(seen['cookie'], 'FSID=old', 'a cookie of another host is not sent')
        self.assertEqual(seen['agent'], bs.KEEPALIVE_HTTP_AGENT)
        values = {(row['name'], row['domain']): row['value'] for row in after}
        self.assertEqual(values[('FSID', '.shop.test')], 'new')
        self.assertEqual(values[('JSESSIONID', 'pay.shop.test')], 'pay-only', 'untouched rows are kept')

    def test_a_refused_request_or_destination_is_not_a_refresh(self):
        import urllib.error
        build, _ = self.opener(error=urllib.error.HTTPError('https://www.shop.test/', 403, 'no', {}, None))
        self.assertEqual(bs.http_refresh('https://www.shop.test/', self.rows(), opener=build,
                                         refusal=lambda url, allowed: None), ('blocked', None))
        self.assertEqual(bs.http_refresh('http://127.0.0.1/', self.rows(), opener=build), ('failed', None))
        self.assertEqual(bs.http_refresh('https://www.shop.test/', self.rows(), opener=build,
                                         refusal=lambda url, allowed: 'blocked_destination'), ('failed', None))


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.store = QuickStore(root)
        self.jar = CountingJar(root / JAR_NAME)
        self.jar.save_export({'shop.test': [cookie('.shop.test', expires=NOW + 30 * 86400)],
                              'other.test': [cookie('.other.test')]})
        self.profile = bs.BrowserProfile(root / 'profile', launcher=lambda d, h: ExportDriver(), jar=self.jar)
        self.refreshes, self.browser_loads = [], []
        self.profile.refresh_session_http = lambda url: self.refreshes.append(url) or {'state': 'refreshed'}
        self.profile.refresh_session = lambda url: self.browser_loads.append(url) or {'state': 'refreshed'}
        self.service = AgentService(self.store, ModelAdapter(lambda *a, **k: {}), lambda *a, **k: {'ok': True, 'result': []},
                                    browser_profile=self.profile)
        self.store.put(BROWSER_OWNER_SIGNINS_KEY, {'shop.test': {'at': NOW - 4 * 3600, 'marks': ['m'], 'host': 'www.shop.test'}})

    def test_a_due_site_the_owner_signed_in_to_is_refreshed_once_where_it_signed_in(self):
        self.assertEqual(self.service.keep_sessions_alive(now=NOW), 'shop.test')
        self.assertEqual(self.refreshes, ['https://www.shop.test/'])
        self.assertEqual(self.store.config(self.service.KEEPALIVE_KEY, {}), {'shop.test': NOW})
        self.assertIsNone(self.service.keep_sessions_alive(now=NOW + 60), 'not due again right away')
        self.assertEqual(len(self.refreshes), 1)

    def test_a_site_signed_in_recently_or_without_a_stored_session_waits(self):
        self.store.put(BROWSER_OWNER_SIGNINS_KEY, {'shop.test': {'at': NOW - 60, 'marks': ['m']},
                                                   'gone.test': {'at': 0, 'marks': ['m']}})
        self.assertIsNone(self.service.keep_sessions_alive(now=NOW))
        self.assertEqual(self.refreshes, [])

    def test_a_received_site_is_refreshed_where_it_is_held_not_here(self):
        self.store.put(family_share.SHARED_KEY, {'shop.test': {'from': 'owner', 'since': 1.0}})
        self.assertIsNone(self.service.keep_sessions_alive(now=NOW))
        self.assertEqual(self.refreshes, [])

    def test_a_busy_browser_records_nothing_and_is_tried_again(self):
        self.profile.refresh_session_http = lambda url: {'state': 'busy'}
        self.assertIsNone(self.service.keep_sessions_alive(now=NOW))
        self.assertEqual(self.store.config(self.service.KEEPALIVE_KEY, {}), {})

    def test_an_observed_logout_shortens_only_that_sites_interval(self):
        self.store.put(self.service.KEEPALIVE_KEY, {'shop.test': NOW - 43 * 60})
        self.assertEqual(self.service.note_signed_out('www.shop.test', now=NOW), 43 * 60)
        self.assertEqual(self.service.note_signed_out('www.shop.test', now=NOW + 3600 * 5), 43 * 60, 'the shortest stays')
        self.assertIsNone(self.service.note_signed_out('other.test', now=NOW), 'not a site the owner signed in to here')
        self.assertEqual(self.store.config(self.service.SESSION_LIFETIMES_KEY, {}), {'shop.test': 43 * 60})
        # 25 min after that refresh the default 3 h cadence would wait; the learned 21.5 min one is due.
        self.assertEqual(self.service.keep_sessions_alive(now=NOW - 43 * 60 + 25 * 60), 'shop.test')

    def test_a_requested_sign_in_records_the_observation(self):
        job = {'id': self.store.enqueue('담아줘', 'k-sign')}
        self.store.put(self.service.KEEPALIVE_KEY, {'shop.test': time.time() - 1800})
        self.service.browser_profile.available = lambda: True
        self.service._request_browser_login(self.store.job(job['id']), 'https://www.shop.test/login', explicit=True)
        lifetime = self.store.config(self.service.SESSION_LIFETIMES_KEY, {}).get('shop.test')
        self.assertTrue(1700 < lifetime < 1900, lifetime)

    def test_a_refresh_is_one_http_request_first_and_needs_no_browser(self):
        """#1015: a page in the browser is ~900 MB on this site class; the request carries the cookies alone."""
        self.assertEqual(self.service.keep_sessions_alive(now=NOW), 'shop.test')
        self.assertEqual((self.refreshes, self.browser_loads), (['https://www.shop.test/'], []))
        self.assertEqual(self.store.config(self.service.KEEPALIVE_VIA_KEY, {}), {'shop.test': 'http'})

    def test_a_site_that_refuses_the_request_is_refreshed_by_the_browser_from_then_on(self):
        self.profile.refresh_session_http = lambda url: self.refreshes.append(url) or {'state': 'blocked'}
        self.assertEqual(self.service.keep_sessions_alive(now=NOW), 'shop.test')
        self.assertEqual(self.browser_loads, ['https://www.shop.test/'])
        self.assertEqual(self.store.config(self.service.KEEPALIVE_BROWSER_ONLY_KEY, []), ['shop.test'])
        self.store.put(self.service.KEEPALIVE_KEY, {'shop.test': NOW - 4 * 3600})
        self.service.keep_sessions_alive(now=NOW)
        self.assertEqual(len(self.refreshes), 1, 'no second HTTP try on a browser-only site')
        self.assertEqual(len(self.browser_loads), 2)

    def test_a_logout_after_an_http_refresh_moves_the_site_to_the_browser(self):
        self.service.keep_sessions_alive(now=NOW)
        self.store.put(self.service.KEEPALIVE_KEY, {'shop.test': NOW - 1800})
        self.service.note_signed_out('www.shop.test', now=NOW)
        self.assertEqual(self.store.config(self.service.KEEPALIVE_BROWSER_ONLY_KEY, []), ['shop.test'])

    def test_the_work_loop_starts_a_check_only_while_idle_and_at_most_once_a_minute(self):
        self.service.SESSION_KEEPALIVE = True
        self.store.enqueue('질문', 'k-1')
        self.assertFalse(self.service.start_session_keepalive(now=NOW), 'a queued Work comes first')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='succeeded'")
        self.assertTrue(self.service.start_session_keepalive(now=NOW + 61))
        self.service._keepalive_thread.join(5)
        self.assertFalse(self.service.start_session_keepalive(now=NOW + 62), 'one check a minute')
        self.assertEqual(len(self.refreshes), 1)
        self.service.SESSION_KEEPALIVE = False
        self.assertFalse(self.service.start_session_keepalive(now=NOW + 999))


if __name__ == '__main__':
    unittest.main()
