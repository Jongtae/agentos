"""The owner can actually reach and complete a Calendar connection.

J4 was recorded as "not wired" for the whole program, and the reasoning was
sound while it held: `CalendarConnector` registers both connector specs on
construction, and registering them without a route an owner can finish turns
a truthful "not configured locally" refusal into Work parked for a connection
nothing can complete.  So the fix had to land as one piece -- credential,
routes, connector -- and this file is what proves the piece is whole.

Everything here is driven through the shipped HTTP surface against a real
local server, with a fake Google token endpoint.  No live Google call is made.
The URL under test is read out of the product's own settings payload and
opened, rather than reconstructed by the test, because a test that rebuilds
the address it then opens cannot notice the product offering a different one.
"""
import json
import tempfile
import threading
import unittest
from http.cookiejar import CookieJar
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import (HTTPCookieProcessor, HTTPRedirectHandler, Request,
                            build_opener)

from cryptography.fernet import Fernet

from personal_agent.calendar import CALENDAR_CONNECTOR_ID, CALENDAR_WRITE_CONNECTOR_ID
from personal_agent.quickstart import configured_service, make_handler
from personal_agent.quickstart_store import QuickStore


class NoRedirect(HTTPRedirectHandler):
    """Capture the redirect instead of following it.

    Following it would make a live request to accounts.google.com, which this
    repository does not authorise and which would make the test depend on the
    network. The Location header is the thing under test anyway.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RedirectCaptured(newurl)


class RedirectCaptured(Exception):
    def __init__(self, location):
        super().__init__(location)
        self.location = location


class CalendarReachabilityTests(unittest.TestCase):
    CLIENT_SECRET = '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ret'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parent))
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(Path(self.temp.name) / 'data')
        self.exchanges = []

    def exchange(self, payload):
        """Stand in for Google's token endpoint."""
        self.exchanges.append(payload)
        return {'access_token': 'fixture-calendar-access',
                'refresh_token': 'fixture-calendar-refresh',
                'expires_in': 3_600,
                'scope': payload.get('__scope__', '')}

    def serve(self, configure=True):
        server = ThreadingHTTPServer(('127.0.0.1', 0), BaseHTTPRequestHandler,
                                     bind_and_activate=False)
        server.server_bind()
        try:
            server.server_activate()
        except Exception:
            server.server_close(); raise
        port = server.server_port
        env = {}
        if configure:
            env = {'AGENTOS_CALENDAR_LOCAL_ONLY': '1',
                   'AGENTOS_CALENDAR_CLIENT_ID': 'calendar-client',
                   'AGENTOS_CALENDAR_CLIENT_SECRET': self.CLIENT_SECRET,
                   'AGENTOS_CALENDAR_LOCAL_PORT': str(port),
                   'AGENTOS_CALENDAR_ENCRYPTION_KEY': Fernet.generate_key().decode()}
        service = configured_service(self.store, env)
        if service.calendar_oauth is not None:
            service.calendar_token_exchange = self.exchange
        server.RequestHandlerClass = make_handler(service, (), 'pairing-token')
        thread = threading.Thread(target=server.serve_forever)
        thread.start()

        def shutdown():
            server.shutdown(); thread.join(); server.server_close()

        self.addCleanup(shutdown)
        return service, f'http://127.0.0.1:{port}'

    def login(self, base):
        self.store.claim(self.store.bootstrap.read_text(), 'long-password-test')
        client = build_opener(HTTPCookieProcessor(CookieJar()), NoRedirect())
        client.open(Request(base + '/api/login',
                            data=json.dumps({'password': 'long-password-test'}).encode(),
                            headers={'Content-Type': 'application/json'}), timeout=3).read()
        return client

    # -- the offer ---------------------------------------------------------

    def test_the_settings_payload_offers_a_route_for_both_grants(self):
        """Read and write are separate connectors and separate offers."""
        service, _ = self.serve()
        rows = {row['connector_id']: row for row in service.settings()['connectors']}
        for connector_id in (CALENDAR_CONNECTOR_ID, CALENDAR_WRITE_CONNECTOR_ID):
            with self.subTest(connector=connector_id):
                row = rows[connector_id]
                self.assertEqual(row['state'], 'disconnected',
                                 'registering a definition must grant nothing')
                path = row['connect_path']
                self.assertTrue(path.startswith('/'), path)
                self.assertEqual(urlsplit(path).netloc, '',
                                 'the offered path must be relative to this install')
        self.assertNotEqual(rows[CALENDAR_CONNECTOR_ID]['connect_path'],
                            rows[CALENDAR_WRITE_CONNECTOR_ID]['connect_path'],
                            'one route must still name which grant it starts')

    def test_an_unconfigured_install_offers_nothing_and_answers_nothing(self):
        """The honest previous state, preserved for installs without a credential.

        A first version of this guarded with `if connector_id in rows`, and an
        unconfigured install emits no connector rows at all, so it asserted
        nothing and a mutation that kept advertising the route survived it.
        Assert the absence directly, and that the route itself is not served.
        """
        service, base = self.serve(configure=False)
        self.assertIsNone(service.calendar_oauth)
        rows = {row['connector_id'] for row in service.settings()['connectors']}
        self.assertNotIn(CALENDAR_CONNECTOR_ID, rows)
        self.assertNotIn(CALENDAR_WRITE_CONNECTOR_ID, rows)
        self.assertEqual(service.connector_connect_url(CALENDAR_CONNECTOR_ID), '')
        self.assertEqual(service.connector_connect_url(CALENDAR_WRITE_CONNECTOR_ID), '')
        # And the owner-authenticated route refuses rather than half-working.
        client = self.login(base)
        with self.assertRaises(HTTPError) as refused:
            client.open(base + '/google-calendar?grant=read', timeout=3)
        self.assertEqual(refused.exception.code, 400)

    # -- the route the offer names -----------------------------------------

    def test_opening_the_offered_path_redirects_to_google(self):
        """Open the product's own string, do not rebuild it."""
        service, base = self.serve()
        client = self.login(base)
        row = next(r for r in service.settings()['connectors']
                   if r['connector_id'] == CALENDAR_CONNECTOR_ID)
        with self.assertRaises(RedirectCaptured) as redirect:
            client.open(base + row['connect_path'], timeout=3)
        target = redirect.exception.location
        self.assertIn('accounts.google.com', target)
        query = parse_qs(urlsplit(target).query)
        self.assertEqual(query['include_granted_scopes'], ['false'])
        self.assertIn('code_challenge', query)
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertNotIn(self.CLIENT_SECRET, target)

    def test_the_connect_route_requires_an_owner_session(self):
        _, base = self.serve()
        with self.assertRaises(HTTPError) as refused:
            build_opener().open(base + '/google-calendar?grant=read', timeout=3)
        self.assertEqual(refused.exception.code, 401)

    def test_an_unknown_grant_is_refused(self):
        _, base = self.serve()
        client = self.login(base)
        with self.assertRaises(HTTPError) as refused:
            client.open(base + '/google-calendar?grant=everything', timeout=3)
        self.assertEqual(refused.exception.code, 400)

    # -- completing it ------------------------------------------------------

    def test_a_forged_callback_is_refused_and_connects_nothing(self):
        service, base = self.serve()
        with self.assertRaises(HTTPError) as refused:
            build_opener().open(base + '/oauth/calendar/callback?code=x&state=forged', timeout=3)
        self.assertEqual(refused.exception.code, 400)
        rows = {row['connector_id']: row for row in service.settings()['connectors']}
        self.assertEqual(rows[CALENDAR_CONNECTOR_ID]['state'], 'disconnected')

    def test_the_callback_route_exists_and_says_nothing_about_configuration(self):
        """One message for every failure, so a guess learns nothing."""
        _, base = self.serve()
        bodies = set()
        for query in ('', '?code=x', '?state=y', '?code=x&state=y', '?error=access_denied'):
            with self.assertRaises(HTTPError) as refused:
                build_opener().open(base + '/oauth/calendar/callback' + query, timeout=3)
            bodies.add(refused.exception.read())
        self.assertEqual(len(bodies), 1, bodies)

    def test_the_client_secret_never_reaches_a_surface(self):
        service, base = self.serve()
        client = self.login(base)
        row = next(r for r in service.settings()['connectors']
                   if r['connector_id'] == CALENDAR_CONNECTOR_ID)
        with self.assertRaises(RedirectCaptured) as redirect:
            client.open(base + row['connect_path'], timeout=3)
        target = redirect.exception.location
        payload = json.dumps(service.settings(), ensure_ascii=False)
        for surface in (target, payload):
            with self.subTest():
                self.assertNotIn(self.CLIENT_SECRET, surface)


if __name__ == '__main__':
    unittest.main()
