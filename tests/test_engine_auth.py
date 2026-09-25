"""#571 ENGINE-AUTH-01: CLI login check before switching and recovery from auth failures."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from personal_agent.bounded_execution import (AgentOSMcpTools, BoundedExecutionAdapter, ExecutionError, ExecutionResult,
                                              is_not_signed_in)
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.subscription_engines import SubscriptionEngines

TOKEN = 'sk-ant-oat01-' + 'x' * 40


class _Caps:
    job_id = 'job'
    private_provenance = set()

    class store:
        root = '/tmp/agentos-auth-test'

    def execute(self, name, arguments):
        return {'ok': True}


class _Done:
    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class AdapterCredentialAndStatus(unittest.TestCase):
    def _adapter(self, runner, token=TOKEN, codex_profile=True):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        profile = Path(self.tmp.name) / 'codex-home'
        if codex_profile:
            profile.mkdir()
        return BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runner=runner,
                                       runtime_root=Path(self.tmp.name) / 'turns', codex_home=profile,
                                       credentials=lambda engine: token if engine == 'claude-code' else '')

    def test_only_claude_code_gets_the_token_and_never_in_argv(self):
        seen = []

        def runner(argv, **kwargs):
            seen.append((argv, kwargs['env']))
            if argv[0].endswith('claude'):
                return _Done(stdout=json.dumps({'result': 'ok'}))
            return _Done(stdout=json.dumps({'item': {'type': 'agent_message', 'text': 'ok'}}))

        adapter = self._adapter(runner)
        adapter.execute('claude-code', 'hi', AgentOSMcpTools(_Caps()))
        adapter.execute('codex', 'hi', AgentOSMcpTools(_Caps()))
        (claude_argv, claude_env), (codex_argv, codex_env) = seen
        self.assertEqual(claude_env.get('CLAUDE_CODE_OAUTH_TOKEN'), TOKEN)
        self.assertNotIn(TOKEN, ' '.join(claude_argv))
        self.assertNotIn('CLAUDE_CODE_OAUTH_TOKEN', codex_env)
        self.assertNotEqual(claude_env['HOME'], str(Path.home()), 'HOME stays the empty per-turn directory')

    def test_no_token_means_no_variable(self):
        seen = []
        adapter = self._adapter(lambda argv, **kw: seen.append(kw['env']) or _Done(stdout=json.dumps({'result': 'ok'})), token='')
        adapter.execute('claude-code', 'hi', AgentOSMcpTools(_Caps()))
        self.assertNotIn('CLAUDE_CODE_OAUTH_TOKEN', seen[0])

    def test_status_parsing(self):
        cases = [
            ('claude-code', _Done(stdout=json.dumps({'loggedIn': True, 'authMethod': 'oauth_token'})), 'signed-in'),
            ('claude-code', _Done(stdout=json.dumps({'loggedIn': False, 'authMethod': 'none'})), 'signed-out'),
            ('claude-code', _Done(stdout='garbled'), 'unknown'),
            ('codex', _Done(stdout='Logged in using ChatGPT'), 'signed-in'),
            ('codex', _Done(returncode=1, stdout='Not logged in'), 'signed-out'),
        ]
        for engine, done, expected in cases:
            with self.subTest(engine=engine, expected=expected):
                argvs = []
                adapter = self._adapter(lambda argv, **kw: argvs.append(argv) or done)
                self.assertEqual(adapter.login_status(engine)['state'], expected)
                self.assertIn('status', argvs[0])

    def test_status_errors_are_unknown_and_missing_profile_is_signed_out(self):
        def boom(argv, **kw):
            raise subprocess.TimeoutExpired(argv, 20)
        self.assertEqual(self._adapter(boom).login_status('claude-code')['state'], 'unknown')
        self.assertEqual(self._adapter(lambda *a, **k: _Done(), codex_profile=False).login_status('codex')['state'], 'signed-out')
        self.assertEqual(BoundedExecutionAdapter(finder=lambda name: None).login_status('codex')['state'], 'signed-out')

    def test_not_signed_in_output_is_classified_auth(self):
        self.assertTrue(is_not_signed_in('Not logged in · Please run /login'))
        self.assertFalse(is_not_signed_in('rate limit reached'))
        adapter = self._adapter(lambda argv, **kw: _Done(returncode=1, stdout=json.dumps(
            {'is_error': True, 'result': 'Not logged in · Please run /login'})))
        with self.assertRaises(ExecutionError) as caught:
            adapter.execute('claude-code', 'hi', AgentOSMcpTools(_Caps()))
        self.assertEqual(caught.exception.failure_class, 'auth')


class _FakeEngine:
    def __init__(self, state='signed-in', fail=None):
        self.state, self.fail, self.checks = state, fail, []

    def login_status(self, engine_id, binary=None):
        self.checks.append((engine_id, binary))
        return {'state': self.state}

    def execute(self, engine, prompt, tools, **kwargs):
        if self.fail:
            raise self.fail
        return ExecutionResult('answer', engine, 0)


class ServiceLoginFlow(unittest.TestCase):
    def _service(self, engine):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = QuickStore(Path(self.tmp.name) / 'state')
        return AgentService(self.store, subscription_engines=SubscriptionEngines(finder=lambda c: '/runtime/' + c, clock=lambda: 1),
                            execution_adapter=engine)

    def test_signed_out_cli_is_not_selected_and_says_how_to_sign_in(self):
        service = self._service(_FakeEngine('signed-out'))
        with self.assertRaises(ValueError) as caught:
            service.connect_subscription_engine({'engine': 'claude-code', 'officially_authenticated': True})
        self.assertIn('claude setup-token', str(caught.exception))
        self.assertEqual(service.subscription_engine_status()['selected'], '')
        login = [e for e in service.subscription_engine_status()['engines'] if e['id'] == 'claude-code'][0]['login']
        self.assertEqual(login['state'], 'signed-out')

    def test_signed_in_and_unknown_can_be_selected_explicitly(self):
        for state in ('signed-in', 'unknown'):
            with self.subTest(state=state):
                engine = _FakeEngine(state)
                service = self._service(engine)
                status = service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
                self.assertEqual(status['selected'], 'codex')
                self.assertEqual(engine.checks[-1], ('codex', '/runtime/codex'), 'checks the same binary discovery found')

    def test_token_is_stored_privately_and_never_reported(self):
        service = self._service(_FakeEngine('signed-in'))
        status = service.save_engine_credential({'engine': 'claude-code', 'token': TOKEN})
        claude = [e for e in status['engines'] if e['id'] == 'claude-code'][0]
        self.assertTrue(claude['credential'])
        self.assertEqual(claude['login']['state'], 'signed-in')
        self.assertEqual(self.store.secret('claude_code_token'), TOKEN)
        self.assertNotIn(TOKEN, json.dumps(service.settings(), ensure_ascii=False))
        with self.assertRaises(ValueError):
            service.save_engine_credential({'engine': 'claude-code', 'token': 'has space in it but long enough'})
        with self.assertRaises(ValueError):
            service.save_engine_credential({'engine': 'codex', 'token': TOKEN})
        service.save_engine_credential({'engine': 'claude-code', 'token': ''})
        self.assertEqual(self.store.secret('claude_code_token'), '')

    def test_default_adapter_reads_the_token_for_claude_code_only(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / 'state')
        service = AgentService(store)
        store.secret('claude_code_token', TOKEN)
        self.assertEqual(service.execution_adapter.credentials('claude-code'), TOKEN)
        self.assertEqual(service.execution_adapter.credentials('codex'), '')

    def test_auth_failure_class_reaches_the_task_summary(self):
        engine = _FakeEngine('unknown', fail=ExecutionError('Claude Code 엔진이 작업을 완료하지 못했습니다.', failure_class='auth', exit_code=1))
        service = self._service(engine)
        service.connect_subscription_engine({'engine': 'claude-code', 'officially_authenticated': True})
        self.store.enqueue('hello', 'k1')
        self.assertTrue(service.run_one())
        task = service.task_progress()['tasks'][0]
        self.assertEqual(task['status'], 'failed')
        self.assertEqual(task['failure_class'], 'auth')


if __name__ == '__main__':
    unittest.main()
