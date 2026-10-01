"""FAMILY-SHARE-01 (#934): the owner shares one signed-in site with a family assistant.

Evidence class: unit tests with an in-memory jar key, a fake loopback
opener, a fake page driver and a model-free local HTTP server.  No real
Keychain, WebKit, launchd or family instance is touched.
"""
import io
import json
import stat
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from personal_agent import browser_session as bs
from personal_agent import family_share
from personal_agent.agent_runtime import DEFINITIONS, ToolError
from personal_agent.browser_jar import JAR_NAME, CookieJar, MemoryKey
from personal_agent.family_setup import _LOOPBACK
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart import make_handler
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.settings_orchestrator import SettingsError

from test_browser_session import ORIGIN, PAGES, Approvals, FakeDriver

SECRET_VALUE = 'cookie-secret-value-9f8e7d'
OTHER_VALUE = 'news-cookie-value-1a2b3c'


def cookie(domain, name='sid', value=SECRET_VALUE, expires=None):
    return {'name': name, 'value': value, 'domain': domain, 'path': '/', 'expires': expires, 'secure': True,
            'http_only': True, 'same_site': None}


def jar_at(folder):
    return CookieJar(Path(folder) / 'private' / 'browser-profile' / JAR_NAME, MemoryKey(), lambda: 1000.0)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Opener:
    """A fake loopback: records every request (url, header, body) and answers ok, or fails when ``down``."""

    def __init__(self):
        self.requests, self.down = [], False

    def __call__(self, request, timeout=None):
        if self.down:
            raise URLError('connection refused')
        body = json.loads(request.data or b'{}')
        headers = {key.lower(): value for key, value in request.header_items()}
        self.requests.append((request.full_url, headers.get(family_share.LINK_HEADER.lower()), body))
        return FakeResponse(json.dumps({'ok': True, 'site': body.get('site'), 'cookies': len(body.get('cookies') or [])}).encode())

    def bodies(self):
        return [body for _url, _header, body in self.requests]


class SharedDriver(FakeDriver):
    """A fake worker that also holds cookies: exports them, imports and deletes on request."""

    def __init__(self, export=None, **kwargs):
        super().__init__(**kwargs)
        self.export = export or ({}, [])
        self.imported, self.deleted, self.starts = [], [], 0

    def alive(self):
        return not self.closed

    def cookies_export(self):
        return self.export

    def cookies_import(self, rows):
        self.imported.extend(rows)
        return len(rows)

    def cookies_delete(self, site):
        self.deleted.append(site)
        return 1

    def close(self):
        self.closed = True


class Names(unittest.TestCase):
    def test_a_site_is_its_registrable_domain_whatever_the_owner_pasted(self):
        for value in ('shop.example.co.kr', 'https://www.shop.example.co.kr/cart?x=1', 'm.shop.example.co.kr/',
                      '  WWW.SHOP.EXAMPLE.CO.KR. '):
            self.assertEqual(family_share.normalize_site(value), 'example.co.kr', value)
        self.assertEqual(family_share.normalize_site('accounts.example.com.lookalike.io'), 'lookalike.io')
        for bad in ('', ' ', 'localhost', 'a|b', 'two words.com'):
            with self.assertRaises(ValueError):
                family_share.normalize_site(bad)

    def test_an_assistant_is_found_by_instance_or_display_name(self):
        names = {'family-1': '아내 비서', 'family-2': 'family-2'}
        self.assertEqual(family_share.resolve_instance('아내  비서', names), 'family-1')
        self.assertEqual(family_share.resolve_instance('FAMILY-1', names), 'family-1')
        self.assertEqual(family_share.resolve_instance('family-2', names), 'family-2')
        with self.assertRaises(ValueError) as caught:
            family_share.resolve_instance('남편 비서', names)
        self.assertIn('아내 비서(family-1)', str(caught.exception))

    def test_an_id_wins_over_a_display_name_and_a_shared_name_is_refused(self):
        # #966 review P2-1: display names are chosen by whoever made each bot; they must name exactly one instance.
        rows = {'family-1': {'name': 'family-2', 'state': 'paired'}, 'family-2': {'name': '아들 비서', 'state': 'paired'}}
        self.assertEqual(family_share.resolve_instance('family-2', rows), 'family-2', 'the id, not the bot named like it')
        self.assertEqual(family_share.resolve_instance('아들 비서', rows), 'family-2')
        twins = {'family-1': {'name': '비서', 'state': 'paired'}, 'family-2': {'name': '비서', 'state': 'setting_up'}, 'main': {'name': '김비서'}}
        with self.assertRaises(ValueError) as caught:
            family_share.resolve_instance('비서', twins)
        self.assertIn('여럿이에요: 비서(family-1, 연결됨), 비서(family-2, 설정 중)', str(caught.exception))
        self.assertIn('id로', str(caught.exception))
        self.assertEqual(family_share.resolve_instance('family-2', twins), 'family-2')
        self.assertEqual(family_share.resolve_instance('김비서', twins), 'main')

    def test_the_link_secret_is_owner_only_and_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = family_share.ensure_link_secret(tmp)
            path = family_share.link_secret_path(tmp)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
            self.assertEqual(family_share.ensure_link_secret(tmp), first, 'an existing secret is kept')
            self.assertTrue(family_share.link_ok(tmp, first))
            for wrong in ('', None, first[:-1], first + 'x', 'ÿ' + first):
                self.assertFalse(family_share.link_ok(tmp, wrong))
        self.assertFalse(family_share.link_ok(tmp, first), 'no file, no match')

    def test_the_tool_offers_share_and_unshare(self):
        change = next(d for d in DEFINITIONS if (d.get('function') or d).get('name') == 'settings_change')
        change = change.get('function') or change
        self.assertIn('share_site', change['parameters']['properties']['setting']['enum'])
        self.assertIn('unshare_site', change['parameters']['properties']['setting']['enum'])
        self.assertIn('share_site', change['description'])


class OwnerSide(unittest.TestCase):
    """The owner's instance: grants, one-way pushes that follow the jar, revocation and retry."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = QuickStore(Path(self.tmp.name) / 'owner')
        self.family_dir = Path(self.tmp.name) / 'family-1'
        self.jar = jar_at(Path(self.tmp.name) / 'owner')
        self.jar.save_export({'shop.test': [cookie('.shop.test'), cookie('www.shop.test', 'pref', 'p')],
                              'news.test': [cookie('news.test', value=OTHER_VALUE)]})
        self.opener = Opener()
        self.located = []

    def locate(self, instance):
        self.located.append(instance)
        if instance != 'family-1':
            raise ValueError('unknown')
        return 8797, self.family_dir

    def share(self, site='shop.test', now=2000.0):
        return family_share.share(self.store, self.jar, 'family-1', site, locate=self.locate, opener=self.opener, now=now)

    def sync(self, touched, now=3000.0, **kwargs):
        return family_share.sync(self.store, self.jar, touched, locate=self.locate, opener=self.opener, now=now, **kwargs)

    def test_sharing_pushes_only_that_sites_rows_with_the_link_secret(self):
        with self.assertLogs('personal_agent.family_share', level='INFO') as logs:
            receipt = self.share('https://www.shop.test/cart')
        self.assertEqual((receipt['site'], receipt['cookies'], receipt['delivered']), ('shop.test', 2, True))
        url, header, body = self.opener.requests[-1]
        self.assertEqual(url, f'http://127.0.0.1:8797{family_share.SHARE_PATH}')
        self.assertEqual(header, family_share.read_link_secret(self.family_dir), 'the secret written into the family folder')
        self.assertEqual((body['op'], body['site']), ('put', 'shop.test'))
        self.assertEqual(sorted(row['domain'] for row in body['cookies']), ['.shop.test', 'www.shop.test'])
        self.assertNotIn(OTHER_VALUE, json.dumps(body), 'the other site stays home')
        grant = family_share.grants(self.store)[0]
        self.assertEqual((grant['instance'], grant['site'], grant['since'], grant['synced'], grant['error']),
                         ('family-1', 'shop.test', 2000.0, 2000.0, None))
        self.assertNotIn(SECRET_VALUE, '\n'.join(logs.output))
        self.assertIn('shop.test -> family-1 (2 cookies)', '\n'.join(logs.output))
        listed = family_share.listing(self.store, {'family-1': '아내 비서'})
        self.assertEqual(listed, [{'instance': 'family-1', 'label': '아내 비서', 'site': 'shop.test', 'since': 2000.0,
                                   'delivered': True, 'state': 'shared'}])

    def test_a_site_the_owner_is_not_signed_in_to_is_not_shared(self):
        with self.assertRaises(ValueError) as caught:
            self.share('other.test')
        self.assertIn('other.test', str(caught.exception))
        self.assertIn('shop.test', str(caught.exception), 'the stored sites help the owner pick')
        self.assertEqual((self.opener.requests, family_share.grants(self.store)), ([], []))
        self.assertFalse(family_share.link_secret_path(self.family_dir).exists())

    def test_an_uninstalled_assistant_is_refused(self):
        with self.assertRaises(ValueError):
            family_share.share(self.store, self.jar, 'family-9', 'shop.test', locate=lambda name: (None, self.family_dir),
                               opener=self.opener)
        self.assertEqual(family_share.grants(self.store), [])

    def test_a_save_of_another_site_pushes_nothing_and_a_save_of_the_shared_site_pushes_it(self):
        self.share()
        self.opener.requests.clear()
        self.assertEqual(self.sync({'news.test'}), 0)
        self.assertEqual(self.opener.requests, [])
        self.jar.save_export({'shop.test': [cookie('.shop.test', value='rotated-value-77')]}, imported={'shop.test'})
        self.assertEqual(self.sync({'shop.test'}), 1)
        body = self.opener.bodies()[-1]
        self.assertEqual([row['value'] for row in body['cookies']], ['rotated-value-77'], 'the refreshed session follows')
        self.assertEqual(family_share.grants(self.store)[0]['synced'], 3000.0)

    def test_signing_out_on_the_owner_side_empties_the_family_copy_but_keeps_the_grant(self):
        self.share()
        self.jar.remove('shop.test')
        self.assertEqual(self.sync({'shop.test'}), 1)
        body = self.opener.bodies()[-1]
        self.assertEqual((body['op'], body['cookies']), ('put', []))
        self.assertEqual(len(family_share.grants(self.store)), 1)

    def test_the_profile_hook_reaches_the_push_after_a_worker_save(self):
        self.share()
        self.opener.requests.clear()
        exports = [({'shop.test': [cookie('.shop.test', value='from-worker-1')]}, ['shop.test'])]

        def launcher(profile_dir, headless):
            profile._seed()   # as the WebKit launcher: the worker starts from the jar's rows
            return SharedDriver(export=exports[-1])
        profile = bs.BrowserProfile(Path(self.tmp.name) / 'owner' / 'private' / 'browser-profile', jar=self.jar, launcher=launcher)
        profile.on_saved = lambda touched: self.sync(touched)
        driver = profile.driver_factory('work-1')()
        driver.close()
        self.assertEqual([row['value'] for row in self.opener.bodies()[-1]['cookies']], ['from-worker-1'])
        self.opener.requests.clear()
        exports.append(({'news.test': [cookie('news.test', value='n2')]}, ['news.test']))
        profile.driver_factory('work-2')().close()
        # The worker was seeded with both sites and exported only news: shop was dropped, so it is touched.
        self.assertEqual(self.opener.bodies()[-1], {'op': 'put', 'site': 'shop.test', 'cookies': []})
        self.opener.requests.clear()
        profile.delete_site('news.test')
        self.assertEqual(self.opener.requests, [], 'a deleted unshared site pushes nothing')

    def test_a_family_instance_that_is_down_keeps_the_grant_and_is_retried(self):
        self.opener.down = True
        with self.assertLogs('personal_agent.family_share', level='WARNING') as logs:
            receipt = self.share()
        self.assertFalse(receipt['delivered'])
        self.assertIn('비서가 켜지면', receipt['response'])
        grant = family_share.grants(self.store)[0]
        self.assertEqual((grant['synced'], grant['error'], grant['attempted']), (None, 'URLError', 2000.0))
        self.assertFalse(family_share.listing(self.store)[0]['delivered'])
        self.assertTrue(family_share.pending(self.store))
        self.assertNotIn(SECRET_VALUE, '\n'.join(logs.output))
        # Still down, inside the retry window: not attempted again.
        self.assertEqual(self.sync(set(), now=2010.0, retry_after=30), 0)
        self.opener.down = False
        self.assertEqual(self.sync(set(), now=2010.0, retry_after=30), 0, 'the window is honoured even when up')
        self.assertEqual(self.sync(set(), now=2040.0, retry_after=30), 1)
        self.assertEqual(self.opener.bodies()[-1]['site'], 'shop.test')
        self.assertFalse(family_share.pending(self.store))
        self.assertEqual(self.sync(None, now=2100.0), 1, 'owner start re-pushes every grant')

    def test_stopping_removes_the_family_copy_and_the_grant_and_is_idempotent(self):
        self.share()
        self.opener.requests.clear()
        receipt = family_share.unshare(self.store, None, 'www.shop.test', locate=self.locate, opener=self.opener)
        self.assertEqual((receipt['instances'], receipt['removed']), (['family-1'], True))
        self.assertEqual(self.opener.bodies(), [{'op': 'remove', 'site': 'shop.test'}])
        self.assertEqual(family_share.grants(self.store), [])
        self.assertEqual(self.jar.site_rows('shop.test')[0]['value'], SECRET_VALUE, "the owner's session is untouched")
        again = family_share.unshare(self.store, 'family-1', 'shop.test', locate=self.locate, opener=self.opener)
        self.assertTrue(again['idempotent'])
        self.assertEqual(len(self.opener.bodies()), 1, 'nothing to send twice')

    def test_a_stop_while_the_family_instance_is_down_blocks_pushes_until_it_is_confirmed(self):
        self.share()
        self.opener.down = True
        receipt = family_share.unshare(self.store, 'family-1', 'shop.test', locate=self.locate, opener=self.opener, now=2500.0)
        self.assertEqual((receipt['pending'], receipt['removed']), (['family-1'], False))
        self.assertEqual(family_share.grants(self.store)[0]['state'], 'revoking')
        self.opener.down = False
        self.opener.requests.clear()
        self.jar.save_export({'shop.test': [cookie('.shop.test', value='newer')]}, imported={'shop.test'})
        self.assertEqual(self.sync({'shop.test'}), 1)
        self.assertEqual(self.opener.bodies(), [{'op': 'remove', 'site': 'shop.test'}], 'a revoking grant never pushes rows')
        self.assertEqual(family_share.grants(self.store), [])

    def test_a_failed_repush_is_due_again_until_it_lands_including_an_emptying_one(self):
        # Review P2-3: a delivered grant whose later push fails (here: the owner signed out).
        self.share()
        self.opener.down = True
        self.jar.remove('shop.test')
        self.assertEqual(self.sync({'shop.test'}, now=2100.0), 0)
        grant = family_share.grants(self.store)[0]
        self.assertEqual((grant['synced'], grant['error']), (None, 'URLError'))
        self.assertTrue(family_share.pending(self.store))
        self.opener.down = False
        self.opener.requests.clear()
        self.assertEqual(self.sync(set(), now=2120.0, retry_after=30), 0, 'inside the retry window')
        self.assertEqual(self.sync(set(), now=2140.0, retry_after=30), 1, 'the work-loop retry delivers it')
        self.assertEqual(self.opener.bodies(), [{'op': 'put', 'site': 'shop.test', 'cookies': []}], 'the family copy is emptied')
        self.assertFalse(family_share.pending(self.store))

    def test_a_received_site_cannot_be_shared_onward(self):
        # Review P1-1: a family instance holding the owner's session (a mark and the rows) may not pass it on.
        self.store.put(family_share.SHARED_KEY, {'shop.test': {'from': 'owner', 'since': 1.0}})
        with self.assertRaises(ValueError) as caught:
            family_share.share(self.store, self.jar, 'family-1', 'www.shop.test', locate=self.locate, opener=self.opener)
        self.assertEqual(str(caught.exception), family_share.NOT_YOURS_TEXT.format(site='shop.test'))
        self.assertEqual((self.opener.requests, family_share.grants(self.store)), ([], []))
        self.assertEqual(self.share('news.test')['site'], 'news.test', "the family member's own sessions are theirs to share")

    def test_a_stop_against_an_uninstalled_instance_settles_as_revoked(self):
        # Review P3-2: the plist is gone, so there is nothing left to revoke; the grant is dropped and logged.
        self.share()
        self.opener.requests.clear()
        with self.assertLogs('personal_agent.family_share', level='INFO') as logs:
            receipt = family_share.unshare(self.store, 'family-1', 'shop.test', locate=lambda name: (None, self.family_dir),
                                           opener=self.opener)
        self.assertEqual((receipt['instances'], receipt['removed'], family_share.grants(self.store)), (['family-1'], True, []))
        self.assertEqual(self.opener.requests, [])
        self.assertIn('nothing left to revoke', '\n'.join(logs.output))

    def test_a_push_that_another_writer_revoked_meanwhile_is_undone(self):
        # Review P2-2: between the push and its write-back the grant turned revoking (another process); the
        # push is followed by a remove and the row is dropped.
        self.share()
        self.opener.requests.clear()
        inner = self.opener.__call__

        def racing(request, timeout=None):
            body = json.loads(request.data)
            if body['op'] == 'put':
                rows = family_share.grants(self.store)
                rows[0]['state'] = 'revoking'
                self.store.put(family_share.GRANTS_KEY, rows)
            return inner(request, timeout)
        self.opener.__call__ = racing
        self.assertEqual(family_share.sync(self.store, self.jar, {'shop.test'}, locate=self.locate, opener=racing, now=3000.0), 1)
        self.assertEqual([body['op'] for body in self.opener.bodies()], ['put', 'remove'])
        self.assertEqual(family_share.grants(self.store), [])

    def test_a_received_site_is_never_pushed_back(self):
        # A family instance's own store: a mark from the owner and (contrived) a grant for the same site.
        self.store.put(family_share.SHARED_KEY, {'shop.test': {'from': 'owner', 'since': 1.0}})
        self.store.put(family_share.GRANTS_KEY, [{'instance': 'family-1', 'site': 'shop.test', 'since': 1.0, 'synced': None}])
        self.assertEqual(self.sync(None), 0)
        self.assertEqual(self.opener.requests, [])


class FamilySide(unittest.TestCase):
    """The family instance: the loopback endpoint, its jar and worker, the mark and the payment refusal."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name) / 'family'
        self.store = QuickStore(root)
        self.jar = jar_at(root)
        self.drivers = []

        def launcher(profile_dir, headless):
            driver = SharedDriver()
            self.drivers.append(driver)
            return driver
        self.profile = bs.BrowserProfile(root / 'private' / 'browser-profile', launcher=launcher, jar=self.jar)
        self.service = AgentService(self.store, ModelAdapter(lambda *a, **k: {}), lambda *a, **k: {'ok': True, 'result': []},
                                    browser_profile=self.profile)
        self.secret = family_share.ensure_link_secret(root)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.service))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def request(self, body, secret=None, tunneled=False, raw=None):
        headers = {'Content-Type': 'application/json'}
        if secret is not None:
            headers[family_share.LINK_HEADER] = secret
        if tunneled:
            headers.update({'X-Forwarded-For': '203.0.113.9', 'X-Forwarded-Proto': 'https'})
        data = raw if raw is not None else json.dumps(body).encode()
        try:
            with urlopen(Request(self.base + family_share.SHARE_PATH, data=data, method='POST', headers=headers), timeout=10) as response:
                return response.status, json.loads(response.read() or b'{}')
        except HTTPError as error:
            return error.code, json.loads(error.read() or b'{}')

    def put(self, rows=None, site='shop.test', secret=True, **kwargs):
        rows = [cookie('.shop.test'), cookie('www.shop.test', 'pref', 'p')] if rows is None else rows
        secret = self.secret if secret is True else secret
        return self.request({'op': 'put', 'site': site, 'cookies': rows}, secret=secret, **kwargs)

    def test_a_push_lands_in_the_jar_the_running_worker_and_the_mark(self):
        driver = self.profile.driver_factory('work-1')()   # a Work holds the profile now
        with self.assertLogs('personal_agent', level='INFO') as logs:
            status, body = self.put()
        self.assertEqual((status, body['site'], body['cookies'], body['running_browser']), (200, 'shop.test', 2, 'imported'))
        self.assertEqual([row['value'] for row in self.jar.site_rows('shop.test')], [SECRET_VALUE, 'p'])
        self.assertEqual(([row['name'] for row in self.drivers[0].imported], self.drivers[0].deleted), (['sid', 'pref'], ['shop.test']))
        self.assertEqual(set(family_share.received(self.store)), {'shop.test'})
        self.assertNotIn(SECRET_VALUE, '\n'.join(logs.output))
        self.assertNotIn(self.secret, '\n'.join(logs.output))
        driver.close()
        self.assertEqual(self.jar.site_rows('shop.test'), [], 'the fake worker exported nothing, so the imported site was dropped')

    def test_only_rows_of_that_site_are_kept(self):
        status, body = self.put([cookie('.shop.test'), cookie('news.test', value=OTHER_VALUE), cookie('shop.test.evil.example')])
        self.assertEqual((status, body['cookies']), (200, 1))
        self.assertEqual([row['domain'] for row in self.jar.site_rows('shop.test')], ['.shop.test'])
        self.assertEqual(self.jar.site_rows('news.test'), [])
        self.assertEqual(self.request({'op': 'put', 'site': 'www.shop.test', 'cookies': []}, secret=self.secret)[0], 400,
                         'a site must already be its registrable domain')

    def test_removal_clears_the_jar_the_worker_and_the_mark_and_is_idempotent(self):
        self.put()
        driver = self.profile.driver_factory('work-1')()
        status, body = self.request({'op': 'remove', 'site': 'shop.test'}, secret=self.secret)
        self.assertEqual((status, body['deleted']), (200, True))
        self.assertEqual(self.jar.site_rows('shop.test'), [])
        self.assertIn('shop.test', self.drivers[0].deleted, 'the running worker dropped it too')
        self.assertEqual(family_share.received(self.store), {})
        status, body = self.request({'op': 'remove', 'site': 'shop.test'}, secret=self.secret)
        self.assertEqual((status, body['ok'], body['received']), (200, True, False), 'a second removal is reported, not failed')
        self.assertEqual(self.drivers[0].deleted.count('shop.test'), 1, 'nothing received: the worker is not touched again')
        driver.close()

    def test_a_removal_leaves_the_family_members_own_session_alone(self):
        # Review P3-1: no mark for the site means it is the member's own sign-in, never the owner's copy.
        self.jar.save_export({'shop.test': [cookie('.shop.test', value='the-members-own-session')]})
        driver = self.profile.driver_factory('work-1')()
        status, body = self.request({'op': 'remove', 'site': 'shop.test'}, secret=self.secret)
        self.assertEqual((status, body['deleted'], body['received']), (200, False, False))
        self.assertEqual([row['value'] for row in self.jar.site_rows('shop.test')], ['the-members-own-session'])
        self.assertEqual(self.drivers[0].deleted, [])
        driver.close()

    def test_a_save_during_a_stop_cannot_leave_the_family_holding_the_session(self):
        # Review P2-2: the owner's push from a jar save fires while the remove is in flight.  Under the
        # store lock it waits, then finds no grant; the family ends with no rows and no mark.
        owner_root = Path(self.tmp.name) / 'owner'
        owner_store, owner_jar = QuickStore(owner_root), jar_at(owner_root)
        owner_jar.save_export({'shop.test': [cookie('.shop.test')]})
        locate = lambda name: (self.server.server_port, self.store.root)
        racers = []

        def opener(request, timeout=None):
            if json.loads(request.data)['op'] == 'remove':
                thread = threading.Thread(target=lambda: family_share.sync(owner_store, owner_jar, {'shop.test'},
                                                                           locate=locate, opener=opener))
                thread.start()
                thread.join(0.3)
                self.assertTrue(thread.is_alive(), 'the push waits for the stop to finish')
                racers.append(thread)
            return _LOOPBACK.open(request, timeout=timeout)
        family_share.share(owner_store, owner_jar, 'family-1', 'shop.test', locate=locate, opener=opener)
        self.assertEqual([row['value'] for row in self.jar.site_rows('shop.test')], [SECRET_VALUE])
        receipt = family_share.unshare(owner_store, 'family-1', 'shop.test', locate=locate, opener=opener)
        for thread in racers:
            thread.join(5)
        self.assertEqual((receipt['removed'], len(racers)), (True, 1))
        self.assertEqual((self.jar.site_rows('shop.test'), family_share.received(self.store), family_share.grants(owner_store)),
                         ([], {}, []))

    def test_the_mark_is_durable_before_the_cookies_and_survives_a_failed_import(self):
        # Codex thread: a crash or a failed import between the mark and the jar leaves a mark without rows,
        # never rows without a mark; payment stays refused either way.
        from personal_agent.browser_jar import JarError
        original = self.profile.import_site
        self.profile.import_site = lambda site, rows: (_ for _ in ()).throw(JarError('key_missing'))
        with self.assertLogs('personal_agent', level='WARNING') as logs:
            status, body = self.put()
        self.assertEqual(status, 400)
        mark = family_share.received(self.store)['shop.test']
        self.assertEqual((mark['from'], mark['error'], 'importing' in mark), ('owner', 'JarError', False))
        self.assertEqual(self.jar.site_rows('shop.test'), [])
        self.assertNotIn(SECRET_VALUE, '\n'.join(logs.output))
        approvals = self.service.browser_approvals_for({'id': 'work-1'})
        self.assertEqual(approvals.refuse('www.shop.test'), family_share.PAYMENT_REFUSED_TEXT, 'mark without rows: still refused')
        self.profile.import_site = original
        status, body = self.put()
        self.assertEqual((status, body['cookies']), (200, 2))
        mark = family_share.received(self.store)['shop.test']
        self.assertEqual((mark['error'], mark['since']), (None, mark['since']))
        self.assertEqual(len(self.jar.site_rows('shop.test')), 2)
        status, body = self.request({'op': 'remove', 'site': 'shop.test'}, secret=self.secret)
        self.assertEqual((status, body['received'], family_share.received(self.store)), (200, True, {}))

    def test_at_start_a_jar_site_with_a_mark_is_refused_for_payment(self):
        # The family instance restarts: the mark alone decides, whether or not the jar holds the rows yet.
        self.store.put(family_share.SHARED_KEY, {'shop.test': {'from': 'owner', 'since': 1.0}})
        self.jar.save_export({'shop.test': [cookie('.shop.test')]}, imported={'shop.test'})
        restarted = AgentService(self.store, ModelAdapter(lambda *a, **k: {}), lambda *a, **k: {'ok': True, 'result': []},
                                 browser_profile=self.profile)
        self.assertEqual(restarted.browser_approvals_for({'id': 'w'}).refuse('www.shop.test'), family_share.PAYMENT_REFUSED_TEXT)
        self.store.put(family_share.SHARED_KEY, {'shop.test': {'from': 'owner', 'since': 1.0, 'importing': 2.0}})
        self.jar.remove('shop.test')
        self.assertEqual(restarted.browser_approvals_for({'id': 'w'}).refuse('shop.test'), family_share.PAYMENT_REFUSED_TEXT,
                         'crashed between the mark and the import: still refused')

    def test_the_retry_runs_off_the_work_loop_one_at_a_time(self):
        # Review P3-3: the owner's service starts one delivery thread; the loop thread never reads the jar.
        owner_store = QuickStore(Path(self.tmp.name) / 'owner')
        owner = AgentService(owner_store, ModelAdapter(lambda *a, **k: {}), lambda *a, **k: {'ok': True, 'result': []},
                             browser_profile=bs.BrowserProfile(Path(self.tmp.name) / 'owner' / 'private' / 'browser-profile',
                                                               launcher=lambda d, h: FakeDriver(), jar=jar_at(Path(self.tmp.name) / 'owner')))
        self.assertEqual(owner.retry_shared_sites(), 0, 'nothing pending: no thread')
        owner_store.put(family_share.GRANTS_KEY, [{'instance': 'family-1', 'site': 'shop.test', 'since': 1.0, 'synced': None}])
        calls, gate = [], threading.Event()
        original = family_share.sync
        family_share.sync = lambda store, jar, touched, **kwargs: (calls.append((threading.current_thread().name, touched, kwargs)), gate.wait(5))
        self.addCleanup(setattr, family_share, 'sync', original)
        self.assertEqual(owner.retry_shared_sites(), 1)
        self.assertEqual(owner.retry_shared_sites(), 0, 'one delivery at a time')
        gate.set()
        owner._shared_sites_thread.join(5)
        self.assertEqual(calls, [('agentos-family-share-retry', set(), {'retry_after': family_share.RETRY_SECONDS})])

    def test_a_wrong_or_missing_secret_and_a_tunnel_are_refused_and_store_nothing(self):
        self.assertEqual(self.put(secret='wrong')[0], 404)
        self.assertEqual(self.request({'op': 'put', 'site': 'shop.test', 'cookies': [cookie('.shop.test')]})[0], 404)
        self.assertEqual(self.put(tunneled=True)[0], 404)
        self.assertEqual(self.put(secret='')[0], 404)
        self.assertEqual((self.jar.site_rows('shop.test'), family_share.received(self.store)), ([], {}))
        # The server refuses an oversized body before reading it, so the client may see the
        # refusal or a closed connection while still sending; either way nothing is stored.
        try:
            status = self.request(None, secret=self.secret, raw=b'x' * (family_share.MAX_BODY + 1))[0]
        except OSError:
            status = 400
        self.assertEqual(status, 400)
        self.assertEqual(family_share.received(self.store), {})
        self.assertEqual(self.request({'op': 'rename', 'site': 'shop.test'}, secret=self.secret)[0], 400)

    def test_without_a_secret_file_nothing_answers(self):
        family_share.link_secret_path(self.store.root).unlink()
        self.assertEqual(self.put()[0], 404)

    def test_a_received_site_refuses_payment_without_asking_and_the_family_side_never_pushes(self):
        self.put()
        approvals = self.service.browser_approvals_for({'id': 'work-1'})
        self.assertEqual(approvals.refuse('www.shop.test'), family_share.PAYMENT_REFUSED_TEXT)
        self.assertIsNone(approvals.refuse('news.test'))
        self.assertIsNone(approvals.refuse(''))
        self.assertEqual(self.service._shared_sites_saved({'shop.test'}), 0, 'no grants here: nothing leaves')
        self.assertEqual(self.service.retry_shared_sites(), 0)


class RefusingApprovals(Approvals):
    def __init__(self, *issued, refused=('fixture.test',)):
        super().__init__(*issued)
        self.refused = set(refused)

    def refuse(self, host):
        return family_share.PAYMENT_REFUSED_TEXT if bs.registrable_domain(host) in self.refused else None


class PaymentRefusal(unittest.TestCase):
    """On a shared site a payment step is refused outright: no approval request, no consumed approval."""

    def session(self, approvals, driver=None):
        driver = driver or FakeDriver()
        return bs.BrowserSession(lambda: driver, work_id='work-1', approvals=approvals), driver

    def test_card_entry_and_the_pay_button_are_refused_without_a_request(self):
        approvals = RefusingApprovals()
        sess, driver = self.session(approvals)
        sess.open({'url': ORIGIN + '/checkout', 'effect': 'navigate'})
        for step, args in (('type', {'target': '카드번호', 'text': '4111', 'effect': 'payment'}),
                           ('click', {'target': '결제하기', 'effect': 'mutate'}),
                           ('click', {'target': '쿠폰 적용', 'effect': 'payment'})):
            with self.subTest(step=step), self.assertRaises(ToolError) as caught:
                getattr(sess, step)(args)
            self.assertEqual((caught.exception.code, str(caught.exception)), ('approval_refused', family_share.PAYMENT_REFUSED_TEXT))
        self.assertEqual((approvals.requests, driver.posts), ([], []), 'nothing was asked and nothing was sent')
        # Reading and an ordinary step still work: the cart is the family assistant's to fill.
        sess.type({'target': '쿠폰', 'text': 'SAVE10', 'effect': 'mutate'})
        self.assertIn(('type', 4, 'SAVE10'), [entry[:3] for entry in driver.log])

    def test_an_approval_the_family_member_gave_does_not_let_a_payment_step_through(self):
        probe = Approvals()
        sess, _ = self.session(probe)
        sess.open({'url': ORIGIN + '/checkout', 'effect': 'navigate'})
        with self.assertRaises(ToolError):
            sess.type({'target': '카드번호', 'text': '4111', 'effect': 'payment'})
        approvals = RefusingApprovals(probe.requests[-1][0])
        sess, driver = self.session(approvals)
        sess.open({'url': ORIGIN + '/checkout', 'effect': 'navigate'})
        with self.assertRaises(ToolError) as caught:
            sess.type({'target': '카드번호', 'text': '4111', 'effect': 'payment'})
        self.assertEqual(caught.exception.code, 'approval_refused')
        self.assertEqual(len(approvals.issued), 1, 'the approval was not even consumed')
        self.assertNotIn('type', [entry[0] for entry in driver.log])

    def test_a_cancelled_payment_submit_is_not_released_or_asked_about(self):
        approvals = RefusingApprovals()
        sess, driver = self.session(approvals)
        sess.open({'url': ORIGIN + '/checkout', 'effect': 'navigate'})
        driver.cancelled = {'page': ORIGIN + '/checkout', 'dom': 0, 'method': 'post', 'action': ORIGIN + '/pay', 'state': 's'}
        with self.assertRaises(ToolError) as caught:
            sess.read()
        self.assertEqual(caught.exception.code, 'approval_refused')
        self.assertEqual(approvals.requests, [])

    def test_the_refusal_sticks_for_the_work_across_a_payment_gateway_hop(self):
        # Review P2-1: the shared site hands checkout to a payment page on another domain.
        approvals = RefusingApprovals()
        sess, driver = self.session(approvals)
        sess.open({'url': ORIGIN + '/cart', 'effect': 'navigate'})
        sess.open({'url': 'http://pg-gateway.test/checkout', 'effect': 'navigate'})
        for step, args in (('type', {'target': '카드번호', 'text': '4111', 'effect': 'payment'}),
                           ('click', {'target': '결제하기', 'effect': 'mutate'})):
            with self.subTest(step=step), self.assertRaises(ToolError) as caught:
                getattr(sess, step)(args)
            self.assertEqual(caught.exception.code, 'approval_refused')
        self.assertEqual((approvals.requests, driver.posts), ([], []))

    def test_a_held_submit_that_posts_to_the_shared_site_is_refused_from_another_page(self):
        approvals = RefusingApprovals()
        sess, driver = self.session(approvals)
        sess.open({'url': 'http://pg-gateway.test/checkout', 'effect': 'navigate'})
        driver.cancelled = {'page': 'http://pg-gateway.test/checkout', 'dom': 0, 'method': 'post', 'action': ORIGIN + '/pay', 'state': 's'}
        with self.assertRaises(ToolError) as caught:
            sess.read()
        self.assertEqual((caught.exception.code, approvals.requests), ('approval_refused', []))

    def test_a_direct_payment_deep_link_into_the_shared_site_is_refused_before_anything_opens(self):
        # Codex thread: the first attempt has no page yet; the requested destination decides.
        approvals = RefusingApprovals()
        sess, driver = self.session(approvals)
        with self.assertRaises(ToolError) as caught:
            sess.open({'url': ORIGIN + '/checkout', 'effect': 'payment'})
        self.assertEqual((caught.exception.code, approvals.requests, driver.log), ('approval_refused', [], []))
        # The resumed, "approved" attempt: the family member's approval is neither consumed nor honoured.
        binding = bs.step_binding('work-1', 'browser_open', ORIGIN + '/checkout', ORIGIN + '/checkout', ORIGIN + '/checkout')
        approvals = RefusingApprovals(binding)
        sess, driver = self.session(approvals)
        with self.assertRaises(ToolError) as caught:
            sess.open({'url': ORIGIN + '/checkout', 'effect': 'payment'})
        self.assertEqual((caught.exception.code, len(approvals.issued), driver.log), ('approval_refused', 1, []))

    def test_navigating_into_the_shared_site_from_an_unshared_page_is_refused_for_payment(self):
        # Codex thread: the link's or the form's destination counts before the step runs; a plain
        # navigation into the shared site is allowed and makes the Work's refusal sticky.
        pages = {'/start': f'''<html><head><title>시작</title></head><body>
              <a href="{ORIGIN}/checkout">결제 페이지</a>
              <form action="{ORIGIN}/pay" method="post"><label>카드번호 <input type="text" autocomplete="cc-number" name="card"></label>
              <button type="submit">바로 결제</button></form></body></html>''', '/checkout': PAGES['/checkout']}
        approvals = RefusingApprovals()
        sess, driver = self.session(approvals, FakeDriver(pages=pages))
        sess.open({'url': 'http://unshared.test/start', 'effect': 'navigate'})
        for step, args in (('click', {'target': '결제 페이지', 'effect': 'payment'}),
                           ('type', {'target': '카드번호', 'text': '4111', 'effect': 'payment'}),
                           ('click', {'target': '바로 결제', 'effect': 'mutate'})):
            with self.subTest(step=step), self.assertRaises(ToolError) as caught:
                getattr(sess, step)(args)
            self.assertEqual(caught.exception.code, 'approval_refused')
        self.assertEqual((approvals.requests, driver.posts), ([], []))
        approvals = RefusingApprovals()
        sess, driver = self.session(approvals, FakeDriver(pages=pages))
        sess.open({'url': 'http://unshared.test/start', 'effect': 'navigate'})
        sess.click({'target': '결제 페이지', 'effect': 'navigate'})
        self.assertEqual(driver.url, ORIGIN + '/checkout', 'reading the shared site is allowed')
        with self.assertRaises(ToolError) as caught:
            sess.type({'target': '카드번호', 'text': '4111', 'effect': 'payment'})
        self.assertEqual((caught.exception.code, approvals.requests), ('approval_refused', []))

    def test_a_work_that_never_touched_a_shared_site_keeps_the_ordinary_approval_path(self):
        approvals = RefusingApprovals(refused=('elsewhere.test',))
        sess, _ = self.session(approvals)
        sess.open({'url': ORIGIN + '/checkout', 'effect': 'navigate'})
        with self.assertRaises(ToolError) as caught:
            sess.type({'target': '카드번호', 'text': '4111', 'effect': 'payment'})
        self.assertEqual(caught.exception.code, 'approval_required', 'the ordinary approval path')
        self.assertEqual(len(approvals.requests), 1)


class Conversation(unittest.TestCase):
    """\"아내 비서에게 로그인 공유해줘\" is a confirmed settings draft; \"공유 그만\" another."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name) / 'owner'
        self.store = QuickStore(root)
        self.jar = jar_at(root)
        self.jar.save_export({'shop.test': [cookie('.shop.test')]})
        profile = bs.BrowserProfile(root / 'private' / 'browser-profile', launcher=lambda d, h: FakeDriver(), jar=self.jar)
        self.service = AgentService(self.store, ModelAdapter(lambda *a, **k: {}), lambda *a, **k: {'ok': True, 'result': []},
                                    browser_profile=profile)
        self.settings = self.service.settings_orchestrator
        self.calls = []
        self.service.share_site = lambda instance, site: self.calls.append(('share', instance, site)) or {'response': f'{instance}:{site} shared'}
        self.service.unshare_site = lambda instance, site: self.calls.append(('unshare', instance, site)) or {'response': f'{instance}:{site} stopped'}
        self._instances = family_share.instances
        # #957: the listing's rows carry each target's name and state; this instance itself is never among them.
        family_share.instances = lambda home=None, locate=None, own=None, now=None: {
            'family-1': {'name': '아내 비서', 'state': 'paired', 'main': False},
            'family-2': {'name': 'family-2', 'state': 'setting_up', 'main': False}}
        self.addCleanup(setattr, family_share, 'instances', self._instances)

    def draft(self, setting, value):
        return self.settings.draft('owner', 'http', {'category': 'family', 'setting': setting, 'value': value})

    def confirm(self, draft):
        return self.settings.confirm('owner', 'http', draft['draft_id'], draft['digest'])

    def test_reading_lists_assistants_signed_in_sites_and_shares_by_name_only(self):
        self.store.put(family_share.GRANTS_KEY, [{'instance': 'family-1', 'site': 'shop.test', 'since': 1.0, 'synced': 2.0}])
        row = self.settings.read('owner', 'family')['settings']['family']
        self.assertEqual(row['share_site']['assistants'],
                         {'family-1': {'name': '아내 비서', 'state': 'paired', 'state_label': '연결됨', 'main': False},
                          'family-2': {'name': 'family-2', 'state': 'setting_up', 'state_label': '설정 중', 'main': False}})
        self.assertEqual(row['add']['value_label'], '아내 비서(family-1, 연결됨), family-2(설정 중)')
        self.assertEqual(row['share_site']['signed_in_sites'], ['shop.test'])
        self.assertEqual(row['share_site']['shared'], [{'instance': 'family-1', 'site': 'shop.test'}])
        self.assertEqual(row['unshare_site']['value_label'], '아내 비서: shop.test')
        self.assertNotIn(SECRET_VALUE, json.dumps(row, ensure_ascii=False))

    def test_a_share_is_drafted_with_the_resolved_names_and_applied_only_on_confirmation(self):
        draft = self.draft('share_site', ' 아내 비서 | https://www.shop.test/cart ')
        self.assertEqual(draft['after'], 'family-1|shop.test')
        self.assertIn("'아내 비서' 비서에 shop.test 로그인 세션을 공유합니다", draft['summary'])
        self.assertNotIn('가족', draft['summary'], 'the target may be the owner\'s own assistant (#957)')
        self.assertIn('비밀번호는 넘기지 않고', draft['note'])
        self.assertEqual(self.calls, [], 'a draft changes nothing')
        result = self.confirm(draft)
        self.assertEqual(self.calls, [('share', 'family-1', 'shop.test')])
        self.assertEqual((result['state'], result['response']), ('applied', 'family-1:shop.test shared'))

    def test_bad_values_are_refused_before_a_draft_exists(self):
        for value, text in (('남편 비서|shop.test', '찾지 못했어요'), ('아내 비서|', '사이트 주소'), ('shop.test', '이름을 주세요'),
                            ('아내 비서|localhost', '사이트 주소')):
            with self.subTest(value=value), self.assertRaises(SettingsError) as caught:
                self.draft('share_site', value)
            self.assertIn(text, str(caught.exception))
        self.store.put(family_share.GRANTS_KEY, [{'instance': 'family-1', 'site': 'shop.test', 'since': 1.0, 'synced': 2.0}])
        with self.assertRaises(SettingsError) as caught:
            self.draft('share_site', '아내 비서|shop.test')
        self.assertIn('이미 공유', str(caught.exception))

    def test_a_received_site_cannot_be_shared_onward_from_the_conversation(self):
        # Review P1-1: on a family instance the model is offered the same tool; the session is not its to pass on.
        self.store.put(family_share.SHARED_KEY, {'shop.test': {'from': 'owner', 'since': 1.0}})
        self.assertEqual(self.settings.read('owner', 'family')['settings']['family']['share_site']['received_sites'], ['shop.test'])
        with self.assertRaises(SettingsError) as caught:
            self.draft('share_site', '아내 비서|https://www.shop.test/')
        self.assertEqual(str(caught.exception), family_share.NOT_YOURS_TEXT.format(site='shop.test'))
        self.assertEqual(self.calls, [])

    def test_a_stop_may_name_the_site_alone_when_one_assistant_holds_it(self):
        with self.assertRaises(SettingsError) as caught:
            self.draft('unshare_site', 'shop.test')
        self.assertIn('공유하고 있지 않아요', str(caught.exception))
        self.store.put(family_share.GRANTS_KEY, [{'instance': 'family-1', 'site': 'shop.test', 'since': 1.0, 'synced': 2.0}])
        draft = self.draft('unshare_site', 'www.shop.test')
        self.assertEqual(draft['after'], 'family-1|shop.test')
        self.assertIn("'아내 비서' 비서의 shop.test 로그인 공유를 그만둡니다", draft['summary'])
        self.assertEqual(self.confirm(draft)['response'], 'family-1:shop.test stopped')
        self.assertEqual(self.calls, [('unshare', 'family-1', 'shop.test')])
        self.store.put(family_share.GRANTS_KEY, [{'instance': 'family-1', 'site': 'shop.test', 'since': 1.0, 'synced': 2.0},
                                                 {'instance': 'family-2', 'site': 'shop.test', 'since': 1.0, 'synced': 2.0}])
        with self.assertRaises(SettingsError) as caught:
            self.draft('unshare_site', 'shop.test')
        self.assertIn('여러 비서', str(caught.exception))
        self.assertEqual(self.draft('unshare_site', 'family-2|shop.test')['after'], 'family-2|shop.test')


if __name__ == '__main__':
    unittest.main()


class LoginWindowNeverCarriesAReceivedSite(unittest.TestCase):
    """#950 review P1: a family member's login window (Mac or phone) never loads, drives or
    overwrites a site received from the owner; agent sessions still carry it."""

    def test_the_window_seed_and_save_leave_the_received_site_alone(self):
        import tempfile
        from personal_agent import browser_session as bs
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        jar = CookieJar(Path(temp.name) / JAR_NAME, MemoryKey(), lambda: 1000.0)
        jar.save_export({'shared.test': [cookie('.shared.test')], 'own.test': [cookie('.own.test')]}, ())
        seeded, drivers = [], []

        class Driver:
            closed = False

            def __init__(self, profile):
                seeded.extend(row['domain'] for row in profile._seed())

            def goto(self, url, timeout):
                return url

            def show(self, url, timeout):
                return {'url': url}

            def is_open(self):
                return not self.closed

            def navigations(self):
                return 0

            def hide(self):
                self.closed = True

            def cookies_export(self):
                # The member signed in to the received site in the window: never saved back.
                return {'shared.test': [cookie('.shared.test', value='member-session')],
                        'own.test': [cookie('.own.test', value='member-own')]}, ()

            def close(self):
                self.closed = True

        profile = bs.BrowserProfile(Path(temp.name), jar=jar, available=lambda: True,
                                    launcher=lambda directory, headless: drivers.append(Driver(profile)) or drivers[-1])
        profile.login_excluded = lambda: {'shared.test'}
        result = profile.open_for_login('https://own.test/login', on_opened=lambda window, host: None,
                                        on_closed=lambda *args: None)
        self.assertTrue(wait_for(lambda: drivers), result)
        profile.close_login_window(result['window'])
        self.assertEqual(seeded, ['.own.test'], 'the received site is never loaded into the window')
        self.assertEqual([row['value'] for row in jar.site_rows('shared.test')], [SECRET_VALUE], 'nor overwritten')
        self.assertEqual([row['value'] for row in jar.site_rows('own.test')], ['member-own'])
        profile._acquire('work')   # an agent session after the window: the share is carried again
        try:
            self.assertIn('.shared.test', [row['domain'] for row in profile._seed()])
        finally:
            profile._release()


def wait_for(condition, seconds=5.0):
    import time
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


class AnyInstanceOnThisMac(unittest.TestCase):
    """FAMILY-SHARE-03 (#957): a share target is any *other* instance on this Mac, the owner's main one
    included, named by its bot's Telegram display name, with the state its own store reports.

    Evidence class: fake launchd definitions and stores in a temporary home,
    a model-free local HTTP server as the receiving instance, fake Telegram
    transports.  No real launchd, Keychain, WebKit or Telegram is touched.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'home'
        (self.home / 'Library/LaunchAgents').mkdir(parents=True)

    # -- a Mac with the owner's service and two named instances --------------------------

    def install(self, instance, port=None, data_dir=None):
        """A launchd definition and a store for one instance; returns its data directory."""
        from personal_agent import service_control as sc
        data_dir = data_dir or (self.home / '.local/share/agentos' if instance is None
                                else self.home / '.local/share/agentos-instances' / instance)
        plist = self.home / 'Library/LaunchAgents' / f'{sc.service_label(instance)}.plist'
        plist.write_bytes(sc.render_plist(Path('/usr/local/bin/agentos'), data_dir, label=sc.service_label(instance),
                                          port=port or sc.DEFAULT_PORT))
        QuickStore(data_dir)
        return data_dir

    def locate(self, name):
        return family_share.locate_instance(name, home=self.home, environ={})

    def instances(self, own):
        return family_share.instances(home=self.home, locate=self.locate, own=own)

    def test_the_listing_excludes_itself_and_includes_the_main_instance_by_its_bot_name(self):
        from personal_agent import family_setup
        owner = self.install(None)
        QuickStore(owner).put('telegram', {'enabled': True, 'username': 'owner_bot', 'bot_name': '김비서', 'user_id': 42})
        spouse = self.install('family-2', 8797)
        QuickStore(spouse).put('telegram', {'enabled': True, 'username': 'spouse_bot', 'bot_name': '이비서', 'user_id': 7})
        # The one-time setup link of the paired instance expired long ago: that is not its state.
        family_setup.write_setup(QuickStore(spouse), instance='family-2', display_name='아내 비서', owner_bot='owner_bot', now=0.0)
        child = self.install('family-1', 8807)
        family_setup.write_setup(QuickStore(child), instance='family-1', display_name='아들 비서', owner_bot='owner_bot')
        # Seen from the spouse's instance: the owner's main instance and the other family instance, not itself.
        self.assertEqual(self.instances(own=spouse),
                         {'main': {'name': '김비서', 'state': 'paired', 'main': True},
                          'family-1': {'name': '아들 비서', 'state': 'setting_up', 'main': False}})
        # Seen from the owner's: both family instances, the paired one reported paired whatever its old link says.
        self.assertEqual(self.instances(own=owner),
                         {'family-2': {'name': '이비서', 'state': 'paired', 'main': False},
                          'family-1': {'name': '아들 비서', 'state': 'setting_up', 'main': False}})
        self.assertEqual(self.locate('main'), (8787, owner.resolve()))
        self.assertEqual(self.locate('family-2')[0], 8797)
        # The display name resolves, case and spacing aside; so does the id.
        rows = self.instances(own=spouse)
        self.assertEqual(family_share.resolve_instance('김비서', rows), 'main')
        self.assertEqual(family_share.resolve_instance(' MAIN ', rows), 'main')
        self.assertEqual(family_share.resolve_instance('아들  비서', rows), 'family-1')
        with self.assertRaises(ValueError) as caught:
            family_share.resolve_instance('이비서', rows)
        self.assertIn('이 Mac의 다른 비서: 김비서(main, 연결됨), 아들 비서(family-1, 설정 중)', str(caught.exception))
        self.assertNotIn('가족', str(caught.exception))
        # An instance never set up at all, and a main service never set up: not connected / not listed.
        self.install('family-3', 8817)
        self.assertEqual(self.instances(own=owner)['family-3'], {'name': 'family-3', 'state': 'not_connected', 'main': False})
        import shutil
        shutil.rmtree(owner)
        self.assertNotIn('main', self.instances(own=spouse))

    def test_the_state_comes_from_the_instances_own_store_read_only(self):
        from personal_agent import family_setup
        folder = Path(self.tmp.name) / 'inst'
        self.assertEqual(family_share.instance_state(folder), 'not_connected', 'no store at all')
        store = QuickStore(folder)
        self.assertEqual(family_share.instance_state(folder), 'not_connected')
        family_setup.write_setup(store, instance='family-1', display_name='아내 비서', owner_bot='owner_bot')
        self.assertEqual(family_share.instance_state(folder), 'setting_up')
        self.assertEqual(family_share.display_name(folder), '아내 비서', 'the setup name until the bot is connected')
        store.put('telegram', {'enabled': True, 'username': 'x_bot', 'bot_name': ' 이  비서 ', 'user_id': True})
        self.assertEqual(family_share.instance_state(folder), 'setting_up', 'a boolean is not a user id')
        store.put('telegram', {'enabled': True, 'username': 'x_bot', 'bot_name': ' 이  비서 ', 'user_id': 7})
        self.assertEqual((family_share.instance_state(folder), family_share.display_name(folder)), ('paired', '이 비서'))
        family_setup.finish_setup(store)
        self.assertEqual(family_share.instance_state(folder), 'paired')
        before = store.path.stat().st_mtime_ns
        family_share.instance_state(folder)
        self.assertEqual(store.path.stat().st_mtime_ns, before, 'a peek never writes the other store')

    def test_main_is_never_a_named_instances_name(self):
        from personal_agent.service_control import service_label
        with self.assertRaises(ValueError):
            service_label('main')
        self.assertEqual(service_label('family-1'), 'com.personal-agentos.family-1')


class MainInstanceReceives(unittest.TestCase):
    """#957: a family instance gives a site to the owner's main instance; the receiving side is unchanged."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name) / 'main'
        self.store, self.jar, self.drivers = QuickStore(root), jar_at(root), []

        def launcher(profile_dir, headless):
            driver = SharedDriver()
            self.drivers.append(driver)
            return driver
        self.profile = bs.BrowserProfile(root / 'private' / 'browser-profile', launcher=launcher, jar=self.jar)
        self.service = AgentService(self.store, ModelAdapter(lambda *a, **k: {}), lambda *a, **k: {'ok': True, 'result': []},
                                    browser_profile=self.profile)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.service))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        # The giver: a family instance holding its member's own sessions.
        giver = Path(self.tmp.name) / 'family-2'
        self.giver_store, self.giver_jar = QuickStore(giver), jar_at(giver)
        self.giver_jar.save_export({'shop.test': [cookie('.shop.test'), cookie('www.shop.test', 'pref', 'p')],
                                    'news.test': [cookie('news.test', value=OTHER_VALUE)]})
        self.located = []

    def locate(self, name):
        self.located.append(name)
        if name != family_share.MAIN_INSTANCE:
            raise ValueError('unknown')
        return self.server.server_port, self.store.root

    def test_a_family_instance_shares_with_the_main_instance_which_marks_refuses_payment_and_never_passes_it_on(self):
        from personal_agent import family_setup
        self.assertFalse(family_setup.setup_recorded(self.store), 'the receiver is the main instance: no family setup here')
        receipt = family_share.share(self.giver_store, self.giver_jar, 'main', 'https://www.shop.test/cart', locate=self.locate,
                                     label='김비서')
        self.assertEqual((receipt['instance'], receipt['site'], receipt['cookies'], receipt['delivered']), ('main', 'shop.test', 2, True))
        self.assertIn('김비서 비서에 shop.test', receipt['response'])
        self.assertTrue(family_share.link_secret_path(self.store.root).exists(), "written into the receiver's data dir")
        # Only that site's rows arrived; the main instance marks it, refuses payment and keeps it out of login windows.
        self.assertEqual([row['value'] for row in self.jar.site_rows('shop.test')], [SECRET_VALUE, 'p'])
        self.assertEqual(self.jar.site_rows('news.test'), [])
        self.assertEqual(set(family_share.received(self.store)), {'shop.test'})
        self.assertEqual(self.service.browser_approvals_for({'id': 'w'}).refuse('www.shop.test'), family_share.PAYMENT_REFUSED_TEXT)
        self.assertEqual(self.profile.login_excluded(), {'shop.test'})
        self.assertEqual(family_share.login_refusal(self.store, 'shop.test'), family_share.LOGIN_REFUSED_TEXT)
        # Onward: the main instance may not share what it received, from code or from the conversation.
        with self.assertRaises(ValueError) as caught:
            family_share.share(self.store, self.jar, 'family-1', 'shop.test', locate=lambda name: (8807, Path(self.tmp.name) / 'x'))
        self.assertEqual(str(caught.exception), family_share.NOT_YOURS_TEXT.format(site='shop.test'))
        self.assertEqual(family_share.grants(self.store), [])
        self.assertEqual(self.service.settings_orchestrator.read('owner', 'family')['settings']['family']['share_site']['received_sites'],
                         ['shop.test'])
        # Unshare revokes at once: the main instance's copy and mark are gone, the giver's own session stays.
        receipt = family_share.unshare(self.giver_store, 'main', 'shop.test', locate=self.locate, labels={'main': '김비서'})
        self.assertEqual((receipt['instances'], receipt['removed']), (['main'], True))
        self.assertIn('김비서 비서에서 shop.test', receipt['response'])
        self.assertEqual((self.jar.site_rows('shop.test'), family_share.received(self.store), family_share.grants(self.giver_store)),
                         ([], {}, []))
        self.assertIsNone(self.service.browser_approvals_for({'id': 'w'}).refuse('www.shop.test'))
        self.assertEqual(self.giver_jar.site_rows('shop.test')[0]['value'], SECRET_VALUE)

    def test_a_receivers_own_session_is_never_replaced_and_it_keeps_every_authority_there(self):
        # #966 review P1-1: the owner's main instance is signed in to the site as itself; a family member
        # shares the same site.  Nothing is swapped, marked or set aside: the push is refused, in words.
        self.jar.save_export({'shop.test': [cookie('.shop.test', value='OWNER-OWN-SESSION')]})
        other = Opener()
        with self.assertLogs('personal_agent.family_share', level='INFO') as logs:
            receipt = family_share.share(self.giver_store, self.giver_jar, 'main', 'shop.test', locate=self.locate, label='김비서', now=2000.0)
        self.assertEqual((receipt['delivered'], receipt['refused']), (False, 'receiver_signed_in'))
        self.assertEqual(receipt['response'], family_share.RECEIVER_SIGNED_IN_RECEIPT.format(label='김비서', site='shop.test'))
        self.assertNotIn(SECRET_VALUE, '\n'.join(logs.output))
        self.assertNotIn('OWNER-OWN-SESSION', '\n'.join(logs.output))
        grant = family_share.grants(self.giver_store)[0]
        self.assertEqual((grant['error'], grant['synced'], grant['attempted']), ('receiver_signed_in', None, 2000.0))
        # The owner's instance: rows, payment, login window and onward sharing exactly as before.
        self.assertEqual([row['value'] for row in self.jar.site_rows('shop.test')], ['OWNER-OWN-SESSION'])
        self.assertEqual(family_share.received(self.store), {})
        self.assertIsNone(self.service.browser_approvals_for({'id': 'w'}).refuse('www.shop.test'))
        self.assertEqual(self.profile.login_excluded(), set())
        self.assertIsNone(family_share.login_refusal(self.store, 'shop.test'))
        onward = family_share.share(self.store, self.jar, 'family-1', 'shop.test', locate=lambda name: (8807, Path(self.tmp.name) / 'f1'), opener=other)
        self.assertTrue(onward['delivered'], 'the owner still shares his own site onward')
        self.assertEqual([row['value'] for row in other.bodies()[-1]['cookies']], ['OWNER-OWN-SESSION'])
        # The giver does not knock every tick: only when its rows for the site change, or at start.
        self.assertFalse(family_share.pending(self.giver_store))
        self.assertEqual(family_share.sync(self.giver_store, self.giver_jar, set(), locate=self.locate, now=2100.0, retry_after=30), 0)
        self.assertEqual(family_share.grants(self.giver_store)[0]['attempted'], 2000.0, 'not attempted again')
        self.assertEqual(family_share.sync(self.giver_store, self.giver_jar, {'shop.test'}, locate=self.locate, now=2200.0), 0)
        self.assertEqual((family_share.grants(self.giver_store)[0]['error'], family_share.grants(self.giver_store)[0]['attempted']),
                         ('receiver_signed_in', 2200.0), 'asked again after a change, refused again')
        self.assertEqual([row['value'] for row in self.jar.site_rows('shop.test')], ['OWNER-OWN-SESSION'])
        # A later unshare deletes nothing on the owner's instance.
        receipt = family_share.unshare(self.giver_store, 'main', 'shop.test', locate=self.locate, labels={'main': '김비서'})
        self.assertEqual((receipt['instances'], receipt['removed'], family_share.grants(self.giver_store)), (['main'], True, []))
        self.assertEqual([row['value'] for row in self.jar.site_rows('shop.test')], ['OWNER-OWN-SESSION'])
        self.assertEqual(family_share.received(self.store), {})
        # Once the owner signs out there, the same share lands (the giver's own session is its to give).
        self.jar.remove('shop.test')
        receipt = family_share.share(self.giver_store, self.giver_jar, 'main', 'shop.test', locate=self.locate, label='김비서')
        self.assertEqual((receipt['delivered'], receipt['refused'], set(family_share.received(self.store))), (True, None, {'shop.test'}))
        self.assertEqual([row['value'] for row in self.jar.site_rows('shop.test')], [SECRET_VALUE, 'p'])

    def test_a_refusal_is_a_coded_400_and_an_ordinary_400_stays_a_transport_error(self):
        self.jar.save_export({'shop.test': [cookie('.shop.test', value='OWNER-OWN-SESSION')]})
        secret = family_share.ensure_link_secret(self.store.root)
        with self.assertRaises(family_share.Refused) as caught:
            family_share.push(self.server.server_port, secret, 'shop.test', [cookie('.shop.test')])
        self.assertEqual((caught.exception.code, str(caught.exception)), ('receiver_signed_in', family_share.RECEIVER_SIGNED_IN_TEXT))
        with self.assertRaises(HTTPError):
            family_share._post(self.server.server_port, secret, {'op': 'rename', 'site': 'shop.test'})
        # Already received: a refreshed push for that site is accepted (the mark says it is the giver's).
        self.store.put(family_share.SHARED_KEY, {'shop.test': {'from': 'owner', 'since': 1.0}})
        self.assertEqual(family_share.push(self.server.server_port, secret, 'shop.test', [cookie('.shop.test')])['cookies'], 1)

    def test_an_instance_is_never_a_target_for_itself(self):
        # #966 review P2-2: ``main`` (or any id) that resolves to this instance's own data dir is refused before
        # a link secret is written or a grant recorded; a ``main`` with no store there is not installed.
        self.giver_jar.save_export({'shop.test': [cookie('.shop.test')]})
        with self.assertRaises(ValueError) as caught:
            family_share.share(self.giver_store, self.giver_jar, 'main', 'shop.test', locate=lambda name: (8787, self.giver_store.root))
        self.assertEqual(str(caught.exception), family_share.SELF_TEXT)
        self.assertFalse(family_share.link_secret_path(self.giver_store.root).exists())
        self.assertEqual(family_share.grants(self.giver_store), [])
        empty = Path(self.tmp.name) / 'nothing-here'
        with self.assertRaises(ValueError) as caught:
            family_share.share(self.giver_store, self.giver_jar, 'main', 'shop.test', locate=lambda name: (8787, empty), label='김비서')
        self.assertEqual(str(caught.exception), family_share.NOT_INSTALLED_TEXT.format(instance='김비서'))
        self.assertFalse(family_share.link_secret_path(empty).exists())
        self.assertEqual(family_share.instances(home=Path(self.tmp.name), locate=lambda name: (8787, self.giver_store.root),
                                               own=self.giver_store.root), {})

    def test_the_main_instances_endpoint_answers_loopback_with_the_secret_only_never_a_tunnel(self):
        secret = family_share.ensure_link_secret(self.store.root)
        base = f'http://127.0.0.1:{self.server.server_port}'

        def post(headers):
            data = json.dumps({'op': 'put', 'site': 'shop.test', 'cookies': [cookie('.shop.test')]}).encode()
            try:
                with urlopen(Request(base + family_share.SHARE_PATH, data=data, method='POST',
                                     headers={'Content-Type': 'application/json', **headers}), timeout=10) as response:
                    return response.status
            except HTTPError as error:
                return error.code
        self.assertEqual(post({family_share.LINK_HEADER: secret, 'X-Forwarded-For': '203.0.113.9', 'X-Forwarded-Proto': 'https'}), 404)
        self.assertEqual(post({family_share.LINK_HEADER: secret[:-1]}), 404)
        self.assertEqual(post({}), 404)
        self.assertEqual((self.jar.site_rows('shop.test'), family_share.received(self.store)), ([], {}))
        self.assertEqual(post({family_share.LINK_HEADER: secret}), 200)
        self.assertEqual(set(family_share.received(self.store)), {'shop.test'})


class BotName(unittest.TestCase):
    """#957: an instance keeps its bot's display name at connect and backfills it once at start, best-effort."""

    def service(self, answers):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / 'inst'
        store = QuickStore(root)
        calls = []

        def transport(url, body, headers=None, timeout=60):
            calls.append(url.rsplit('/', 1)[-1])
            answer = answers.get(url.rsplit('/', 1)[-1], {})
            if isinstance(answer, Exception):
                raise answer
            return {'ok': True, 'result': answer}
        profile = bs.BrowserProfile(root / 'private' / 'browser-profile', launcher=lambda d, h: FakeDriver(), jar=jar_at(root))
        return AgentService(store, ModelAdapter(lambda *a, **k: {}), transport, browser_profile=profile), store, calls

    def test_connect_keeps_the_display_name(self):
        service, store, _calls = self.service({'getMe': {'username': 'owner_test_bot', 'first_name': ' 김  비서 '}})
        service.connect_telegram({'token': '123456:TEST_TOKEN'})
        self.assertEqual(store.config('telegram')['bot_name'], '김 비서')
        self.assertEqual(family_share.display_name(store.root), '김 비서')

    def test_the_backfill_is_best_effort(self):
        answers = {'getMe': OSError('offline')}
        service, store, calls = self.service(answers)
        self.assertFalse(service.backfill_bot_name(), 'Telegram not connected: nothing to ask')
        self.assertEqual(calls, [])
        store.secret('telegram_token', '123456:TEST_TOKEN')
        store.put('telegram', {'enabled': True, 'username': 'owner_test_bot', 'user_id': 42})
        with self.assertLogs('personal_agent', level='WARNING') as logs:
            self.assertFalse(service.backfill_bot_name())
        self.assertNotIn('TEST_TOKEN', '\n'.join(logs.output))
        self.assertNotIn('bot_name', store.config('telegram'), 'a failure changes nothing')
        answers['getMe'] = {'username': 'owner_test_bot'}
        self.assertFalse(service.backfill_bot_name(), 'no name in the answer: nothing stored')
        answers['getMe'] = {'username': 'owner_test_bot', 'first_name': '김비서'}
        self.assertTrue(service.backfill_bot_name())
        self.assertEqual(store.config('telegram')['bot_name'], '김비서')
        self.assertEqual(store.config('telegram')['user_id'], 42, 'the pairing is untouched')
        self.assertEqual(calls, ['getMe', 'getMe', 'getMe'])
        self.assertFalse(service.backfill_bot_name(), 'known: not asked again')
        self.assertEqual(len(calls), 3)
