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

    def deliver(self, port, handoff, token, creator_id=None):
        if getattr(self, 'fail_deliveries', 0):
            self.fail_deliveries -= 1
            raise OSError('family instance not up yet')
        self.delivered.append((port, handoff, token, creator_id))

    def update(self, username=None, bot_id=4242):
        return {'user': {'id': 99, 'is_bot': False}, 'bot': {'id': bot_id, 'is_bot': True, 'username': username or self.record['username']}}

    def test_a_pending_username_is_fetched_restricted_and_handed_over_once(self):
        receipt = family_setup.accept_managed_bot(self.owner, self.call, self.update(), self.deliver)
        self.assertEqual(receipt, {'accepted': True, 'instance': 'spouse', 'delivered': True})
        self.assertEqual(self.calls, [('getManagedBotToken', {'user_id': 4242}),
                                      ('setManagedBotAccessSettings', {'user_id': 4242, 'is_access_restricted': True})])
        self.assertEqual(self.delivered, [(8797, self.record['handoff'], FAMILY_TOKEN, 99)])
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
            self.assertEqual(service.ingest_managed_bot(self.update()), {'accepted': True, 'instance': 'spouse', 'delivered': True})
            self.assertEqual(len(self.delivered), 1)
            self.assertFalse(service.ingest_managed_bot({'bot': 'broken'})['accepted'])
        finally:
            family_setup.deliver_token = original

    def test_a_failed_hand_over_is_retried_until_it_succeeds_and_never_rebinds(self):
        """Review P2-3: a transient failure no longer strands the setup."""
        self.fail_deliveries = 1
        first = family_setup.accept_managed_bot(self.owner, self.call, self.update(), self.deliver, now=100)
        self.assertEqual(first, {'accepted': True, 'instance': 'spouse', 'delivered': False})
        self.assertNotIn(('setManagedBotAccessSettings', {'user_id': 4242, 'is_access_restricted': True}), self.calls,
                         'the bot is restricted only after the hand-over succeeds')
        self.assertEqual(family_setup.retry_pending(self.owner, self.call, self.deliver, now=105), 0, 'waits its retry interval')
        self.assertEqual(family_setup.retry_pending(self.owner, self.call, self.deliver, now=100 + family_setup.RETRY_SECONDS), 1)
        self.assertEqual(len(self.delivered), 1)
        other = family_setup.accept_managed_bot(self.owner, self.call, self.update(bot_id=5151), self.deliver, now=200)
        self.assertFalse(other['accepted'], 'a setup bound to one bot never takes another')

    def test_a_failed_restriction_is_retried_without_re_delivering_the_token(self):
        """Re-review P2-6: only the missing step runs again."""
        failures = {'setManagedBotAccessSettings': 1}

        def call(method, body):
            self.calls.append((method, body))
            if failures.get(method):
                failures[method] -= 1
                raise OSError('telegram busy')
            return FAMILY_TOKEN if method == 'getManagedBotToken' else True
        first = family_setup.accept_managed_bot(self.owner, call, self.update(), self.deliver, now=100)
        self.assertFalse(first['delivered'])
        self.assertEqual(len(self.delivered), 1)
        self.assertEqual(family_setup.retry_pending(self.owner, call, self.deliver, now=100 + family_setup.RETRY_SECONDS), 1)
        self.assertEqual(len(self.delivered), 1, 'the token is not handed over twice')
        self.assertEqual([method for method, _ in self.calls].count('getManagedBotToken'), 1)

    def test_retries_stop_after_the_attempt_cap(self):
        self.fail_deliveries = 10 ** 6
        family_setup.accept_managed_bot(self.owner, self.call, self.update(), self.deliver, now=0)
        for step in range(1, 40):
            family_setup.retry_pending(self.owner, self.call, self.deliver, now=step * family_setup.RETRY_SECONDS)
        row = self.owner.config(family_setup.PENDING_KEY)[0]
        self.assertEqual(row['attempts'], family_setup.MAX_ATTEMPTS)

    def test_the_suggested_username_carries_32_random_bits(self):
        self.assertRegex(self.record['username'], r'_ag[0-9a-f]{8}_bot$')

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

    def test_an_expired_setup_answers_nothing_and_the_gate_stays_closed(self):
        """Review P2-2: a tunnel left up after expiry still reaches nothing."""
        family_setup._update_setup(self.store, expires=time.time() - 1)
        self.assertEqual(self.request('/family-setup' + self.code(), tunneled=True)[0], 404)
        self.assertEqual(self.request('/healthz', tunneled=True)[0], 404)
        self.assertNotEqual(self.request('/healthz')[0], 404, 'this Mac itself is unaffected')

    def test_a_non_ascii_code_is_a_404_not_a_crash(self):
        """Review P2-1."""
        for path in ('/family-setup?code=%C3%A9', '/api/family/status?code=%ED%95%9C'):
            self.assertEqual(self.request(path, tunneled=True)[0], 404)
        self.assertEqual(self.request('/api/family/telegram-token', 'POST', {'token': FAMILY_TOKEN},
                                      headers={family_setup.HANDOFF_HEADER: 'x'})[0], 404)

    def test_only_the_bots_creator_can_pair(self):
        """Review P2-5: the pairing code alone is not enough."""
        header = {family_setup.HANDOFF_HEADER: self.record['handoff']}
        self.assertEqual(self.request('/api/family/telegram-token', 'POST', {'token': FAMILY_TOKEN, 'creator_id': 555}, headers=header)[0], 200)
        cfg = self.store.config('telegram')
        self.assertEqual(cfg['pair_user_id'], 555)
        generation, code = cfg['generation'], cfg['pair_code']

        def start(sender, update_id):
            self.service.ingest_update({'update_id': update_id, 'message': {'message_id': update_id, 'date': int(time.time()),
                                        'chat': {'id': sender, 'type': 'private'}, 'from': {'id': sender, 'is_bot': False},
                                        'text': '/start ' + code}}, generation)
        start(777, 1)
        self.assertIsNone(self.store.config('telegram').get('user_id'), 'a stranger holding the code cannot pair')
        start(555, 2)
        self.assertEqual(self.store.config('telegram').get('user_id'), 555)
        again = self.request('/api/family/telegram-token', 'POST', {'token': FAMILY_TOKEN, 'creator_id': 555}, headers=header)
        self.assertEqual(json.loads(again[1]), {'ok': True, 'already_connected': True})
        self.assertEqual(self.store.config('telegram').get('user_id'), 555, 'a repeated hand-over never un-pairs')


    def start_update(self, sender, update_id, text):
        cfg = self.store.config('telegram')
        self.service.ingest_update({'update_id': update_id, 'message': {'message_id': update_id, 'date': int(time.time()),
                                    'chat': {'id': sender, 'type': 'private'}, 'from': {'id': sender, 'is_bot': False},
                                    'text': text}}, cfg['generation'])

    def test_the_creators_plain_start_pairs(self):
        """#927: Telegram's bot-creation screen opens the chat and sends a plain /start."""
        header = {family_setup.HANDOFF_HEADER: self.record['handoff']}
        self.request('/api/family/telegram-token', 'POST', {'token': FAMILY_TOKEN, 'creator_id': 555}, headers=header)
        self.start_update(777, 1, '/start')
        self.start_update(777, 2, '안녕')
        self.assertIsNone(self.store.config('telegram').get('user_id'), 'a stranger never pairs')
        self.start_update(555, 3, '/start')
        cfg = self.store.config('telegram')
        self.assertEqual(cfg.get('user_id'), 555)
        self.assertEqual((cfg.get('pair_code'), cfg.get('pair_expires')), ('', 0), 'the code is spent')

    def test_only_a_private_first_message_from_the_creator_pairs(self):
        """#928 review P3-3: group, edited and already-paired cases."""
        header = {family_setup.HANDOFF_HEADER: self.record['handoff']}
        self.request('/api/family/telegram-token', 'POST', {'token': FAMILY_TOKEN, 'creator_id': 555}, headers=header)
        generation = self.store.config('telegram')['generation']
        self.service.ingest_update({'update_id': 1, 'message': {'message_id': 1, 'date': int(time.time()),
                                    'chat': {'id': -100, 'type': 'group'}, 'from': {'id': 555, 'is_bot': False}, 'text': '/start'}},
                                   generation)
        self.service.ingest_update({'update_id': 2, 'edited_message': {'message_id': 2, 'date': int(time.time()),
                                    'chat': {'id': 555, 'type': 'private'}, 'from': {'id': 555, 'is_bot': False}, 'text': '안녕'}},
                                   generation)
        self.assertIsNone(self.store.config('telegram').get('user_id'))
        self.start_update(555, 3, '안녕')
        self.start_update(777, 4, '안녕')
        self.assertEqual(self.store.config('telegram').get('user_id'), 555, 'paired once; a stranger never switches it')

    def test_without_a_creator_only_the_code_pairs(self):
        cfg = self.store.config('telegram') or {}
        self.service.connect_telegram({'token': FAMILY_TOKEN})
        cfg = self.store.config('telegram')
        self.assertNotIn('pair_user_id', cfg)
        self.start_update(555, 1, '/start')
        self.assertIsNone(self.store.config('telegram').get('user_id'))
        self.start_update(555, 2, '/start ' + cfg['pair_code'])
        self.assertEqual(self.store.config('telegram').get('user_id'), 555)

    def test_the_creators_first_message_pairs_even_after_the_code_expired(self):
        header = {family_setup.HANDOFF_HEADER: self.record['handoff']}
        self.request('/api/family/telegram-token', 'POST', {'token': FAMILY_TOKEN, 'creator_id': 555}, headers=header)
        cfg = self.store.config('telegram')
        cfg['pair_expires'] = time.time() - 1
        self.store.put('telegram', cfg)
        self.start_update(555, 1, '내가 할 수 있는 건 뭐야?')
        self.assertEqual(self.store.config('telegram').get('user_id'), 555)
        self.assertTrue(any(job['message'] == '내가 할 수 있는 건 뭐야?' for job in self.store.jobs()), 'the message is handled')

    def test_the_hand_over_describes_the_bot(self):
        header = {family_setup.HANDOFF_HEADER: self.record['handoff']}
        calls = []
        original = self.service.telegram.call
        self.service.telegram.call = lambda method, body, **kw: calls.append((method, body)) or original(method, body, **kw)
        self.request('/api/family/telegram-token', 'POST', {'token': FAMILY_TOKEN, 'creator_id': 555}, headers=header)
        described = {method: body for method, body in calls if method.startswith('setMy')}
        self.assertIn(self.record['display_name'], described['setMyDescription']['description'])
        self.assertIn(self.record['display_name'], described['setMyShortDescription']['short_description'])
        self.assertLessEqual(len(described['setMyDescription']['description']), 512)
        self.assertLessEqual(len(described['setMyShortDescription']['short_description']), 120)

    def test_a_failed_description_never_blocks_the_hand_over(self):
        def refuse(method, body, timeout=None):
            raise OSError('telegram down')
        family_setup.describe_bot(refuse, '아내 비서')


class OwnerCommand(unittest.TestCase):
    """`agentos family add spouse` with fake Telegram, ngrok and launchd."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.owner = QuickStore(self.root / 'owner')
        self.owner.secret('telegram_token', '6000000000:OwnerTokenValue_abcdefghijklmnopq')
        self.owner.put('telegram', {'enabled': True, 'username': 'owner_bot', 'user_id': 111, 'generation': 'g'})
        self.owner.put('subscription_engine', {'id': 'claude-code', 'connected_at': 1, 'authentication': 'owner-confirmed-official-login'})
        self.owner.secret('claude_code_token', 'sk-ant-oat01-owner-shared-subscription')
        self.owner.secret('gmail_refresh', 'never-shared')
        self.owner.put('file_roots', [{'id': 'r1', 'path': '/Users/owner/private'}])
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
        # Review P1: the family member can talk to an AI - the owner's route, and nothing else of the owner's.
        self.assertEqual(family.config('subscription_engine')['id'], 'claude-code')
        self.assertEqual(family.secret('claude_code_token'), 'sk-ant-oat01-owner-shared-subscription')
        self.assertEqual(family.secret('gmail_refresh'), '')
        self.assertEqual(family.secret('telegram_token'), '', "the owner's bot token never moves")
        self.assertEqual(family.config('file_roots', []), [])

    def test_without_bot_management_mode_nothing_is_created(self):
        self.can_manage = False
        self.assertEqual(self.invoke('add', 'spouse'), 1)
        self.assertIn('Bot Management Mode', self.output[-1])
        self.assertEqual(self.actions, [])
        self.assertFalse((self.root / 'home/.local/share/agentos-instances/spouse').exists())

    def test_each_route_travels_with_its_companions_and_only_its_secrets(self):
        """Re-review P2-7/P3-8/P3-9."""
        family = QuickStore(self.root / 'family-direct')
        self.owner.put('subscription_engine', {})
        self.owner.put('model', {'provider': 'openai', 'endpoint': 'https://api.openai.com/v1', 'model': 'gpt-x'})
        self.owner.put('model_test', {'ok': True, 'fingerprint': 'f'})
        self.owner.secret('model_key', 'sk-owner-model')
        self.owner.put('decision_route', {'transport': 'direct_api'})
        self.owner.put('decision_route_checks', [{'ok': True}])
        self.owner.put('decision_jev', {'model': 'jev'})
        self.owner.secret('decision_jev_key', 'jev-key')
        self.owner.secret('decision_model_key', 'orphan-key')
        copied = family_setup.share_ai_route(self.owner, family)
        self.assertEqual(family.config('model_test'), {'ok': True, 'fingerprint': 'f'}, 'a direct route arrives ready')
        self.assertEqual((family.secret('model_key'), family.secret('decision_jev_key')), ('sk-owner-model', 'jev-key'))
        self.assertEqual(family.config('decision_route_checks'), [{'ok': True}])
        self.assertEqual(family.secret('decision_model_key'), '', 'a secret without its row stays behind')
        self.assertNotIn('sk-owner-model', json.dumps(copied))
        # A route the family instance already has is kept on a re-run.
        self.owner.put('model', {'provider': 'anthropic', 'endpoint': 'https://api.anthropic.com', 'model': 'other'})
        self.assertEqual(family_setup.share_ai_route(self.owner, family), [])
        self.assertEqual(family.config('model')['model'], 'gpt-x')

    def test_without_an_owner_ai_route_nothing_is_installed(self):
        self.owner.put('subscription_engine', {})
        self.assertEqual(self.invoke('add', 'spouse'), 1)
        self.assertIn('AI', self.output[-1])
        self.assertEqual(self.actions, [])

    def test_a_missing_ngrok_stops_before_anything_is_created(self):
        """#913 review P2-2: checked before the route is copied or the instance installed."""
        from unittest.mock import patch
        with patch('shutil.which', return_value=None), patch('pathlib.Path.home', return_value=self.root / 'home'):
            code = family_setup.family_main(['add', 'spouse'], service_action=self.service_action, owner_data=self.root / 'owner',
                                            environ=self.environ, opener=self.opener, out=self.output.append,
                                            sleep=lambda _s: None, free=lambda port: True)
        self.assertEqual(code, 1)
        self.assertIn('ngrok', self.output[-1])
        self.assertEqual(self.actions, [])
        self.assertEqual(self.owner.config(family_setup.PENDING_KEY, []), [])

    def test_a_tunnel_that_does_not_open_is_reported_and_closed(self):
        def broken_popen(argv, **kwargs):
            raise FileNotFoundError('ngrok')
        from unittest.mock import patch
        with patch('pathlib.Path.home', return_value=self.root / 'home'):
            code = family_setup.family_main(['add', 'spouse'], service_action=self.service_action, owner_data=self.root / 'owner',
                                            environ=self.environ, opener=self.opener, popen=broken_popen,
                                            out=self.output.append, sleep=lambda _s: None, free=lambda port: True)
        self.assertEqual(code, 1)
        self.assertIn('임시 링크를 열지 못했습니다', self.output[-1])
        self.assertEqual(self.owner.config(family_setup.PENDING_KEY, []), [], 'the pending row and secret are cleared')

    def test_a_retry_reuses_an_unpaired_instance_and_skips_leftover_folders(self):
        """#913 review P2-3."""
        home = self.root / 'home'
        agents = home / 'Library/LaunchAgents'
        agents.mkdir(parents=True)
        data = home / '.local/share/agentos-instances'
        (agents / 'com.personal-agentos.family-1.plist').write_text('x')
        QuickStore(data / 'family-1')                      # installed, not paired
        self.assertEqual(family_setup.pick_instance_name(home), 'family-1')
        QuickStore(data / 'family-1').put('telegram', {'enabled': True, 'user_id': 5})
        (data / 'family-2').mkdir(parents=True)            # left by an uninstalled instance
        self.assertEqual(family_setup.pick_instance_name(home), 'family-3')

    def test_reconcile_closes_setups_left_by_a_restart(self):
        record = {'instance': 'spouse', 'username': 'x_bot', 'expires': time.time() + 60, 'handoff': 'h'}
        family_setup.register_pending(self.owner, record, 8797)
        family_setup.reconcile_pending(self.owner)
        self.assertEqual(self.owner.config(family_setup.PENDING_KEY), [])
        self.assertEqual(self.owner.secret(family_setup.handoff_secret_key('spouse')), '')

    def test_an_invalid_name_is_refused(self):
        self.assertEqual(self.invoke('add', 'Not/Valid'), 2)
        self.assertEqual(self.actions, [])


if __name__ == '__main__':
    unittest.main()
