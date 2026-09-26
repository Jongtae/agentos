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
                # A query made of note words only: nothing in it is permitted
                # for a public lookup, so nothing leaves (#605).
                tools.call('web_search', {'query': 'PRIVATE-XYZ'})
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
        # #605: the label names the earlier Work's actual source.
        self.assertIn('history:personal-space', self.engine.taint[-1])
        self.assertEqual(len(self.engine.web_search_error), 1, 'the CLI web_search call is refused')
        self.assertIn('개인 자료는 공개 조회에 보내지 않으므로', self.engine.web_search_error[0])
        self.assertNotIn('연결 문서', self.engine.web_search_error[0])



class BridgeProcessEgressGuard(unittest.TestCase):
    """Re-review of #574: the taint must reach the separate MCP bridge process the CLI actually calls."""

    def _service_turns(self, turns, query='today news'):
        import io, contextlib, sys
        from unittest import mock
        from personal_agent import mcp_bridge
        from personal_agent.local_tools import LocalTools
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / 'state')
        captured = {}

        class Done:
            returncode = 0
            stdout = json.dumps({'item': {'type': 'agent_message', 'text': 'engine answer'}})

        network_calls = []
        requests = '\n'.join(json.dumps(r) for r in [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'web_search', 'arguments': {'query': query}}},
        ]) + '\n'

        def runner(argv, **kwargs):
            # The scripted CLI calls the bridge during the Work, as a real one
            # would: since #604 the bridge acts only for a running Work.
            config = json.loads((Path(kwargs['cwd']) / 'agentos-mcp.json').read_text())
            args = captured['args'] = config['mcpServers']['agentos']['args']
            provenance = [part.split('=', 1)[1] for part in args if part.startswith('--provenance=')]
            out = io.StringIO()
            with mock.patch.object(LocalTools, 'execute', lambda self, plan: network_calls.append(plan) or {'results': []}), \
                 mock.patch.object(sys, 'stdin', io.StringIO(requests)), contextlib.redirect_stdout(out):
                mcp_bridge.serve(str(store.root), args[args.index('--job') + 1], provenance)
            captured['replies'] = [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]
            return Done()

        profile = Path(tmp.name) / 'codex-home'; profile.mkdir()
        adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runner=runner,
                                          runtime_root=Path(tmp.name) / 'turns', codex_home=profile)
        service = AgentService(store, adapter=ModelAdapter(lambda *a: {'choices': [{'message': {'content': 'x'}}]}),
                               subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/codex', clock=lambda: 1),
                               execution_adapter=adapter)
        service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        for index, text in enumerate(turns):
            network_calls.clear()
            store.enqueue(text, f'k{index}')
            self.assertTrue(service.run_one())
        args = captured['args']
        provenance = [part.split('=', 1)[1] for part in args if part.startswith('--provenance=')]
        return provenance, captured['replies'][-1], network_calls

    def test_prior_private_answer_closes_web_search_in_the_real_bridge(self):
        provenance, reply, network_calls = self._service_turns(['/note PRIVATE-XYZ', '/notes', 'search the web for today news'],
                                                               query='PRIVATE-XYZ today news')
        self.assertIn('history:personal-space', provenance, 'the adapter forwards the taint to the bridge process')
        # #605: the bridge composes the lookup from permitted words only.
        self.assertIn('result', reply)
        self.assertEqual(network_calls, [{'tool': 'web_search', 'query': 'today news'}])

    def test_same_turn_note_summary_provenance_now_reaches_the_bridge(self):
        provenance, reply, network_calls = self._service_turns(['/note PRIVATE-XYZ', '/summarize'])
        self.assertIn('personal-space', provenance, 'same-turn provenance was never forwarded before this change')
        # #607: a refusal is a typed MCP tool-result error (or a protocol error).
        self.assertTrue('error' in reply or reply.get('result', {}).get('isError'))
        self.assertEqual(network_calls, [])

    def test_positive_control_first_turn_reaches_the_network_stub(self):
        provenance, reply, network_calls = self._service_turns(['hello there'])
        self.assertEqual(provenance, [])
        self.assertIn('result', reply)
        self.assertEqual(len(network_calls), 1)



class _EchoEngine:
    """Answers with a marker when Drive content was in its prompt, and records every call."""
    def __init__(self):
        self.calls = []

    def execute(self, engine, prompt, tools, **kwargs):
        self.calls.append({'prompt': prompt, 'context': kwargs.get('context')})
        answer = 'derived from DRIVE-SECRET' if 'DRIVE-SECRET' in prompt else 'plain answer'
        return ExecutionResult(answer, engine, 0)


class DestinationScopedHistory(unittest.TestCase):
    """Automated review on #574: Drive / context-inbox answers are approved for one destination only."""

    def setUp(self):
        from types import SimpleNamespace
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = QuickStore(Path(self.tmp.name) / 'state')
        self.engine = _EchoEngine()
        self.service = AgentService(self.store, adapter=ModelAdapter(lambda *a: {'choices': [{'message': {'content': 'x'}}]}),
                                    subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/cli', clock=lambda: 1),
                                    execution_adapter=self.engine,
                                    drive_web_oauth=SimpleNamespace(status=lambda: {'state': 'connected'}))
        self.service.requests_drive_access = lambda prompt: 'drive' in prompt
        self.service.selected_drive_context = lambda chat_id: 'DRIVE-SECRET contents'
        self.service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})

    def _run(self, text, key):
        self.store.enqueue(text, key, channel='telegram:1', chat_id=1)
        self.assertTrue(self.service.run_one())

    def test_a_drive_answer_is_not_carried_into_a_later_cli_turn(self):
        self._run('summarize my drive file', 'd1')
        self.assertIn('DRIVE-SECRET', self.engine.calls[-1]['prompt'], 'the Drive turn itself used the content')
        self._run('what should I do today', 'k2')
        later = self.engine.calls[-1]
        self.assertNotIn('DRIVE-SECRET', later['prompt'])
        self.assertNotIn('derived from DRIVE-SECRET', json.dumps(later['context'], ensure_ascii=False))


class OversizeRequestKeepsWorking(DestinationScopedHistory):
    """Automated review on #574: a request that fit before must not start failing because of the envelope."""

    def test_a_near_limit_prepared_request_is_sent_bare_to_codex(self):
        # A Drive excerpt makes the prepared request ~47 KB: it fit before this
        # change, but not together with the shared instructions envelope.
        self.service.selected_drive_context = lambda chat_id: 'DRIVE-SECRET ' + 'd' * 46_600
        self._run('summarize my drive file', 'big')
        call = self.engine.calls[-1]
        self.assertLessEqual(len(call['prompt'].encode()), 48_000)
        self.assertNotIn('# AgentOS instructions', call['prompt'], 'falls back to the bare request, as before')
        self.assertIsNone(call['context'])
        job = self.store.jobs()[0]
        self.assertEqual(job['status'], 'succeeded')


# -- AGENCY-BASE-01 (#603, AX-11): no-model baseline reproducers ---------------
#
# Evidence class: controlled local integration without a model.  A scripted
# model transport or scripted CLI stands in for the worker and a stub replaces
# only the public network; AgentService.run_one, turn context, Capabilities,
# provenance and the route's real tool facade run unchanged.  The
# ``test_finding_*`` tests are ``expectedFailure`` baselines of known defects
# owned by later AGENCY children (#604 bindings, #605 context/egress).  They
# are not repaired here; an unexpected pass fails the suite so the owning
# change removes the marker.  #604 fixed and un-marked the CLI weather binding;
# #605 fixed and un-marked both prior-assistant egress findings.

class _PublicNetwork:
    """Stands in for LocalTools' public reads; records every outbound plan."""
    def __init__(self):
        self.plans = []

    def execute(self, plan):
        self.plans.append(plan)
        if plan['tool'] == 'weather':
            return {'location': {'name': 'Daejeon'}, 'sources': ['https://open-meteo.com/'],
                    'forecast': {'current': {'time': '2026-09-25T12:00', 'temperature_2m': 21, 'apparent_temperature': 21,
                                             'precipitation': 1.2, 'wind_speed_10m': 5},
                                 'current_units': {'temperature_2m': '°C', 'apparent_temperature': '°C',
                                                   'precipitation': 'mm', 'wind_speed_10m': 'km/h'}}}
        return {'query': plan.get('query'), 'retrieved_at': 1, 'sources': ['https://example.org/'],
                'results': [{'title': 'news', 'url': 'https://example.org/', 'snippet': 'public snippet'}]}


class _ScriptedCli:
    """A CLI that uses the AgentOS tool the goal needs when the route offers it."""
    def __init__(self):
        self.offered, self.refusals = [], []

    def execute(self, engine, prompt, tools, **kwargs):
        names = [tool['name'] for tool in tools.definitions()]
        self.offered.append(names)
        request = (kwargs.get('context') or {}).get('request', prompt)
        wanted = ('weather', {'city': 'Daejeon', 'country': 'KR'}) if '비' in request else \
                 ('web_search', {'query': 'today news'}) if 'search' in request else None
        if wanted and wanted[0] in names:
            try:
                tools.call(*wanted)
            except Exception as exc:
                self.refusals.append(str(exc))
        return ExecutionResult('engine answer', engine, 0)


WEATHER_TURNS = ('나는 대전에 있어.', '아직 비가 내려? 우산 챙겨야 해?')


class _RouteFixture(unittest.TestCase):
    CONFIG = {'provider': 'compatible', 'endpoint': 'http://127.0.0.1:9999', 'model': 'fixture'}

    def _service(self, script=None, cli=False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'state')
        self.network, self.engine, self.requests = _PublicNetwork(), _ScriptedCli(), []

        def transport(url, body, headers):
            self.requests.append(json.loads(json.dumps(body)))
            return script(body['messages']) if script else {'choices': [{'message': {'content': 'answer'}}]}

        self.service = AgentService(self.store, adapter=ModelAdapter(transport),
                                    subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/cli', clock=lambda: 1),
                                    execution_adapter=self.engine)
        self.service.local_tools = self.network
        if cli:
            self.service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        else:
            self.store.put('model', self.CONFIG)
            self.store.put('model_test', {'ok': True, 'tools_ok': True, 'time': 9999999999,
                                          'fingerprint': self.service.model_fingerprint(self.CONFIG)})

    def _turns(self, *texts):
        for index, text in enumerate(texts):
            self.store.enqueue(text, f'k{index}')
            self.assertTrue(self.service.run_one())

    def _outbound(self, tool):
        return [plan for plan in self.network.plans if plan['tool'] == tool]


def _tool_call(name, arguments):
    return {'choices': [{'message': {'content': None, 'tool_calls': [
        {'id': 'c1', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments)}}]}}]}


def _answer(text='answer'):
    return {'choices': [{'message': {'content': text}}]}


class MissingWeatherBinding(_RouteFixture):
    """AX-S01 shape: an authorized prior city, then a rain question (no city/weather keyword pair)."""

    @staticmethod
    def _weather_model(messages):
        last = messages[-1]
        if last['role'] == 'tool':
            return _answer('대전은 지금 1.2mm 비가 옵니다.')
        if last['role'] == 'user' and '비' in last['content']:
            # #605 R2: in a clean context the worker's transliteration and a
            # validated ISO-2 country code are sent (no judgment since #654).
            return _tool_call('weather', {'city': 'Daejeon', 'country': 'KR'})
        return _answer()

    def test_direct_api_route_reaches_weather_and_returns_the_observation(self):
        """Positive control: the native binding exists and its observation reaches the next model input."""
        self._service(self._weather_model)
        self._turns(*WEATHER_TURNS)
        self.assertEqual(self._outbound('weather'), [{'tool': 'weather', 'city': 'Daejeon', 'country': 'KR'}])
        self.assertEqual(self.requests[-1]['messages'][-1]['role'], 'tool')
        self.assertIn('Daejeon', self.requests[-1]['messages'][-1]['content'])
        self.assertIn('weather', [tool['function']['name'] for tool in self.requests[-1]['tools']])

    def test_finding_cli_route_has_no_weather_binding(self):
        """Fixed by #604 (AX-02); was an ``expectedFailure`` baseline from #603.

        The CLI's tool list is derived from ``Capabilities.definitions()``
        through the trusted-local profile, so ``weather`` is offered.  Still
        owned elsewhere: the lexical preflight (#606) and the second turn's
        history taint that refuses this call once any assistant answer is in
        context (#605) -- which is why the offer, not the outbound request, is
        what this reproducer can require.
        """
        self._service(cli=True)
        self._turns(*WEATHER_TURNS)
        self.assertEqual(len(self.engine.offered), 2, 'the scripted CLI ran both turns')
        self.assertTrue(self._outbound('weather') or 'weather' in self.engine.offered[-1],
                        f'offered={self.engine.offered[-1]} outbound={self.network.plans}')


class PriorAssistantEgressDecision(_RouteFixture):
    """Which earlier assistant messages close public egress, per route.

    Defect layer for both findings (#603): the decision was taken from the
    message *role* (CLI: any assistant message -> ``conversation-history``) or
    from the file-workspace job list (API), not from the provenance of the
    source that produced the earlier answer.  #605 reads each earlier Work's
    recorded sources for exactly the messages a worker is shown.
    """

    @staticmethod
    def _search_model(messages):
        last = messages[-1]
        if last['role'] == 'user' and 'search' in last['content']:
            # The scripted model derives its query from the visible history.
            prior = [m['content'] for m in messages if m['role'] == 'assistant']
            return _tool_call('web_search', {'query': prior[-1][:80] if prior else 'today news'})
        return _answer('done') if last['role'] == 'tool' else _answer('hello back')

    def test_cli_first_turn_reaches_public_search(self):
        """Allowed control (CLI)."""
        self._service(cli=True)
        self._turns('search the web for today news')
        self.assertEqual(len(self._outbound('web_search')), 1)
        self.assertEqual(self.engine.refusals, [])

    def test_cli_prior_note_listing_closes_public_search(self):
        """Denied control (CLI): a private note listing in history never reaches search.

        Since #605 the owner's own words still do: AgentOS composes the
        lookup from text permitted for it, so the ordinary query goes out and
        the note does not.
        """
        self._service(cli=True)
        self._turns('/note PRIVATE-XYZ', '/notes', 'search the web for today news')
        self.assertEqual(self._outbound('web_search'), [{'tool': 'web_search', 'query': 'today news'}])
        self.assertNotIn('PRIVATE-XYZ', json.dumps(self.network.plans))

    def test_api_first_turn_reaches_public_search(self):
        """Allowed control (API)."""
        self._service(self._search_model)
        self._turns('search the web for today news')
        self.assertEqual(self._outbound('web_search'), [{'tool': 'web_search', 'query': 'today news'}])

    def test_finding_cli_benign_prior_answer_closes_public_search(self):
        """Fixed by #605 (AX-04); was an ``expectedFailure`` baseline from #603.
        Over-restriction: a greeting answer is not private material, yet
        ``run_one`` tainted the CLI Work with ``conversation-history`` and the
        refusal text blamed connected documents that were never read."""
        self._service(cli=True)
        self._turns('hello there', 'search the web for today news')
        self.assertEqual(self.engine.refusals, [])
        self.assertEqual(len(self._outbound('web_search')), 1)

    def test_finding_api_prior_private_answer_does_not_close_public_search(self):
        """Fixed by #605 (AX-04); was an ``expectedFailure`` baseline from #603.
        Under-restriction on the API route: a note listing answered earlier
        stayed in the visible history untainted, so a model-composed query
        carrying it reached the public search host."""
        self._service(self._search_model)
        self._turns('/note PRIVATE-XYZ', '/notes', 'search the web for it')
        self.assertTrue(self.requests, 'the scripted model was consulted')
        self.assertFalse([plan for plan in self._outbound('web_search') if 'PRIVATE-XYZ' in plan['query']],
                         self.network.plans)

if __name__ == '__main__':
    unittest.main()
