"""SESSION-KEEP-01 (#990): a login window writes the jar only when cookies changed, and a site the
owner signed in to through AgentOS is kept signed in by loading one of its pages, where it is held."""

import base64
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from personal_agent import browser_session as bs
from personal_agent import family_share
from personal_agent.agent_runtime import ToolError
from personal_agent.browser_jar import (JAR_NAME, CookieJar, MemoryKey, effective_expiry, latest_token_expiry,
                                        token_expiry)
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


def jwt(claims):
    """A compact JWT with ``claims`` (unsigned: only ``exp`` is ever read)."""
    part = lambda value: base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b'=').decode()
    return part({'alg': 'HS256', 'typ': 'JWT'}) + '.' + part(claims) + '.sig'


class TokenExpiryTests(unittest.TestCase):
    """#1269: a session held in token cookies without a cookie expiry is scheduled by the token's own ``exp``."""

    def test_only_a_compact_token_with_a_numeric_exp_has_an_expiry(self):
        self.assertEqual(token_expiry(jwt({'exp': NOW + 7200, 'sub': 'x'})), NOW + 7200)
        for value in ('plain', 'a.b', 'a.b.c', jwt({'sub': 'x'}), jwt({'exp': 'soon'}), jwt({'exp': True}),
                      jwt({'exp': -1}), jwt(['exp']), None, '', 'x.' + 'A' * 9000 + '.y'):
            self.assertIsNone(token_expiry(value), value)

    def test_the_effective_expiry_is_the_earlier_of_cookie_and_token(self):
        self.assertEqual(effective_expiry(cookie('.shop.test', value=jwt({'exp': NOW + 60}))), NOW + 60)
        self.assertEqual(effective_expiry(cookie('.shop.test', value=jwt({'exp': NOW + 600}), expires=NOW + 60)), NOW + 60)
        self.assertEqual(effective_expiry(cookie('.shop.test', expires=NOW + 60)), NOW + 60)
        self.assertIsNone(effective_expiry(cookie('.shop.test')))
        self.assertEqual(latest_token_expiry([cookie('.a', 'a', jwt({'exp': NOW + 1})), cookie('.a', 'r', jwt({'exp': NOW + 9})),
                                              cookie('.a')]), NOW + 9)
        self.assertIsNone(latest_token_expiry([cookie('.a')]))

    def test_the_marks_carry_the_effective_expiry_and_never_the_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            jar = CookieJar(Path(tmp) / JAR_NAME, MemoryKey(), lambda: NOW)
            value = jwt({'exp': NOW + 7200})
            jar.save_export({'shop.test': [cookie('.shop.test', 'refresh', value)]})
            marks, _now = jar.site_cookie_marks('shop.test')
            self.assertEqual([(mark[1], mark[3]) for mark in marks], [(None, NOW + 7200)])
            self.assertNotIn(value, json.dumps(marks))


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

    def test_the_earlier_time_arrives_while_the_cookie_still_lives(self):
        """#1269: measured from ``now``, a cookie left the list exactly when its refresh became due."""
        expires = NOW + 2 * 3600
        for now in (expires - bs.KEEPALIVE_LEAD_SECONDS, expires - 60):
            self.assertLessEqual(bs.keepalive_due_at([expires], NOW, now), now)
        self.assertEqual(bs.keepalive_due_at([expires], NOW, expires + 1), NOW + bs.KEEPALIVE_SECONDS,
                         'an expired cookie sets no earlier time')

    def test_short_lived_cookies_never_refresh_more_often_than_the_minimum_gap(self):
        self.assertEqual(bs.keepalive_due_at([NOW + 900], NOW, NOW), NOW + bs.KEEPALIVE_MIN_GAP_SECONDS)
        self.assertEqual(bs.keepalive_due_at([NOW + 60], NOW, NOW), NOW + bs.KEEPALIVE_SECONDS,
                         'a cookie about to expire anyway sets no earlier time')


class JitterTests(unittest.TestCase):
    """#1041: about every 3 h, never at a machine-regular cadence."""

    def test_each_refresh_interval_is_within_the_jitter_and_stable_for_one_refresh(self):
        values = [bs.keepalive_interval('shop.test', NOW + k * 3600) for k in range(50)]
        low, high = bs.KEEPALIVE_SECONDS * (1 - bs.KEEPALIVE_JITTER), bs.KEEPALIVE_SECONDS * (1 + bs.KEEPALIVE_JITTER)
        self.assertTrue(all(low <= value <= high for value in values))
        self.assertGreater(len({round(value) for value in values}), 40, 'the cadence varies')
        self.assertEqual(bs.keepalive_interval('shop.test', NOW), bs.keepalive_interval('shop.test', NOW))


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

    def test_a_refresh_never_goes_to_this_computer_and_reports_a_busy_profile(self):
        self.jar.save_export({'shop.test': [cookie('.shop.test')]})
        self.assertEqual(self.profile.refresh_session_http('http://127.0.0.1:8787/')['state'], 'failed')
        self.assertEqual(self.profile.refresh_session_http('file:///etc/passwd')['state'], 'failed')
        self.assertEqual(self.drivers, [])
        self.profile._acquire('work-1')
        self.addCleanup(self.profile._release)
        self.assertEqual(self.profile.refresh_session_http('https://www.shop.test/'), {'state': 'busy'})

    def test_an_http_refresh_rewrites_only_that_site_and_pushes_it(self):
        self.jar.save_export({'shop.test': [cookie('.shop.test', 'FSID', 'old')], 'news.test': [cookie('.news.test')]})
        writes = self.jar.writes
        build, _ = HttpRefreshTests().opener(set_cookie='FSID=new; Domain=.shop.test; Path=/')
        # #1269: no token cookie tells whether the session lives: the site answered, nothing more.
        self.assertEqual(self.profile.refresh_session_http('https://www.shop.test/', opener=build), {'state': 'answered'})
        self.assertEqual(self.drivers, [], 'no browser was started')
        self.assertEqual(self.jar.writes, writes + 1)
        self.assertEqual([row['value'] for row in self.jar.site_rows('shop.test')], ['new'])
        self.assertEqual(len(self.jar.site_rows('news.test')), 1, 'another site is untouched')
        self.assertEqual(self.touched[-1], {'shop.test'})
        self.assertTrue(self.profile._lock.acquire(blocking=False))
        self.profile._lock.release()

    def test_a_refresh_is_refreshed_only_when_the_token_expiry_moved_later(self):
        """#1269 (live 2026-10-10): a page script renews the token; a plain GET left it, yet was logged refreshed."""
        old = jwt({'exp': NOW + 3600})
        self.jar.save_export({'shop.test': [cookie('.shop.test', 'refresh', old), cookie('.shop.test', 'FSID', 'a')]})
        build, _ = HttpRefreshTests().opener(set_cookie='FSID=b; Domain=.shop.test; Path=/')
        self.assertEqual(self.profile.refresh_session_http('https://www.shop.test/', opener=build), {'state': 'unchanged'})
        self.assertEqual(sorted(row['value'] for row in self.jar.site_rows('shop.test')), sorted([old, 'b']),
                         'what the site answered is still kept')
        build, _ = HttpRefreshTests().opener(set_cookie=f"refresh={jwt({'exp': NOW + 7200})}; Domain=.shop.test; Path=/")
        self.assertEqual(self.profile.refresh_session_http('https://www.shop.test/', opener=build), {'state': 'refreshed'})

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
        self.refreshes = []
        self.profile.refresh_session_http = lambda url: self.refreshes.append(url) or {'state': 'refreshed'}
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

    def test_a_site_that_refuses_is_paused_without_the_browser_until_the_next_sign_in(self):
        """#1041: a regular automated cadence drew a bot-activity alert; a refusal is never pushed past."""
        self.profile.refresh_session_http = lambda url: self.refreshes.append(url) or {'state': 'blocked'}
        self.assertFalse(hasattr(self.profile, 'refresh_session'), 'no browser refresh exists any more')
        self.assertEqual(self.service.keep_sessions_alive(now=NOW), 'shop.test')
        self.assertEqual(self.store.config(self.service.KEEPALIVE_PAUSED_KEY, {}), {'shop.test': NOW})
        self.store.put(self.service.KEEPALIVE_KEY, {'shop.test': NOW - 4 * 3600})
        self.assertIsNone(self.service.keep_sessions_alive(now=NOW + 60), 'paused')
        # The owner signs in again after the pause (times shifted so the fixed jar clock sees it as due).
        self.store.put(self.service.KEEPALIVE_PAUSED_KEY, {'shop.test': NOW - 5 * 3600})
        self.store.put(BROWSER_OWNER_SIGNINS_KEY, {'shop.test': {'at': NOW - 4 * 3600, 'marks': ['m'], 'host': 'www.shop.test'}})
        self.store.put(self.service.KEEPALIVE_KEY, {})
        self.profile.refresh_session_http = lambda url: self.refreshes.append(url) or {'state': 'refreshed'}
        self.assertEqual(self.service.keep_sessions_alive(now=NOW + 4 * 3600), 'shop.test', 'a new sign-in lifts the pause')
        self.assertEqual(len(self.refreshes), 2)

    def test_a_refresh_that_could_not_extend_the_session_pauses_the_site_until_the_next_sign_in(self):
        """#1269: repeating a request that cannot extend a session only adds automated traffic (#1041)."""
        self.profile.refresh_session_http = lambda url: self.refreshes.append(url) or {'state': 'unchanged'}
        self.assertEqual(self.service.keep_sessions_alive(now=NOW), 'shop.test')
        self.assertEqual(self.store.config(self.service.KEEPALIVE_PAUSED_KEY, {}), {'shop.test': NOW})
        self.store.put(self.service.KEEPALIVE_KEY, {'shop.test': NOW - 4 * 3600})
        self.assertIsNone(self.service.keep_sessions_alive(now=NOW + 60), 'paused')
        self.assertEqual(len(self.refreshes), 1)

    def test_a_token_expiring_before_the_interval_brings_the_refresh_ahead_of_it(self):
        """#1269: a session cookie without a cookie expiry whose token lapses in 2 h is refreshed before 3 h."""
        self.jar.save_export({'shop.test': [cookie('.shop.test', 'refresh', jwt({'exp': NOW + 300}))]})
        self.store.put(BROWSER_OWNER_SIGNINS_KEY, {'shop.test': {'at': NOW - 6900, 'marks': ['m'], 'host': 'www.shop.test'}})
        self.assertEqual(self.service.keep_sessions_alive(now=NOW), 'shop.test', 'due 10 min before the token lapses')
        self.assertEqual(self.refreshes, ['https://www.shop.test/'])

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
