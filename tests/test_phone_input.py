"""PHONE-INPUT-01 (#1213): a one-time phone link for the own Google client and Google consent.

Model-free and network-free: a fake ngrok, a fake Telegram, an injected token
exchange, and a real local HTTP server in-process.  Tunneled requests are
simulated with proxy forwarding headers, as in ``test_remote_login``.
"""
import json
import pathlib
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

from cryptography.fernet import Fernet

from personal_agent import phone_input
from personal_agent.google_drive_read import DRIVE_CONNECTOR_ID, DRIVE_READONLY_SCOPE
from personal_agent.quickstart import configured_service, make_handler
from personal_agent.quickstart_service import DRIVE_CALLBACK_PATH
from personal_agent.quickstart_store import QuickStore

CHAT = 4242
CLIENT = json.dumps({'installed': {'client_id': '123-abcdefgh.apps.googleusercontent.com', 'client_secret': 'phone-secret'}})


class FakeTunnel:
    def __init__(self):
        self.processes = []

    def __call__(self, argv, **kwargs):
        class Process:
            stdout = iter([json.dumps({'msg': 'started tunnel', 'url': 'https://abc123.ngrok-free.app'}) + '\n'])
            terminated = False

            def terminate(inner):
                inner.terminated = True
        process = Process()
        self.processes.append(process)
        return process


class CallbackParamsTest(unittest.TestCase):
    REDIRECT = 'http://127.0.0.1:8787' + DRIVE_CALLBACK_PATH

    def test_the_loopback_callback_of_the_service_is_accepted(self):
        pasted = f'http://127.0.0.1:8787{DRIVE_CALLBACK_PATH}?state=drive.abc.def&code=4/xyz&scope=x'
        self.assertEqual(phone_input.callback_params(pasted, self.REDIRECT), {'state': 'drive.abc.def', 'code': '4/xyz'})
        denied = f'http://localhost:8787{DRIVE_CALLBACK_PATH}?state=s&error=access_denied'
        self.assertEqual(phone_input.callback_params(denied, self.REDIRECT), {'state': 's', 'error': 'access_denied'})

    def test_anything_else_is_refused(self):
        for pasted in (f'https://127.0.0.1:8787{DRIVE_CALLBACK_PATH}?state=s&code=c',
                       f'http://evil.test{DRIVE_CALLBACK_PATH}?state=s&code=c',
                       'http://127.0.0.1:8787/oauth/gmail/callback?state=s&code=c',
                       f'http://127.0.0.1:8787{DRIVE_CALLBACK_PATH}?code=c',
                       f'http://127.0.0.1:8787{DRIVE_CALLBACK_PATH}?state=s',
                       f'http://127.0.0.1:8787{DRIVE_CALLBACK_PATH}?state=a&state=b&code=c',
                       f'http://u:p@127.0.0.1:8787{DRIVE_CALLBACK_PATH}?state=s&code=c',
                       'x' * 9000, 7, ''):
            self.assertIsNone(phone_input.callback_params(pasted, self.REDIRECT), pasted)


class SessionTest(unittest.TestCase):
    def test_binding_code_and_expiry(self):
        clock = [1000.0]
        tunnel = FakeTunnel()
        session = phone_input.PhoneInput(phone_input.GOOGLE_CLIENT, '자체 Google client', popen=tunnel, clock=lambda: clock[0])
        link = session.start(8787)
        self.assertTrue(link.startswith('https://abc123.ngrok-free.app/phone-input?code='))
        self.assertTrue(session.code_ok(session.code))
        self.assertFalse(session.code_ok('wrong'))
        issued = session.open_page('')
        self.assertTrue(issued)
        self.assertTrue(session.client_ok(issued))
        self.assertFalse(session.client_ok('other'))
        self.assertIs(session.open_page('other'), False)
        clock[0] += phone_input.SESSION_SECONDS + 1
        self.assertFalse(session.code_ok(session.code))
        session.finish('expired')
        self.assertTrue(tunnel.processes[0].terminated)


class PhoneInputServiceCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = QuickStore(str(pathlib.Path(temp.name) / 'data'))
        self.service = configured_service(self.store, {'AGENTOS_GOOGLE_LOCAL_PORT': '8787',
                                                       'AGENTOS_GOOGLE_OAUTH_KEY': Fernet.generate_key().decode()})
        self.calls = []
        self.service.telegram.call = lambda method, body: self.calls.append((method, body)) or {'message_id': 1}
        self.service.telegram.send_message = lambda chat, text: self.calls.append(('notice', text))
        self.tunnel = FakeTunnel()
        self.service.phone_input_popen = self.tunnel
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.service))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.end_session)
        self.service.local_server_port = self.server.server_port
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def end_session(self):
        session = self.service.phone_input_session()
        if session is not None:
            session.finish('closed')

    def pair(self):
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': 'g1', 'cursor': 0})

    def request(self, path, method='GET', body=None, tunneled=True, cookie=None):
        headers = {}
        if tunneled:
            headers.update({'X-Forwarded-For': '203.0.113.9', 'X-Forwarded-Proto': 'https'})
        if cookie:
            headers['Cookie'] = f'{phone_input.COOKIE_NAME}={cookie}'
        data = json.dumps(body).encode() if body is not None else None
        if body is not None:
            headers['Content-Type'] = 'application/json'
        try:
            with urlopen(Request(self.base + path, data=data, method=method, headers=headers), timeout=10) as response:
                return response.status, response.read(), dict(response.headers)
        except HTTPError as error:
            return error.code, error.read(), dict(error.headers)

    def open_page(self, session):
        status, _body, headers = self.request(f'{phone_input.PAGE_PATH}?code={session.code}')
        self.assertEqual(status, 200)
        cookie = headers['Set-Cookie'].split(';')[0].split('=', 1)[1]
        return cookie

    def assistant_rows(self):
        with self.store.db() as db:
            return [row['content'] for row in db.execute("SELECT content FROM messages WHERE role='assistant'")]


class StartTest(PhoneInputServiceCase):
    def test_the_link_needs_a_paired_telegram_chat(self):
        with self.assertRaises(ValueError):
            self.service.start_phone_input(phone_input.GOOGLE_CLIENT)
        self.assertEqual(self.tunnel.processes, [])

    def test_the_link_goes_to_the_paired_chat_only_and_one_at_a_time(self):
        self.pair()
        answer = self.service.start_phone_input(phone_input.GOOGLE_CLIENT)
        self.assertIn('Telegram으로 보냈어요', answer)
        sent = [body for method, body in self.calls if method == 'sendMessage']
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]['chat_id'], CHAT)
        self.assertIn('https://abc123.ngrok-free.app/phone-input?code=', sent[0]['text'])
        with self.assertRaises(ValueError):
            self.service.start_phone_input(phone_input.GOOGLE_CLIENT)

    def test_a_link_that_was_not_delivered_stops_the_tunnel(self):
        self.pair()

        def broken(method, body):
            raise RuntimeError('telegram down')
        self.service.telegram.call = broken
        with self.assertRaises(ValueError):
            self.service.start_phone_input(phone_input.GOOGLE_CLIENT)
        self.assertTrue(self.tunnel.processes[0].terminated)
        self.assertIsNone(self.service.phone_input_session())

    def test_an_unoffered_kind_is_refused(self):
        self.pair()
        with self.assertRaises(ValueError):
            self.service.start_phone_input(DRIVE_CONNECTOR_ID)  # no own client yet: no Drive connector
        with self.assertRaises(ValueError):
            self.service.start_phone_input('anything')


class GateTest(PhoneInputServiceCase):
    def test_once_started_a_tunnel_reaches_only_the_phone_paths(self):
        self.pair()
        self.assertNotEqual(self.request('/api/status')[0], 404, 'before any session the gate is open as today')
        self.service.start_phone_input(phone_input.GOOGLE_CLIENT)
        self.assertEqual(self.request('/api/status')[0], 404)
        self.assertEqual(self.request('/google-drive-connect')[0], 404)
        self.assertNotEqual(self.request('/api/status', tunneled=False)[0], 404, 'this Mac itself is unaffected')

    def test_a_wrong_code_or_another_client_gets_404(self):
        self.pair()
        self.service.start_phone_input(phone_input.GOOGLE_CLIENT)
        session = self.service.phone_input_session()
        self.assertEqual(self.request(f'{phone_input.PAGE_PATH}?code=wrong')[0], 404)
        cookie = self.open_page(session)
        status, _body, _ = self.request(f'{phone_input.CLIENT_PATH}?code={session.code}', 'POST',
                                        {'client_json': 'x'}, cookie='other')
        self.assertEqual(status, 404)
        status, _body, _ = self.request(f'{phone_input.CLIENT_PATH}?code={session.code}', 'POST',
                                        {'client_json': 'x'}, cookie=cookie)
        self.assertEqual(status, 400, 'the bound client reaches the API; a malformed client is refused')


class FlowTest(PhoneInputServiceCase):
    def test_the_own_client_is_saved_from_the_phone_and_the_conversation_is_told(self):
        self.pair()
        self.service.start_phone_input(phone_input.GOOGLE_CLIENT)
        session = self.service.phone_input_session()
        cookie = self.open_page(session)
        status, body, _ = self.request(f'{phone_input.CLIENT_PATH}?code={session.code}', 'POST',
                                       {'client_json': CLIENT}, cookie=cookie)
        self.assertEqual((status, json.loads(body)), (200, {'ok': True}))
        self.assertEqual(self.service.google_client_status()['source'], 'settings')
        self.assertTrue(any(row.startswith('휴대폰 링크에서 자체 Google client') for row in self.assistant_rows()))
        self.assertNotIn('phone-secret', json.dumps(self.assistant_rows()))
        session._ended.wait(2)
        self.assertFalse(session.alive())
        self.assertTrue(self.tunnel.processes[0].terminated)

    def test_a_google_service_is_connected_from_the_phone_by_pasting_the_callback(self):
        self.pair()
        self.service.save_google_client({'client_json': CLIENT})
        self.service.drive_read_token_exchange = lambda payload: {
            'access_token': 'a', 'expires_in': 3600, 'refresh_token': 'r', 'scope': DRIVE_READONLY_SCOPE}
        self.service.start_phone_input(DRIVE_CONNECTOR_ID)
        session = self.service.phone_input_session()
        cookie = self.open_page(session)
        status, body, _ = self.request(f'{phone_input.START_PATH}?code={session.code}', 'POST', {}, cookie=cookie)
        self.assertEqual(status, 200)
        consent = urlsplit(json.loads(body)['authorization_url'])
        self.assertEqual(consent.hostname, 'accounts.google.com')
        query = parse_qs(consent.query)
        redirect, state = query['redirect_uri'][0], query['state'][0]
        # A wrong address is refused and connects nothing.
        status, _body, _ = self.request(f'{phone_input.FINISH_PATH}?code={session.code}', 'POST',
                                        {'url': 'http://127.0.0.1:1/oauth/gmail/callback?state=x&code=y'}, cookie=cookie)
        self.assertEqual(status, 400)
        pasted = redirect + '?' + urlencode({'state': state, 'code': 'phone-code', 'scope': DRIVE_READONLY_SCOPE})
        status, body, _ = self.request(f'{phone_input.FINISH_PATH}?code={session.code}', 'POST', {'url': pasted}, cookie=cookie)
        self.assertEqual((status, json.loads(body)), (200, {'ok': True}))
        self.assertEqual(self.service.drive_oauth.status(self.service.connector_callback_owner(DRIVE_CONNECTOR_ID))['state'],
                         'connected')
        self.assertTrue(any('Google Drive 연결이 완료되었습니다' in row for row in self.assistant_rows()))

    def test_the_conversation_can_request_the_link_through_a_confirmed_draft(self):
        self.pair()
        read = self.service.conversation_settings_request({'operation': 'read', 'category': 'phone_link'})
        options = [option['value'] for option in read['settings']['phone_link']['send']['options']]
        self.assertEqual(options, [phone_input.GOOGLE_CLIENT])
        draft = self.service.settings_orchestrator.propose('local-owner', 'web', 'phone_link', 'send', phone_input.GOOGLE_CLIENT)
        self.assertIn('휴대폰으로', draft['response'])
        self.assertIsNone(self.service.phone_input_session(), 'a draft opens nothing')
        result = self.service.settings_orchestrator.confirm('local-owner', 'web', draft['draft_id'], draft['digest'])
        self.assertIn('Telegram으로 보냈어요', result['response'])
        self.assertIsNotNone(self.service.phone_input_session())
        self.assertEqual([body['chat_id'] for method, body in self.calls if method == 'sendMessage'], [CHAT])


if __name__ == '__main__':
    unittest.main()


class ReviewFollowupTest(PhoneInputServiceCase):
    def test_the_consent_address_is_a_link_to_tap_not_a_popup(self):
        session = phone_input.PhoneInput(DRIVE_CONNECTOR_ID, 'Google Drive 연결')
        page = phone_input.page(session, 'n')
        self.assertIn('id="consent"', page)
        self.assertNotIn('window.open', page)

    def test_an_unexpected_failure_still_answers_the_phone(self):
        self.pair()
        self.service.start_phone_input(phone_input.GOOGLE_CLIENT)
        session = self.service.phone_input_session()
        cookie = self.open_page(session)

        def boom(session, body):
            raise OSError('token endpoint unreachable')
        self.service.phone_input_client = boom
        status, body, _ = self.request(f'{phone_input.CLIENT_PATH}?code={session.code}', 'POST', {'client_json': 'x'},
                                       cookie=cookie)
        self.assertEqual(status, 502)
        self.assertNotIn('unreachable', body.decode())
