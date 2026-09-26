"""PRESENCE-SETTINGS-02 / #619: Main AI chooser, per-provider keys, follow_main.

Evidence class: deterministic unit tests with a fixture HTTP transport shaped
after the OpenAI chat-completions and Anthropic messages responses, a fixture
subscription-engine finder and a fake execution adapter.  No live provider,
CLI, account or credential is used.
"""
import json
import tempfile
import unittest
from pathlib import Path

from personal_agent.bounded_execution import ExecutionResult
from personal_agent.decision import OUTCOME_DECIDED, DecisionContext, UnavailableDecisionEngine
from personal_agent.decision_routes import DecisionRouteError, MODE_FOLLOW
from personal_agent.main_ai import MainAiError
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.subscription_engines import SubscriptionEngines

OPENAI_KEY = 'sk-fixture-openai-0001'
ANTHROPIC_KEY = 'ak-fixture-anthropic-0001'


class Transport:
    """Answers the connection probe and one `decide` call, per destination."""

    def __init__(self):
        self.calls = []
        self.refuse = set()  # hostnames that answer HTTP 401
        self.refuse_decide = set()  # hostnames that answer the probe but not a judgment

    def __call__(self, url, body, headers=None, timeout=60):
        from urllib.parse import urlsplit
        from personal_agent.providers import ProviderError
        host = urlsplit(url).hostname
        self.calls.append({'host': host, 'model': body.get('model'), 'headers': dict(headers or {})})
        if host in self.refuse:
            raise ProviderError('HTTP 401', status=401)
        tools = body.get('tools') or []
        name = (tools[0].get('function') or {}).get('name') if tools and 'function' in tools[0] else \
            (tools[0].get('name') if tools else None)
        if name == 'decide' and host in self.refuse_decide:
            raise ProviderError('HTTP 401', status=401)
        if name == 'decide':
            arguments = {'choice': 'retry', 'confidence': 0.9}
        elif name:
            arguments = {}
        if url.endswith('/v1/messages'):
            if not name:
                return {'model': body['model'], 'content': [{'type': 'text', 'text': 'ok'}]}
            return {'model': body['model'], 'content': [{'type': 'tool_use', 'id': 't1', 'name': name, 'input': arguments}]}
        if not name:
            return {'model': body['model'], 'choices': [{'message': {'role': 'assistant', 'content': 'ok'}}]}
        return {'model': body['model'], 'choices': [{'message': {'role': 'assistant', 'tool_calls': [
            {'id': 'c1', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments)}}]}}]}


class _Engine:
    def __init__(self):
        self.calls = 0

    def execute(self, engine, prompt, tools, **_kwargs):
        self.calls += 1
        return ExecutionResult('engine answer', engine, 0)

    def login_status(self, engine_id, binary=None):
        return {'state': 'signed-in'}


class MainAiRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'state'
        self.transport = Transport()
        self.service = self._service()
        self.store = self.service.store

    def _service(self):
        return AgentService(QuickStore(self.root), adapter=ModelAdapter(self.transport),
                            subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/cli', clock=lambda: 1),
                            execution_adapter=_Engine())

    def _save(self, provider, key):
        return self.service.save_main_ai_key({'provider': provider, 'key': key})

    # -- AC4 per-provider keys -------------------------------------------------
    def test_keys_are_stored_per_provider_and_never_returned(self):
        self._save('openai', OPENAI_KEY)
        status = self._save('anthropic', ANTHROPIC_KEY)
        self.assertEqual(self.store.secret('api_key:openai'), OPENAI_KEY)
        self.assertEqual(self.store.secret('api_key:anthropic'), ANTHROPIC_KEY)
        routes = {row['id']: row for row in status['routes']}
        self.assertTrue(routes['openai']['key']['saved'] and routes['anthropic']['key']['saved'])
        self.assertIsNotNone(routes['openai']['key']['saved_at'])
        self.assertFalse(routes['openrouter']['key']['saved'])
        dumped = json.dumps(self.service.settings())
        self.assertNotIn(OPENAI_KEY, dumped)
        self.assertNotIn(ANTHROPIC_KEY, dumped)
        self.assertNotIn('fixture-openai', dumped)  # no partial value either

    def test_saving_a_key_never_switches(self):
        self.service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        self._save('openai', OPENAI_KEY)
        self.assertEqual(self.service.main_ai.current(), 'codex')
        self.assertEqual(self.store.secret('model_key'), '')
        self.assertEqual(self.transport.calls, [])

    def test_migration_moves_model_key_into_its_provider_slot_exactly_once(self):
        self.store.put('model', {'provider': 'openai', 'endpoint': 'https://api.openai.com/v1', 'model': 'gpt-4o-mini'})
        self.store.secret('model_key', OPENAI_KEY)
        self.assertTrue(self.service.main_ai.migrate())
        self.assertEqual(self.store.secret('api_key:openai'), OPENAI_KEY)
        # Survives a restart and never runs twice.
        restarted = self._service()
        self.store.secret('model_key', 'sk-typed-later')
        self.assertFalse(restarted.main_ai.migrate())
        self.assertEqual(self.store.secret('api_key:openai'), OPENAI_KEY)

    def test_migration_does_not_attribute_a_local_or_unknown_endpoint(self):
        self.store.put('model', {'provider': 'compatible', 'endpoint': 'https://example.test/v1', 'model': 'm'})
        self.store.secret('model_key', 'k-other')
        self.service.main_ai.migrate()
        for slot in ('openai', 'anthropic', 'openrouter'):
            self.assertEqual(self.store.secret(f'api_key:{slot}'), '')

    # -- AC5 probe-and-switch ------------------------------------------------
    def test_confirm_and_use_probes_then_switches_work_and_judgment(self):
        self.service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        self._save('anthropic', ANTHROPIC_KEY)
        result = self.service.activate_main_ai({'route': 'anthropic'})
        self.assertEqual(self.service.main_ai.current(), 'anthropic')
        self.assertEqual(self.store.secret('model_key'), ANTHROPIC_KEY)
        self.assertTrue(self.service.model_ready())
        # AC7: the following Judgment AI moved to Anthropic's light model.
        self.assertEqual(result['judgment'], {'state': 'active'})
        active = result['decision_route']['active']
        self.assertEqual((active['source'], active['destination'], active['requested_model']),
                         ('follow', 'api.anthropic.com', 'claude-haiku-4-5'))
        self.assertTrue(active['available'])
        self.assertEqual({call['host'] for call in self.transport.calls}, {'api.anthropic.com'})

    def test_failed_probe_keeps_previous_main_and_judgment(self):
        self._save('openai', OPENAI_KEY)
        self.service.activate_main_ai({'route': 'openai'})
        judgment_before = self.store.config('decision_route')
        self._save('anthropic', ANTHROPIC_KEY)
        self.transport.refuse.add('api.anthropic.com')
        with self.assertRaisesRegex(MainAiError, '그대로'):
            self.service.activate_main_ai({'route': 'anthropic'})
        self.assertEqual(self.service.main_ai.current(), 'openai')
        self.assertEqual(self.store.secret('model_key'), OPENAI_KEY)
        self.assertEqual(self.store.config('decision_route'), judgment_before)
        check = self.service.main_ai.status()['routes'][3]['check']
        self.assertEqual((check['state'], bool(check['checked_at'])), ('failed', True))

    def test_missing_key_is_refused_without_a_call(self):
        with self.assertRaisesRegex(MainAiError, '키'):
            self.service.activate_main_ai({'route': 'openrouter'})
        self.assertEqual(self.transport.calls, [])

    def test_removing_the_active_key_needs_attention_without_fallback(self):
        self._save('openai', OPENAI_KEY)
        self._save('anthropic', ANTHROPIC_KEY)
        self.service.activate_main_ai({'route': 'openai'})
        self._save('openai', '')
        self.assertEqual(self.service.main_ai.current(), 'openai')
        self.assertFalse(self.service.model_ready())
        self.assertEqual(self.store.secret('model_key'), '')
        self.assertEqual(self.store.secret('api_key:anthropic'), ANTHROPIC_KEY)
        # The following Judgment AI does not borrow any other key.
        self.assertIsNone(self.service.decision_routes._follow_resolve(self.store.config('decision_route')))

    def test_a_newly_saved_key_reaches_neither_work_nor_judgment_before_confirm(self):
        # #643 review P2-1: the Judgment AI uses the Main AI's probed key.
        self._save('openai', OPENAI_KEY)
        self.service.activate_main_ai({'route': 'openai'})
        self._save('openai', 'sk-fixture-openai-NEW')
        self.assertTrue(self.service.main_ai.status()['routes'][2]['key']['pending'])
        before = len(self.transport.calls)
        decision = self.service.decision_engine.choose(DecisionContext('p', {'a': 'b'}), ('retry', 'x'), 'q')
        self.assertEqual(decision.outcome, OUTCOME_DECIDED)
        used = [call['headers'].get('Authorization') for call in self.transport.calls[before:]]
        self.assertEqual(used, ['Bearer ' + OPENAI_KEY])

    # -- AC6 re-check without switching ----------------------------------------
    def test_check_reprobes_current_without_switching(self):
        self._save('openai', OPENAI_KEY)
        self._save('anthropic', ANTHROPIC_KEY)
        self.service.activate_main_ai({'route': 'openai'})
        before = len(self.transport.calls)
        status = self.service.check_main_ai()['main_ai']
        self.assertEqual(status['current'], 'openai')
        self.assertEqual(status['last_check']['state'], 'ok')
        self.assertGreater(len(self.transport.calls), before)
        self.assertEqual({call['host'] for call in self.transport.calls[before:]}, {'api.openai.com'})

    # -- AC7 no fallback on a failed judgment probe -------------------------------
    def test_failed_follow_probe_leaves_judgment_needing_attention(self):
        self._save('openai', OPENAI_KEY)
        self.service.activate_main_ai({'route': 'openai'})
        self._save('anthropic', ANTHROPIC_KEY)
        self.transport.refuse_decide.add('api.anthropic.com')
        result = self.service.activate_main_ai({'route': 'anthropic'})
        self.assertEqual(self.service.main_ai.current(), 'anthropic')
        self.assertEqual(result['judgment']['state'], 'attention')
        row = self.store.config('decision_route')
        self.assertEqual((row['mode'], row['main'], row['transport']), (MODE_FOLLOW, 'anthropic', 'off'))
        self.assertFalse(result['decision_route']['active']['available'])
        # No judgment reaches OpenAI (the previous route) or any other host.
        calls = len(self.transport.calls)
        decision = self.service.decision_engine.choose(DecisionContext('p', {'a': 'b'}), ('x', 'y'), 'q')
        self.assertNotEqual(decision.outcome, OUTCOME_DECIDED)
        self.assertEqual(len(self.transport.calls), calls)

    def test_stale_follow_row_is_unavailable_after_a_legacy_switch(self):
        self._save('openai', OPENAI_KEY)
        self.service.activate_main_ai({'route': 'openai'})
        # A legacy/other path switches the Work route without re-resolving.
        self.service.connect_subscription_engine({'engine': 'claude-code', 'officially_authenticated': True})
        self.assertIsInstance(self.service.decision_routes.engine(), UnavailableDecisionEngine)
        active = self.service.decision_routes.status()['active']
        self.assertTrue(active['stale'])
        self.assertFalse(active['available'])

    def test_explicit_judgment_is_not_changed_by_a_main_switch(self):
        self._save('anthropic', ANTHROPIC_KEY)
        self.store.put('decision_route', {'transport': 'off'})
        result = self.service.activate_main_ai({'route': 'anthropic'})
        self.assertEqual(result['judgment']['state'], 'unchanged')
        self.assertEqual(self.store.config('decision_route'), {'transport': 'off'})
        self.assertEqual(result['decision_route']['mode'], 'off')

    # -- AC8 Codex cannot be followed ----------------------------------------------
    def test_codex_main_makes_follow_unavailable_with_reason(self):
        self._save('openai', OPENAI_KEY)
        self.service.activate_main_ai({'route': 'openai'})
        result = self.service.activate_main_ai({'route': 'codex'})
        self.assertEqual(self.service.main_ai.current(), 'codex')
        self.assertEqual(result['judgment']['failure'], 'follow-unsupported')
        route = result['decision_route']
        self.assertFalse(route['follow']['available'])
        self.assertIn('Codex', route['follow']['reason'])
        self.assertFalse(route['active']['available'])
        with self.assertRaises(DecisionRouteError):
            self.service.activate_decision_route({'transport': MODE_FOLLOW})

    def test_claude_code_follow_uses_lowest_qualified_light_candidate(self):
        seen = []

        def fake_cli(body, extra=None):
            seen.append((body, extra))
            raise DecisionRouteError('fixture: not qualified')
        self.service.decision_routes._activate_cli = fake_cli
        result = self.service.activate_main_ai({'route': 'claude-code'})
        self.assertEqual(seen, [({'engine': 'claude-code', 'model_policy': 'lowest_qualified', 'candidates': ['haiku']},
                                 {'mode': MODE_FOLLOW, 'main': 'claude-code'})])
        self.assertEqual(result['judgment']['state'], 'attention')
        self.assertEqual(self.store.config('decision_route')['transport'], 'off')

    def test_explicit_follow_failure_keeps_previous_judgment(self):
        self._save('openai', OPENAI_KEY)
        self.service.activate_main_ai({'route': 'openai'})
        self.store.put('decision_route', {'transport': 'off'})
        self.transport.refuse_decide.add('api.openai.com')
        with self.assertRaises(DecisionRouteError):
            self.service.activate_decision_route({'transport': MODE_FOLLOW})
        self.assertEqual(self.store.config('decision_route'), {'transport': 'off'})

    # -- AC9 / AC11 --------------------------------------------------------------
    def test_existing_ollama_config_renders_truthfully_and_is_not_offered(self):
        self.store.put('model', {'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434', 'model': 'llama'})
        status = self.service.main_ai.status()
        self.assertEqual(status['current'], 'other')
        self.assertEqual(status['other']['provider'], 'ollama')
        self.assertEqual(status['order'], ['codex', 'claude-code', 'openai', 'anthropic', 'openrouter'])
        self.assertNotIn('ollama', [row['id'] for row in status['routes']])

    def test_opening_settings_makes_no_model_call(self):
        self._save('openai', OPENAI_KEY)
        self.service.settings()
        self.service.settings()
        self.assertEqual(self.transport.calls, [])


if __name__ == '__main__':
    unittest.main()
