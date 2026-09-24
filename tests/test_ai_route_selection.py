"""#504: the owner explicitly selects the effective AI route; no silent switch or fallback."""
import json
import tempfile
import threading
import unittest
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from personal_agent.bounded_execution import ExecutionResult
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart import make_handler
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
            self.assertEqual((job['provider'], job['model']), ('compatible', 'fixture'))

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

    def test_expired_or_changed_verification_is_refused(self):
        self._ready_model()
        stale = dict(self.store.config('model_test'), time=1)
        self.store.put('model_test', stale)
        with self.assertRaisesRegex(ValueError, '연결 확인'):
            self.service.select_ai_route({'route': 'direct-api'})
        self._ready_model()
        self.store.put('model', dict(self.CONFIG, model='other-model'))  # changed after the test
        with self.assertRaisesRegex(ValueError, '연결 확인'):
            self.service.select_ai_route({'route': 'direct-api'})
        self.assertEqual(self.service.subscription_engine_status()['selected'], 'codex')

    def test_switch_during_running_work_does_not_redirect_it(self):
        self._ready_model()
        original = self.store.history
        def history_then_switch():
            # The owner switches after this Work took its route snapshot.
            self.service.select_ai_route({'route': 'direct-api'})
            return original()
        self.store.history = history_then_switch
        job = self._run('hello', 'mid-switch')
        self.store.history = original
        self.assertEqual((self.engine.calls, self.model_calls, job['provider']), (1, 0, 'subscription'))
        self._run('next', 'after-switch')
        self.assertEqual((self.engine.calls, self.model_calls >= 1), (1, True))

    def test_selection_survives_restart(self):
        self._ready_model()
        self.service.select_ai_route({'route': 'direct-api'})
        self.service = self._service()
        self.assertEqual(self.service.subscription_engine_status()['selected'], '')
        self._run('after restart', 'restart-1')
        self.assertEqual(self.engine.calls, 0)

    def _route(self, job_id):
        return next(task for task in self.service.task_progress()['tasks'] if task['id'] == job_id)['route']

    def test_task_reports_the_route_it_used_even_after_a_later_switch(self):
        from personal_agent.bounded_execution import ExecutionError
        class Failing:
            def execute(self, *args): raise ExecutionError('engine failed', failure_class='request-rejected', exit_code=1)
        self.service.execution_adapter = Failing()
        failed = self._run('hello', 'route-failed')
        self._ready_model()
        self.service.select_ai_route({'route': 'direct-api'})
        direct = self._run('hello again', 'route-direct')
        self.assertEqual(self._route(failed['id']), {'kind': 'subscription', 'engine': 'codex', 'status': 'failed'})
        route = self._route(direct['id'])
        self.assertEqual((route['kind'], route['status']), ('direct-api', 'succeeded'))

    def test_task_without_ai_execution_reports_no_route(self):
        job = self.store.enqueue('/note remember milk', 'note-only')
        self.service.run_one()
        self.assertIsNone(self._route(job))

    def test_unknown_route_is_rejected(self):
        for body in ({'route': 'gpt-anything'}, {}, None):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.service.select_ai_route(body)
        self.assertEqual(self.service.subscription_engine_status()['selected'], 'codex')

    def test_route_endpoint_requires_session_and_same_origin(self):
        self._ready_model()
        self.store.claim(self.store.bootstrap.read_text(), 'long-password-test')
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.service))
        thread = threading.Thread(target=server.serve_forever); thread.start()
        client = build_opener(HTTPCookieProcessor(CookieJar())); url = 'http://127.0.0.1:' + str(server.server_port)
        def request(path, body, **headers):
            req = Request(url + path, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', **headers})
            with client.open(req, timeout=3) as response: return json.load(response)
        try:
            with self.assertRaises(HTTPError) as error: request('/api/ai-route', {'route': 'direct-api'})
            self.assertEqual(error.exception.code, 401)
            request('/api/login', {'password': 'long-password-test'})
            with self.assertRaises(HTTPError) as error:
                request('/api/ai-route', {'route': 'direct-api'}, Origin='https://attacker.invalid')
            self.assertEqual(error.exception.code, 403)
            self.assertEqual(self.service.subscription_engine_status()['selected'], 'codex')
            self.assertEqual(request('/api/ai-route', {'route': 'direct-api'})['selected'], '')
        finally:
            server.shutdown(); thread.join(); server.server_close()


if __name__ == '__main__':
    unittest.main()
