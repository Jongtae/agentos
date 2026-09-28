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
from pathlib import Path

from personal_agent.agent_runtime import SETTINGS_ACTIONS, Capabilities, recorded_arguments
from personal_agent.bounded_execution import (BOUNDED_PROFILE, ISOLATED_PROFILE, STRICT_PROFILE, profile_actions,
                                              route_unavailable)
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent import preparations as prep
from personal_agent.settings_orchestrator import (BUSY_MESSAGE, CREDENTIAL_VALUE_MESSAGE, FOLLOW_REQUESTED_MESSAGE,
                                                  NOT_OWNER_TYPED_MESSAGE, STUCK_APPLYING_SECONDS, SettingsError,
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


class OrchestratorCategories(_Case):
    def test_read_is_redacted_and_names_the_allowed_values(self):
        self.connect_two_api_routes()
        self.store.secret('decision_model_key', 'decision-owner-key-value-0003')
        read = self.settings.read('owner')
        text = json.dumps(read, ensure_ascii=False)
        for secret in (TELEGRAM_SECRET, OPENAI_KEY, OPENROUTER_KEY, 'decision-owner-key-value-0003'):
            self.assertNotIn(secret, text)
        self.assertNotIn('https://', text, 'no endpoint is reported')
        self.assertEqual(set(read['settings']), {'current_context', 'judgment_ai', 'main_ai'})
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
        self.assertIn(f"/settings 확인 {draft['id']}", json.dumps(self.store.task_events(work), ensure_ascii=False))
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

    def test_p2_3_only_one_slow_apply_at_a_time(self):
        self.service.main_ai.save_key({'provider': 'openai', 'key': OPENAI_KEY})
        self.service.activate_main_ai({'route': 'openai'})
        self.service.main_ai.save_key({'provider': 'openrouter', 'key': OPENROUTER_KEY})
        self.service.activate_main_ai({'route': 'openrouter'})
        started, release = self.slow_openai_probe()
        first = self.draft('main_ai', 'route', 'openai')
        self.settings.confirm('owner', 'http', first['draft_id'], first['digest'], notify=lambda text: None)
        self.assertTrue(started.wait(5))
        second = self.draft('main_ai', 'route', 'openai')
        with self.assertRaisesRegex(SettingsError, BUSY_MESSAGE[:10]):
            self.settings.confirm('owner', 'http', second['draft_id'], second['digest'], notify=lambda text: None)
        self.assertEqual(self.store.config('settings_change_drafts')[second['draft_id']]['state'], 'awaiting-confirmation')
        release.set(); self.settings.thread.join(5)

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

    def test_p3_stuck_applying_is_failed_with_an_audit_row(self):
        draft = self.draft('current_context', 'enabled', 'on')
        rows = self.store.config('settings_change_drafts')
        rows[draft['draft_id']].update(state='applying', applying_at=self.clock[0])
        self.store.put('settings_change_drafts', rows)
        self.settings.read('owner')
        self.assertEqual(self.store.config('settings_change_drafts')[draft['draft_id']]['state'], 'applying')
        self.clock[0] += STUCK_APPLYING_SECONDS + 1
        self.settings.read('owner')
        self.assertEqual(self.store.config('settings_change_drafts')[draft['draft_id']]['state'], 'failed')
        audit = self.store.config('settings_audit')[-1]
        self.assertEqual((audit['terminal'], audit['error_class']), ('failed', 'stuck-applying'))

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
