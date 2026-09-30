"""FAMILY-02 (#897): a one-page family setup - Telegram install to a working bot.

Evidence class: unit tests and a model-free local HTTP server with an
injected Telegram transport, a fake ngrok process and a fake launchd seam.
No live Telegram, ngrok or launchd operation is observed here.
"""
import io
import json
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from personal_agent import family_setup
from personal_agent.conversation_handoff import TELEGRAM_POLL_UPDATE_KINDS
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart import make_handler
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore

FAMILY_TOKEN = '7000000001:AAFamilyBotTokenValue_abcdefghijklmn'


def telegram_transport(calls, username='spouse_agab12_bot'):
    def transport(url, body=None, headers=None, timeout=None):
        calls.append((url, body))
        if url.endswith('/getMe'):
            return {'ok': True, 'result': {'username': username}}
        if url.endswith('/getWebhookInfo'):
            return {'ok': True, 'result': {'url': ''}}
        if url.endswith('/getUpdates'):
            return {'ok': True, 'result': []}
        raise AssertionError(url)
    return transport


class Names(unittest.TestCase):
    def test_suggested_usernames_are_valid_telegram_bot_usernames(self):
        for name in ('spouse', 'a-very-long-family-member-name', 'x', '---'):
            username = family_setup.suggested_username(name)
            self.assertTrue(family_setup._BOT_USERNAME.match(username), username)
            self.assertLessEqual(len(username), 32)

    def test_the_owner_bot_polls_managed_bot_updates(self):
        self.assertIn('managed_bot', TELEGRAM_POLL_UPDATE_KINDS)

    def test_the_create_link_is_telegrams_managed_bots_deep_link(self):
        self.assertEqual(family_setup.create_link('owner_bot', 'spouse_agab12_bot', '아내 비서'),
                         'https://t.me/newbot/owner_bot/spouse_agab12_bot?name=%EC%95%84%EB%82%B4%20%EB%B9%84%EC%84%9C')

    def test_port_pairs_skip_recorded_and_bound_ports(self):
        self.assertEqual(family_setup.choose_port({8787, 8788, 8797, 8798}, free=lambda port: True), 8799)
        self.assertEqual(family_setup.choose_port(set(), free=lambda port: port != 8797), 8799)


class ManagerBot(unittest.TestCase):
    """The owner's instance hands a family member's new bot to their instance."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.owner = QuickStore(Path(self.temp.name) / 'owner')
        self.family = QuickStore(Path(self.temp.name) / 'family')
        self.record = family_setup.write_setup(self.family, instance='spouse', display_name='아내 비서', owner_bot='owner_bot')
        family_setup.register_pending(self.owner, self.record, 8797)
        self.calls, self.delivered = [], []

    def call(self, method, body):
        self.calls.append((method, body))
        return FAMILY_TOKEN if method == 'getManagedBotToken' else True

    def deliver(self, port, handoff, token):
        self.delivered.append((port, handoff, token))

    def update(self, username=None, bot_id=4242):
        return {'user': {'id': 99, 'is_bot': False}, 'bot': {'id': bot_id, 'is_bot': True, 'username': username or self.record['username']}}

    def test_a_pending_username_is_fetched_restricted_and_handed_over_once(self):
        receipt = family_setup.accept_managed_bot(self.owner, self.call, self.update(), self.deliver)
        self.assertEqual(receipt, {'accepted': True, 'instance': 'spouse'})
        self.assertEqual(self.calls, [('getManagedBotToken', {'user_id': 4242}),
                                      ('setManagedBotAccessSettings', {'user_id': 4242, 'is_access_restricted': True})])
        self.assertEqual(self.delivered, [(8797, self.record['handoff'], FAMILY_TOKEN)])
        self.assertNotIn(FAMILY_TOKEN, json.dumps(receipt) + json.dumps(self.owner.config(family_setup.PENDING_KEY)))
        again = family_setup.accept_managed_bot(self.owner, self.call, self.update(), self.deliver)
        self.assertFalse(again['accepted'], 'a setup is handed over once')

    def test_an_unknown_edited_or_expired_bot_is_ignored_without_any_telegram_call(self):
        for update, now in ((self.update('someone_elses_bot'), None), (self.update(), self.record['expires'] + 1),
                            ({'bot': {'id': 'x', 'username': self.record['username']}}, None), ({}, None)):
            with self.subTest(update=update, now=now):
                self.assertFalse(family_setup.accept_managed_bot(self.owner, self.call, update, self.deliver, now=now)['accepted'])
        self.assertEqual((self.calls, self.delivered), ([], []))

    def test_the_owner_service_ingests_a_managed_bot_update(self):
        service = AgentService(self.owner, ModelAdapter(lambda *a, **k: {}), telegram_transport([]))
        service.telegram.call = self.call
        original = family_setup.deliver_token
        family_setup.deliver_token = self.deliver
        try:
            self.assertEqual(service.ingest_managed_bot(self.update()), {'accepted': True, 'instance': 'spouse'})
            self.assertEqual(len(self.delivered), 1)
            self.assertFalse(service.ingest_managed_bot({'bot': 'broken'})['accepted'])
        finally:
            family_setup.deliver_token = original

    def test_clear_pending_removes_the_row_and_the_handoff_secret(self):
        family_setup.clear_pending(self.owner, 'spouse')
        self.assertEqual(self.owner.config(family_setup.PENDING_KEY), [])
        self.assertEqual(self.owner.secret(family_setup.handoff_secret_key('spouse')), '')


class SetupSurface(unittest.TestCase):
    """The family instance: only the setup paths answer through a tunnel."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(Path(self.temp.name) / 'family')
        self.calls = []
        self.service = AgentService(self.store, ModelAdapter(lambda *a, **k: {}), telegram_transport(self.calls))
        self.record = family_setup.write_setup(self.store, instance='spouse', display_name='아내 비서', owner_bot='owner_bot')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.service))
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def request(self, path, method='GET', body=None, tunneled=False, headers=None):
        headers = dict(headers or {})
        if tunneled:
            headers.update({'X-Forwarded-For': '203.0.113.9', 'X-Forwarded-Proto': 'https'})
        data = json.dumps(body).encode() if body is not None else (b'' if method == 'POST' else None)
        if body is not None:
            headers['Content-Type'] = 'application/json'
        try:
            with urlopen(Request(self.base + path, data=data, method=method, headers=headers), timeout=10) as response:
                return response.status, response.read(), dict(response.headers)
        except HTTPError as error:
            return error.code, error.read(), dict(error.headers)

    def code(self):
        return '?code=' + self.record['code']

    def test_through_the_tunnel_only_the_setup_paths_answer_and_only_with_the_code(self):
        for path in ('/', '/api/status', '/api/settings', '/healthz', '/api/claim'):
            with self.subTest(path=path):
                self.assertEqual(self.request(path, tunneled=True)[0], 404)
        self.assertEqual(self.request('/family-setup?code=wrong', tunneled=True)[0], 404)
        status, body, headers = self.request('/family-setup' + self.code(), tunneled=True)
        self.assertEqual(status, 200)
        self.assertIn('nonce-', headers['Content-Security-Policy'])
        self.assertIn("default-src 'none'", headers['Content-Security-Policy'])
        self.assertIn('아내 비서', body.decode())
        state = json.loads(self.request('/api/family/status' + self.code(), tunneled=True)[1])
        self.assertEqual(state['state'], 'waiting_bot')
        self.assertTrue(state['create_url'].startswith('https://t.me/newbot/owner_bot/'))

    def test_the_token_arrives_over_loopback_with_the_handoff_secret_only(self):
        header = {family_setup.HANDOFF_HEADER: self.record['handoff']}
        self.assertEqual(self.request('/api/family/telegram-token', 'POST', {'token': FAMILY_TOKEN}, tunneled=True, headers=header)[0], 404)
        self.assertEqual(self.request('/api/family/telegram-token', 'POST', {'token': FAMILY_TOKEN},
                                      headers={family_setup.HANDOFF_HEADER: 'wrong'})[0], 404)
        self.assertEqual(self.request('/api/family/telegram-token', 'POST', {'token': FAMILY_TOKEN}, headers=header)[0], 200)
        self.assertEqual(self.store.secret('telegram_token'), FAMILY_TOKEN)
        state = json.loads(self.request('/api/family/status' + self.code(), tunneled=True)[1])
        self.assertEqual(state['state'], 'bot_connected')
        self.assertTrue(state['pair_url'].startswith('https://t.me/spouse_agab12_bot?start='))
        self.assertNotIn(FAMILY_TOKEN, json.dumps(state))

    def test_pairing_closes_the_setup_and_the_tunnel_paths_stop_answering(self):
        cfg = {'enabled': True, 'username': 'spouse_agab12_bot', 'user_id': 555, 'generation': 'g'}
        self.store.put('telegram', cfg)
        state = json.loads(self.request('/api/family/status' + self.code(), tunneled=True)[1])
        self.assertEqual(state['state'], 'paired')
        self.assertIsNone(family_setup.read_setup(self.store))
        self.assertEqual(self.request('/family-setup' + self.code(), tunneled=True)[0], 404)

    def test_an_expired_setup_answers_nothing_and_no_longer_gates(self):
        family_setup._update_setup(self.store, expires=time.time() - 1)
        self.assertEqual(self.request('/family-setup' + self.code(), tunneled=True)[0], 404)
        self.assertNotEqual(self.request('/healthz', tunneled=True)[0], 404, 'without a pending setup the instance behaves as before')


class OwnerCommand(unittest.TestCase):
    """`agentos family add spouse` with fake Telegram, ngrok and launchd."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.owner = QuickStore(self.root / 'owner')
        self.owner.secret('telegram_token', '6000000000:OwnerTokenValue_abcdefghijklmnopq')
        self.owner.put('telegram', {'enabled': True, 'username': 'owner_bot', 'user_id': 111, 'generation': 'g'})
        self.environ = {'HOME': str(self.root / 'home')}
        self.output, self.sent, self.actions = [], [], []
        self.states = iter(['waiting_bot', 'bot_connected', 'paired'])
        self.can_manage = True

    def opener(self, request, timeout=None):
        url = request if isinstance(request, str) else request.full_url
        if url.endswith('/getMe'):
            body = {'ok': True, 'result': {'username': 'owner_bot', 'can_manage_bots': self.can_manage}}
        elif url.endswith('/sendMessage'):
            self.sent.append(json.loads(request.data))
            body = {'ok': True, 'result': {}}
        elif '/api/family/status' in url:
            body = {'state': next(self.states)}
        else:
            raise AssertionError(url)
        return io.BytesIO(json.dumps(body).encode())

    def popen(self, argv, **kwargs):
        self.argv = argv

        class Process:
            stdout = iter([json.dumps({'msg': 'started tunnel', 'url': 'https://abc123.ngrok-free.app'}) + '\n'])
            terminated = False

            def terminate(inner):
                inner.terminated = True
        self.process = Process()
        return self.process

    def service_action(self, action, **options):
        self.actions.append((action, options))
        return {'ok': True, 'background_available': action == 'install', 'status': 'running'}

    def invoke(self, *argv):
        from unittest.mock import patch
        with patch('pathlib.Path.home', return_value=self.root / 'home'):
            return family_setup.family_main(list(argv), service_action=self.service_action, owner_data=self.root / 'owner',
                                            environ=self.environ, opener=self.opener, popen=self.popen,
                                            out=self.output.append, sleep=lambda _s: None, free=lambda port: True)

    def test_one_command_installs_opens_a_link_waits_for_pairing_and_closes_everything(self):
        self.assertEqual(self.invoke('add', 'spouse', '--display-name', '아내 비서'), 0)
        self.assertEqual([action for action, _ in self.actions], ['status', 'install'])
        self.assertEqual(self.actions[-1][1], {'instance': 'spouse', 'port': 8797})
        self.assertEqual(self.argv[:3], ['ngrok', 'http', '127.0.0.1:8797'])
        self.assertIn('--host-header=rewrite', self.argv)
        link = next(line for line in self.output if 'ngrok-free.app/family-setup?code=' in line)
        self.assertIn('아내 비서', link)
        self.assertEqual(self.sent[0]['chat_id'], 111, 'the link also reaches the owner on Telegram to forward')
        self.assertTrue(self.process.terminated)
        self.assertEqual(self.owner.config(family_setup.PENDING_KEY), [])
        family = QuickStore(self.root / 'home/.local/share/agentos-instances/spouse')
        self.assertIsNone(family_setup.read_setup(family), 'the setup is closed afterwards')
        self.assertNotIn('OwnerTokenValue', '\n'.join(map(str, self.output)))

    def test_without_bot_management_mode_nothing_is_created(self):
        self.can_manage = False
        self.assertEqual(self.invoke('add', 'spouse'), 1)
        self.assertIn('Bot Management Mode', self.output[-1])
        self.assertEqual(self.actions, [])
        self.assertFalse((self.root / 'home/.local/share/agentos-instances/spouse').exists())

    def test_an_invalid_name_is_refused(self):
        self.assertEqual(self.invoke('add', 'Not/Valid'), 2)
        self.assertEqual(self.actions, [])


if __name__ == '__main__':
    unittest.main()
