"""OWNER-SETTINGS-01 (#814): owner settings read and changed in conversation, confirm-before-apply.

Evidence class: model-free, fixture transports.  A scripted compatible-API
model and a recording Telegram transport replace only the provider and the
wires; the real QuickStore, ``AgentService`` (its own setters, ``run_one``,
``deliver_notification``, the callback handler), ``SettingsOrchestrator``,
``run_agent`` and ``Capabilities`` run unchanged.  The Judgment AI
qualification suite is replaced by a pass for the one model-change case.  No
live model or Telegram is contacted, and none is claimed.
"""
import json
import tempfile
import threading
import unittest
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.request import HTTPCookieProcessor, Request, build_opener

from personal_agent.agent_runtime import SETTINGS_ACTIONS, Capabilities, recorded_arguments
from personal_agent.conversation_handoff import JUDGMENT_NO, JUDGMENT_UNAVAILABLE, JUDGMENT_YES, Judgment
from personal_agent.bounded_execution import (BOUNDED_PROFILE, ISOLATED_PROFILE, STRICT_PROFILE, profile_actions,
                                              route_unavailable)
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent import preparations as prep
from personal_agent.settings_orchestrator import (CREDENTIAL_VALUE_MESSAGE, FOLLOW_REQUESTED_MESSAGE,
                                                  NOT_OWNER_TYPED_MESSAGE, SettingsError,
                                                  canonical_timezone)

CHAT, GENERATION = 77, 'gen-1'
TELEGRAM_SECRET = 'bot-token-value-1234-abcdef'
OPENAI_KEY = 'openai-owner-key-value-0001'
OPENROUTER_KEY = 'openrouter-owner-key-value-0002'


def call(ident, name, **args):
    return {'id': ident, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}


class _Case(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'data')
        self.telegram, self.script, self.urls = [], [], []
        self.clock = [1000.0]
        self.service = AgentService(self.store, ModelAdapter(self._model), self._telegram)
        self.settings = self.service.settings_orchestrator
        self.settings.now = lambda: self.clock[0]
        self.store.secret('telegram_token', TELEGRAM_SECRET)
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': GENERATION, 'cursor': 0})
        self.update_id, self.message_id = 100, 500

    def _model(self, url, body, headers=None, timeout=60):
        self.urls.append(url)
        names = [tool.get('function', {}).get('name') for tool in body.get('tools', [])]
        if 'agentos_connection_probe' in names:
            return {'choices': [{'message': {'tool_calls': [{'id': 'p', 'function': {'name': 'agentos_connection_probe', 'arguments': '{}'}}]}}]}
        step = self.script.pop(0) if self.script else {'content': '끝났습니다.'}
        return {'choices': [{'message': step}]}

    def _telegram(self, url, body=None, headers=None, timeout=60):
        method = url.rsplit('/', 1)[-1]
        self.telegram.append((method, body))
        if method == 'sendMessage':
            return {'ok': True, 'result': {'message_id': 9000 + len(self.telegram)}}
        return {'ok': True, 'result': True}

    def connect_two_api_routes(self):
        """OpenAI then OpenRouter, both checked; OpenRouter is the Main AI."""
        self.service.main_ai.save_key({'provider': 'openai', 'key': OPENAI_KEY})
        self.service.activate_main_ai({'route': 'openai'})
        self.service.main_ai.save_key({'provider': 'openrouter', 'key': OPENROUTER_KEY})
        self.service.activate_main_ai({'route': 'openrouter'})

    def draft(self, category, setting, value, owner='owner', channel='http'):
        return self.settings.draft(owner, channel, {'category': category, 'setting': setting, 'value': value})

    def context(self):
        return self.service.context_observations.settings()


class FamilyAssistantConversation(_Case):
    """#912: "아내 비서 만들어줘" is a confirmed draft, never a command the owner types."""

    def setUp(self):
        super().setUp()
        self.started = []
        self.service.start_family_setup = lambda display_name, name=None, notify=None: self.started.append(display_name) or {'state': 'requested'}
        # #962: no other assistant on "this Mac" unless a test adds one (never the real machine's).
        from unittest import mock
        patcher = mock.patch('personal_agent.family_share.instances', return_value={})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_family_assistant_is_drafted_then_started_only_after_confirmation(self):
        draft = self.draft('family', 'add', ' 아내   비서 ')
        self.assertEqual((draft['state'], draft['applied'], draft['after']), ('awaiting-confirmation', False, '아내 비서'))
        self.assertIn("가족 비서 '아내 비서'를 만듭니다", draft['response'])
        self.assertIn('확인해야 적용됩니다', draft['response'])
        self.assertEqual(self.started, [], 'a draft starts nothing')
        result = self.settings.confirm('owner', 'http', draft['draft_id'], draft['digest'])
        self.assertEqual(result['state'], 'requested')
        self.assertIn('설정 링크', result['response'])
        self.assertEqual(self.started, ['아내 비서'])
        with self.assertRaisesRegex(SettingsError, '이미 적용'):
            self.settings.confirm('owner', 'http', draft['draft_id'], draft['digest'])
        self.assertEqual(self.started, ['아내 비서'], 'confirmed once, started once')

    def test_bad_names_and_credential_shapes_create_nothing(self):
        for value in ('', '   ', 'x' * 65, '아내\n비서'):
            with self.assertRaises(SettingsError):
                self.draft('family', 'add', value)
        with self.assertRaises(SettingsError):
            self.draft('family', 'add', TELEGRAM_SECRET)
        self.assertEqual(self.started, [])

    def test_the_tool_offers_family_add(self):
        from personal_agent.agent_runtime import DEFINITIONS
        change = next(row['function'] for row in DEFINITIONS if row['function']['name'] == 'settings_change')
        self.assertIn('family', change['parameters']['properties']['category']['enum'])
        self.assertIn('add', change['parameters']['properties']['setting']['enum'])
        self.assertIn('family add', change['description'])


class FamilySetupInTheService(_Case):
    """#912: after confirmation the service runs the setup and reports on Telegram."""

    def run_setup(self, prepare, watch=None, notify=None):
        from personal_agent import family_setup
        originals = (family_setup.prepare_family_setup, family_setup.watch_family_setup, family_setup.pick_instance_name)
        family_setup.prepare_family_setup = prepare
        family_setup.watch_family_setup = watch or (lambda handle, store, on_state: on_state('paired'))
        family_setup.pick_instance_name = lambda home=None: 'family-2'
        try:
            receipt = self.service.start_family_setup('아내 비서', notify=notify) if notify else self.service.start_family_setup('아내 비서')
            self.service._family_setup_thread.join(5)
            return receipt
        finally:
            family_setup.prepare_family_setup, family_setup.watch_family_setup, family_setup.pick_instance_name = originals

    def sent(self):
        return [body['text'] for method, body in self.telegram if method == 'sendMessage']

    def test_the_link_then_the_outcome_reach_the_owner(self):
        calls = []

        def prepare(owner_store, name, display_name, **kwargs):
            calls.append((name, display_name))
            return {'display_name': display_name, 'link': 'https://abc.ngrok-free.app/family-setup?code=c'}
        receipt = self.run_setup(prepare)
        self.assertEqual(receipt, {'state': 'requested', 'instance': 'family-2'})
        self.assertEqual(calls, [('family-2', '아내 비서')], 'the next free instance name')
        texts = self.sent()
        self.assertIn('https://abc.ngrok-free.app/family-setup?code=c', texts[0])
        self.assertIn('연결이 끝났어요', texts[1])

    def test_a_setup_that_cannot_start_tells_the_owner_why(self):
        from personal_agent.family_setup import SetupError

        def prepare(*args, **kwargs):
            raise SetupError("BotFather 미니앱에서 Bot Management Mode를 켜 주세요.")
        self.run_setup(prepare)
        self.assertEqual(self.sent(), ["BotFather 미니앱에서 Bot Management Mode를 켜 주세요."])

    def test_the_link_and_outcome_go_to_the_confirming_conversation(self):
        """#913 review P2-1."""
        heard = []

        def prepare(owner_store, name, display_name, **kwargs):
            return {'display_name': display_name, 'link': 'https://abc.ngrok-free.app/family-setup?code=c'}
        self.run_setup(prepare, notify=heard.append)
        self.assertIn('https://abc.ngrok-free.app/family-setup?code=c', heard[0])
        self.assertIn('연결이 끝났어요', heard[1])
        self.assertEqual(self.sent(), [], 'not duplicated to another chat')

    def test_an_undelivered_link_closes_the_setup_at_once(self):
        """#913 review P1: no public link stays open when the owner never got it."""
        from personal_agent import family_setup
        closed, watched = [], []

        def prepare(owner_store, name, display_name, **kwargs):
            return {'display_name': display_name, 'link': 'https://abc.ngrok-free.app/family-setup?code=c'}

        def refuse(text):
            raise OSError('telegram down')
        original = family_setup.close_family_setup
        family_setup.close_family_setup = lambda handle, store: closed.append(handle['link'])
        try:
            self.run_setup(prepare, watch=lambda handle, store, on_state: watched.append(1), notify=refuse)
        finally:
            family_setup.close_family_setup = original
        self.assertEqual(closed, ['https://abc.ngrok-free.app/family-setup?code=c'])
        self.assertEqual(watched, [], 'no wait for a pairing that cannot come')

    def test_nothing_starts_when_the_link_could_reach_nobody(self):
        self.store.put('telegram', {'enabled': True, 'generation': GENERATION, 'cursor': 0})
        with self.assertRaisesRegex(ValueError, '보낼 곳이 없어요'):
            self.service.start_family_setup('아내 비서')
        self.assertIsNone(self.service.__dict__.get('_family_setup_thread'))

    def test_one_setup_at_a_time(self):
        import threading
        gate = threading.Event()

        def prepare(owner_store, name, display_name, **kwargs):
            gate.wait(5)
            return {'display_name': display_name, 'link': 'https://x/family-setup?code=c'}
        from personal_agent import family_setup
        originals = (family_setup.prepare_family_setup, family_setup.watch_family_setup)
        family_setup.prepare_family_setup = prepare
        family_setup.watch_family_setup = lambda handle, store, on_state: None
        try:
            self.service.start_family_setup('아내 비서', name='spouse')
            with self.assertRaisesRegex(ValueError, '이미 가족 비서를 만드는 중'):
                self.service.start_family_setup('엄마 비서', name='mom')
        finally:
            gate.set()
            self.service._family_setup_thread.join(5)
            family_setup.prepare_family_setup, family_setup.watch_family_setup = originals


class OrchestratorCategories(_Case):
    def test_read_is_redacted_and_names_the_allowed_values(self):
        self.connect_two_api_routes()
        self.store.secret('decision_model_key', 'decision-owner-key-value-0003')
        read = self.settings.read('owner')
        text = json.dumps(read, ensure_ascii=False)
        for secret in (TELEGRAM_SECRET, OPENAI_KEY, OPENROUTER_KEY, 'decision-owner-key-value-0003'):
            self.assertNotIn(secret, text)
        self.assertNotIn('https://', text, 'no endpoint is reported')
        self.assertEqual(set(read['settings']), {'current_context', 'judgment_ai', 'main_ai', 'owner_model', 'family', 'skills'})
        self.assertEqual([o['value'] for o in read['settings']['main_ai']['route']['options']], ['openai', 'openrouter'])
        self.assertEqual(read['settings']['current_context']['enabled']['value'], 'off')
        self.assertIn('기본 AI · 경로: OpenRouter', read['response'])
        self.assertIn('Telegram', read['response'])
        only = self.settings.read('owner', 'current_context')
        self.assertEqual(list(only['settings']), ['current_context'])
        with self.assertRaises(SettingsError):
            self.settings.read('owner', 'secrets')

    def test_current_context_enabled_applies_once_after_confirm(self):
        draft = self.draft('current_context', 'enabled', 'on')
        self.assertEqual((draft['state'], draft['applied'], draft['before'], draft['after']),
                         ('awaiting-confirmation', False, 'off', 'on'))
        self.assertFalse(self.context()['enabled'], 'a draft changes nothing')
        with self.assertRaises(SettingsError):
            self.settings.confirm('owner', 'http', draft['draft_id'], 'f' * 64)
        with self.assertRaises(SettingsError):
            self.settings.confirm('other', 'http', draft['draft_id'], draft['digest'])
        self.assertFalse(self.context()['enabled'])
        applied = self.settings.confirm('owner', 'http', draft['draft_id'], draft['digest'])
        self.assertEqual(applied['state'], 'applied')
        self.assertTrue(self.context()['enabled'])
        with self.assertRaisesRegex(SettingsError, '이미 적용'):
            self.settings.confirm('owner', 'http', draft['draft_id'], draft['digest'])
        terminals = [row['terminal'] for row in self.store.config('settings_audit')]
        self.assertEqual(terminals, ['drafted', 'applied'])

    def test_timezone_draft_cancel_expiry_and_stale(self):
        with self.assertRaisesRegex(SettingsError, 'IANA'):
            self.draft('current_context', 'timezone', 'Mars/Olympus')
        cancelled = self.draft('current_context', 'timezone', 'Asia/Seoul')
        self.assertEqual(self.settings.cancel('owner', 'http', cancelled['draft_id'])['state'], 'canceled')
        with self.assertRaises(SettingsError):
            self.settings.confirm('owner', 'http', cancelled['draft_id'], cancelled['digest'])
        expired = self.draft('current_context', 'timezone', 'Asia/Seoul')
        self.clock[0] += self.settings.TTL_SECONDS + 1
        with self.assertRaisesRegex(SettingsError, '만료'):
            self.settings.confirm('owner', 'http', expired['draft_id'], expired['digest'])
        stale = self.draft('current_context', 'timezone', 'Asia/Seoul')
        self.service.set_current_context({'timezone': 'Europe/Paris'})
        with self.assertRaisesRegex(SettingsError, '바뀌었'):
            self.settings.confirm('owner', 'http', stale['draft_id'], stale['digest'])
        self.assertEqual(self.context()['timezone'], 'Europe/Paris', 'a stale draft never applies')
        fresh = self.draft('current_context', 'timezone', 'Asia/Seoul')
        self.settings.confirm('owner', 'http', fresh['draft_id'], fresh['digest'])
        self.assertEqual(self.context()['timezone'], 'Asia/Seoul')

    def test_owner_model_upkeep_pause_and_cap(self):
        """#805's controls, through ``owner_model_request`` (set) only."""
        self.assertEqual(self.settings.read('owner', 'owner_model')['settings']['owner_model']['enabled']['value'], 'on')
        pause = self.draft('owner_model', 'enabled', 'off')
        self.assertTrue(self.service.owner_model.settings()['enabled'], 'a draft changes nothing')
        self.settings.confirm('owner', 'http', pause['draft_id'], pause['digest'])
        self.assertFalse(self.service.owner_model.settings()['enabled'])
        for value in ('-1', '201', '1.5', '열', '２０'):
            with self.subTest(value=value), self.assertRaisesRegex(SettingsError, '0~200'):
                self.draft('owner_model', 'daily_calls', value)
        cap = self.draft('owner_model', 'daily_calls', 5)
        self.assertEqual((cap['after'], cap['summary']), ('5', '알아 두기 하루 판단 횟수: 20회 → 5회'))
        self.settings.confirm('owner', 'http', cap['draft_id'], cap['digest'])
        self.assertEqual(self.service.owner_model.settings()['daily_calls'], 5)

    def test_judgment_ai_mode_and_model(self):
        draft = self.draft('judgment_ai', 'mode', 'off')
        self.assertEqual(self.service.decision_routes.mode(), 'follow_main')
        self.settings.confirm('owner', 'http', draft['draft_id'], draft['digest'])
        self.assertEqual(self.service.decision_routes.mode(), 'off')
        # An owner-chosen direct route: the model is one of its listed models.
        self.store.secret('decision_model_key', 'decision-owner-key-value-0003')
        self.store.put('decision_route', {'transport': 'direct_api', 'provider': 'openai',
                                          'requested_model': 'gpt-4o-mini', 'model_policy': 'explicit'})
        with self.assertRaisesRegex(SettingsError, '다음 중 하나'):
            self.draft('judgment_ai', 'model', 'gpt-imaginary')
        qualified = []
        self.service.decision_routes._first_qualified = lambda candidates, make: (
            qualified.append(list(candidates)) or candidates[0],
            {'suite_version': 'test', 'score': 1.0, 'qualified': True}, [{'observed_model': candidates[0]}])
        model = self.draft('judgment_ai', 'model', 'gpt-6-luna')
        self.assertEqual(qualified, [], 'a draft runs no qualification')
        self.settings.confirm('owner', 'http', model['draft_id'], model['digest'])
        self.assertEqual(qualified, [['gpt-6-luna']])
        self.assertEqual(self.service.decision_routes.active()['requested_model'], 'gpt-6-luna')

    def test_main_ai_route_and_model_only_among_connected_checked_routes(self):
        self.connect_two_api_routes()
        with self.assertRaisesRegex(SettingsError, '다음 중 하나'):
            self.draft('main_ai', 'route', 'anthropic')  # no key, never checked
        with self.assertRaisesRegex(SettingsError, '다음 중 하나'):
            self.draft('main_ai', 'route', 'codex')
        with self.assertRaisesRegex(SettingsError, '이미'):
            self.draft('main_ai', 'route', 'openrouter')
        probes = len(self.urls)
        draft = self.draft('main_ai', 'route', 'openai')
        self.assertIn('api.openai.com', draft['note'], 'a destination change says where Work goes')
        self.assertEqual((self.service.main_ai.current(), len(self.urls)), ('openrouter', probes), 'nothing probed or switched')
        self.settings.confirm('owner', 'http', draft['draft_id'], draft['digest'])
        self.assertEqual(self.service.main_ai.current(), 'openai')
        with self.assertRaisesRegex(SettingsError, '다음 중 하나'):
            self.draft('main_ai', 'model', 'gpt-imaginary')
        model = self.draft('main_ai', 'model', 'gpt-6-luna')
        self.settings.confirm('owner', 'http', model['draft_id'], model['digest'])
        self.assertEqual(self.store.config('model')['model'], 'gpt-6-luna')

    def test_refusals_are_fail_closed(self):
        self.connect_two_api_routes()
        before = self.store.config('settings_change_drafts', {})
        for category, setting, value, message in (
                ('main_ai', 'api_key', 'x', '대화로 바꿀 수 있는 설정이 아닙니다'),
                ('main_ai', 'endpoint', 'https://evil.example', '대화로 바꿀 수 있는 설정이 아닙니다'),
                ('secrets', 'route', 'openai', '대화로 바꿀 수 있는 설정이 아닙니다'),
                ('main_ai', 'route', 'sk-proj-abcdefghijklmnopqrstuvwxyz0123456789', CREDENTIAL_VALUE_MESSAGE),
                ('main_ai', 'model', OPENAI_KEY, CREDENTIAL_VALUE_MESSAGE),
                ('current_context', 'timezone', TELEGRAM_SECRET, CREDENTIAL_VALUE_MESSAGE),
                ('current_context', 'enabled', 'maybe', '다음 중 하나'),
                ('connections', 'telegram', 'off', '대화에서 제공하지 않습니다')):
            with self.subTest(setting=setting, value=value[:12]):
                with self.assertRaises(SettingsError) as caught:
                    self.draft(category, setting, value)
                self.assertIn(message, str(caught.exception))
                self.assertNotIn(value if len(value) > 20 else '\0', str(caught.exception))
        self.assertEqual(self.store.config('settings_change_drafts', {}), before)
        self.assertEqual(self.service.main_ai.current(), 'openrouter')


class ToolSurface(_Case):
    def caps(self, **kwargs):
        return Capabilities(self.store, None, {}, '', 'job', lambda *a: None, document_access=False, **kwargs)

    def test_offered_only_when_wired_and_relayed_only_on_trusted_local(self):
        names = lambda caps: {d['function']['name'] for d in caps.definitions()}
        self.assertFalse(SETTINGS_ACTIONS & names(self.caps()))
        self.assertEqual(SETTINGS_ACTIONS & names(self.caps(settings=lambda *a: None)), SETTINGS_ACTIONS)
        self.assertLessEqual(SETTINGS_ACTIONS, set(profile_actions(BOUNDED_PROFILE)))
        for profile in (STRICT_PROFILE, ISOLATED_PROFILE):
            with self.subTest(profile=profile):
                self.assertFalse(SETTINGS_ACTIONS & set(profile_actions(profile)))
                self.assertLessEqual(SETTINGS_ACTIONS, set(route_unavailable(profile)))
        delegated = self.caps(settings=lambda *a: {'applied': True}, delegated=True)
        with self.assertRaisesRegex(Exception, '설정'):
            delegated.execute('settings_change', {'category': 'current_context', 'setting': 'enabled', 'value': 'on'})

    def test_a_proposed_credential_value_is_never_recorded(self):
        args = {'category': 'main_ai', 'setting': 'model', 'value': 'sk-proj-abcdefghijklmnopqrstuvwxyz0123456789'}
        recorded = recorded_arguments('settings_change', args, redact=self.service._redact_known_secrets)
        self.assertNotIn('abcdefghijklmnopqrstuvwxyz', json.dumps(recorded))

    def test_settings_read_tool_output_holds_no_secret(self):
        self.connect_two_api_routes()
        tools = self.service.settings_tools({'id': 'w', 'channel': 'web', 'chat_id': None})
        text = json.dumps(tools('settings_read', {}), ensure_ascii=False)
        for secret in (TELEGRAM_SECRET, OPENAI_KEY, OPENROUTER_KEY):
            self.assertNotIn(secret, text)
        self.assertIn('main_ai', text)


class ConversationConfirmation(_Case):
    def setUp(self):
        super().setUp()
        self.service.save_model({'provider': 'compatible', 'endpoint': 'https://example.test/v1', 'model': 'test-model', 'api_key': 'k'})
        self.assertTrue(self.service.test_model()['ok'])
        self.applies = []
        original = self.service.set_current_context
        self.service.set_current_context = lambda body: (self.applies.append(dict(body)), original(body))[1]

    def change_turn(self):
        self.script = [{'content': None, 'tool_calls': [call('1', 'settings_change', category='current_context',
                                                             setting='enabled', value='on', reason='현재 맥락을 켜 달라고 하셨습니다.')]},
                       {'content': '현재 맥락 켜기를 확인해 주세요.'}]

    def test_a_web_turn_drafts_and_the_owner_confirms_in_the_conversation(self):
        self.change_turn()
        work = self.store.enqueue('현재 맥락 켜 줘', 'web-1')
        self.assertTrue(self.service.run_one())
        job = self.store.job(work)
        self.assertEqual(job['status'], 'partial', 'drafted, not applied')
        self.assertEqual(self.applies, [])
        self.assertFalse(self.context()['enabled'])
        [draft] = self.settings.pending_for_work(work)
        # #855: no command is ever shown; the compatibility form still confirms when the owner types it.
        self.assertNotIn('/settings', json.dumps(self.store.task_events(work), ensure_ascii=False))
        # The web chat route (``/api/chat``) enqueues the owner's typed message with ``owner_typed``.
        self.assertTrue(self.store.enqueue(f"/settings 확인 {draft['id']}", 'web-2', owner_typed=True))
        self.assertTrue(self.service.run_one())
        self.assertEqual(self.applies, [{'enabled': True}])
        self.assertTrue(self.context()['enabled'])

    def receive(self, text):
        self.update_id += 1
        self.message_id += 1
        self.service.ingest_update({'update_id': self.update_id, 'message': {
            'message_id': self.message_id, 'from': {'id': CHAT}, 'chat': {'id': CHAT, 'type': 'private'},
            'text': text, 'date': 1}}, GENERATION)
        work = self.store.jobs()[0]['id']
        self.assertTrue(self.service.run_one())
        return work

    def tap(self, data, message_id, sender=CHAT):
        self.service.ingest_callback({'id': 'cb', 'from': {'id': sender}, 'data': data,
                                      'message': {'message_id': message_id, 'chat': {'id': sender, 'type': 'private'}}},
                                     GENERATION)

    def notification(self, work):
        with self.store.db() as db:
            return dict(db.execute("SELECT * FROM telegram_notifications WHERE job_id=? AND kind='settings_change_proposed'",
                                   (work,)).fetchone())

    def test_telegram_button_applies_exactly_once_and_only_for_the_exact_message(self):
        self.change_turn()
        work = self.receive('현재 맥락 켜 줘')
        self.assertEqual(self.store.job(work)['owner_typed'], 1, 'Telegram text ingress marks the owner-typed message')
        self.service.deliver_one()
        self.assertTrue(self.service.deliver_notification())
        sent = [body for method, body in self.telegram if method == 'sendMessage'][-1]
        self.assertIn('현재 맥락 사용: 꺼짐 → 켜짐', sent['text'])
        self.assertIn('p7s:', json.dumps(sent['reply_markup']))
        self.assertEqual(self.applies, [])
        notification = self.notification(work)
        self.tap(f"p7s:{notification['id']}:confirm", notification['message_id'] + 1)
        self.tap(f"p7s:{notification['id']}:confirm", notification['message_id'], sender=CHAT + 1)
        self.assertEqual(self.applies, [], 'another message or chat applies nothing')
        self.tap(f"p7s:{notification['id']}:confirm", notification['message_id'])
        self.tap(f"p7s:{notification['id']}:confirm", notification['message_id'])
        self.assertEqual(self.applies, [{'enabled': True}], 'applied exactly once')
        self.assertTrue(self.context()['enabled'])
        edited = [body for method, body in self.telegram if method == 'editMessageText'][-1]
        self.assertIn('바꿨습니다', edited['text'])

    def test_a_stale_digest_or_a_cancel_applies_nothing(self):
        self.change_turn()
        work = self.receive('현재 맥락 켜 줘')
        self.service.deliver_one()
        self.service.deliver_notification()
        notification = self.notification(work)
        with self.store.db() as db:
            db.execute('UPDATE telegram_notifications SET fingerprint=? WHERE id=?', ('0' * 64, notification['id']))
        self.tap(f"p7s:{notification['id']}:confirm", notification['message_id'])
        self.assertEqual(self.applies, [])
        with self.store.db() as db:
            db.execute('UPDATE telegram_notifications SET fingerprint=? WHERE id=?', (notification['fingerprint'], notification['id']))
        self.tap(f"p7s:{notification['id']}:cancel", notification['message_id'])
        self.tap(f"p7s:{notification['id']}:confirm", notification['message_id'])
        self.assertEqual(self.applies, [])
        self.assertFalse(self.context()['enabled'])
        [row] = [row for row in self.store.config('settings_change_drafts').values() if row.get('work_id') == work]
        self.assertEqual(row['state'], 'canceled')


class ReviewRemediation(ConversationConfirmation):
    """#814 review: P1 owner-typed confirmation, P2 receipts/scrub/off-thread apply, P3 hardening."""

    def web_draft(self, reason='현재 맥락을 켜 달라고 하셨습니다.'):
        self.script = [{'content': None, 'tool_calls': [call('1', 'settings_change', category='current_context',
                                                             setting='enabled', value='on', reason=reason)]},
                       {'content': '확인해 주세요.'}]
        work = self.store.enqueue('현재 맥락 켜 줘', 'web-1', owner_typed=True)
        self.assertTrue(self.service.run_one())
        [draft] = self.settings.pending_for_work(work)
        return work, draft

    def test_p1_a_model_authored_preparation_cannot_confirm_or_cancel(self):
        """The reviewer's scenario: a preparation whose goal is the confirm command."""
        work, draft = self.web_draft()
        for command in (f"/settings 확인 {draft['id']}", f"/settings 취소 {draft['id']}"):
            with self.subTest(command=command):
                now = self.service.preparations.clock()
                self.service.preparations.create(kind=prep.KIND_PREPARE, goal=command, due_at=now - 1, timezone='UTC',
                                                 recurrence=None, channel=prep.CHANNEL_WEB, created_from=work,
                                                 state=prep.STATE_SCHEDULED, accepted_by=prep.ACCEPTED_OWNER_REQUEST,
                                                 window=None, delivery_mode=None)
                self.assertTrue(self.service.run_due_preparation())
                self.assertTrue(self.service.run_one())
                ran = self.store.jobs()[0]
                self.assertIsNone(ran['owner_typed'])
                self.assertIn(NOT_OWNER_TYPED_MESSAGE, str(ran['response']) + str(ran['error']))
        self.assertEqual(self.applies, [])
        self.assertFalse(self.context()['enabled'])
        self.assertEqual(self.store.config('settings_change_drafts')[draft['id']]['state'], 'awaiting-confirmation')
        # Any other AgentOS-enqueued message (no owner_typed) is refused the same way.
        self.store.enqueue(f"/settings 확인 {draft['id']}", 'agentos-internal')
        self.assertTrue(self.service.run_one())
        self.assertEqual(self.applies, [])

    def test_p1_the_web_chat_route_marks_the_owner_typed_message(self):
        from http.cookiejar import CookieJar
        from http.server import ThreadingHTTPServer
        from urllib.request import HTTPCookieProcessor, Request, build_opener
        from personal_agent.quickstart import make_handler
        self.store.claim(self.store.bootstrap.read_text(), 'long-password-test')
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.service))
        thread = threading.Thread(target=server.serve_forever); thread.start()
        client = build_opener(HTTPCookieProcessor(CookieJar())); base = 'http://127.0.0.1:' + str(server.server_port)
        def post(path, body):
            with client.open(Request(base + path, data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'}), timeout=3) as response:
                return json.load(response)
        try:
            post('/api/login', {'password': 'long-password-test'})
            work = post('/api/chat', {'message': '/settings 확인 abc', 'request_key': 'web-typed'})['id']
        finally:
            server.shutdown(); thread.join(); server.server_close()
        self.assertEqual(self.store.job(work)['owner_typed'], 1)

    def test_p2_1_follow_main_is_requested_not_applied(self):
        self.service.main_ai.save_key({'provider': 'openai', 'key': OPENAI_KEY})
        self.service.activate_main_ai({'route': 'openai'})
        off = self.draft('judgment_ai', 'mode', 'off')
        self.assertEqual(self.settings.confirm('owner', 'http', off['draft_id'], off['digest'])['state'], 'applied')
        follow = self.draft('judgment_ai', 'mode', 'follow_main')
        result = self.settings.confirm('owner', 'http', follow['draft_id'], follow['digest'])
        self.assertEqual((result['state'], result['response']), ('requested', FOLLOW_REQUESTED_MESSAGE))
        self.assertNotIn('바꿨습니다', result['response'])
        self.assertEqual(self.store.config('settings_change_drafts')[follow['draft_id']]['state'], 'requested')
        self.assertEqual(self.store.config('settings_audit')[-1]['terminal'], 'requested')
        self.assertIsNotNone(self.service.decision_routes.qualification('openai'), 'only a qualification was queued')

    def test_p2_2_reason_is_scrubbed_where_arguments_are_recorded(self):
        work, _draft = self.web_draft(reason=f'토큰 {TELEGRAM_SECRET} 로 바꿔 달라고 하셨습니다.')
        recorded = recorded_arguments('settings_change', {'value': 'on', 'reason': f'x {TELEGRAM_SECRET}'},
                                      redact=self.service._redact_known_secrets)
        self.assertNotIn(TELEGRAM_SECRET, json.dumps(recorded))
        with self.store.db() as db:
            details = [row['detail'] for row in db.execute('SELECT detail FROM tool_events WHERE job_id=?', (work,))]
        self.assertTrue(any('settings_change' in str(detail) for detail in details))
        self.assertNotIn(TELEGRAM_SECRET, json.dumps(details))

    def slow_openai_probe(self):
        """The OpenAI probe waits until released, as a slow provider check would."""
        started, release, original = threading.Event(), threading.Event(), self._model
        def model(url, body, headers=None, timeout=60):
            if 'api.openai.com' in url:
                started.set(); release.wait(5)
            return original(url, body, headers, timeout)
        self.service.adapter.transport = model
        return started, release

    def test_p2_3_a_slow_setter_runs_off_the_callers_thread_single_flight(self):
        self.service.main_ai.save_key({'provider': 'openai', 'key': OPENAI_KEY})
        self.service.activate_main_ai({'route': 'openai'})
        self.service.main_ai.save_key({'provider': 'openrouter', 'key': OPENROUTER_KEY})
        self.service.activate_main_ai({'route': 'openrouter'})
        started, release = self.slow_openai_probe()
        told = []
        route = self.draft('main_ai', 'route', 'openai')
        result = self.settings.confirm('owner', 'http', route['draft_id'], route['digest'], notify=told.append)
        self.assertEqual(result['state'], 'applying', 'answered before the probe finished')
        self.assertTrue(started.wait(5))
        self.assertEqual(self.service.main_ai.current(), 'openrouter')
        timezone = self.draft('current_context', 'timezone', 'Asia/Seoul')
        self.settings.confirm('owner', 'http', timezone['draft_id'], timezone['digest'], notify=told.append)
        self.assertEqual(self.context()['timezone'], 'Asia/Seoul', 'a fast setter is not held behind a slow one')
        release.set(); self.settings.thread.join(5)
        self.assertEqual(self.service.main_ai.current(), 'openai')
        self.assertEqual(len(told), 1)
        self.assertIn('바꿨습니다', told[0])
        self.assertEqual(self.store.config('settings_change_drafts')[route['draft_id']]['state'], 'applied')

    def two_api_routes_and_a_direct_judgment_route(self):
        self.service.main_ai.save_key({'provider': 'openai', 'key': OPENAI_KEY})
        self.service.activate_main_ai({'route': 'openai'})
        self.service.main_ai.save_key({'provider': 'openrouter', 'key': OPENROUTER_KEY})
        self.service.activate_main_ai({'route': 'openrouter'})
        self.store.secret('decision_model_key', 'decision-owner-key-value-0003')
        self.store.put('decision_route', {'transport': 'direct_api', 'provider': 'openai',
                                          'requested_model': 'gpt-4o-mini', 'model_policy': 'explicit'})
        self.service.decision_routes._first_qualified = lambda candidates, make: (
            candidates[0], {'suite_version': 'test', 'score': 1.0, 'qualified': True}, [{'observed_model': candidates[0]}])

    def telegram_drafts(self, *changes):
        self.script = [{'content': '알겠습니다.'}]
        work = self.receive('설정 바꿔 줘')
        job = self.store.job(work)
        owner = self.service.settings_owner(job)
        drafts = []
        for category, setting, value in changes:
            drafts.append(self.settings.propose(owner, job['channel'], category, setting, value, work_id=work))
            self.clock[0] += 1
        self.service.queue_settings_confirmation(job)
        self.service.deliver_one()
        self.assertTrue(self.service.deliver_notification())
        return work, drafts

    def test_p2_3_one_tap_queues_two_slow_drafts_in_order(self):
        """Re-review P2: both slow drafts of one tap apply, one after another, each told once."""
        self.two_api_routes_and_a_direct_judgment_route()
        work, (route, model) = self.telegram_drafts(('main_ai', 'route', 'openai'), ('judgment_ai', 'model', 'gpt-6-luna'))
        notification = self.notification(work)
        started, release = self.slow_openai_probe()
        self.telegram.clear()
        self.tap(f"p7s:{notification['id']}:confirm", notification['message_id'])
        self.assertTrue(started.wait(5))
        edited = [body['text'] for method, body in self.telegram if method == 'editMessageText'][-1]
        self.assertEqual(edited.count('확인하고 있어요'), 2, 'both drafts are queued, neither is refused')
        release.set(); self.settings.thread.join(10)
        drafts = self.store.config('settings_change_drafts')
        self.assertEqual((drafts[route['draft_id']]['state'], drafts[model['draft_id']]['state']), ('applied', 'applied'))
        self.assertEqual(self.service.main_ai.current(), 'openai')
        self.assertEqual(self.service.decision_routes.active()['requested_model'], 'gpt-6-luna')
        told = [body['text'] for method, body in self.telegram if method == 'sendMessage']
        self.assertEqual(len(told), 2)
        self.assertIn('기본 AI', told[0]); self.assertIn('판단 AI', told[1])

    def test_p2_3_a_queued_draft_rechecks_its_own_before(self):
        """The reviewer's reproduction: two drafts with the same ``before``; the second is refused as stale."""
        self.two_api_routes_and_a_direct_judgment_route()
        work, (first, second) = self.telegram_drafts(('main_ai', 'route', 'openai'), ('main_ai', 'route', 'openai'))
        notification = self.notification(work)
        self.tap(f"p7s:{notification['id']}:confirm", notification['message_id'])
        self.settings.thread.join(10)
        drafts = self.store.config('settings_change_drafts')
        self.assertEqual((drafts[first['draft_id']]['state'], drafts[second['draft_id']]['state']), ('applied', 'failed'))
        told = [body['text'] for method, body in self.telegram if method == 'sendMessage'][-2:]
        self.assertIn('바꿨습니다', told[0]); self.assertIn('바뀌었', told[1])
        self.assertEqual(self.settings.pending_for_work(work), [], 'nothing is left awaiting a consumed message')

    def test_p3_a_worker_that_cannot_start_fails_its_draft_and_releases_everything(self):
        from personal_agent import settings_orchestrator as orchestrator
        self.two_api_routes_and_a_direct_judgment_route()
        route = self.draft('main_ai', 'route', 'openai')
        class Refused(threading.Thread):
            def start(self):raise RuntimeError('cannot start thread')
        real = orchestrator.threading.Thread
        orchestrator.threading.Thread = Refused
        try:
            with self.assertRaisesRegex(SettingsError, '시작하지 못했습니다'):
                self.settings.confirm('owner', 'http', route['draft_id'], route['digest'], notify=lambda text: None)
        finally:
            orchestrator.threading.Thread = real
        self.assertEqual(self.store.config('settings_change_drafts')[route['draft_id']]['state'], 'failed')
        self.assertEqual(self.settings._in_flight, set())
        again = self.draft('main_ai', 'route', 'openai')
        self.settings.confirm('owner', 'http', again['draft_id'], again['digest'], notify=lambda text: None)
        self.settings.thread.join(10)
        self.assertEqual(self.service.main_ai.current(), 'openai', 'the worker slot was released')

    def test_p3_the_retired_control_branch_rewrites_drafts_under_the_lock(self):
        from test_settings_orchestrator import legacy_draft
        self.store.put('settings_change_drafts', {'legacy-draft': legacy_draft()})
        held = []
        original = self.settings._put_drafts
        self.settings._put_drafts = lambda rows: (held.append(self.settings._confirming._is_owned()), original(rows))[1]
        with self.assertRaises(SettingsError):
            self.settings.confirm('owner', 'http', 'legacy-draft', 'legacy-digest')
        self.assertEqual(held, [True])
        self.assertEqual(self.store.config('settings_change_drafts')['legacy-draft']['state'], 'failed')

    def test_p2_3_the_telegram_tap_is_answered_before_a_slow_apply(self):
        self.service.main_ai.save_key({'provider': 'openai', 'key': OPENAI_KEY})
        self.service.activate_main_ai({'route': 'openai'})
        self.service.main_ai.save_key({'provider': 'openrouter', 'key': OPENROUTER_KEY})
        self.service.activate_main_ai({'route': 'openrouter'})
        self.script = [{'content': '알겠습니다.'}]
        work = self.receive('기본 AI를 OpenAI로 바꿔 줘')
        job = self.store.job(work)
        self.settings.propose(self.service.settings_owner(job), job['channel'], 'main_ai', 'route', 'openai', work_id=work)
        self.service.queue_settings_confirmation(job)
        self.service.deliver_one()
        self.assertTrue(self.service.deliver_notification())
        notification = self.notification(work)
        started, release = self.slow_openai_probe()
        self.telegram.clear()
        self.tap(f"p7s:{notification['id']}:confirm", notification['message_id'])
        self.assertTrue(started.wait(5))
        methods = [method for method, _body in self.telegram]
        self.assertEqual(methods[:2], ['answerCallbackQuery', 'editMessageText'], 'the tap is answered at once')
        self.assertIn('확인하고 있어요', self.telegram[1][1]['text'])
        release.set(); self.settings.thread.join(5)
        self.assertEqual(self.service.main_ai.current(), 'openai')
        followup = [body for method, body in self.telegram if method == 'sendMessage']
        self.assertEqual(len(followup), 1)
        self.assertIn('바꿨습니다', followup[0]['text'])

    def test_a_draft_cut_off_mid_apply_by_a_restart_is_in_doubt_not_failed(self):
        """Codex P2 (restart): the setter may or may not have committed; the owner is told to check."""
        draft = self.draft('current_context', 'timezone', 'Asia/Seoul')
        rows = self.store.config('settings_change_drafts')
        rows[draft['draft_id']].update(state='applying', applying_at=self.clock[0])
        self.store.put('settings_change_drafts', rows)
        # A restart: a new service over the same store starts with nothing in flight.
        restarted = AgentService(self.store, ModelAdapter(self._model), self._telegram)
        restarted.settings_orchestrator.now = lambda: self.clock[0]
        restarted.settings_orchestrator.reconcile()
        row = self.store.config('settings_change_drafts')[draft['draft_id']]
        self.assertEqual(row['state'], 'unknown')
        audit = self.store.config('settings_audit')[-1]
        self.assertEqual((audit['terminal'], audit['error_class']), ('unknown', 'interrupted'))
        read = restarted.settings_orchestrator.read('owner')
        self.assertIn('현재 값을 확인', read['response'])
        self.assertIn('시간대', read['response'])
        with self.assertRaisesRegex(SettingsError, '확인하지 못했어요'):
            restarted.settings_orchestrator.confirm('owner', 'http', draft['draft_id'], draft['digest'])
        self.assertEqual(self.context()['timezone'], '', 'an in-doubt draft is never re-applied')

    def test_an_in_process_apply_is_not_mistaken_for_an_interrupted_one(self):
        started, release = threading.Event(), threading.Event()
        original = self.service.set_current_context
        def slow(body):
            started.set(); release.wait(5); return original(body)
        self.service.set_current_context = slow
        draft = self.draft('current_context', 'enabled', 'on')
        worker = threading.Thread(target=self.settings.confirm, args=('owner', 'http', draft['draft_id'], draft['digest']))
        worker.start()
        self.assertTrue(started.wait(5))
        self.settings.read('owner')
        self.assertEqual(self.store.config('settings_change_drafts')[draft['draft_id']]['state'], 'applying')
        release.set(); worker.join(5)
        self.assertEqual(self.store.config('settings_change_drafts')[draft['draft_id']]['state'], 'applied')

    def test_concurrent_confirms_of_one_setting_are_compare_and_apply(self):
        """Codex P2: two drafts with the same ``before``; the second is refused as stale, never applied."""
        first = self.draft('current_context', 'timezone', 'Asia/Seoul')
        second = self.draft('current_context', 'timezone', 'Europe/Paris')
        self.assertEqual(first['before'], second['before'])
        entered, release = threading.Event(), threading.Event()
        original = self.service.set_current_context
        def slow(body):
            entered.set(); release.wait(5); return original(body)
        self.service.set_current_context = slow
        outcomes = {}
        def confirm(draft):
            try:outcomes[draft['draft_id']] = self.settings.confirm('owner', 'http', draft['draft_id'], draft['digest'])['state']
            except SettingsError as exc:outcomes[draft['draft_id']] = str(exc)
        one = threading.Thread(target=confirm, args=(first,)); one.start()
        self.assertTrue(entered.wait(5))
        two = threading.Thread(target=confirm, args=(second,)); two.start()
        two.join(0.3)
        self.assertTrue(two.is_alive(), 'the second compare-and-apply waits for the first')
        release.set(); one.join(5); two.join(5)
        self.assertEqual(outcomes[first['draft_id']], 'applied')
        self.assertIn('바뀌었', outcomes[second['draft_id']])
        self.assertEqual(self.context()['timezone'], 'Asia/Seoul')
        states = {key: row['state'] for key, row in self.store.config('settings_change_drafts').items()}
        self.assertEqual((states[first['draft_id']], states[second['draft_id']]), ('applied', 'failed'))

    def test_the_off_thread_apply_holds_the_category_lock_until_it_commits(self):
        self.service.main_ai.save_key({'provider': 'openai', 'key': OPENAI_KEY})
        self.service.activate_main_ai({'route': 'openai'})
        self.service.main_ai.save_key({'provider': 'openrouter', 'key': OPENROUTER_KEY})
        self.service.activate_main_ai({'route': 'openrouter'})
        started, release = self.slow_openai_probe()
        route = self.draft('main_ai', 'route', 'openai')
        again = self.draft('main_ai', 'route', 'openai')
        self.settings.confirm('owner', 'http', route['draft_id'], route['digest'], notify=lambda text: None)
        self.assertTrue(started.wait(5))
        waiter = {}
        def confirm_second():
            try:waiter['state'] = self.settings.confirm('owner', 'http', again['draft_id'], again['digest'])['state']
            except SettingsError as exc:waiter['state'] = str(exc)
        second = threading.Thread(target=confirm_second); second.start()
        second.join(0.3)
        self.assertTrue(second.is_alive())
        release.set(); self.settings.thread.join(5); second.join(10)
        self.assertEqual(self.service.main_ai.current(), 'openai')
        self.assertIn('바뀌었', waiter['state'], 'refused as stale after the first committed')

    def test_p3_non_string_fields_are_settings_errors(self):
        for intent in ({'category': ['main_ai'], 'setting': 'route', 'value': 'openai'},
                       {'category': 'main_ai', 'setting': {'x': 1}, 'value': 'openai'},
                       {'category': 'current_context', 'setting': 'timezone', 'value': ['Asia/Seoul']},
                       {'category': 'current_context', 'setting': 'timezone', 'value': 'Asia/Seoul', 'reason': 7}):
            with self.subTest(intent=intent), self.assertRaises(SettingsError):
                self.settings.draft('owner', 'http', intent)
        with self.assertRaises(ValueError):
            self.service.conversation_settings_request({'operation': 'draft', 'intent': {'category': 1, 'setting': 2, 'value': 3}})

    def test_p3_timezone_is_stored_in_its_canonical_spelling(self):
        self.assertEqual(canonical_timezone('asia/seoul'), 'Asia/Seoul')
        draft = self.draft('current_context', 'timezone', 'asia/SEOUL')
        self.assertEqual(draft['after'], 'Asia/Seoul')
        self.settings.confirm('owner', 'http', draft['draft_id'], draft['digest'])
        self.assertEqual(self.context()['timezone'], 'Asia/Seoul')

    def test_p3_concurrent_drafts_and_settles_lose_nothing(self):
        drafts = [self.draft('current_context', 'timezone', zone) for zone in ('Asia/Seoul', 'Europe/Paris')]
        errors = []
        def propose(index):
            try:self.draft('current_context', 'timezone', 'America/New_York' if index % 2 else 'Asia/Tokyo')
            except Exception as exc:errors.append(exc)
        def cancel(draft):
            try:self.settings.cancel('owner', 'http', draft['draft_id'])
            except Exception as exc:errors.append(exc)
        threads = [threading.Thread(target=propose, args=(i,)) for i in range(20)]
        threads += [threading.Thread(target=cancel, args=(draft,)) for draft in drafts]
        for thread in threads:thread.start()
        for thread in threads:thread.join(5)
        self.assertEqual(errors, [])
        rows = self.store.config('settings_change_drafts')
        self.assertEqual(len(rows), 22)
        self.assertEqual([rows[d['draft_id']]['state'] for d in drafts], ['canceled', 'canceled'])


if __name__ == '__main__':
    unittest.main()


class TypedConfirmation(ReviewRemediation):
    """OWNER-SETTINGS-02 (#855): the owner's next typed message answers the pending draft; no command is shown.

    The DecisionEngine's two binary judgments are replaced by fixed verdicts
    (``judge``); everything else - the store, ``run_one``, the orchestrator's
    confirm path with digest/TTL/audit, the web route - runs unchanged.
    """

    def judge(self, confirmed, declined=JUDGMENT_NO):
        patches = [mock.patch.object(self.service.decision_judge, 'settings_draft_confirmed',
                                     return_value=Judgment(confirmed)),
                   mock.patch.object(self.service.decision_judge, 'settings_draft_declined',
                                     return_value=Judgment(declined))]
        return [self.enterContext(patch) for patch in patches]

    def owner_turn(self, text, owner_typed=True, reply='알겠습니다.'):
        self.script = [{'content': reply}] * 4
        work = self.store.enqueue(text, 'web-next-' + str(len(self.store.jobs())), owner_typed=owner_typed)
        self.assertTrue(self.service.run_one())
        return self.store.job(work)

    def test_a_typed_yes_applies_through_the_confirm_path(self):
        work, draft = self.web_draft()
        confirmed, declined = self.judge(JUDGMENT_YES)
        job = self.owner_turn('응, 그렇게 바꿔')
        self.assertEqual(self.applies, [{'enabled': True}])
        self.assertTrue(self.context()['enabled'])
        self.assertIn('바꿨습니다', job['response'])
        self.assertEqual(self.store.config('settings_change_drafts')[draft['id']]['state'], 'applied')
        [(pending, message)] = [call.args for call in confirmed.call_args_list]
        self.assertIn('현재 맥락 사용', pending)
        self.assertEqual(message, '응, 그렇게 바꿔')
        declined.assert_not_called()
        self.assertEqual(self.store.config('settings_audit')[-1]['terminal'], 'applied')

    def test_a_message_agentos_ran_never_confirms_even_when_judged_a_yes(self):
        work, draft = self.web_draft()
        confirmed, _declined = self.judge(JUDGMENT_YES)
        self.owner_turn('응, 그렇게 바꿔', owner_typed=False)
        confirmed.assert_not_called()
        self.assertEqual(self.applies, [])
        self.assertEqual(self.store.config('settings_change_drafts')[draft['id']]['state'], 'awaiting-confirmation')

    def test_a_typed_no_cancels(self):
        work, draft = self.web_draft()
        self.judge(JUDGMENT_NO, JUDGMENT_YES)
        job = self.owner_turn('아니')
        self.assertEqual(self.applies, [])
        self.assertEqual(self.store.config('settings_change_drafts')[draft['id']]['state'], 'canceled')
        self.assertIn('취소했습니다', job['response'])

    def test_an_unrelated_or_unjudged_message_leaves_the_draft_pending_and_is_a_normal_turn(self):
        work, draft = self.web_draft()
        for verdicts in ((JUDGMENT_NO, JUDGMENT_NO), (JUDGMENT_UNAVAILABLE, JUDGMENT_UNAVAILABLE)):
            with self.subTest(verdicts=verdicts):
                self.judge(*verdicts)
                job = self.owner_turn('오늘 저녁 뭐 먹을까', reply='김치찌개 어떠세요.')
                self.assertEqual(job['status'], 'succeeded')
                self.assertIn('김치찌개', job['response'])
        self.assertEqual(self.applies, [])
        self.assertEqual(self.store.config('settings_change_drafts')[draft['id']]['state'], 'awaiting-confirmation')
        self.assertEqual(self.settings.pending_for_work(work), [dict(self.settings.pending_for_work(work)[0])])
        # An expired draft is no longer answered by a yes.
        self.clock[0] += self.settings.TTL_SECONDS + 1
        confirmed, _ = self.judge(JUDGMENT_YES)
        self.owner_turn('응')
        confirmed.assert_not_called()
        self.assertEqual(self.applies, [])

    def test_no_owner_facing_string_names_a_settings_command(self):
        from personal_agent.agent_runtime import SETTINGS_CHANGE_DESCRIPTION
        work, draft = self.web_draft()
        tools = self.service.settings_tools(self.store.job(work))
        result = tools('settings_change', {'category': 'current_context', 'setting': 'timezone', 'value': 'America/New_York'})
        texts = [result['next_step'], SETTINGS_CHANGE_DESCRIPTION, json.dumps(self.store.task_events(work), ensure_ascii=False),
                 self.settings.confirmation_text(self.settings.pending_for_work(work)), str(self.store.job(work)['response'])]
        for text in texts:
            self.assertNotIn('/settings', text)
        self.assertIn('적용', result['next_step'])

    def test_the_web_turn_offers_the_same_buttons_through_the_work_scoped_route(self):
        from personal_agent.quickstart import make_handler
        work, draft = self.web_draft()
        self.store.claim(self.store.bootstrap.read_text(), 'long-password-test')
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.service))
        thread = threading.Thread(target=server.serve_forever); thread.start()
        client = build_opener(HTTPCookieProcessor(CookieJar())); base = 'http://127.0.0.1:' + str(server.server_port)
        def request(path, body=None):
            data = None if body is None else json.dumps(body).encode()
            with client.open(Request(base + path, data=data, headers={'Content-Type': 'application/json'} if data else {}),
                             timeout=3) as response:
                return json.load(response)
        try:
            request('/api/login', {'password': 'long-password-test'})
            [shown] = request('/api/tasks/' + work)['selected']['settings_drafts']
            self.assertEqual(shown['id'], draft['id'])
            self.assertNotIn('digest', shown)
            self.assertIn('현재 맥락 사용', shown['effect'])
            applied = request('/api/tasks/' + work + '/settings-draft', {'action': 'confirm'})
            self.assertEqual(applied['state'], 'applied')
            self.assertEqual(request('/api/tasks/' + work)['selected']['settings_drafts'], [])
        finally:
            server.shutdown(); thread.join(); server.server_close()
        self.assertEqual(self.applies, [{'enabled': True}])
        app = (Path(__file__).resolve().parents[1] / 'src/personal_agent/web/app.js').read_text()
        self.assertIn("/settings-draft'", app)
        self.assertIn('settings_drafts', app)
        self.assertNotIn('/settings 확인', app)

    def test_review_p1_a_typed_no_is_the_drafts_decline_not_a_continuity_cancel(self):
        work, draft = self.web_draft()
        self.judge(JUDGMENT_NO, JUDGMENT_YES)
        with mock.patch.object(self.service, 'continuity_relation') as continuity, \
                mock.patch.object(self.service, 'cancel_focused_work') as cancel_work:
            job = self.owner_turn('아니')
        continuity.assert_not_called()
        cancel_work.assert_not_called()
        self.assertEqual(self.store.config('settings_change_drafts')[draft['id']]['state'], 'canceled')
        self.assertIn('취소했습니다', job['response'])

    def test_review_p1_a_pending_calendar_draft_keeps_its_own_approval(self):
        work, draft = self.web_draft()
        confirmed, _declined = self.judge(JUDGMENT_YES)
        with mock.patch.object(self.service.calendar_conversation, 'claims', return_value=True) as claims:
            self.owner_turn('응')
        claims.assert_called()
        confirmed.assert_not_called()
        self.assertEqual(self.applies, [])
        self.assertEqual(self.store.config('settings_change_drafts')[draft['id']]['state'], 'awaiting-confirmation')

    def test_review_p2_the_web_receipt_outlives_the_buttons(self):
        work, draft = self.web_draft()
        result = self.service.work_settings_draft(work, {'action': 'confirm'})
        self.assertEqual(self.service.task_progress(work)['selected']['settings_drafts'], [])
        self.assertIn(result['response'], self.store.job(work)['response'])
        self.assertIn('바꿨습니다', self.store.job(work)['response'])

    def test_the_web_cancel_button_and_a_second_press_apply_nothing(self):
        work, draft = self.web_draft()
        self.assertEqual(self.service.work_settings_draft(work, {'action': 'cancel'})['state'], 'canceled')
        with self.assertRaises(ValueError):
            self.service.work_settings_draft(work, {'action': 'confirm'})
        self.assertEqual(self.applies, [])
        self.assertEqual(self.store.config('settings_change_drafts')[draft['id']]['state'], 'canceled')
