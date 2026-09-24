"""#504: the owner explicitly selects the effective AI route; no silent switch or fallback."""
import tempfile
import unittest
from pathlib import Path

from personal_agent.bounded_execution import ExecutionResult
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.subscription_engines import SubscriptionEngines


class _Engine:
    def __init__(self): self.calls = 0
    def execute(self, engine, prompt, tools):
        self.calls += 1
        return ExecutionResult('engine answer', engine, 0)


class AiRouteSelectionTests(unittest.TestCase):
    CONFIG = {'provider': 'compatible', 'endpoint': 'http://127.0.0.1:9999', 'model': 'fixture'}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = QuickStore(Path(self.tmp.name) / 'state')
        self.model_calls = 0
        self.engine = _Engine()
        self.service = self._service()
        self.service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})

    def _service(self):
        def transport(url, body, headers):
            self.model_calls += 1
            return {'choices': [{'message': {'content': 'api answer'}}]}
        return AgentService(self.store, adapter=ModelAdapter(transport),
                            subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/cli', clock=lambda: 1),
                            execution_adapter=self.engine)

    def _ready_model(self):
        self.store.put('model', self.CONFIG)
        self.store.put('model_test', {'ok': True, 'tools_ok': True, 'time': 9999999999,
                                      'fingerprint': self.service.model_fingerprint(self.CONFIG)})

    def _run(self, text, key, **channel):
        job = self.store.enqueue(text, key, **channel)
        self.assertTrue(self.service.run_one())
        return self.store.job(job)

    def test_saving_a_ready_api_does_not_switch_the_route(self):
        self._ready_model()
        self.assertEqual(self.service.subscription_engine_status()['selected'], 'codex')
        self._run('hello', 'no-switch')
        self.assertEqual((self.engine.calls, self.model_calls), (1, 0))

    def test_cli_to_direct_api_routes_next_web_and_telegram_work(self):
        self._ready_model()
        self.assertEqual(self.service.select_ai_route({'route': 'direct-api'})['selected'], '')
        web = self._run('hello from web', 'web-1')
        telegram = self._run('hello from telegram', 'tg-1', channel='telegram:fixture', chat_id=7)
        self.assertEqual(self.engine.calls, 0)
        self.assertGreaterEqual(self.model_calls, 2)
        for job in (web, telegram):
            self.assertEqual(job['status'], 'succeeded')
            self.assertNotEqual(job['provider'], 'subscription')

    def test_direct_api_back_to_cli(self):
        self._ready_model()
        self.service.select_ai_route({'route': 'direct-api'})
        status = self.service.select_ai_route({'route': 'codex', 'officially_authenticated': True})
        self.assertEqual(status['selected'], 'codex')
        job = self._run('hello', 'back-to-cli')
        self.assertEqual((self.engine.calls, job['provider']), (1, 'subscription'))

    def test_cli_switch_still_requires_login_confirmation(self):
        self._ready_model()
        self.service.select_ai_route({'route': 'direct-api'})
        with self.assertRaises(ValueError):
            self.service.select_ai_route({'route': 'codex'})
        self.assertEqual(self.service.subscription_engine_status()['selected'], '')

    def test_unverified_or_missing_api_is_refused_and_previous_route_stays(self):
        with self.assertRaisesRegex(ValueError, '현재 경로는 그대로'):
            self.service.select_ai_route({'route': 'direct-api'})
        self.store.put('model', self.CONFIG)
        self.store.put('model_test', {'ok': False})
        with self.assertRaisesRegex(ValueError, '연결 확인'):
            self.service.select_ai_route({'route': 'direct-api'})
        self.assertEqual(self.service.subscription_engine_status()['selected'], 'codex')
        self._run('hello', 'still-cli')
        self.assertEqual((self.engine.calls, self.model_calls), (1, 0))

    def test_selection_survives_restart(self):
        self._ready_model()
        self.service.select_ai_route({'route': 'direct-api'})
        self.service = self._service()
        self.assertEqual(self.service.subscription_engine_status()['selected'], '')
        self._run('after restart', 'restart-1')
        self.assertEqual(self.engine.calls, 0)

    def test_unknown_route_is_rejected(self):
        for body in ({'route': 'gpt-anything'}, {}, None):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.service.select_ai_route(body)
        self.assertEqual(self.service.subscription_engine_status()['selected'], 'codex')

    def test_route_endpoint_is_authenticated_post(self):
        source = (Path(__file__).parents[1] / 'src/personal_agent/quickstart.py').read_text(encoding='utf-8')
        auth = source.index("if not self.auth():return")
        self.assertGreater(source.index("path=='/api/ai-route'"), auth)


if __name__ == '__main__':
    unittest.main()
