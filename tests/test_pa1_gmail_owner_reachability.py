"""J3/J7 owner reachability for the Gmail route (PA1-INT-01 / #394).

The Gmail connector already composed: the route, the contract and the
exactly-once resume are covered by ``test_quickstart`` and the first-use
acceptance.  What an owner could not do was *reach* any of it - there was no
command to create the credential file, no documentation, and no surface that
ever named ``/google-gmail``.  J3 requires AgentOS to explain the minimum
connection and resume the original request; J7 requires a contextual next
action rather than a dead end.  Both need the owner to actually arrive.

So every test here ends at a surface an owner touches - the CLI, the settings
payload the web management UI renders, the Telegram reply, the HTTP route -
and the two central ones deliberately refuse to use knowledge the owner would
not have.  ``test_the_telegram_handoff_carries_the_address_that_completes_it``
opens only the address it parsed out of the message, and
``test_the_settings_payload_offers_the_route_the_server_answers`` opens only
the path it read out of the payload.  A literal ``/google-gmail`` written into
either of those requests would make them pass while the owner-facing surface
pointed nowhere, which is exactly the gap being closed.
"""
import io
import json
import os
import re
import stat
import tempfile
import threading
import unittest
from http.cookiejar import CookieJar
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler

from cryptography.fernet import Fernet

from personal_agent.connector_contract import CONNECTOR_STATE_KEY, ConnectorState
from personal_agent.decision import OUTCOME_DECIDED, FixtureDecisionEngine, SelectionDecision, fixture_confidence
from personal_agent.gmail import GMAIL_CONNECTOR_ID, GMAIL_READONLY_SCOPE
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart import (configured_service, drive_config_main, gmail_config_main,
                                       make_handler)
from personal_agent.quickstart_service import GMAIL_CONNECT_PATH
from personal_agent.quickstart_store import QuickStore

WEB = Path(__file__).resolve().parents[1] / 'src' / 'personal_agent' / 'web'

#: Any absolute http(s) address in owner-facing text.  The tests below use
#: this instead of building the expected URL, so a message that names no
#: address fails rather than silently being handed one by the test.
URL_IN_TEXT = re.compile(r'https?://[^\s,]+')


class NoRedirect(HTTPRedirectHandler):
    """Never follow a 303, so no test can reach accounts.google.com."""

    def redirect_request(self, *args, **kwargs):
        return None


def opener(*handlers):
    return build_opener(NoRedirect(), *handlers)


def gmail_transport(method, endpoint, params, headers):
    """A fixture Gmail API, so no live Google call is ever made or claimed."""
    if endpoint.endswith('/messages'):
        return {'messages': [{'id': 'm_1', 'threadId': 't_1'}]}
    return {'id': 'm_1', 'threadId': 't_1', 'payload': {'headers': [
        {'name': 'Subject', 'value': '예산 승인 안내'},
        {'name': 'From', 'value': 'Finance <finance@example.test>'},
        {'name': 'Date', 'value': 'Mon, 1 Sep 2026 10:00:00 +0000'}]}}


def write_client_json(directory, client_id='web-client-id', client_secret='web-client-secret',
                      section='web'):
    """A downloaded Google OAuth client file, as the owner would have it."""
    path = os.path.join(directory, 'client_secret.json')
    with open(path, 'w') as output:
        json.dump({section: {'client_id': client_id, 'client_secret': client_secret,
                             'redirect_uris': ['http://localhost:8787/oauth/gmail/callback']}},
                  output)
    return path


class GmailConfigCommandTest(unittest.TestCase):
    """``agentos gmail-config``: the missing owner entry point.

    The claim under test is not "a file appears".  It is that the file this
    command writes is one the shipped service loads and then successfully
    uses - the Fernet key it generated really decrypts the stored token, and
    the client secret it stored is really the one sent to the token endpoint.
    """

    CLIENT_SECRET = 'never-print-this-gmail-secret'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.external = tempfile.TemporaryDirectory(); self.addCleanup(self.external.cleanup)
        self.store = QuickStore(self.temp.name)
        self.secret_file = os.path.join(self.external.name, 'nested', 'gmail.json')

    def run_config(self, argv):
        """Run the subcommand, returning its stdout, never a credential."""
        stdout = io.StringIO()
        with patch('sys.stdout', stdout):
            gmail_config_main(argv)
        return stdout.getvalue()

    def create(self, client_secret=None):
        source = write_client_json(self.external.name,
                                   client_secret=client_secret or self.CLIENT_SECRET)
        printed = self.run_config(['--oauth-client-json', source, '--secret-file', self.secret_file])
        return source, printed

    # -- the round trip ---------------------------------------------------
    def test_the_cli_writes_a_file_the_service_actually_loads_and_uses(self):
        _source, printed = self.create()
        self.assertIn('Created owner-only local Gmail credential file.', printed)
        # Nothing secret is ever printed.
        self.assertNotIn(self.CLIENT_SECRET, printed)

        written = json.loads(Path(self.secret_file).read_text())
        self.assertEqual(sorted(written), ['client_id', 'client_secret', 'encryption_key'])
        self.assertEqual(written['client_id'], 'web-client-id')
        self.assertEqual(written['client_secret'], self.CLIENT_SECRET)
        # No Picker key: Gmail has no browser-visible key to leak, and the
        # loader would reject an extra required value it cannot find.
        self.assertNotIn('picker_api_key', written)
        self.assertEqual(stat.S_IMODE(os.stat(self.secret_file).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(self.secret_file)).st_mode), 0o700)

        # The service the shipped entry point builds accepts exactly this
        # file, with no environment credential of any kind.
        service = configured_service(self.store, {'AGENTOS_GMAIL_LOCAL_ONLY': '1',
                                                  'AGENTOS_GMAIL_SECRET_FILE': self.secret_file})
        self.assertIsNotNone(service.gmail)
        self.assertEqual(service.gmail.client_id, 'web-client-id')
        self.assertNotIn(self.CLIENT_SECRET, json.dumps(service.settings()))

        # The generated Fernet key is a *working* key rather than a string the
        # loader merely accepted: a complete authorization is committed with
        # it and a Gmail read then succeeds, which requires the stored token
        # to encrypt and decrypt through exactly the key the CLI generated.
        service.gmail.transport = gmail_transport
        service.gmail_token_exchange = lambda payload: {
            'access_token': 'fixture-access', 'refresh_token': 'fixture-refresh',
            'expires_in': 3600, 'scope': GMAIL_READONLY_SCOPE}
        url = service.begin_gmail_connection()['authorization_url']
        state = parse_qs(urlsplit(url).query)['state'][0]
        service.complete_gmail_connection({'code': 'fixture-code', 'state': state})
        owner = service.connector_callback_owner(GMAIL_CONNECTOR_ID)
        self.assertEqual(service.connector_registry.status(owner, GMAIL_CONNECTOR_ID).state,
                         ConnectorState.CONNECTED)
        self.assertEqual([row.subject for row in service.gmail.search(owner, '예산')],
                         ['예산 승인 안내'])

        # The client secret in the file is the value actually sent to Google's
        # token endpoint - it reaches it from the file, not the environment.
        posted = []
        class Response:
            def __enter__(inner): return inner
            def __exit__(inner, *args): return False
            def read(inner): return b'{"access_token":"fixture"}'
        def fake_urlopen(request, timeout=None):
            posted.append(request.data.decode()); return Response()
        fresh = configured_service(QuickStore(tempfile.mkdtemp()),
                                   {'AGENTOS_GMAIL_LOCAL_ONLY': '1',
                                    'AGENTOS_GMAIL_SECRET_FILE': self.secret_file})
        with patch('personal_agent.quickstart.urlopen', fake_urlopen):
            fresh.gmail_token_exchange({'code': 'fixture-code'})
        self.assertIn('client_secret=' + self.CLIENT_SECRET, posted[0])

    def test_the_written_file_still_has_to_pass_the_owner_only_boundary(self):
        """The command does not exempt its own output from the loader."""
        self.create()
        os.chmod(self.secret_file, 0o644)
        with self.assertRaisesRegex(ValueError, 'owner-only regular JSON file'):
            configured_service(self.store, {'AGENTOS_GMAIL_LOCAL_ONLY': '1',
                                            'AGENTOS_GMAIL_SECRET_FILE': self.secret_file})

    def test_the_cli_refuses_a_relative_secret_file(self):
        source = write_client_json(self.external.name)
        with self.assertRaises(SystemExit):
            self.run_config(['--oauth-client-json', source, '--secret-file', 'gmail.json'])
        self.assertFalse(os.path.exists(os.path.join(os.getcwd(), 'gmail.json')))

    def test_the_cli_refuses_to_replace_an_existing_secret_file(self):
        source, _printed = self.create()
        before = Path(self.secret_file).read_text()
        stderr = io.StringIO()
        with patch('sys.stderr', stderr), self.assertRaises(SystemExit):
            self.run_config(['--oauth-client-json', source, '--secret-file', self.secret_file])
        # The explicit refusal, not only the O_EXCL backstop underneath it:
        # an owner who re-runs the command must be told the existing
        # credential was kept rather than shown a raw errno.
        self.assertIn('Refusing to replace an existing Gmail secret file', stderr.getvalue())
        self.assertEqual(Path(self.secret_file).read_text(), before)

    def test_the_cli_refuses_a_json_that_is_not_a_google_web_client(self):
        installed = write_client_json(self.external.name, section='installed')
        with self.assertRaises(SystemExit):
            self.run_config(['--oauth-client-json', installed, '--secret-file', self.secret_file])
        self.assertFalse(os.path.exists(self.secret_file))


class DriveConfigUnchangedTest(unittest.TestCase):
    """The shared writer must not have weakened or reordered ``drive-config``.

    ``gmail-config`` reuses Drive's path check, client reader and 0600
    exclusive create.  Sharing them is only safe if Drive still behaves
    exactly as it did, including *when* it refuses - a refactor that moved the
    absolute-path check after the Picker prompt would prompt the owner for a
    restricted API key before rejecting the path they typed.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.external = tempfile.TemporaryDirectory(); self.addCleanup(self.external.cleanup)
        self.store = QuickStore(self.temp.name)

    def test_drive_config_still_writes_the_picker_key_and_loads_back(self):
        source = write_client_json(self.external.name, client_id='drive-client',
                                   client_secret='drive-secret')
        target = os.path.join(self.external.name, 'drive.json')
        with patch('sys.stdin', io.StringIO('restricted-picker-key\n')), patch('sys.stdout', io.StringIO()):
            drive_config_main(['--oauth-client-json', source, '--secret-file', target,
                               '--picker-key-stdin'])
        written = json.loads(Path(target).read_text())
        self.assertEqual(sorted(written),
                         ['client_id', 'client_secret', 'encryption_key', 'picker_api_key'])
        self.assertEqual(written['picker_api_key'], 'restricted-picker-key')
        self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o600)
        service = configured_service(self.store, {'AGENTOS_DRIVE_LOCAL_ONLY': '1',
                                                  'AGENTOS_DRIVE_SECRET_FILE': target})
        self.assertIsNotNone(service.drive_web_oauth)
        self.assertEqual(service.drive_picker_config['developer_key'], 'restricted-picker-key')

    def test_drive_config_refuses_a_relative_path_before_reading_the_picker_key(self):
        source = write_client_json(self.external.name)
        stdin = io.StringIO('restricted-picker-key\n')
        with patch('sys.stdin', stdin), patch('sys.stdout', io.StringIO()):
            with self.assertRaises(SystemExit):
                drive_config_main(['--oauth-client-json', source, '--secret-file', 'drive.json',
                                   '--picker-key-stdin'])
        # Nothing was read from standard input, so the owner was never asked
        # for a restricted key that was about to be thrown away.
        self.assertEqual(stdin.tell(), 0)

    def test_drive_config_still_requires_a_picker_key(self):
        source = write_client_json(self.external.name)
        target = os.path.join(self.external.name, 'drive.json')
        with patch('sys.stdin', io.StringIO('   \n')), patch('sys.stdout', io.StringIO()):
            with self.assertRaises(SystemExit):
                drive_config_main(['--oauth-client-json', source, '--secret-file', target,
                                   '--picker-key-stdin'])
        self.assertFalse(os.path.exists(target))


class GmailRouteReachabilityTest(unittest.TestCase):
    """The owner-facing surfaces that now name the Gmail start route."""

    CHAT = 987654
    OWNER = f'telegram:{CHAT}'
    GENERATION = 'reachability-generation'
    MAIL_REQUEST = '메일에서 예산 관련 내용 찾아줘'
    CLIENT_SECRET = 'never-return-this-gmail-secret'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(self.temp.name)
        self.sent = []
        self.exchanges = []
        self.gmail_calls = []
        self.keys = iter(range(1000))
        self.store.put('telegram', {'enabled': True, 'mode': 'owner-token', 'username': 'ownerbot',
                                    'generation': self.GENERATION, 'cursor': 0, 'user_id': self.CHAT})

    # -- fixtures ---------------------------------------------------------
    def telegram(self, url, body, headers=None, timeout=60):
        if url.endswith('/sendMessage') or url.endswith('/editMessageText'):
            self.sent.append(body)
            return {'ok': True, 'result': {'message_id': len(self.sent)}}
        raise AssertionError('unexpected outbound call: ' + url)

    def gmail_transport(self, method, endpoint, params, headers):
        self.gmail_calls.append((method, endpoint))
        return gmail_transport(method, endpoint, params, headers)

    def exchange(self, request):
        self.exchanges.append(dict(request))
        return {'access_token': 'fixture-access', 'refresh_token': 'fixture-refresh',
                'expires_in': 3600, 'scope': GMAIL_READONLY_SCOPE}

    def serve(self, public_hosts=(), configure_gmail=True):
        """Bind first, then build the service against the port actually bound.

        The address the owner is given has to be the address that answers, so
        this test cannot configure a guessed port and serve on a different
        one.  The listener is bound before the service exists and the handler
        is attached afterwards, which is the only way the redirect URI, the
        guidance URL and the live server can all agree.
        """
        server = ThreadingHTTPServer(('127.0.0.1', 0), BaseHTTPRequestHandler,
                                     bind_and_activate=False)
        server.server_bind()
        try:
            server.server_activate()
        except Exception:
            server.server_close(); raise
        port = server.server_port
        env = {}
        if configure_gmail:
            env = {'AGENTOS_GMAIL_LOCAL_ONLY': '1', 'AGENTOS_GMAIL_CLIENT_ID': 'gmail-client',
                   'AGENTOS_GMAIL_CLIENT_SECRET': self.CLIENT_SECRET,
                   'AGENTOS_GMAIL_LOCAL_PORT': str(port),
                   'AGENTOS_GMAIL_ENCRYPTION_KEY': Fernet.generate_key().decode()}
        service = configured_service(self.store, env)
        service.use_decision_engine(FixtureDecisionEngine(choose=lambda context,candidates,question:
            SelectionDecision(OUTCOME_DECIDED,'none-of-these',candidates,fixture_confidence())
            if context.purpose == 'unsupported-capability' else None))
        service.telegram_transport = self.telegram
        service.adapter = ModelAdapter(self.telegram)
        if service.gmail is not None:
            service.gmail.transport = self.gmail_transport
            service.gmail_token_exchange = self.exchange
        server.RequestHandlerClass = make_handler(service, public_hosts, 'pairing-token')
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        def shutdown():
            server.shutdown(); thread.join(); server.server_close()
        self.addCleanup(shutdown)
        return service, f'http://127.0.0.1:{port}'

    def login(self, base):
        self.store.claim(self.store.bootstrap.read_text(), 'long-password-test')
        client = opener(HTTPCookieProcessor(CookieJar()))
        client.open(Request(base + '/api/login',
                            data=json.dumps({'password': 'long-password-test'}).encode(),
                            headers={'Content-Type': 'application/json'}), timeout=3).read()
        return client

    def session_headers(self):
        """A real owner session as a header, not through a cookie jar.

        When a public tunnel host is configured the server marks the session
        cookie `Secure`, and an `http://` cookie jar correctly refuses to
        store it.  That would make these tests observe 401 - the session
        check - and never reach the tunnel-host refusal they exist to hold.
        The token still comes from `QuickStore`, so the session is genuine.
        """
        return {'Cookie': 'agentos_session=' + self.store.local_session()}

    def enqueue(self, message):
        return self.store.enqueue(message, f'reach-{next(self.keys)}',
                                  channel=f'telegram:{self.GENERATION}', chat_id=self.CHAT)

    # -- the web management surface ---------------------------------------
    def test_the_settings_payload_offers_the_route_the_server_answers(self):
        service, base = self.serve()
        rows = service.settings()['connectors']
        row = next(item for item in rows if item['connector_id'] == GMAIL_CONNECTOR_ID)
        self.assertEqual(row['state'], ConnectorState.DISCONNECTED.value)
        self.assertEqual(row['required_scopes'], [GMAIL_READONLY_SCOPE])
        self.assertTrue(row['connect_path'])
        # Relative on purpose: the session cookie is SameSite=Strict and
        # host-scoped, so an absolute `localhost` form would drop the session
        # of an owner who opened AgentOS at 127.0.0.1.
        self.assertTrue(row['connect_path'].startswith('/'))
        self.assertIsNone(urlsplit(row['connect_path']).netloc or None)

        # Follow only the path the payload offered.  No credential is exposed
        # by the surface that offered it.
        self.assertNotIn(self.CLIENT_SECRET, json.dumps(rows))
        client = self.login(base)
        with self.assertRaises(HTTPError) as redirect:
            client.open(base + row['connect_path'], timeout=3)
        self.assertEqual(redirect.exception.code, 303)
        location = redirect.exception.headers['Location']
        self.assertTrue(location.startswith('https://accounts.google.com/'))
        self.assertEqual(parse_qs(urlsplit(location).query)['scope'], [GMAIL_READONLY_SCOPE])

        # Reading the state and being offered the link granted nothing.
        self.assertEqual(service.connector_registry.status(self.OWNER, GMAIL_CONNECTOR_ID).state,
                         ConnectorState.DISCONNECTED)
        self.assertIsNone(self.store.config(CONNECTOR_STATE_KEY, None))

    def test_an_installation_without_gmail_offers_no_connection(self):
        service, _base = self.serve(configure_gmail=False)
        self.assertEqual(service.settings()['connectors'], [])
        self.assertEqual(service.connector_connect_url(GMAIL_CONNECTOR_ID), '')

    def test_the_documented_address_is_the_one_the_route_answers(self):
        """QUICKSTART is the only place an owner learns this before connecting.

        The route path and the settings payload share one constant, so a
        rename keeps them agreeing with each other while silently orphaning
        the documentation an owner reads first.  This is the assertion that
        notices.
        """
        quickstart = (Path(__file__).resolve().parents[1] / 'QUICKSTART.md').read_text()
        self.assertIn('\nagentos gmail-config \\\n', quickstart)
        # The documented name must be the name the CLI actually dispatches.
        dispatcher = (Path(__file__).resolve().parents[1]
                      / 'src' / 'personal_agent' / 'quickstart.py').read_text()
        self.assertIn("sys.argv[1]=='gmail-config'", dispatcher)
        self.assertIn(f'http://127.0.0.1:8787{GMAIL_CONNECT_PATH}', quickstart)
        # The documented host is the one AgentOS advertises for itself, which
        # is the host the owner's session cookie is scoped to.
        service, _base = self.serve()
        self.assertTrue(service.connector_connect_url(GMAIL_CONNECTOR_ID)
                        .startswith('http://127.0.0.1:'))

    def test_the_web_ui_renders_the_offered_path_as_a_same_origin_navigation(self):
        html = (WEB / 'index.html').read_text()
        script = (WEB / 'app.js').read_text()
        self.assertIn('id="connector-controls"', html)
        # The renderer is wired to the payload key the service actually emits.
        self.assertIn('renderConnectors(settings.connectors)', script)
        self.assertIn('connector.connect_path', script)
        self.assertIn('link.href=connector.connect_path', script)
        # An <a> navigation, not api()/fetch: /google-gmail answers 303 to
        # Google, which a cross-origin fetch would follow and discard.
        renderer = script.split('function renderConnectors(')[1].split('\nfunction ')[0]
        self.assertNotIn('api(', renderer)
        self.assertNotIn('fetch(', renderer)

    # -- the Telegram surface ---------------------------------------------
    def test_the_telegram_handoff_carries_the_address_that_completes_it(self):
        service, _base = self.serve()
        job_id = self.enqueue(self.MAIL_REQUEST)
        self.assertTrue(service.run_one())
        job = self.store.job(job_id)
        self.assertEqual(job['status'], 'awaiting_connection')
        message = job['response']
        self.assertIn('연결이 아직 없어', message)

        # The owner is told an address, not just a requirement.  Everything
        # below uses only what the message contained.
        found = URL_IN_TEXT.findall(message)
        self.assertEqual(len(found), 1, f'expected exactly one address in: {message}')
        address = found[0]
        self.assertEqual(urlsplit(address).path, GMAIL_CONNECT_PATH)

        client = self.login(f'http://127.0.0.1:{urlsplit(address).port}')
        with self.assertRaises(HTTPError) as redirect:
            client.open(address, timeout=3)
        self.assertEqual(redirect.exception.code, 303)
        location = redirect.exception.headers['Location']
        self.assertTrue(location.startswith('https://accounts.google.com/'))
        self.assertNotIn(self.CLIENT_SECRET, location)

        # J3 end to end: the parked request resumes after the owner-controlled
        # authorization completes, exactly once.
        state = parse_qs(urlsplit(location).query)['state'][0]
        callback = (f'http://127.0.0.1:{urlsplit(address).port}/oauth/gmail/callback'
                    f'?code=fixture-code&state={state}')
        with build_opener().open(callback, timeout=3) as response:
            self.assertEqual(response.status, 200)
        self.assertEqual(self.store.job(job_id)['status'], 'queued')
        self.assertTrue(service.run_one())
        self.assertEqual(self.store.job(job_id)['status'], 'succeeded')
        self.assertIn('예산 승인 안내', self.store.job(job_id)['response'])

    def test_an_unreachable_installation_still_names_no_address(self):
        """Guidance never invents a link it cannot honour.

        This is the mutation guard for the URL being *derived*: a hard-coded
        default address would still be appended here, where the installation
        offers no Gmail route at all.
        """
        from personal_agent.conversation_handoff import ConnectorHandoff
        from personal_agent.connector_contract import (ConnectorResult, ConnectorResultKind,
                                                       RecoveryAction)
        result = ConnectorResult(ConnectorResultKind.CONNECTION_REQUIRED, GMAIL_CONNECTOR_ID,
                                 (GMAIL_READONLY_SCOPE,), RecoveryAction.CONNECT)
        self.assertEqual(URL_IN_TEXT.findall(ConnectorHandoff.guidance(result)), [])
        blocked = ConnectorResult(ConnectorResultKind.BLOCKED, GMAIL_CONNECTOR_ID,
                                  (GMAIL_READONLY_SCOPE,), RecoveryAction.CONNECT)
        # BLOCKED's next action is reviewing access, not opening a consent
        # screen, so it is not given one even when a route exists.
        self.assertEqual(
            URL_IN_TEXT.findall(ConnectorHandoff.guidance(blocked, 'http://localhost:1/x')), [])

    # -- the refusals the link must not have loosened ---------------------
    def test_the_start_route_still_requires_the_owner_session(self):
        service, base = self.serve()
        path = service.settings()['connectors'][0]['connect_path']
        with self.assertRaises(HTTPError) as error:
            build_opener().open(base + path, timeout=3)
        self.assertEqual(error.exception.code, 401)
        self.assertIsNone(self.store.config(CONNECTOR_STATE_KEY, None))

    def test_the_start_route_still_refuses_a_public_tunnel_host(self):
        service, base = self.serve(public_hosts=('mobile.example.test',))
        path = service.settings()['connectors'][0]['connect_path']
        headers = {**self.session_headers(), 'Host': 'mobile.example.test'}
        # A genuine owner session is supplied, so the 400 below is the tunnel
        # refusal and not the session check answering first.
        with self.assertRaises(HTTPError) as error:
            opener().open(Request(base + path, headers=headers), timeout=3)
        self.assertEqual(error.exception.code, 400)
        self.assertIsNone(self.store.config(CONNECTOR_STATE_KEY, None))
        # The same session from the local address is accepted, which is what
        # makes the refusal above about the host rather than the credential.
        with self.assertRaises(HTTPError) as redirect:
            opener().open(Request(base + path, headers=self.session_headers()), timeout=3)
        self.assertEqual(redirect.exception.code, 303)

    def test_the_callback_still_answers_one_identical_400_for_every_failure(self):
        """No new surface may let a caller distinguish callback failures."""
        service, base = self.serve(public_hosts=('mobile.example.test',))
        with self.assertRaises(HTTPError) as redirect:
            opener().open(Request(base + GMAIL_CONNECT_PATH,
                                  headers=self.session_headers()), timeout=3)
        state = parse_qs(urlsplit(redirect.exception.headers['Location']).query)['state'][0]
        bodies = []
        for request in (
            Request(base + '/oauth/gmail/callback?code=c&state=' + state,
                    headers={'Host': 'mobile.example.test'}),
            Request(base + '/oauth/gmail/callback?code=c&state=forged-state'),
            Request(base + '/oauth/gmail/callback?error=access_denied&state=' + state),
            Request(base + '/oauth/gmail/callback'),
        ):
            with self.assertRaises(HTTPError) as error:
                build_opener().open(request, timeout=3)
            self.assertEqual(error.exception.code, 400)
            bodies.append(error.exception.read())
        self.assertEqual(len(set(bodies)), 1, 'callback failures became distinguishable')


if __name__ == '__main__':
    unittest.main()
