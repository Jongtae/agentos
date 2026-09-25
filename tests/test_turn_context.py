"""#569 PRESENCE-WORKER-CTX-01: every AI route receives the same AgentOS turn context."""
import json
import tempfile
import unittest
from pathlib import Path

from personal_agent.agent_runtime import (CLI_TOOL_GUIDANCE, CONTEXT_BUDGET_BYTES, CORE_INSTRUCTIONS, MESSAGE_CAP_CHARS,
                                          POLICY, render_turn_prompt, turn_context)
from personal_agent.bounded_execution import AgentOSMcpTools, BoundedExecutionAdapter, ExecutionResult
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.subscription_engines import SubscriptionEngines


class _Caps:
    job_id = 'job'

    class store:
        root = '/tmp/agentos-test-store'

    def execute(self, name, arguments):
        return {'ok': True}


class TurnContextBuilder(unittest.TestCase):
    def test_every_route_shares_the_core_instructions(self):
        api = turn_context([{'role': 'user', 'content': 'hi'}], 'api')
        cli = turn_context([{'role': 'user', 'content': 'hi'}], 'cli')
        self.assertTrue(api['instructions'].startswith(CORE_INSTRUCTIONS))
        self.assertTrue(cli['instructions'].startswith(CORE_INSTRUCTIONS))
        self.assertTrue(cli['instructions'].endswith(CLI_TOOL_GUIDANCE))
        self.assertEqual(api['instructions'], POLICY, 'the direct-API system text is the shared core plus its tool guidance')
        self.assertIn('Personal AgentOS', CORE_INSTRUCTIONS)

    def test_order_budget_and_current_request_are_preserved(self):
        history = [{'role': 'user', 'content': f'old {i}'} for i in range(30)]
        history.append({'role': 'user', 'content': 'current request'})
        context = turn_context(history, 'cli')
        self.assertEqual(context['request'], 'current request')
        self.assertEqual(len(context['conversation']), 15, 'at most 16 messages including the current request')
        self.assertEqual(context['conversation'][-1]['content'], 'old 29', 'newest prior turn is kept')
        big = [{'role': 'assistant', 'content': 'x' * 10_000} for _ in range(20)]
        request = 'y' * 20_000
        bounded = turn_context([*big, {'role': 'user', 'content': request}], 'cli')
        self.assertEqual(bounded['request'], request, 'the current request is never shortened')
        size = sum(len(m['content'].encode()) for m in bounded['conversation'])
        self.assertLessEqual(size + len(request.encode()) + len(bounded['instructions'].encode()), CONTEXT_BUDGET_BYTES)
        self.assertTrue(all(len(m['content']) <= MESSAGE_CAP_CHARS + 6 for m in bounded['conversation']))

    def test_rejects_a_history_without_a_current_request(self):
        with self.assertRaises(ValueError):
            turn_context([{'role': 'assistant', 'content': 'x'}], 'api')

    def test_envelope_marks_context_as_not_pending(self):
        context = turn_context([{'role': 'user', 'content': 'a'}, {'role': 'assistant', 'content': 'b'},
                                {'role': 'user', 'content': 'c'}], 'cli')
        text = render_turn_prompt(context)
        self.assertLess(text.index('# AgentOS instructions'), text.index('# Recent conversation'))
        self.assertLess(text.index('# Recent conversation'), text.index('# Current request'))
        self.assertIn('not pending tasks', text)
        self.assertNotIn('# AgentOS instructions', render_turn_prompt(context, include_instructions=False))


class CliAdapterPlacement(unittest.TestCase):
    def _run(self, engine):
        seen = {}

        class Done:
            returncode = 0
            stdout = json.dumps({'result': 'ok'}) if engine == 'claude-code' else json.dumps(
                {'item': {'type': 'agent_message', 'text': 'ok'}})

        def runner(argv, **kwargs):
            seen['argv'] = argv
            return Done()

        context = turn_context([{'role': 'user', 'content': 'earlier'}, {'role': 'assistant', 'content': 'reply'},
                                {'role': 'user', 'content': 'now'}], 'cli')
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder) / 'codex-home'
            profile.mkdir()
            adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runner=runner,
                                              runtime_root=Path(folder) / 'turns', codex_home=profile)
            adapter.execute(engine, render_turn_prompt(context), AgentOSMcpTools(_Caps()), context=context)
        return seen['argv'], context

    def test_claude_code_gets_instructions_as_a_system_prompt_addition(self):
        argv, context = self._run('claude-code')
        flag = argv.index('--append-system-prompt')
        self.assertEqual(argv[flag + 1], context['instructions'])
        prompt = argv[argv.index('-p') + 1]
        self.assertNotIn('# AgentOS instructions', prompt)
        self.assertIn('# Recent conversation', prompt)
        self.assertIn('now', prompt)

    def test_codex_gets_the_instructions_inside_the_envelope(self):
        argv, context = self._run('codex')
        prompt = argv[-1]
        self.assertIn('# AgentOS instructions', prompt)
        self.assertIn(CORE_INSTRUCTIONS, prompt)
        self.assertNotIn('--append-system-prompt', argv)


class _RecordingEngine:
    def __init__(self):
        self.calls = []

    def execute(self, engine, prompt, tools, **kwargs):
        self.calls.append({'engine': engine, 'prompt': prompt, 'context': kwargs.get('context')})
        return ExecutionResult('engine answer', engine, 0)


class RoutesReceiveTheSameContext(unittest.TestCase):
    CONFIG = {'provider': 'compatible', 'endpoint': 'http://127.0.0.1:9999', 'model': 'fixture'}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = QuickStore(Path(self.tmp.name) / 'state')
        self.engine = _RecordingEngine()
        self.api_messages = []

        def transport(url, body, headers):
            self.api_messages.append(body['messages'])
            return {'choices': [{'message': {'content': 'api answer'}}]}

        self.service = AgentService(self.store, adapter=ModelAdapter(transport),
                                    subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/cli', clock=lambda: 1),
                                    execution_adapter=self.engine)
        self.store.put('model', self.CONFIG)
        self.store.put('model_test', {'ok': True, 'tools_ok': True, 'time': 9999999999,
                                      'fingerprint': self.service.model_fingerprint(self.CONFIG)})

    def _run(self, text, key):
        self.store.enqueue(text, key)
        self.assertTrue(self.service.run_one())

    def test_cli_and_api_receive_the_same_instructions_and_conversation(self):
        self._run('first question about lunch', 'k1')           # direct API (no CLI selected yet)
        self._run('second question about dinner', 'k2')         # direct API
        api_last = self.api_messages[-1]
        self.assertEqual(api_last[0]['role'], 'system')
        self.assertTrue(api_last[0]['content'].startswith(CORE_INSTRUCTIONS))
        self.service.connect_subscription_engine({'engine': 'claude-code', 'officially_authenticated': True})
        self._run('third question about breakfast', 'k3')       # CLI route
        call = self.engine.calls[-1]
        context = call['context']
        self.assertIsNotNone(context, 'the CLI adapter receives the shared context')
        self.assertTrue(context['instructions'].startswith(CORE_INSTRUCTIONS))
        self.assertEqual(context['request'], 'third question about breakfast')
        prior = [m['content'] for m in context['conversation']]
        self.assertIn('first question about lunch', prior)
        self.assertIn('second question about dinner', prior)
        self.assertIn('api answer', prior, 'earlier assistant answers are part of the context')
        self.assertIn('first question about lunch', call['prompt'], 'the prompt carries the conversation too')

    def test_document_rows_stay_excluded_on_the_cli_route(self):
        self._run('secret document summary request', 'doc')
        doc_job = self.store.jobs()[0]['id']
        self.store.put('file_workspace_document_jobs', [doc_job])
        self._run('ordinary follow-up', 'k2')
        self.service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        self._run('now on the cli', 'k3')
        call = self.engine.calls[-1]
        self.assertNotIn('secret document summary request', call['prompt'])
        self.assertNotIn('secret document summary request', json.dumps(call['context'], ensure_ascii=False))
        self.assertIn('ordinary follow-up', call['prompt'])



class _ProbingEngine:
    """Records the egress taint the CLI tools would see, and tries web_search."""
    def __init__(self):
        self.taint = []
        self.web_search_error = []

    def execute(self, engine, prompt, tools, **kwargs):
        self.taint.append(tools.capabilities.private_egress_provenance())
        try:
            if self.taint[-1]:
                tools.call('web_search', {'query': 'today news'})
        except Exception as exc:  # the refusal is what we assert on
            self.web_search_error.append(str(exc))
        return ExecutionResult('engine answer', engine, 0)


class CrossTurnEgressGuard(unittest.TestCase):
    """Independent review M1 on #574: private answers from earlier turns must not reach public egress."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = QuickStore(Path(self.tmp.name) / 'state')
        self.engine = _ProbingEngine()
        self.service = AgentService(self.store, adapter=ModelAdapter(lambda *a: {'choices': [{'message': {'content': 'x'}}]}),
                                    subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/cli', clock=lambda: 1),
                                    execution_adapter=self.engine)
        self.service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})

    def _run(self, text, key):
        self.store.enqueue(text, key)
        self.assertTrue(self.service.run_one())

    def test_first_cli_turn_without_prior_answers_is_not_tainted(self):
        self._run('hello there', 'k1')
        self.assertEqual(self.engine.taint[-1], [])

    def test_a_prior_note_listing_closes_cli_web_search(self):
        self._run('/note PRIVATE-XYZ', 'n1')
        self._run('/notes', 'n2')
        self._run('search the web for today news', 'k3')
        self.assertIn('conversation-history', self.engine.taint[-1])
        self.assertEqual(len(self.engine.web_search_error), 1, 'the CLI web_search call is refused')


if __name__ == '__main__':
    unittest.main()
