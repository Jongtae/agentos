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

from personal_agent.calendar import (CALENDAR_CONNECTOR_ID, CALENDAR_SPEC,
                                     CALENDAR_WRITE_CONNECTOR_ID, CALENDAR_WRITE_SPEC)
from personal_agent.calendar import CalendarConnector
from personal_agent.calendar_oauth import (EncryptedCalendarSecretStore,
                                           calendar_transport)
from personal_agent.google_calendar import GoogleCalendar
from personal_agent.providers import ModelAdapter
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
        self.grant = 'read'
        self.public_hosts = ()

    def exchange(self, payload):
        """Stand in for Google's token endpoint.

        Returns the exact scope set of whichever grant is completing, which
        is what `_validated_tokens` requires. `self.grant` is set by the test
        that started the authorization.
        """
        self.exchanges.append(payload)
        spec = CALENDAR_WRITE_SPEC if self.grant == 'write' else CALENDAR_SPEC
        return {'access_token': f'fixture-{self.grant}-access',
                'refresh_token': f'fixture-{self.grant}-refresh',
                'expires_in': 3_600,
                'scope': ' '.join(spec.required_scopes)}

    def authorize(self, service, base, grant='read'):
        """Drive one whole authorization through the shipped routes.

        Nothing here reaches Google: the redirect is captured rather than
        followed, and `self.exchange` stands in for the token endpoint. This
        is the success path -- the thing no test covered, which is exactly
        why the callback shipped reporting a committed connection as a
        failure and refusing the retry.
        """
        self.grant = grant
        client = self.login(base)
        connector_id = (CALENDAR_WRITE_CONNECTOR_ID if grant == 'write'
                        else CALENDAR_CONNECTOR_ID)
        row = next(r for r in service.settings()['connectors']
                   if r['connector_id'] == connector_id)
        with self.assertRaises(RedirectCaptured) as redirect:
            client.open(base + row['connect_path'], timeout=3)
        state = parse_qs(urlsplit(redirect.exception.location).query)['state'][0]
        return build_opener().open(
            base + f'/oauth/calendar/callback?code=fixture-code&state={state}', timeout=3)

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
            self.encryption_key = Fernet.generate_key().decode()
            env = {'AGENTOS_CALENDAR_LOCAL_ONLY': '1',
                   'AGENTOS_CALENDAR_CLIENT_ID': 'calendar-client',
                   'AGENTOS_CALENDAR_CLIENT_SECRET': self.CLIENT_SECRET,
                   'AGENTOS_CALENDAR_LOCAL_PORT': str(port),
                   'AGENTOS_CALENDAR_ENCRYPTION_KEY': self.encryption_key}
        service = configured_service(self.store, env)
        if service.calendar_oauth is not None:
            service.calendar_token_exchange = self.exchange
        server.RequestHandlerClass = make_handler(service, self.public_hosts, 'pairing-token')
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

    def test_the_apply_surface_refuses_a_tunnel_host(self):
        """The first route in this server with a real third-party effect.

        It was modelled on `/api/personal-space/memory-candidates`, which
        admits the public tunnel host because it has no external effect.
        This one creates, changes or cancels a real calendar event, and
        every other Calendar route already refuses a tunnel host. Review
        drove list -> approve -> apply over `Host: tunnel.example.test` and
        the provider's `create` fired.
        """
        self.public_hosts = ('tunnel.example.test',)
        _, base = self.serve()
        self.store.claim(self.store.bootstrap.read_text(), 'long-password-test')
        headers = {'Cookie': 'agentos_session=' + self.store.local_session(),
                   'Host': 'tunnel.example.test'}
        request = Request(base + '/api/calendar/drafts', headers=headers)
        with self.assertRaises(HTTPError) as refused:
            build_opener().open(request, timeout=3)
        self.assertEqual(refused.exception.code, 400)
        post = Request(base + '/api/calendar/drafts/request',
                       data=json.dumps({'operation': 'list'}).encode(),
                       headers={**headers, 'Content-Type': 'application/json'})
        with self.assertRaises(HTTPError) as refused:
            build_opener().open(post, timeout=3)
        self.assertEqual(refused.exception.code, 400)

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

    # -- the two owner identities, which is where the bugs lived ----------

    def park_write_work(self, service):
        """Park a *local/web* Work for the write connector, Telegram paired.

        That combination is the one that separates the two identifiers: the
        write connector has a record naming `local-owner`, while the read
        connector can never have one and falls back to the paired Telegram
        owner. With the Work parked under the Telegram chat instead, both
        ids return the same string and the bug is invisible.
        """
        job_id = service.store.enqueue('내일 3시에 회의 잡아줘', 'park-1')
        service.connector_handoff.park('local-owner', job_id,
                                       CALENDAR_WRITE_CONNECTOR_ID)
        return job_id

    def test_the_write_callback_resolves_the_owner_that_parked_the_work(self):
        """Resolving every callback through the read connector id is a dead end.

        `connector_callback_owner` recovers the identity by matching the
        connector's parked record. No intent maps to `google-calendar`, so a
        read record can never exist and that id always falls back to the
        first candidate -- the paired Telegram owner. The write grant was
        being stored under a different identity than the one that parked the
        Work, the pending slot did not match, and the authorization could
        never complete.

        Without a paired Telegram owner both ids collapse to `local-owner`
        and the bug is invisible, which is why this test pairs one.
        """
        service, base = self.serve()
        service.store.put('telegram', {'enabled': True, 'user_id': 4242})
        self.park_write_work(service)
        # Precondition: the two identifiers genuinely disagree here. Read
        # them BEFORE the callback -- resuming consumes the parked record,
        # after which the write id also falls back to the Telegram owner and
        # the disagreement disappears.
        write_owner = service.connector_callback_owner(CALENDAR_WRITE_CONNECTOR_ID)
        read_owner = service.connector_callback_owner(CALENDAR_CONNECTOR_ID)
        self.assertNotEqual(write_owner, read_owner)
        response = self.authorize(service, base, grant='write')
        self.assertEqual(response.status, 200)
        self.assertEqual(
            service.connector_registry.status(write_owner, CALENDAR_WRITE_CONNECTOR_ID).state.value,
            'connected',
            'the grant must land under the identity that parked the Work')
        # ...and not under the identity the read connector would have named.
        self.assertEqual(
            service.connector_registry.status(read_owner, CALENDAR_WRITE_CONNECTOR_ID).state.value,
            'disconnected')

    def test_an_unparked_connection_does_not_tell_the_owner_it_failed(self):
        """`resume_connector_work` notifies before it raises.

        Calling it with nothing parked both produced the HTTP 400 and pushed
        a refusal bubble to a paired Telegram owner on a connection that had
        in fact succeeded. The parked pre-read is what prevents the
        notification; the exception catch alone would still have sent it.
        """
        service, base = self.serve()
        service.store.put('telegram', {'enabled': True, 'user_id': 4242})
        sent = []
        service.telegram_transport = lambda url, body=None, headers=None, timeout=30: (
            sent.append((url, body)) or {'ok': True, 'result': {}})
        response = self.authorize(service, base)
        self.assertEqual(response.status, 200)
        self.assertEqual([url for url, _ in sent if url.endswith('/sendMessage')], [],
                         'a successful connection must not report a refusal')

    def test_a_parked_resume_that_fails_still_reports_the_connection(self):
        """The catch, isolated from the parked pre-read.

        The two masked each other: with the pre-read in place an unparked
        callback never reaches the resume, so removing the
        `ConversationHandoffError` catch changed nothing observable. This is
        the case where the resume genuinely runs and genuinely fails -- the
        Work was parked under a Telegram generation that has since changed --
        and the connection must still be reported as the success it is,
        because it is one.
        """
        service, base = self.serve()
        job_id = service.store.enqueue('내일 3시에 회의 잡아줘', 'park-gen',
                                       channel='telegram:1', chat_id=4242)
        service.store.put('telegram', {'enabled': True, 'user_id': 4242})
        service.connector_handoff.park('telegram:4242', job_id,
                                       CALENDAR_WRITE_CONNECTOR_ID,
                                       generation='telegram:1')
        # The bot was reconnected: the parked generation no longer matches.
        service.store.put('telegram', {'enabled': True, 'user_id': 4242,
                                       'generation': 'telegram:2'})
        response = self.authorize(service, base, grant='write')
        self.assertEqual(response.status, 200,
                         'a committed connection must not be reported as a failure '
                         'because its resume was refused')
        rows = {r['connector_id']: r for r in service.settings()['connectors']}
        self.assertEqual(rows[CALENDAR_WRITE_CONNECTOR_ID]['state'], 'connected')

    def test_a_telegram_work_reads_the_grant_its_own_owner_connected(self):
        """The per-owner binding, driven through the worker.

        The tool used the Memory owner while the connector used
        `connector_owner_id`, so a Telegram owner could finish the OAuth and
        still be told the calendar was disconnected. Deleting that fix left
        the whole suite green, because no test joined the callback to a Work.
        This runs a real job through `run_one`.
        """
        service, base = self.serve()
        service.store.put('telegram', {'enabled': True, 'user_id': 4242})
        self.authorize(service, base)

        calls = []

        def transport(url, body, headers=None, timeout=60):
            tools = [t.get('function', {}).get('name') for t in body.get('tools', [])]
            if any(t == 'agentos_connection_probe' for t in tools):
                return {'message': {'content': '', 'tool_calls': [
                    {'function': {'name': 'agentos_connection_probe', 'arguments': {}}}]}}
            if 'calendar_query' in tools and not calls:
                calls.append(True)
                return {'message': {'content': '', 'tool_calls': [{'function': {
                    'name': 'calendar_query',
                    'arguments': {'start': '2026-09-23T00:00:00+09:00',
                                  'end': '2026-09-24T00:00:00+09:00',
                                  'timezone': 'Asia/Seoul'}}}]}}
            return {'message': {'content': '일정을 확인했습니다.'}}

        # Rebuild the connector factory with a fake HTTPS opener, from the
        # same encryption key the environment gave `configured_service`, so
        # the whole path -- owner resolution, grant lookup, token, provider
        # call -- runs offline. Without this the authority step passes and
        # the provider call reaches for the real Google endpoint.
        self.provider_calls = []

        def fake_opener(method, url, body, headers):
            self.provider_calls.append((method, url, headers.get('Authorization')))
            return {'items': []}

        secrets = EncryptedCalendarSecretStore(service.store, self.encryption_key)
        registry = service.connector_registry
        service.calendar_factory = lambda owner_id: CalendarConnector(
            service.store,
            GoogleCalendar(calendar_transport(secrets, registry, owner_id,
                                              allow_writes=True, opener=fake_opener)),
            registry=registry)
        service.adapter = ModelAdapter(transport)
        service.save_model({'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434',
                            'model': 'test-model', 'api_key': ''})
        # The worker refuses to run a tool-calling turn until the model's
        # tool-call path has been verified once.
        self.assertTrue(service.test_model()['ok'])
        job_id = service.store.enqueue('내일 일정 뭐 있어?', 'cal-1',
                                       channel='telegram:1', chat_id=4242)
        service.run_one()
        events = [e for e in service.store.task_events(job_id) if e['tool'] == 'calendar_query']
        self.assertTrue(events, 'the model never reached calendar_query')
        # The refusal we must NOT see is the disconnected one: the Telegram
        # owner connected, so their own Work must find the grant.
        # Assert the success positively. A first version only checked that
        # certain refusal strings were absent, which a differently worded
        # failure satisfies -- the `calendar_owner` mutant survived it.
        statuses = [event['status'] for event in events]
        self.assertTrue(self.provider_calls,
                        'the connector never reached the provider, so the '
                        'grant was not found for this Work owner')
        self.assertEqual(self.provider_calls[0][2], 'Bearer fixture-read-access')
        self.assertIn('succeeded', statuses,
                      'the Telegram owner connected, so their own Work must '
                      'find the grant: ' +
                      json.dumps([dict(e) for e in events], ensure_ascii=False, default=str)[:400])

    # -- the success path, which nothing covered -------------------------

    def test_an_ordinary_connection_succeeds_and_says_so(self):
        """The flow the settings payload advertises, with nothing parked.

        This shipped returning HTTP 400 -- "could not be completed, start
        again" -- while the connection was committed, because the callback
        called `resume_connector_work` unconditionally and `no_pending_work`
        is the normal case for an owner who simply clicks connect. Gmail
        reads the parked record first and this did not.
        """
        service, base = self.serve()
        response = self.authorize(service, base)
        self.assertEqual(response.status, 200)
        self.assertIn(b'connected', response.read().lower())
        rows = {r['connector_id']: r for r in service.settings()['connectors']}
        self.assertEqual(rows[CALENDAR_CONNECTOR_ID]['state'], 'connected')
        # ...and the write grant did not come along for the ride.
        self.assertEqual(rows[CALENDAR_WRITE_CONNECTOR_ID]['state'], 'disconnected')

    def test_the_write_grant_completes_under_its_own_connector(self):
        """The callback must resolve the owner from the grant the state names.

        It resolved every callback through the read connector id. No intent
        maps to the read connector, so its record can never exist and the id
        always falls back to the first owner candidate -- which meant that on
        a Telegram-paired install the write authorization could never
        complete and its Work stayed parked.
        """
        service, base = self.serve()
        response = self.authorize(service, base, grant='write')
        self.assertEqual(response.status, 200)
        rows = {r['connector_id']: r for r in service.settings()['connectors']}
        self.assertEqual(rows[CALENDAR_WRITE_CONNECTOR_ID]['state'], 'connected')
        self.assertEqual(rows[CALENDAR_CONNECTOR_ID]['state'], 'disconnected')

    def test_the_connection_survives_a_paired_telegram_owner(self):
        """Both owner identities, because one process serves both.

        `connector_owner_id` is the paired chat for Telegram Work and the
        local owner for web Work, and the grant is stored under whichever the
        callback resolved. A connection completed here must be the one the
        tool later reads.
        """
        service, base = self.serve()
        service.store.put('telegram', {'enabled': True, 'user_id': 4242})
        self.authorize(service, base)
        rows = {r['connector_id']: r for r in service.settings()['connectors']}
        self.assertEqual(rows[CALENDAR_CONNECTOR_ID]['state'], 'connected')

    def test_the_tool_reads_the_grant_the_callback_committed(self):
        """The per-owner binding, end to end.

        The tool used the Memory owner while the connector used
        `connector_owner_id`, so a Telegram owner could finish the OAuth and
        still be told the calendar was disconnected. Deleting the fix left
        the whole 1109-test suite green, because nothing joined the two
        halves. This is that join.
        """
        service, base = self.serve()
        self.authorize(service, base)
        owner = service.connector_owner_id({})
        connector = service.calendar_for({})
        self.assertIsNotNone(connector)
        # The connector built for this Work's owner sees the committed grant.
        status = service.connector_registry.status(owner, CALENDAR_CONNECTOR_ID)
        self.assertEqual(status.state.value, 'connected')
        # And a Work belonging to the *other* identity does not.
        other = service.connector_owner_id({'chat_id': 4242})
        self.assertNotEqual(other, owner)
        self.assertEqual(
            service.connector_registry.status(other, CALENDAR_CONNECTOR_ID).state.value,
            'disconnected')

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
