"""ORCH-01 (#710): the Judgment AI orchestrates each Work.

Evidence class: model-free unit and service tests.  A scripted
``FixtureDecisionEngine`` plays the Judgment AI (plan and ``goal_reached``),
a fixture HTTP transport plays the API worker, and a fake execution adapter
plays the subscription CLI; the real ``AgentService.run_one``, ``run_agent``,
``Capabilities``, bridge argv/config builders and ``mcp_bridge.serve`` run
unchanged.  No live model, CLI, account or credential is used, and no
request, site, provider or category is named in ``src``.
"""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from personal_agent import browser_session as bs
from personal_agent import mcp_bridge
from personal_agent.agent_runtime import GOAL_NOT_SHOWN, GOAL_UNJUDGED, WorkBudget, render_turn_prompt, turn_context
from personal_agent.bounded_execution import (BOUNDED_PROFILE, AgentOSMcpTools, BoundedExecutionAdapter,
                                              ExecutionError, ExecutionResult, turn_actions)
from personal_agent.conversation_handoff import ConversationJudgments
from personal_agent.decision import (OUTCOME_DECIDED, OUTCOME_MALFORMED, OUTCOME_UNAVAILABLE, STRUCTURED_UNSUPPORTED,
                                     BinaryDecision, DecisionContext, DecisionPolicy, FixtureDecisionEngine,
                                     ModelDecisionEngine, RoutedDecisionEngine, StructuredDecision,
                                     UnavailableDecisionEngine, audit_record, fixture_confidence)
from personal_agent.decision_adapters import JevDecisionEngine
from personal_agent.orchestrator import (ATTEMPTS_CHARS, EVENT_TOOL, FALLBACK_TEXT, MAX_REDELEGATIONS, NOTICE_ONCE,
                                         QUESTION, SECTIONS, Attempt, Catalogue, Orchestration, plan_schema,
                                         render_catalogue)
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.subscription_engines import SubscriptionEngines

OPENAI_KEY = 'sk-fixture-openai-0710'
#: A bundled listing without the ranked gpt-6-luna (codex-cli 0.153.4 shape).
BUNDLED = ('gpt-5.6-terra', 'gpt-5.6-luna', 'gpt-5.5')
SEARCH_TOOLS = ('bounded_public_research', 'web_search')
#: #795: what ``cli_metadata`` reports for a complete CLI stream with no tool
#: call.  A trusted-local attempt is re-delegated only when its CLI reported this much.
NO_TOOL_CALLS = {'tool_calls': [], 'stream_tail': ['thread.started', 'turn.started', 'turn.completed']}


def reported(calls, end='turn.completed'):
    """``cli_metadata``'s shape for a stream that ended with ``end`` and reported ``calls``."""
    return {'tool_calls': list(calls), 'stream_tail': ['turn.started', end]}


def plan(worker, notes, *, model='', reason='fits'):
    """One plan (#820, #826): worker, model and optional notes; it never selects context, criteria or a tool subset."""
    return {'worker': worker, 'model': model, 'brief': {'notes': notes}, 'reason': reason}


def decided(data, probability=0.9):
    return StructuredDecision(OUTCOME_DECIDED, data, fixture_confidence(probability))


class Transport:
    """OpenAI-shaped chat completions: the connection probe, then scripted answers."""

    def __init__(self):
        self.bodies = []
        self.answers = []

    def __call__(self, url, body, headers=None, timeout=60):
        tools = body.get('tools') or []
        names = [(tool.get('function') or {}).get('name') for tool in tools]
        if 'agentos_connection_probe' in names:
            return {'model': body['model'], 'choices': [{'message': {'role': 'assistant', 'tool_calls': [
                {'id': 'p1', 'type': 'function', 'function': {'name': 'agentos_connection_probe', 'arguments': '{}'}}]}}]}
        if not tools:
            return {'model': body['model'], 'choices': [{'message': {'role': 'assistant', 'content': 'ok'}}]}
        self.bodies.append(json.loads(json.dumps(body)))
        answer = self.answers.pop(0) if self.answers else 'api answer'
        return {'model': body['model'], 'choices': [{'message': {'role': 'assistant', 'content': answer}}]}


class Engine:
    """A fake subscription CLI: records what each turn was given and answers."""

    def __init__(self):
        self.turns = []
        self.answers = []
        self.before = None
        self.fail = []
        self.meta = dict(NO_TOOL_CALLS)

    def execute(self, engine, prompt, tools, **kwargs):
        offered = sorted(tools._offered())
        self.turns.append({'engine': engine, 'prompt': prompt, 'model': kwargs.get('model'),
                           'native_search': tools.native_search, 'reason': tools.native_search_reason,
                           'offered': offered,
                           'context': kwargs.get('context')})
        if self.before:
            self.before(tools)
        if self.fail:
            raise self.fail.pop(0)
        return ExecutionResult(self.answers.pop(0) if self.answers else 'cli answer', engine, 0, self.meta)

    def login_status(self, engine_id, binary=None):
        return {'state': 'signed-in'}


class Harness(unittest.TestCase):
    """Two configured workers: Codex (the default Main AI) and a verified OpenAI API route."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.store = QuickStore(self.tmp / 'state')
        self.transport = Transport()
        self.engine = Engine()
        self.service = AgentService(self.store, adapter=ModelAdapter(self.transport),
                                    subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/cli', clock=lambda: 1),
                                    execution_adapter=self.engine,
                                    browser_profile=bs.BrowserProfile(self.tmp / 'browser', available=lambda: False))
        self.service.use_decision_engine(UnavailableDecisionEngine())
        # The owner connected OpenAI with 확인하고 사용, then made Codex the Main AI.
        self.service.save_main_ai_key({'provider': 'openai', 'key': OPENAI_KEY})
        with mock.patch.object(self.service.decision_routes, 'follow_main_switched', return_value={'state': 'skipped'}):
            self.service.activate_main_ai({'route': 'openai'})
            self.service.activate_main_ai({'route': 'codex'})
        self.assertEqual(self.service.main_ai.current(), 'codex')
        # #735: what `codex debug models --bundled` lists for the installed binary.
        self.service.decision_routes.bundled_models = lambda engine: list(BUNDLED)
        self.plans, self.goals = [], []
        self.asked_plans = []

    def script(self, plans, goals=(), owner_inputs=()):
        """The Judgment AI: ``plans`` answer the plan calls in order, ``goals`` the CLI goal judgments,
        ``owner_inputs`` the #740 owner-input judgments asked after a goal judged no."""
        self.plans, self.goals, self.owner_inputs = list(plans), list(goals), list(owner_inputs)
        self.asked_owner_inputs = []
        self.asked_goals = []

        def structured(context, question, schema):
            self.asked_plans.append((context, question, schema))
            if not self.plans:
                return None
            item = self.plans.pop(0)
            return item if isinstance(item, StructuredDecision) or item is None else decided(item)

        def judge(context, proposition):
            if context.purpose == 'owner-input-needed':
                self.asked_owner_inputs.append(context)
                if self.owner_inputs:
                    return BinaryDecision(OUTCOME_DECIDED, self.owner_inputs.pop(0), fixture_confidence())
                return None
            if context.purpose == 'goal-reached':
                self.asked_goals.append(context)
            if context.purpose != 'goal-reached' or not self.goals:
                return None
            return BinaryDecision(OUTCOME_DECIDED, self.goals.pop(0), fixture_confidence())
        engine = FixtureDecisionEngine(structured=structured, judge=judge)
        self.service.use_decision_engine(engine)
        return engine

    def run_work(self, text, key=None):
        job = self.store.enqueue(text, key or f'orch-{len(self.engine.turns)}-{len(self.transport.bodies)}-{text}')
        self.assertTrue(self.service.run_one())
        return job, self.store.job(job)

    def codex_tools(self):
        from personal_agent.orchestrator import worker_catalogue
        return worker_catalogue(self.service).worker('codex')['tools']

    def events(self, job, status=None):
        with self.store.db() as db:
            rows = db.execute('SELECT status,detail FROM tool_events WHERE job_id=? AND tool=? ORDER BY id',
                              (job, EVENT_TOOL)).fetchall()
        return [(row['status'], json.loads(row['detail'])) for row in rows if status is None or row['status'] == status]


class RoutingAndBriefs(Harness):
    def test_different_requests_go_to_different_workers_and_models_with_their_own_briefs(self):
        self.script([plan('codex', 'Find and compare the two options the owner named; cite each source.',
                          model='gpt-5.6-luna'),
                     plan('openai', 'Rewrite the owner\'s paragraph in a warmer tone, same meaning.')],
                    goals=[True])
        first, row = self.run_work('이 두 가지 비교해줘')
        self.assertEqual(row['status'], 'succeeded')
        self.assertEqual(len(self.engine.turns), 1)
        turn = self.engine.turns[0]
        self.assertEqual((turn['engine'], turn['model']), ('codex', 'gpt-5.6-luna'))
        self.assertIn('# Orchestration notes', turn['prompt'])
        self.assertIn('Find and compare the two options', turn['prompt'])
        self.assertNotIn('Done when:', turn['prompt'], '#820: a plan writes no completion criteria')
        self.assertIn('# Current request\n이 두 가지 비교해줘', turn['prompt'], 'the owner\'s words stay the request')

        second, row = self.run_work('이 문단 다정하게 다시 써줘')
        self.assertEqual(row['status'], 'succeeded')
        self.assertEqual(row['response'], 'api answer')
        self.assertEqual(len(self.engine.turns), 1, 'the CLI did not run the second request')
        # run_agent's own execution check may ask the model once more (#606); the first turn carries the brief.
        body = self.transport.bodies[0]
        self.assertEqual({item['model'] for item in self.transport.bodies}, {'gpt-4o-mini'})
        system = body['messages'][0]['content']
        self.assertIn('Rewrite the owner\'s paragraph in a warmer tone', system)
        self.assertEqual(body['messages'][-1], {'role': 'user', 'content': '이 문단 다정하게 다시 써줘'})
        # Each plan call saw the owner's request and both available workers.
        requests = [context.facts['owner_request'] for context, _q, _s in self.asked_plans]
        self.assertEqual(requests, ['이 두 가지 비교해줘', '이 문단 다정하게 다시 써줘'])
        self.assertEqual(set(self.asked_plans[0][2]['properties']['worker']['enum']), {'codex', 'openai'})
        # Evidence: worker, model, brief digest and the one-line reason, never the brief text.
        [(status, planned)] = self.events(first, 'planned')
        self.assertEqual((planned['worker'], planned['model'], planned['reason']), ('codex', 'gpt-5.6-luna', 'fits'))
        self.assertRegex(planned['brief_digest'], r'^[0-9a-f]{16}$')
        self.assertNotIn('Find and compare', json.dumps(planned))
        self.assertIn('Codex · gpt-5.6-luna', planned['text'])
        [(_s, evaluated)] = self.events(first, 'evaluated')
        self.assertEqual((evaluated['outcome'], evaluated['next'], evaluated['stop']), ('reached', 'stop', 'reached'))
        [(_s, planned)] = self.events(second, 'planned')
        # #804, #820: every section is always given; a plan selects none.
        self.assertEqual((planned['worker'], planned['model'], planned['sections']),
                         ('openai', None, ['current_context', 'history', 'prepared', 'profile']))

    def test_a_plan_never_drops_the_conversation_the_worker_receives(self):
        """#820: the conversation always reaches the worker; the plan's notes only add to it."""
        self.store.put('model', self.store.config('model', {}))
        self.store.enqueue('앞선 질문', 'orch-history')
        self.engine.answers = ['first']
        self.service.use_decision_engine(UnavailableDecisionEngine())
        self.assertTrue(self.service.run_one())
        self.script([plan('codex', 'Answer from general knowledge.')], goals=[True])
        self.run_work('다음 질문')
        context = self.engine.turns[-1]['context']
        self.assertEqual([m['content'] for m in context['conversation']], ['앞선 질문', 'first'])
        self.assertEqual(context['request'], '다음 질문')
        self.assertEqual(context['brief'], 'Answer from general knowledge.')


class Redelegation(Harness):
    def test_a_shortfall_is_redelegated_with_an_adjusted_brief_to_another_worker(self):
        self.script([plan('codex', 'Look it up.'), plan('openai', 'Explain it step by step with the definition first.')],
                    goals=[False])
        job, row = self.run_work('이것 좀 알려줘')
        self.assertEqual(row['status'], 'succeeded')
        self.assertEqual(row['response'], 'api answer', 'the owner gets the attempt that reached the goal')
        self.assertEqual(len(self.engine.turns), 1)
        self.assertTrue(self.transport.bodies)
        self.assertIn('An earlier attempt\'s reply was judged not to serve', self.transport.bodies[0]['messages'][0]['content'])
        # The re-plan saw the first attempt and its evaluation.
        attempts = self.asked_plans[1][0].facts['previous_attempts']
        self.assertIn('attempt 1: worker=codex', attempts)
        self.assertIn('evaluation=not_reached', attempts)
        self.assertIn('cli answer', attempts)
        rows = [(status, detail.get('attempt'), detail.get('worker'), detail.get('outcome'), detail.get('next'))
                for status, detail in self.events(job)]
        self.assertEqual(rows, [('planned', 1, 'codex', None, None), ('evaluated', 1, 'codex', 'not_reached', 'redelegate'),
                                ('planned', 2, 'openai', None, None), ('evaluated', 2, 'openai', 'reached', 'stop')])
        digests = [detail['brief_digest'] for status, detail in self.events(job, 'planned')]
        self.assertNotEqual(digests[0], digests[1])

    def test_at_most_two_redelegations(self):
        # #729: each re-plan must change the worker, model or tools.
        self.script([plan('codex', f'Try path {n}.', model=model)
                     for n, model in enumerate(('', 'gpt-5.6-luna', 'gpt-5.6-terra', 'haiku', 'sonnet'))],
                    goals=[False] * 5)
        job, row = self.run_work('끝까지 해줘')
        self.assertEqual(len(self.engine.turns), 1 + MAX_REDELEGATIONS)
        self.assertEqual(len(self.asked_plans), 1 + MAX_REDELEGATIONS)
        last = self.events(job, 'evaluated')[-1][1]
        self.assertEqual((last['attempt'], last['next'], last['stop']), (3, 'stop', 'limit'))
        self.assertEqual(row['response'], 'cli answer')
        # Review P1: judged short and not re-delegated is never stored as succeeded;
        # no tool result was observed, so it failed.
        self.assertEqual(row['status'], 'failed')
        self.assertIn(GOAL_NOT_SHOWN, row['owner_cause'])

    def test_a_cli_attempt_judged_short_with_an_observation_is_partial(self):
        def search(tools):
            tools.capabilities.record('web_search', 'succeeded',
                                      json.dumps({'host_action': 'web_search', 'evidence': {'sources': ['https://a.test']}}))
        self.engine.before = search
        self.script([plan('codex', 'Look it up.')], goals=[False])
        job, row = self.run_work('찾아줘')
        self.assertEqual(self.events(job, 'evaluated')[-1][1]['stop'], 'replan_failed')
        self.assertEqual(row['status'], 'partial')
        self.assertIn(GOAL_NOT_SHOWN, row['owner_cause'])

    def test_a_cli_attempt_that_could_not_be_judged_is_partial_with_the_unknown_stated(self):
        self.script([plan('codex', 'Look it up.')], goals=[])
        job, row = self.run_work('찾아줘')
        last = self.events(job, 'evaluated')[-1][1]
        self.assertEqual((last['outcome'], last['stop']), ('unjudged', 'unjudged'))
        self.assertEqual(row['status'], 'partial')
        self.assertIn(GOAL_UNJUDGED, row['owner_cause'])

    def test_no_redelegation_when_the_work_budget_is_nearly_spent(self):
        clock = [0.0]
        self.service.work_budget = lambda job_id: WorkBudget(clock=lambda: clock[0], seconds=600)
        self.engine.before = lambda tools: clock.__setitem__(0, clock[0] + 590)
        self.script([plan('codex', 'Look it up.'), plan('openai', 'Other path.')], goals=[False])
        job, _row = self.run_work('시간 걸리는 일')
        self.assertEqual(len(self.engine.turns), 1)
        self.assertEqual(self.transport.bodies, [])
        # Review P2-3: the deadline is checked before each call, so neither the
        # goal judgment nor a re-plan is asked once the time is short.
        self.assertEqual(self.goals, [False], 'no goal_reached call')
        self.assertEqual(len(self.asked_plans), 1, 'no plan call')
        last = self.events(job, 'evaluated')[-1][1]
        self.assertEqual((last['outcome'], last['stop']), ('not_judged', 'budget'))

    def test_the_deadline_is_checked_again_before_the_replan(self):
        clock = [0.0]
        self.service.work_budget = lambda job_id: WorkBudget(clock=lambda: clock[0], seconds=600)
        self.script([plan('codex', 'Look it up.'), plan('openai', 'Other path.')])

        def judge(context, proposition):
            # The goal judgment itself uses up the Work's remaining time.
            clock[0] += 590
            return BinaryDecision(OUTCOME_DECIDED, False, fixture_confidence())
        self.service.decision_engine._judge = judge
        job, _row = self.run_work('시간 걸리는 일')
        self.assertEqual(len(self.asked_plans), 1, 'the re-plan call was not made')
        self.assertEqual(self.transport.bodies, [])
        last = self.events(job, 'evaluated')[-1][1]
        self.assertEqual((last['outcome'], last['stop']), ('not_reached', 'budget'))

    def test_a_later_attempt_keeps_this_works_private_reads_in_its_record(self):
        """Review P2-1 / #826: attempt 1 read notes; attempt 2 keeps the CLI's own web search and the
        private reads together (owner decision), and the envelope stays size/digest only."""
        def read_notes(tools):
            if len(self.engine.turns) == 1:
                tools.capabilities.record('list_notes', 'succeeded',
                                          json.dumps({'host_action': 'list_notes', 'evidence': {'count': 1}}))
        self.engine.before = read_notes
        self.script([plan('codex', 'Read the saved notes.'), plan('codex', 'Answer from them.', model='gpt-5.6-luna')],
                    goals=[False, True])
        job, row = self.run_work('메모 확인해줘')
        self.assertEqual(len(self.engine.turns), 2)
        first, second = self.engine.turns
        self.assertTrue(second['native_search'])
        self.assertIn('list_notes', second['offered'])
        record = self.store.turn_provenance(job)
        self.assertTrue(record['prompt_envelope'].startswith('[not stored'), record['prompt_envelope'])
        self.assertIn('personal-space', record['prompt_withheld'])
        self.assertIn('personal-space', record['egress_taint'])
        self.assertEqual(row['status'], 'succeeded')

    def test_no_redelegation_after_an_attempt_that_ran_an_effect(self):
        def effect(tools):
            tools.capabilities.record('save_note', 'succeeded', json.dumps({'host_action': 'save_note', 'evidence': {}}))
        self.engine.before = effect
        self.script([plan('codex', 'Save it.'), plan('openai', 'Save it again.')], goals=[False])
        job, _row = self.run_work('이거 처리해줘')
        self.assertEqual(len(self.engine.turns), 1)
        self.assertEqual(len(self.asked_plans), 1, 'no re-plan after an effect')
        self.assertEqual(self.events(job, 'evaluated')[-1][1]['stop'], 'effect')
        self.assertEqual(self.goals, [False], 'no judgment was asked when nothing may follow')

    def test_a_failed_worker_is_redelegated(self):
        self.engine.fail = [ExecutionError('usage limit', failure_class='usage-limit', meta=NO_TOOL_CALLS)]
        self.script([plan('codex', 'Look it up.'), plan('openai', 'Answer directly.')])
        job, row = self.run_work('알려줘')
        self.assertEqual(row['status'], 'succeeded')
        self.assertEqual(row['response'], 'api answer')
        first = self.events(job, 'evaluated')[0][1]
        self.assertEqual((first['outcome'], first['next']), ('worker_failed', 'redelegate'))

    def test_a_failed_worker_without_a_new_plan_fails_as_before(self):
        self.engine.fail = [ExecutionError('usage limit', failure_class='usage-limit', meta=NO_TOOL_CALLS)]
        self.script([plan('codex', 'Look it up.')])
        job, row = self.run_work('알려줘')
        self.assertEqual(row['status'], 'failed')
        self.assertEqual(self.events(job, 'evaluated')[-1][1]['stop'], 'replan_failed')


class Fallback(Harness):
    def assert_default_raw_run(self, job, code):
        [turn] = self.engine.turns
        self.assertEqual((turn['engine'], turn['model']), ('codex', None))
        self.assertNotIn('# Brief for this attempt', turn['prompt'])
        [(status, detail)] = self.events(job)
        self.assertEqual((status, detail['code'], detail['worker']), ('fallback', code, 'codex'))
        self.assertEqual(detail['text'], FALLBACK_TEXT[code])

    def test_unavailable_judgment_ai_runs_the_default_with_the_raw_request(self):
        job, row = self.run_work('알려줘')
        self.assertEqual(row['status'], 'succeeded')
        self.assert_default_raw_run(job, 'judgment_unavailable')
        self.assertNotIn(NOTICE_ONCE, row['response'], 'nothing changed: orchestration never worked here')

    def test_an_invalid_plan_runs_the_default_with_the_raw_request(self):
        for bad, what in ((plan('codex', 'x', model='not-a-listed-model'), 'model'),
                          (plan('not-a-worker', 'x'), 'worker')):
            with self.subTest(what=what):
                self.engine.turns.clear()
                self.script([bad])
                job, row = self.run_work('알려줘', key=f'bad-{what}')
                self.assert_default_raw_run(job, 'plan_invalid')
                self.assertEqual(self.events(job)[0][1]['invalid'], what)

    def test_a_malformed_or_unconfident_plan_falls_back(self):
        for answer, code in ((StructuredDecision(OUTCOME_MALFORMED), 'plan_malformed'),
                             (decided(plan('codex', 'x'), probability=0.2), 'plan_unconfident')):
            with self.subTest(code=code):
                self.engine.turns.clear()
                self.script([answer])
                job, _row = self.run_work('알려줘', key=f'weak-{code}')
                self.assert_default_raw_run(job, code)

    def test_the_owner_is_told_once_when_working_orchestration_falls_back(self):
        self.script([plan('codex', 'Look it up.')], goals=[True])
        _job, row = self.run_work('하나')
        self.assertNotIn(NOTICE_ONCE, row['response'])
        self.service.use_decision_engine(UnavailableDecisionEngine())
        _job, row = self.run_work('둘')
        self.assertTrue(row['response'].endswith(NOTICE_ONCE))
        _job, row = self.run_work('셋')
        self.assertNotIn(NOTICE_ONCE, row['response'], 'said once, not on every turn')


class PrivateReadsWithSearch(Harness):
    """EGRESS-OPEN-01 (#826): private reads and the CLI's own web search run in the same attempt."""

    def test_private_reads_and_the_clis_own_search_are_offered_together(self):
        self.script([plan('codex', 'Answer.')], goals=[True])
        self.run_work('메모에서 찾아서 웹에서도 확인해줘')
        [turn] = self.engine.turns
        self.assertTrue(turn['native_search'])
        for name in ('list_notes', 'list_memory', 'calendar_query', 'find_files', 'read_file', 'list_roots', 'save_memory'):
            self.assertIn(name, turn['offered'])
        self.assertFalse(set(turn['offered']) & set(SEARCH_TOOLS), 'the CLI\'s own search replaces the bridge search')

    def test_the_claude_allowlist_pre_approves_private_reads_beside_websearch(self):
        adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runner=lambda *a, **k: None,
                                          runtime_root=self.tmp / 'turns')
        config = self.tmp / 'mcp.json'
        config.write_text(json.dumps({'mcpServers': {'agentos': {'args': []}}}))
        argv = adapter.command('claude-code', '/runtime/claude', 'p', config, native_search=True)
        allowed = argv[-1].split(',')
        self.assertIn('WebSearch', allowed)
        for name in ('list_notes', 'list_memory', 'find_files', 'read_file'):
            self.assertIn('mcp__agentos__' + name, allowed)
        self.assertNotIn('mcp__agentos__web_search', allowed)
        self.assertEqual(turn_actions(BOUNDED_PROFILE, native_search=True),
                         tuple(name for name in turn_actions(BOUNDED_PROFILE) if name not in SEARCH_TOOLS))

    def test_the_bridge_process_serves_private_reads_on_a_native_search_turn(self):
        job = self.store.enqueue('메모', 'bridge-native')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job,))
        requests = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
                    {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}]
        out = io.StringIO()
        with mock.patch.object(sys, 'stdin', io.StringIO(''.join(json.dumps(r) + '\n' for r in requests))), \
                mock.patch.object(sys, 'stdout', out):
            mcp_bridge.serve(str(self.store.root), job, native_search=True)
        replies = [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]
        names = [tool['name'] for tool in replies[1]['result']['tools']]
        for name in ('list_notes', 'find_files', 'read_file', 'list_roots', 'public_page_read'):
            self.assertIn(name, names)
        self.assertNotIn('web_search', names)


class ToolsAndReplan(Harness):
    """ORCH-02 (#729): full toolset by default, learning from failed attempts, the bridge timeout."""

    def test_the_worker_always_keeps_its_full_toolset(self):
        """#826: the plan has no tool subset (its one reason, keeping private reads and search apart, is gone)."""
        self.assertIn('The worker keeps its full offered toolset', QUESTION)
        self.script([plan('codex', 'Answer.')], goals=[True])
        job, _row = self.run_work('알려줘')
        [turn] = self.engine.turns
        self.assertIn('weather', turn['offered'], 'the full offered toolset, not a subset')
        context, _question, schema = self.asked_plans[0]
        self.assertEqual(set(schema['required']), {'worker', 'model', 'brief', 'reason'})
        descriptions = context.facts['tool_descriptions']
        self.assertIn('- bounded_public_research: ', descriptions)
        self.assertIn('- list_notes: ', descriptions)
        self.assertTrue(all(len(line) < 260 for line in descriptions.splitlines()), 'one line per tool')
        self.assertNotIn('tools', self.events(job, 'planned')[0][1])

    def test_a_replan_never_repeats_a_failed_combination_and_sees_the_incomplete_call(self):
        def hang(tools):
            # The bridge recorded the call as running; the CLI closed the connection before a result.
            tools.capabilities.record('bounded_public_research', 'running', json.dumps(
                {'scope': 'subscription-mcp-bridge', 'host_action': 'bounded_public_research'}))
        self.engine.before = hang
        first = plan('codex', 'Research it.')
        self.script([first, dict(first)], goals=[False])
        job, row = self.run_work('조사해줘')
        self.assertEqual(len(self.engine.turns), 1, 'the identical combination was not run again')
        last = self.events(job, 'evaluated')[-1][1]
        self.assertEqual((last['stop'], last['invalid']), ('replan_failed', 'repeat'))
        replan = self.asked_plans[1][0].facts['previous_attempts']
        self.assertIn('tools called: bounded_public_research', replan)
        self.assertIn('never completed (tool_incomplete): bounded_public_research', replan)
        self.assertIn('did not show the goal met', replan)
        with self.store.db() as db:
            failed = [json.loads(r['detail']) for r in db.execute(
                "SELECT detail FROM tool_events WHERE job_id=? AND tool='bounded_public_research' AND status='failed'", (job,))]
        self.assertEqual([(item['code'], item['retry'], item['effect']) for item in failed],
                         [('tool_incomplete', 'transient', 'none')])
        self.assertNotEqual(row['status'], 'succeeded')

    def test_a_changed_model_is_allowed_after_a_failure(self):
        self.script([plan('codex', 'Research it.'), plan('codex', 'Try another model.', model='gpt-5.6-luna')],
                    goals=[False, True])
        job, row = self.run_work('조사해줘')
        self.assertEqual(len(self.engine.turns), 2)
        self.assertEqual(self.engine.turns[1]['model'], 'gpt-5.6-luna')
        self.assertEqual(row['status'], 'succeeded')

    def test_an_incomplete_effect_is_recorded_as_unknown(self):
        def hang(tools):
            tools.capabilities.record('save_note', 'running', json.dumps(
                {'scope': 'subscription-mcp-bridge', 'host_action': 'save_note'}))
        self.engine.before = hang
        self.script([plan('codex', 'Save it.')], goals=[False])
        job, row = self.run_work('처리해줘')
        with self.store.db() as db:
            [detail] = [json.loads(r['detail']) for r in db.execute(
                "SELECT detail FROM tool_events WHERE job_id=? AND tool='save_note' AND status='failed'", (job,))]
        self.assertEqual((detail['code'], detail['effect']), ('tool_incomplete', 'unknown'))
        self.assertEqual(row['status'], 'unknown')

    def test_goal_reached_sees_the_model_stated_answer_when_native_search_has_no_urls(self):
        seen = []
        self.engine.meta = {**NO_TOOL_CALLS, 'native_searches': [{'id': 'n1', 'state': 'succeeded', 'queries': ['q'], 'results': []}]}
        self.engine.answers = ['about forty minutes by car']
        self.script([plan('codex', 'Answer it.'), plan('openai', 'Answer it another way.')])

        def judge(context, proposition):
            seen.append(dict(context.facts))
            return BinaryDecision(OUTCOME_DECIDED, False, fixture_confidence())
        self.service.decision_engine._judge = judge
        self.run_work('얼마나 걸려?')
        # #820: the reply is its own fact, labelled model-stated by the proposition; the observations are tools' results.
        self.assertEqual(seen[0]['reply'], 'about forty minutes by car')
        self.assertIn('"sources": []', seen[0]['observations'])
        self.assertIn('own web searches that reported no source URL: 1', self.asked_plans[1][0].facts['previous_attempts'])


class RunnableModels(Harness):
    """#735: only bundled models, and a model the account refused never comes back."""

    def test_codex_offers_only_bundled_listed_models(self):
        from personal_agent.orchestrator import worker_catalogue
        models = worker_catalogue(self.service).worker('codex')['models']
        self.assertEqual(set(models), set(BUNDLED))
        self.assertNotIn('gpt-6-luna', models, 'ranked but not bundled by the installed binary')
        self.service.decision_routes.bundled_models = lambda engine: None
        self.assertEqual(worker_catalogue(self.service).worker('codex')['models'], [],
                         'no listing: only the worker default')

    def test_a_refused_model_is_remembered_and_never_repeated(self):
        from personal_agent.orchestrator import MODEL_REFUSALS_KEY, worker_catalogue
        refusal = "The 'gpt-5.6-luna' model is not supported when using Codex with a ChatGPT account."
        self.engine.fail = [ExecutionError('Codex 엔진이 작업을 완료하지 못했습니다(종료 코드 1). 엔진 응답: ' + refusal,
                                           failure_class='request-rejected', exit_code=1, reason=refusal,
                                           meta={**NO_TOOL_CALLS, 'unsupported_model': 'gpt-5.6-luna'})]
        self.script([plan('codex', 'Answer.', model='gpt-5.6-luna'), plan('codex', 'Answer.', model='gpt-5.6-luna')])
        job, row = self.run_work('알려줘')
        self.assertEqual(len(self.engine.turns), 1, 'the refused model did not run again')
        last = self.events(job, 'evaluated')[-1][1]
        self.assertEqual((last['stop'], last['invalid']), ('replan_failed', 'model'))
        stored = self.store.config(MODEL_REFUSALS_KEY, {})
        self.assertEqual(set(stored['codex']), {'gpt-5.6-luna'})
        self.assertNotIn(refusal, json.dumps(stored), 'no refusal text is kept')
        self.assertNotIn('gpt-5.6-luna', worker_catalogue(self.service).worker('codex')['models'])
        self.assertEqual(row['status'], 'failed')

    def test_another_rejection_is_not_a_model_refusal(self):
        """#735 review: a generic rejection that names the model (context length) is not a refusal."""
        from personal_agent.orchestrator import MODEL_REFUSALS_KEY, model_refused
        context = "This model's maximum context length for gpt-5.6-luna is exceeded."
        self.engine.fail = [ExecutionError('rejected: ' + context, failure_class='request-rejected', reason=context,
                                           meta=NO_TOOL_CALLS)]
        self.script([plan('codex', 'Answer.', model='gpt-5.6-luna')])
        self.run_work('알려줘')
        self.assertEqual(self.store.config(MODEL_REFUSALS_KEY, {}), {})
        self.assertFalse(model_refused('gpt-5.5', {}))
        self.assertFalse(model_refused('', {'unsupported_model': ''}))
        self.assertFalse(model_refused('gpt-5.5', {'unsupported_model': 'gpt-5.6-luna'}))

    def test_a_refused_configured_default_is_substituted_by_the_next_runnable_model(self):
        """#735 review, choice recorded: "" runs the next runnable model; with none left the worker is unavailable."""
        from personal_agent.main_ai import SUBSCRIPTION_MODELS
        from personal_agent.orchestrator import remember_model_refusal, worker_catalogue
        self.store.put(SUBSCRIPTION_MODELS, {'codex': 'gpt-5.6-luna'})
        remember_model_refusal(self.store, 'codex', 'gpt-5.6-luna')
        codex = worker_catalogue(self.service).worker('codex')
        self.assertEqual((codex['default_model'], codex['default_refused'], codex['available']),
                         ('gpt-5.6-terra', 'gpt-5.6-luna', True))
        self.assertNotIn('gpt-5.6-luna', codex['models'])
        self.script([plan('codex', 'Answer.')], goals=[True])
        job, _row = self.run_work('알려줘')
        self.assertEqual(self.engine.turns[0]['model'], 'gpt-5.6-terra', 'the refused default is never run')
        self.assertEqual(self.events(job, 'planned')[0][1]['model'], 'gpt-5.6-terra')
        for model in BUNDLED:
            remember_model_refusal(self.store, 'codex', model)
        codex = worker_catalogue(self.service).worker('codex')
        self.assertEqual((codex['available'], codex['reason']), (False, 'default_model_refused'))

    def test_a_default_refused_mid_work_is_not_resolved_again(self):
        from personal_agent.main_ai import SUBSCRIPTION_MODELS
        self.store.put(SUBSCRIPTION_MODELS, {'codex': 'gpt-5.6-luna'})
        refusal = "The 'gpt-5.6-luna' model is not supported when using Codex with a ChatGPT account."
        self.engine.fail = [ExecutionError(refusal, failure_class='request-rejected', reason=refusal,
                                           meta={**NO_TOOL_CALLS, 'unsupported_model': 'gpt-5.6-luna'})]
        self.script([plan('codex', 'Answer.'), plan('codex', 'Answer again.')], goals=[True])
        self.run_work('알려줘')
        self.assertEqual([turn['model'] for turn in self.engine.turns], ['gpt-5.6-luna', 'gpt-5.6-terra'])

    def test_a_refusal_expires(self):
        from personal_agent.orchestrator import MODEL_REFUSAL_TTL_SECONDS, refused_models, remember_model_refusal
        remember_model_refusal(self.store, 'codex', 'gpt-5.5', now=1000)
        self.assertEqual(refused_models(self.store, now=1001), {'codex': {'gpt-5.5'}})
        self.assertEqual(refused_models(self.store, now=1000 + MODEL_REFUSAL_TTL_SECONDS), {'codex': set()})


class BundledListing(__import__('test_decision_routes').ServiceFixture):
    """#735: `codex debug models --bundled` runs in an empty CODEX_HOME, once per installed binary."""

    def test_the_bundled_listing_is_cached_per_binary(self):
        service = self.service()
        self.assertEqual(service.decision_routes.bundled_models('codex'), ['gpt-5.6-terra', 'gpt-5.6-luna'],
                         'hidden models are not offered')
        self.assertEqual(service.decision_routes.bundled_models('codex'), ['gpt-5.6-terra', 'gpt-5.6-luna'])
        listings = [call for call in self.runner.calls if call['argv'][1:3] == ['debug', 'models']]
        self.assertEqual([call['argv'][1:] for call in listings], [['debug', 'models', '--bundled']], 'run once')
        self.assertTrue(all(call['env']['CODEX_HOME'] == call['env']['HOME'] == call['cwd'] for call in listings),
                        'an empty per-call CODEX_HOME')
        self.assertIsNone(service.decision_routes.bundled_models('claude-code'), 'no machine-readable listing')

    def test_a_failed_listing_is_cached_per_binary_too(self):
        """#735 review: a binary whose `--bundled` listing failed is not re-run on every Work."""
        from test_decision_routes import CliRunner
        service = self.service(runner=CliRunner(bundled=''))
        self.assertIsNone(service.decision_routes.bundled_models('codex'))
        self.assertIsNone(service.decision_routes.bundled_models('codex'))
        listings = [call for call in self.runner.calls if call['argv'][1:3] == ['debug', 'models']]
        self.assertEqual(len(listings), 1, 'the failed discovery is cached for this binary')
        self.assertTrue(self.store.config(service.decision_routes.BUNDLED_CACHE)['failed'])


class UnsupportedModelSignal(unittest.TestCase):
    """#735 review: only the CLI's own unsupported-model signal marks a model refused."""

    def run_codex(self, message, model='gpt-5.6-luna'):
        error = json.dumps({'status': 400, 'error': {'type': 'invalid_request_error', 'message': message}})

        class Failed:
            returncode = 1
            stdout = json.dumps({'type': 'turn.failed', 'error': {'message': error}})
            stderr = ''
        with tempfile.TemporaryDirectory() as folder:
            store = QuickStore(Path(folder) / 'state')
            from personal_agent.agent_runtime import Capabilities
            adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runner=lambda *a, **k: Failed(),
                                              runtime_root=Path(folder) / 'turns', codex_home=Path(folder))
            with self.assertRaises(ExecutionError) as caught:
                adapter.execute('codex', 'hello', AgentOSMcpTools(Capabilities(store, None, {}, '', 'job', lambda *a: None,
                                                                               document_access=False)), model=model)
        return caught.exception

    def test_the_codex_unsupported_model_message_is_remembered(self):
        exc = self.run_codex("The 'gpt-5.6-luna' model is not supported when using Codex with a ChatGPT account.")
        self.assertEqual((exc.failure_class, exc.meta.get('unsupported_model')), ('request-rejected', 'gpt-5.6-luna'))

    def test_a_context_length_rejection_naming_the_model_is_not(self):
        exc = self.run_codex("This model's maximum context length is 400000 tokens for gpt-5.6-luna.")
        self.assertEqual(exc.failure_class, 'request-rejected')
        self.assertNotIn('unsupported_model', exc.meta)

    def test_another_models_refusal_is_not_this_models(self):
        exc = self.run_codex("The 'gpt-5.5' model is not supported when using Codex with a ChatGPT account.")
        self.assertNotIn('unsupported_model', exc.meta)

    def test_claude_codes_own_tag(self):
        from personal_agent.bounded_execution import unsupported_model
        self.assertEqual(unsupported_model('claude-code', 'opus', '', 'x [claude-code:unrecognized_model] y'), 'opus')
        self.assertEqual(unsupported_model('claude-code', 'opus', "model 'opus' context too long", ''), '')


class ResolverProcess(unittest.TestCase):
    """#735 root cause: the page reader's resolver child must never end the caller with an EOFError."""

    def test_macos_resolves_in_a_spawned_process(self):
        from personal_agent.local_tools import resolver_start_method
        self.assertEqual(resolver_start_method('darwin', ['fork', 'spawn', 'forkserver']), 'spawn')
        self.assertEqual(resolver_start_method('linux', ['fork', 'spawn', 'forkserver']), 'fork')
        self.assertEqual(resolver_start_method('win32', ['spawn']), 'spawn')

    def test_a_resolver_child_that_dies_is_an_os_error(self):
        from personal_agent.local_tools import _bounded_system_resolver
        with self.assertRaises(OSError) as caught:
            _bounded_system_resolver('localhost', 443, timeout=20, target=_resolver_child_dies)
        self.assertIn('ended without an answer', str(caught.exception))


def _resolver_child_dies(send_connection, host, port):
    """A resolver child that crashes before answering (module level, so a spawned child can load it)."""
    import os
    os._exit(3)


class BridgeSurvives(unittest.TestCase):
    """#735: the real stdio bridge answers a call whose tool raised an unmapped exception, and keeps serving."""

    def test_the_bridge_types_an_unexpected_exception_and_stays_up(self):
        import subprocess
        with tempfile.TemporaryDirectory() as folder:
            store = QuickStore(Path(folder) / 'state')
            store.put('subscription_engine', {'id': 'codex', 'connected_at': 0})
            job = store.enqueue('요청', 'bridge-survives')
            with store.db() as db:
                db.execute("UPDATE jobs SET status='running' WHERE id=?", (job,))
            # The research step raises what a dead resolver child used to raise.
            launcher = Path(folder) / 'launch.py'
            launcher.write_text(
                'import runpy\n'
                'from personal_agent import agent_runtime\n'
                'def research(self, *args, **kwargs):\n'
                '    raise EOFError()\n'
                'agent_runtime.Capabilities._research = research\n'
                'runpy.run_module("personal_agent.mcp_bridge", run_name="__main__")\n', encoding='utf-8')
            requests = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
                        {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {
                            'name': 'bounded_public_research', 'arguments': {'mode': 'travel_plan', 'query': 'q'}}},
                        {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list'}]
            src = str(Path(__file__).resolve().parents[1] / 'src')
            import os
            env = {**os.environ, 'PYTHONPATH': os.pathsep.join(filter(None, (src, os.environ.get('PYTHONPATH'))))}
            done = subprocess.run([sys.executable, str(launcher), '--data', str(store.root), '--job', job,
                                   '--profile=trusted-local'],
                                  input=''.join(json.dumps(r) + '\n' for r in requests), capture_output=True, text=True,
                                  env=env, timeout=120)
            self.assertEqual(done.returncode, 0, done.stderr[-2000:])
            replies = {reply['id']: reply for reply in map(json.loads, done.stdout.splitlines())}
            self.assertEqual(set(replies), {1, 2, 3}, 'the call was answered and the bridge kept serving')
            typed = replies[2]['result']['structuredContent']
            self.assertEqual((replies[2]['result']['isError'], typed['code'], typed['effect'], typed['exception']),
                             (True, 'tool_failed', 'none', 'EOFError'))
            with store.db() as db:
                rows = [(r['status'], json.loads(r['detail'])) for r in db.execute(
                    "SELECT status,detail FROM tool_events WHERE job_id=? AND tool='bounded_public_research' ORDER BY id", (job,))]
            self.assertEqual([status for status, _detail in rows], ['running', 'failed'], 'a terminal record, not incomplete')


class BridgeTimeout(unittest.TestCase):
    """#729: the agentos server's own tool-call timeout on the Codex argv (fake CLI)."""

    def argv(self, engine='codex', budget=None, relay=False):
        seen = {}

        class Done:
            returncode = 0
            stdout = (json.dumps({'item': {'type': 'agent_message', 'text': 'ok'}}) if engine == 'codex'
                      else json.dumps({'type': 'result', 'result': 'ok', 'is_error': False}))
            stderr = ''

        def runner(argv, **kwargs):
            seen['argv'] = list(argv)
            return Done()
        with tempfile.TemporaryDirectory() as folder:
            store = QuickStore(Path(folder) / 'state')
            from personal_agent.agent_runtime import Capabilities
            capabilities = Capabilities(store, None, {}, '', 'job', lambda *a: None, document_access=False,
                                        **({'budget': budget} if budget else {}))
            tools = AgentOSMcpTools(capabilities)
            if relay:
                tools.browser_relay = str(Path(folder) / 'relay')
            adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runner=runner,
                                              runtime_root=Path(folder) / 'turns', codex_home=Path(folder))
            adapter.execute(engine, 'hello', tools)
        return seen['argv']

    @staticmethod
    def overrides(argv):
        return [argv[index + 1] for index, value in enumerate(argv[:-1]) if value == '-c']

    def test_codex_carries_the_verified_per_server_tool_timeout(self):
        from personal_agent.bounded_execution import (BRIDGE_TOOL_MARGIN_SECONDS, CODEX_TOOL_TIMEOUT_KEY,
                                                      MAX_TIMEOUT_SECONDS, bridge_tool_bound)
        self.assertEqual(CODEX_TOOL_TIMEOUT_KEY, 'tool_timeout_sec')
        timeouts = [value for value in self.overrides(self.argv()) if CODEX_TOOL_TIMEOUT_KEY in value]
        research = bridge_tool_bound(['bounded_public_research'])
        self.assertGreater(research, 60, 'longer than Codex\'s own default')
        expected = min(MAX_TIMEOUT_SECONDS, research + BRIDGE_TOOL_MARGIN_SECONDS)
        self.assertEqual(timeouts, [f'mcp_servers.agentos.tool_timeout_sec={expected}'], 'the agentos server only')

    def test_the_timeout_is_capped_by_the_remaining_work_budget(self):
        clock = [0.0]
        budget = WorkBudget(clock=lambda: clock[0], seconds=45)
        timeouts = [value for value in self.overrides(self.argv(budget=budget)) if 'tool_timeout_sec' in value]
        self.assertEqual(timeouts, ['mcp_servers.agentos.tool_timeout_sec=45'])

    def test_a_native_search_bound_covers_every_continuation_request(self):
        """#729 review: an ai-native search may resend after pause_turn; each request has its own timeout."""
        from personal_agent.bounded_execution import bridge_tool_bound
        from personal_agent.local_tools import MAX_PAGE_SECONDS
        from personal_agent.research import MAX_RESEARCH_PAGES
        from personal_agent.search_providers import (NATIVE_CONTINUATIONS, NATIVE_MAX_REQUESTS, NATIVE_TIMEOUT_SECONDS,
                                                     SEARCH_TIMEOUT_SECONDS)
        self.assertEqual(NATIVE_MAX_REQUESTS, NATIVE_CONTINUATIONS + 1)
        search = NATIVE_MAX_REQUESTS * NATIVE_TIMEOUT_SECONDS
        self.assertGreater(search, SEARCH_TIMEOUT_SECONDS)
        self.assertEqual(bridge_tool_bound(['web_search']), search)
        self.assertEqual(bridge_tool_bound(['bounded_public_research']), search + MAX_RESEARCH_PAGES * MAX_PAGE_SECONDS)

    def test_the_anthropic_search_sends_at_most_the_bounded_number_of_requests(self):
        from personal_agent.search_providers import NATIVE_MAX_REQUESTS, AiNativeProvider, SearchProviderError
        sent = []

        def transport(url, body, headers, timeout):
            sent.append(timeout)
            # Always paused and never using a search: only the request cap ends it.
            return {'type': 'message', 'stop_reason': 'pause_turn', 'content': [{'type': 'text', 'text': 'x'}]}
        search = AiNativeProvider('anthropic', {'endpoint': 'https://api.anthropic.com', 'model': 'm'}, 'k', transport=transport)
        with self.assertRaises(SearchProviderError):
            search.search('q')  # nothing cited: an empty native search
        self.assertEqual(len(sent), NATIVE_MAX_REQUESTS)

    def test_the_longest_offered_tool_sets_the_bound(self):
        from personal_agent.bounded_execution import bridge_tool_bound, bridge_tool_timeout
        from personal_agent.cli_browser_relay import CALL_SECONDS
        self.assertEqual(bridge_tool_bound(['list_notes', 'browser_click']), CALL_SECONDS)
        self.assertEqual(bridge_tool_bound([]), 60)
        self.assertEqual(bridge_tool_timeout(['browser_open'], 120), 120)
        self.assertEqual(bridge_tool_timeout(['weather'], 600), 25 + 30)

    def test_claude_code_argv_is_unchanged(self):
        self.assertFalse([value for value in self.argv('claude-code') if 'tool_timeout_sec' in value])

    def test_incomplete_bridge_calls_are_paired_by_tool(self):
        from personal_agent.bounded_execution import incomplete_bridge_calls
        bridge = lambda action: json.dumps({'scope': 'subscription-mcp-bridge', 'host_action': action})  # noqa: E731
        rows = [('web_search', 'running', bridge('web_search')), ('web_search', 'succeeded', bridge('web_search')),
                ('bounded_public_research', 'running', bridge('bounded_public_research')),
                ('web_search', 'running', bridge('web_search')),
                ('model', 'running', '{}'), ('weather', 'running', json.dumps({'scope': 'other'}))]
        self.assertEqual(incomplete_bridge_calls(rows), [('bounded_public_research', 'bounded_public_research'),
                                                         ('web_search', 'web_search')])


class PlannerHistory(Harness):
    def test_the_plan_call_reads_the_conversation_the_worker_is_shown(self):
        """#740: only document-job rows are withheld, as from the worker; source labels no longer hide a row."""
        from personal_agent.agent_runtime import WORK_SOURCES_KEY
        jobs = []
        for text, answer in (('문서 질문', 'DOCUMENT-ANSWER'), ('브라우저 질문', 'BROWSER-ANSWER'), ('일반 질문', 'PLAIN-ANSWER')):
            self.engine.answers = [answer]
            jobs.append(self.run_work(text)[0])
        document, browsed, _plain = jobs
        self.store.put('file_workspace_document_jobs', [document])
        records = self.store.config(WORK_SOURCES_KEY, {})
        records[browsed] = [*records[browsed], 'owner-browser-session', 'history:personal-space']
        self.store.put(WORK_SOURCES_KEY, records)
        self.script([plan('codex', 'Answer.')], goals=[True])
        self.run_work('이어서')
        excerpt = self.asked_plans[-1][0].facts['recent_conversation']
        for shown in ('PLAIN-ANSWER', '일반 질문', 'BROWSER-ANSWER', '브라우저 질문'):
            self.assertIn(shown, excerpt)
        for withheld in ('DOCUMENT-ANSWER', '문서 질문'):
            self.assertNotIn(withheld, excerpt)

    def test_a_work_without_a_source_record_is_still_shown(self):
        from personal_agent.agent_runtime import WORK_SOURCES_KEY
        self.engine.answers = ['UNRECORDED-ANSWER']
        earlier, _row = self.run_work('예전 질문')
        records = self.store.config(WORK_SOURCES_KEY, {})
        records.pop(earlier)
        self.store.put(WORK_SOURCES_KEY, records)
        row = {'role': 'assistant', 'content': 'x', 'job_id': earlier}
        self.assertEqual(self.service.planner_history([row, {'role': 'user', 'content': 'now'}], ()), [row])

    def test_the_question_never_lets_a_plan_rewrite_the_owners_message(self):
        """#820: the plan chooses worker, model and tools; the owner's words reach the worker verbatim."""
        self.assertIn('recent_conversation', QUESTION)
        self.assertIn('you do not rewrite the owner\'s message', QUESTION)
        self.assertIn('receives the owner\'s message verbatim', QUESTION)
        self.assertIn('Notes never restate, replace, narrow or extend the owner\'s message', QUESTION)
        self.assertIn('never tell the worker to skip looking something up or to skip a tool', QUESTION)
        self.assertIn('never ask it to ask the owner for something', QUESTION)


class OwnerQuestion(Harness):
    """#740, #820: a worker's question the owner must answer is judged by the one outcome judgment."""

    def test_a_needed_question_is_the_reply_and_is_not_re_delegated(self):
        """The one judgment reads the reply and the conversation; a needed question serves the message."""
        self.engine.answers = ['출발 위치를 알려 주시겠어요?']
        self.script([plan('codex', 'Answer.'), plan('openai', 'Other path.')], goals=[True])
        job, row = self.run_work('얼마나 걸려?')
        self.assertEqual(len(self.engine.turns), 1, 'no re-delegation')
        self.assertEqual(row['status'], 'succeeded')
        self.assertEqual(row['response'], '출발 위치를 알려 주시겠어요?')
        [(_status, evaluated)] = self.events(job, 'evaluated')
        self.assertEqual((evaluated['outcome'], evaluated['stop']), ('reached', 'reached'))
        [context] = self.asked_goals
        self.assertEqual(context.facts['reply'], '출발 위치를 알려 주시겠어요?')
        self.assertEqual(context.facts['owner_request'], '얼마나 걸려?')
        self.assertIn('recent_conversation', context.facts)
        self.assertEqual(self.asked_owner_inputs, [], '#820: one outcome judgment, no second one')

    def test_an_unneeded_question_stays_short_and_is_re_delegated(self):
        self.engine.answers = ['어디서 출발하세요?', 'answer']
        self.script([plan('codex', 'Answer.'), plan('openai', 'Other path.')], goals=[False, True])
        job, _row = self.run_work('얼마나 걸려?')
        outcomes = [detail['outcome'] for _status, detail in self.events(job, 'evaluated')]
        self.assertEqual(outcomes[0], 'not_reached')
        self.assertEqual(len(self.asked_plans), 2, 'the attempt was re-delegated')

    def test_a_short_attempt_still_delivers_its_reply(self):
        """#820: a reply judged not to serve the message is delivered under the truthful header."""
        from personal_agent.conversation_projection import TERMINAL_ANSWER_LABEL
        self.engine.answers = ['어느 날짜로 할까요?']
        self.script([plan('codex', 'Answer.')], goals=[False])
        job, row = self.run_work('찾아줘')
        self.assertEqual(self.events(job, 'evaluated')[-1][1]['outcome'], 'not_reached')
        self.assertEqual(row['status'], 'failed')
        self.assertEqual(row['response'], '어느 날짜로 할까요?')
        bubble = self.service.telegram_result_text(row['response'], row['owner_cause'], row['status'])
        self.assertIn(TERMINAL_ANSWER_LABEL + '\n어느 날짜로 할까요?', bubble)

    def test_the_conversation_is_redacted_before_it_is_cut(self):
        """Review P2: a cut landing inside a stored secret never leaves a fragment of it."""
        self.engine.answers = ['키: ' + OPENAI_KEY + ' ' + 'Y' * 1490]
        self.run_work('예전 질문')
        self.engine.answers = ['출발 위치를 알려 주세요?']
        self.script([plan('codex', 'Answer.')], goals=[True])
        self.run_work('이어서')
        excerpts = [self.asked_plans[-1][0].facts['recent_conversation'],
                    self.asked_goals[-1].facts['recent_conversation']]
        for excerpt in excerpts:
            self.assertNotIn(OPENAI_KEY[-6:], excerpt)


class Preflight(Harness):
    def test_the_preflight_still_runs_with_the_usual_tools(self):
        self.script([plan('codex', 'Search it.')], goals=[True])
        job, _row = self.run_work('/search 서울 날씨')
        with self.store.db() as db:
            scopes = [json.loads(r['detail']).get('scope') for r in db.execute(
                "SELECT detail FROM tool_events WHERE job_id=? AND tool='web_search'", (job,))]
        self.assertIn('subscription-preflight', scopes)


class NotPinned(Harness):
    def test_spliced_private_material_no_longer_pins_the_default_worker(self):
        """#826: material spliced into the turn (here the notes of /summarize) leaves every available worker open."""
        self.store.save_note = None
        with self.store.db() as db:
            db.execute('INSERT INTO notes VALUES (?,?,?)', ('n1', 'a saved note', 1.0))
        self.script([plan('codex', 'Summarize the notes.')], goals=[True])
        self.run_work('/summarize')
        [(_context, _question, schema)] = self.asked_plans
        self.assertEqual(set(schema['properties']['worker']['enum']), {'codex', 'openai'})


class CatalogueData(Harness):
    def test_catalogue_lists_configured_routes_with_models_tiers_and_availability(self):
        from personal_agent.orchestrator import worker_catalogue
        catalogue = worker_catalogue(self.service)
        codex, openai = catalogue.worker('codex'), catalogue.worker('openai')
        self.assertTrue(codex['default'] and codex['available'])
        self.assertIn('gpt-5.6-luna', codex['models'])
        self.assertIn('list_notes', codex['tools'])
        self.assertNotIn('private_tools', codex)
        self.assertTrue(openai['available'])
        self.assertEqual(openai['models'], ['gpt-4o-mini'], 'only the tool-call-verified model')
        self.assertEqual(openai['model_tiers'], {'gpt-4o-mini': 'lowest-cost'})
        self.assertEqual((catalogue.worker('claude-code')['available'], catalogue.worker('claude-code')['reason']),
                         (False, 'not_connected'))
        self.assertEqual(catalogue.worker('anthropic')['reason'], 'no_api_key')
        self.assertNotIn(OPENAI_KEY, render_catalogue(catalogue.workers))
        self.assertNotIn(OPENAI_KEY, json.dumps(catalogue.workers))

    def test_a_key_saved_after_the_probe_is_not_offered(self):
        from personal_agent.orchestrator import worker_catalogue
        self.service.save_main_ai_key({'provider': 'openai', 'key': 'sk-fixture-later-0710'})
        self.assertEqual(worker_catalogue(self.service).worker('openai')['reason'], 'not_verified')

    def test_a_passing_recheck_keeps_the_route_offerable_after_a_switch(self):
        """Review P2: 확인 on an API Main AI keeps its verified config and probe fields."""
        from personal_agent.orchestrator import worker_catalogue
        with mock.patch.object(self.service.decision_routes, 'follow_main_switched', return_value={'state': 'skipped'}):
            self.service.activate_main_ai({'route': 'openai'})
        self.service.check_main_ai()
        check = self.store.config('main_ai_checks', {})['openai']
        self.assertEqual((check['state'], check['config']['model']), ('ok', 'gpt-4o-mini'))
        self.assertTrue(check['test']['tools_ok'])
        self.assertNotIn(OPENAI_KEY, json.dumps(check))
        with mock.patch.object(self.service.decision_routes, 'follow_main_switched', return_value={'state': 'skipped'}):
            self.service.activate_main_ai({'route': 'codex'})
        self.assertTrue(worker_catalogue(self.service).worker('openai')['available'])

    def test_a_recheck_with_a_replaced_pending_key_does_not_verify_that_key(self):
        with mock.patch.object(self.service.decision_routes, 'follow_main_switched', return_value={'state': 'skipped'}):
            self.service.activate_main_ai({'route': 'openai'})
        self.service.save_main_ai_key({'provider': 'openai', 'key': 'sk-fixture-pending-0710'})
        self.service.check_main_ai()
        self.assertNotIn('config', self.store.config('main_ai_checks', {})['openai'])

    def test_a_signed_out_cli_is_not_offered(self):
        from personal_agent.orchestrator import worker_catalogue
        self.store.put('main_ai_checks', {**self.store.config('main_ai_checks', {}), 'claude-code': {'state': 'ok', 'checked_at': 1}})
        self.store.put('engine_login', {'claude-code': {'state': 'signed-out'}})
        self.assertEqual(worker_catalogue(self.service).worker('claude-code')['reason'], 'signed_out')


INVALID_OUTPUT = '엔진이 요구된 구조화된 응답을 반환하지 않았습니다.'


def bridge_step(record, tool, declared=None, *, status='succeeded', host='page.example.test'):
    """One browser call as the MCP bridge records it: its running event, then its result (#787)."""
    extra = {'declared_effect': declared} if declared else {}
    record(tool, 'running', json.dumps({'scope': 'subscription-mcp-bridge', 'host_action': tool,
                                        'step': {'action': tool, 'host': host}, **extra}))
    result = ({'evidence': {'state': 'page', 'url': f'https://{host}/', 'title': 'Page'}} if status == 'succeeded'
              else {'code': 'tool_failed', 'retry': 'permanent', 'effect': 'none', 'error': '실행하지 못했습니다.'})
    record(tool, status, json.dumps({'scope': 'subscription-mcp-bridge', 'host_action': tool, **result, **extra}))


class ReadIsNotAnEffect(Harness):
    """ORCH-05 (#787): a page load the worker declared read/navigate is repeatable; a state change is not."""

    def attempt_with(self, *steps, plans=None):
        def run(tools):
            if len(self.engine.turns) == 1:
                for tool, declared in steps:
                    bridge_step(tools.capabilities.record, tool, declared)
        self.engine.before = run
        self.engine.fail = [ExecutionError(INVALID_OUTPUT, failure_class='invalid-output', meta=NO_TOOL_CALLS)]
        self.script(plans or [plan('codex', 'Look it up.'), plan('openai', 'Answer directly.')])
        return self.run_work('알려줘', key=f'read-effect-{len(self.asked_plans)}-{steps}')

    def test_a_failed_attempt_that_only_loaded_a_page_is_redelegated(self):
        for declared in ('read', 'navigate'):
            with self.subTest(declared=declared):
                self.engine.turns.clear()
                job, row = self.attempt_with(('browser_open', declared), ('browser_read', None), ('browser_find', None))
                first = self.events(job, 'evaluated')[0][1]
                self.assertEqual((first['outcome'], first['next'], first['stop']), ('worker_failed', 'redelegate', None))
                self.assertEqual(row['status'], 'succeeded')
                self.assertEqual(row['response'], 'api answer')

    def test_a_failed_attempt_that_may_have_changed_state_is_not_redelegated(self):
        for steps in ((('browser_open', 'read'), ('browser_click', 'navigate')),
                      (('browser_open', 'read'), ('browser_type', 'read')),
                      (('browser_open', 'mutate'),),
                      (('browser_open', 'payment'),),
                      # A record with no declaration (written before #787) stays an effect.
                      (('browser_open', None),)):
            with self.subTest(steps=steps):
                self.engine.turns.clear()
                self.asked_plans.clear()
                bodies = len(self.transport.bodies)
                job, row = self.attempt_with(*steps)
                last = self.events(job, 'evaluated')[-1][1]
                self.assertEqual((last['outcome'], last['next'], last['stop']), ('worker_failed', 'stop', 'effect'))
                self.assertEqual(len(self.asked_plans), 1, 'no re-plan after a possible state change')
                self.assertEqual(len(self.transport.bodies), bodies, 'no other worker ran')
                self.assertEqual(row['status'], 'failed')

    def test_a_failed_final_attempt_reports_what_was_tried_what_failed_and_the_next_step(self):
        from personal_agent.conversation_projection import TERMINAL_FAILED_HEADER
        from personal_agent.quickstart_service import FAILED_NEXT_REVIEW
        job, row = self.attempt_with(('browser_open', 'navigate'), plans=[plan('codex', 'Look it up.')])
        self.assertEqual(self.events(job, 'evaluated')[-1][1]['stop'], 'replan_failed')
        self.assertEqual(row['status'], 'failed')
        report = row['owner_cause']
        self.assertTrue(report)
        self.assertIn('구독 CLI 실행: ' + INVALID_OUTPUT, report)
        self.assertIn('시도한 단계: 브라우저 페이지 열기 (page.example.test) 완료', report)
        self.assertIn('판단 AI가 새 계획을 내지 못해 더 맡기지 않았습니다.', report)
        # The next step says what the retry gate allows: a trusted-local CLI turn is not replayed blindly.
        self.assertIn('다음 단계 제안: ' + FAILED_NEXT_REVIEW, report)
        self.assertFalse(self.service.safe_retry(row)[0])
        with self.store.db() as db:
            said = db.execute("SELECT content FROM messages WHERE job_id=? AND role='assistant'", (job,)).fetchone()[0]
        self.assertEqual(said, TERMINAL_FAILED_HEADER + '\n\n' + report)
        bubble = self.service.telegram_result_text(None, report, 'failed')
        self.assertIn(report, bubble)

    def test_the_report_after_a_state_change_names_the_effect_stop_and_no_retry(self):
        from personal_agent.quickstart_service import FAILED_NEXT_REVIEW
        job, row = self.attempt_with(('browser_open', 'read'), ('browser_click', 'mutate'))
        report = row['owner_cause']
        self.assertIn('브라우저에서 누르기 (page.example.test) 완료', report)
        self.assertIn('되돌릴 수 없는 작업이 실행되어 같은 요청을 다시 맡기지 않았습니다.', report)
        self.assertIn('다음 단계 제안: ' + FAILED_NEXT_REVIEW, report)
        self.assertFalse(self.service.safe_retry(row)[0])
        # Without the unmediated-turn gate, the recorded click alone refuses the retry.
        self.assertFalse(self.service.effect_calls({'tool': 'browser_open', 'trace': {'host_action': 'browser_open',
                                                                                     'declared_effect': 'read'}}))
        self.assertTrue(any(self.service.effect_calls(event) for event in self.store.task_events(job)))

    def test_the_next_step_follows_a_typed_need_then_the_retry_gate(self):
        from personal_agent.quickstart_service import FAILED_NEXT_RETRY, FAILED_NEXT_SETUP
        job = self.store.enqueue('알려줘', 'next-step')
        with self.store.db() as db:
            db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                       (job, 'subscription_engine', 'failed', json.dumps({'error': INVALID_OUTPUT}), 1.0))
        with mock.patch.object(self.service, 'safe_retry', return_value=(True, None)):
            self.assertTrue(self.service.failed_attempt_report(self.store.job(job), INVALID_OUTPUT)
                            .endswith('다음 단계 제안: ' + FAILED_NEXT_RETRY))
            with self.store.db() as db:
                db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                           (job, 'calendar_query', 'failed', json.dumps({'host_action': 'calendar_query', 'code': 'needs_setup',
                                                                        'requires': 'connector', 'error': '연결이 필요합니다.'}), 2.0))
            report = self.service.failed_attempt_report(self.store.job(job), INVALID_OUTPUT)
        self.assertTrue(report.endswith('다음 단계 제안: ' + FAILED_NEXT_SETUP))
        self.assertIn('일정 조회: 연결이 필요합니다.', report)
        self.assertIn('일정 조회 실패', report)

    def test_a_malformed_declaration_is_an_effect(self):
        from personal_agent.agent_runtime import page_load_only
        for value in ({'x': 1}, ['read'], 'Read', ' read', None, 1):
            with self.subTest(value=value):
                self.assertFalse(page_load_only('browser_open', {'declared_effect': value}))
        self.assertFalse(page_load_only('browser_click', {'declared_effect': 'read'}))
        self.assertTrue(page_load_only('browser_open', {'declared_effect': 'navigate'}))

    def test_a_worker_failure_before_any_attempt_keeps_the_plain_failure(self):
        # A Work with no recorded worker attempt has nothing observed to report.
        job = self.store.enqueue('알려줘', 'no-attempt')
        self.assertIsNone(self.service.failed_attempt_report(self.store.job(job), 'x'))


class RetryReadIsNotAnEffect(Harness):
    """#787: ``safe_retry`` uses the same page-load rule as re-delegation."""

    def failed_work(self, *events):
        job = self.store.enqueue('다시 해볼 요청', f'retry-{len(events)}-{json.dumps(events)}')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='failed' WHERE id=?", (job,))
            for tool, host_action, declared in events:
                detail = {'host_action': host_action, **({'declared_effect': declared} if declared else {})}
                db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                           (job, tool, 'succeeded', json.dumps(detail), 1.0))
        return self.store.job(job)

    def test_only_a_declared_page_load_is_replayable(self):
        from personal_agent.quickstart_service import EFFECT_RETRY_REFUSAL
        cases = [((('browser_open', 'browser_open', 'read'),), True),
                 ((('browser_open', 'browser_open', 'navigate'), ('browser_read', 'browser_read', None)), True),
                 # A package tool id aliasing the open keeps the declaration of its host action.
                 ((('package_open', 'browser_open', 'navigate'),), True),
                 ((('browser_open', 'browser_open', None),), False),
                 ((('browser_open', 'browser_open', 'mutate'),), False),
                 ((('browser_open', 'browser_open', 'payment'),), False),
                 ((('browser_open', 'browser_open', 'read'), ('browser_click', 'browser_click', 'read')), False),
                 ((('browser_type', 'browser_type', 'navigate'),), False),
                 # A public id naming the open cannot hide a write behind its host action.
                 ((('browser_open', 'save_note', 'read'),), False)]
        for events, allowed in cases:
            with self.subTest(events=events):
                self.assertEqual(self.service.safe_retry(self.failed_work(*events)),
                                 (True, None) if allowed else (False, EFFECT_RETRY_REFUSAL))

    def test_the_retry_note_lists_only_steps_that_may_have_changed_state(self):
        note = self.service.retry_effect_note(self.failed_work(('browser_open', 'browser_open', 'read'),
                                                               ('browser_click', 'browser_click', 'mutate')))
        self.assertIn('- browser_click', note)
        self.assertNotIn('browser_open', note)
        self.assertIsNone(self.service.retry_effect_note(self.failed_work(('browser_open', 'browser_open', 'navigate'))))


class OrchestrationUnit(unittest.TestCase):
    def catalogue(self):
        workers = [{'id': 'a', 'kind': 'subscription', 'name': 'A', 'destination': '', 'default': True, 'available': True,
                    'reason': '', 'native_search': True, 'browser': False, 'cost': 'c', 'latency': 'l',
                    'default_model': '', 'models': ['m1'], 'model_tiers': {'m1': 'lowest-cost'},
                    'tools': ['list_notes', 'web_search']},
                   {'id': 'b', 'kind': 'api', 'name': 'B', 'destination': '', 'default': False, 'available': True,
                    'reason': '', 'native_search': False, 'browser': False, 'cost': 'c', 'latency': 'l',
                    'default_model': 'm2', 'models': ['m2'], 'model_tiers': {}, 'tools': ['weather']},
                   {'id': 'c', 'kind': 'api', 'name': 'C', 'destination': '', 'default': False, 'available': False,
                    'reason': 'no_api_key', 'native_search': False, 'browser': False, 'cost': 'c', 'latency': 'l',
                    'default_model': '', 'models': [], 'model_tiers': {}, 'tools': []}]
        return Catalogue(workers, {}, 'a')

    def orchestration(self, answer, **kwargs):
        engine = FixtureDecisionEngine(structured=lambda context, question, schema: answer)
        events = []
        orchestration = Orchestration(ConversationJudgments(engine), self.catalogue(), request='요청',
                                      record=lambda status, detail: events.append((status, detail)), **kwargs)
        return orchestration, events, engine

    def test_validation_is_deterministic(self):
        catalogue = self.catalogue()
        orchestration, _events, _engine = self.orchestration(None)
        candidates = catalogue.available()
        self.assertEqual([row['id'] for row in candidates], ['a', 'b'], 'an unavailable worker is never offered')
        ok, _ = orchestration.validate(plan('b', 'g'), candidates, 1)
        self.assertEqual((ok.worker, ok.signature), ('b', ('b', 'm2')))
        for data, what in ((plan('c', 'g'), 'worker'), (plan('zz', 'g'), 'worker'), (plan('a', 'g', model='m2'), 'model'),
                           ({'worker': 'a'}, 'shape'),
                           ({**plan('a', 'g'), 'brief': {'goal': 'g'}}, 'shape')):
            with self.subTest(what=what):
                self.assertEqual(orchestration.validate(data, candidates, 1), (None, what))
        spent = Orchestration(None, catalogue, request='r', budget=WorkBudget(seconds=10))
        self.assertEqual(spent.validate(plan('a', 'g'), candidates, 1), (None, 'budget'))

    def test_no_plan_or_goal_call_once_the_deadline_is_short(self):
        asked = []
        engine = FixtureDecisionEngine(structured=lambda *a: asked.append('plan'),
                                       judge=lambda *a: asked.append('goal'))
        orchestration = Orchestration(ConversationJudgments(engine), self.catalogue(), request='r',
                                      budget=WorkBudget(seconds=30))
        attempt = orchestration.first()
        self.assertEqual((attempt.fallback, asked), ('budget_short', []))
        self.assertEqual(orchestration.evaluate_answer('answer', 'none'), 'not_judged')
        self.assertEqual(asked, [])

    def test_every_available_worker_is_offered(self):
        """#826: no pin to the default worker."""
        self.assertEqual([row['id'] for row in self.catalogue().available()], ['a', 'b'])

    def test_the_question_and_catalogue_name_no_request(self):
        rendered = render_catalogue(self.catalogue().available())
        self.assertIn('tools: list_notes, web_search', rendered)
        self.assertIn('m1 (lowest-cost)', rendered)
        schema = plan_schema(self.catalogue().available())
        self.assertEqual(schema['properties']['worker']['enum'], ['a', 'b'])
        self.assertEqual(set(schema['required']), set(schema['properties']))
        self.assertEqual(set(schema['properties']['brief']['required']), set(schema['properties']['brief']['properties']))
        self.assertIn('you do not do the work yourself', QUESTION)

    def test_the_plan_context_carries_the_request_whole_and_bounds_the_rest(self):
        request = '긴 요청 ' * 2000
        seen = []
        engine = FixtureDecisionEngine(structured=lambda context, question, schema: seen.append(context))
        orchestration = Orchestration(ConversationJudgments(engine), self.catalogue(), request=request,
                                      conversation='x' * 9000)
        orchestration.first()
        [context] = seen
        self.assertEqual(context.facts['owner_request'], request)
        self.assertLessEqual(len(context.facts['recent_conversation']), 1500)
        self.assertFalse(context.too_large())

    def test_attempts_history_is_bounded(self):
        orchestration, _events, _engine = self.orchestration(None)
        orchestration.orchestrated = True
        for n in range(3):
            orchestration.history.append((Attempt(n + 1, 'a', notes='g' * 500, planned=True), 'not_reached', 'y' * 900, 'z' * 900))
        self.assertLessEqual(len(orchestration._attempts_text()), ATTEMPTS_CHARS)


class DecisionLayerStructured(unittest.TestCase):
    def test_model_engine_answers_one_structured_object_and_audits_no_content(self):
        audits = []

        class Adapter:
            def tool_turn(self, config, key, messages, tools, **kwargs):
                self.tools = tools
                arguments = {'worker': 'a', 'secret_text': 'owner words', 'confidence': 0.8}
                return {'tool_calls': [{'function': {'name': 'decide', 'arguments': json.dumps(arguments)}}]}, 'm'
        adapter = Adapter()
        engine = ModelDecisionEngine(adapter, lambda: ({'provider': 'openai', 'endpoint': 'https://api.openai.com/v1',
                                                        'model': 'gpt-4o-mini'}, 'k'), audit=audits.append)
        schema = {'type': 'object', 'properties': {'worker': {'type': 'string'}, 'secret_text': {'type': 'string'}},
                  'required': ['worker', 'secret_text']}
        decision = engine.structured(DecisionContext('p', {'f': 'v'}), 'q', schema)
        self.assertEqual(decision.outcome, OUTCOME_DECIDED)
        self.assertEqual(decision.data, {'worker': 'a', 'secret_text': 'owner words'})
        declared = adapter.tools[0]['function']['parameters']
        self.assertEqual(declared['required'], ['worker', 'secret_text', 'confidence'])
        self.assertFalse(declared['additionalProperties'])
        self.assertIsNone(audits[0]['answer'])
        self.assertNotIn('owner words', json.dumps(audits))
        self.assertEqual(DecisionPolicy().structured(decision), {'worker': 'a', 'secret_text': 'owner words'})
        bad = engine.structured(DecisionContext('p', {}), 'q', schema, valid=lambda data: False)
        self.assertEqual(bad.outcome, OUTCOME_MALFORMED)

    def test_engines_without_a_structured_answer_say_so(self):
        for engine in (UnavailableDecisionEngine(), JevDecisionEngine(lambda: 'k'), FixtureDecisionEngine(),
                       RoutedDecisionEngine(lambda: UnavailableDecisionEngine())):
            with self.subTest(engine=type(engine).__name__):
                decision = engine.structured(DecisionContext('p', {}), 'q', {'type': 'object', 'properties': {}})
                self.assertEqual(decision.outcome, OUTCOME_UNAVAILABLE)
                self.assertIsNone(DecisionPolicy().structured(decision))
        self.assertEqual(UnavailableDecisionEngine().structured(DecisionContext('p', {}), 'q', {}).confidence.engine,
                         STRUCTURED_UNSUPPORTED)
        self.assertEqual(FixtureDecisionEngine().asked, [], 'an unscripted fixture records no structured call')

    def test_audit_record_of_a_structured_answer_is_content_free(self):
        record = audit_record(DecisionContext('p', {}), 'structured', OUTCOME_DECIDED, {'goal': 'owner text'},
                              fixture_confidence(), 1.0)
        self.assertIsNone(record['answer'])


class TurnContextBrief(unittest.TestCase):
    def test_brief_is_its_own_section_before_the_request(self):
        context = turn_context([{'role': 'user', 'content': 'the request'}], 'cli', brief='a note')
        text = render_turn_prompt(context)
        self.assertLess(text.index('# Orchestration notes'), text.index('# Current request'))
        self.assertIn('never replace or narrow the owner\'s request', text)
        self.assertTrue(text.endswith('# Current request\nthe request'))
        self.assertNotIn('brief', turn_context([{'role': 'user', 'content': 'r'}], 'cli'))


if __name__ == '__main__':
    unittest.main()


class GoalDecidesOutcome(Harness):
    """#752: the goal judgment decides a CLI Work's outcome, not its intermediate steps."""

    @staticmethod
    def step(tools, action, status, **detail):
        tools.capabilities.record(action, status, json.dumps({'host_action': action, **detail}))

    def test_a_reached_goal_after_an_effect_succeeds_despite_step_failures(self):
        def work(tools):
            self.step(tools, 'browser_open', 'succeeded', evidence={'qualifiers': ['truncated']})
            self.step(tools, 'browser_click', 'failed', code='target_not_found', effect='none', error='없음. 목록: 1 · 2')
            self.step(tools, 'browser_click', 'succeeded', evidence={})
            self.step(tools, 'weather', 'failed', code='transient_failure')
        self.engine.before = work
        self.engine.answers = ['추천 상품 네 가지와 링크입니다.']
        self.script([plan('codex', 'Answer.'), plan('openai', 'Other path.')], goals=[True])
        job, row = self.run_work('어디서 살 수 있을까?')
        self.assertEqual(len(self.engine.turns), 1, 'no re-delegation after an effect')
        last = self.events(job, 'evaluated')[-1][1]
        self.assertEqual((last['outcome'], last['stop']), ('reached', 'reached'))
        self.assertEqual(row['status'], 'succeeded')
        self.assertFalse(row['owner_cause'])
        self.assertEqual(row['response'], '추천 상품 네 가지와 링크입니다.')

    def test_a_goal_not_shown_after_an_effect_stays_short(self):
        def work(tools):
            self.step(tools, 'browser_click', 'succeeded', evidence={})
            self.step(tools, 'weather', 'failed', code='transient_failure')
        self.engine.before = work
        self.script([plan('codex', 'Answer.')], goals=[False])
        job, row = self.run_work('해줘')
        self.assertEqual(self.events(job, 'evaluated')[-1][1]['stop'], 'effect')
        self.assertEqual(row['status'], 'partial')

    def test_an_unknown_effect_is_never_judged(self):
        def work(tools):
            self.step(tools, 'browser_click', 'failed', code='tool_incomplete', effect='unknown')
        self.engine.before = work
        self.script([plan('codex', 'Answer.')], goals=[True])
        job, row = self.run_work('해줘')
        self.assertEqual(self.events(job, 'evaluated')[-1][1]['outcome'], 'not_judged')
        self.assertEqual(self.goals, [True], 'no goal judgment was asked')
        self.assertNotEqual(row['status'], 'succeeded')

    def test_a_reached_verdict_never_outranks_a_failed_state_changing_action(self):
        """#752 review: a refused click or write with no later success keeps the Work short."""
        for code in ('approval_required', 'tool_failed'):
            with self.subTest(code=code):
                def work(tools, code=code):
                    self.step(tools, 'browser_click', 'succeeded', evidence={})
                    self.step(tools, 'browser_type', 'failed', code=code, effect='none')
                    self.step(tools, 'browser_read', 'succeeded', evidence={})
                self.engine.before = work
                self.script([plan('codex', 'Answer.')], goals=[True])
                job, row = self.run_work('주문해줘', key=f'short-{code}')
                self.assertEqual(self.events(job, 'evaluated')[-1][1]['outcome'], 'reached')
                self.assertEqual(row['status'], 'partial')

    def test_a_pending_browser_approval_blocks_the_upgrade(self):
        from personal_agent.quickstart_service import BROWSER_REQUESTS_KEY
        def work(tools):
            self.step(tools, 'browser_click', 'succeeded', evidence={})
            self.step(tools, 'weather', 'failed', code='transient_failure')
            self.store.put(BROWSER_REQUESTS_KEY, {tools.capabilities.job_id: {'state': 'requested', 'action': 'browser_click'}})
        self.engine.before = work
        self.script([plan('codex', 'Answer.')], goals=[True])
        _job, row = self.run_work('결제해줘')
        self.assertEqual(row['status'], 'partial', 'approving the step must still resume this Work (C14)')

    def test_a_reached_goal_is_not_demoted_by_a_login_page_and_asks_no_login(self):
        from personal_agent.quickstart_service import BROWSER_LOGINS_KEY
        def work(tools):
            self.step(tools, 'browser_open', 'succeeded', evidence={'state': 'login_required'})
            self.store.put(BROWSER_LOGINS_KEY, {tools.capabilities.job_id: {
                'work_id': tools.capabilities.job_id, 'url': 'https://login.test/', 'host': 'login.test',
                'state': 'requested', 'requested_at': 1.0}})
            self.step(tools, 'weather', 'failed', code='transient_failure')
        self.engine.before = work
        self.script([plan('codex', 'Answer.')], goals=[True])
        with mock.patch.object(self.service, 'offer_browser_login') as offer:
            job, row = self.run_work('찾아줘')
        self.assertEqual(row['status'], 'succeeded')
        offer.assert_not_called()


class OwnerStateOnTheCliRoute(Harness):
    """#774: the trusted-local CLI turn reaches Memory, preparations and the calendar through the service."""

    def test_a_cli_turn_schedules_a_preparation_through_the_service(self):
        from datetime import datetime, timedelta, timezone
        due = (datetime.now(timezone.utc) + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        seen = {}

        def work(tools):
            seen['offered'] = sorted(tools._offered())
            try:
                seen['result'] = tools.call('schedule_preparation', {
                'kind': 'reminder', 'goal': '출발 시간입니다.', 'due': due, 'timezone': 'Asia/Seoul'})
            except Exception as exc:
                seen['result'] = f'{type(exc).__name__}: {exc} {getattr(exc, "code", "")}'
        self.engine.before = work
        self.script([plan('codex', 'Remind the owner.')], goals=[True])
        job, _row = self.run_work('오후 4시 반에 출발하라고 알려줘')
        # A native-search turn offers the relayed writes and, since #826, the private reads too.
        for name in ('schedule_preparation', 'calendar_draft_create'):
            self.assertIn(name, seen['offered'])
        with self.store.db() as db:
            rows = db.execute('SELECT goal_text,state FROM preparations').fetchall()
        self.assertEqual([row['goal_text'] for row in rows], ['출발 시간입니다.'], seen.get('result'))

    def test_a_cli_memory_write_without_an_explicit_request_stays_a_candidate(self):
        """#597's gate holds on the relayed path: no owner request, so a MemoryCandidate, never canonical Memory."""
        self.engine.before = lambda tools: tools.call('save_memory', {'memory_key': 'profile.place.home',
                                                                      'content': '성남 백현동'})
        self.script([plan('codex', 'Answer.')], goals=[True])
        self.run_work('백현동에서 출발해')
        with self.store.db() as db:
            memories = db.execute('SELECT count(*) FROM memories').fetchone()[0]
            candidates = db.execute("SELECT content FROM memory_candidates WHERE state='pending'").fetchall()
        self.assertEqual(memories, 0)
        self.assertEqual([row['content'] for row in candidates], ['성남 백현동'])


class HostRelayRouting(unittest.TestCase):
    """#774: the relay serves browser and owner-state tools, and nothing else."""

    def test_the_relay_forwards_owner_state_calls_and_refuses_others(self):
        from personal_agent.cli_browser_relay import BrowserRelay, RelayClient

        class Tools:
            def __init__(self):
                self.calls = []
                self.capabilities = type('C', (), {'tools': {
                    'schedule_preparation': {'host_action': 'schedule_preparation'},
                    'save_memory': {'host_action': 'save_memory'},
                    'web_search': {'host_action': 'web_search'}}})()

            def call(self, name, arguments):
                self.calls.append(name)
                return {'ok': name}
        tools = Tools()
        relay = BrowserRelay(tools)
        try:
            client = RelayClient(relay.address)
            self.assertEqual(client.call('schedule_preparation', {'kind': 'reminder'}), {'ok': 'schedule_preparation'})
            self.assertEqual(client.call('save_memory', {'memory_key': 'k', 'content': 'v'}), {'ok': 'save_memory'})
            with self.assertRaises(Exception):
                client.call('web_search', {'query': 'x'})
            self.assertEqual(tools.calls, ['schedule_preparation', 'save_memory'])
        finally:
            relay.close()

    def test_the_bridge_facade_forwards_owner_state_calls_to_the_relay(self):
        from personal_agent.bounded_execution import AgentOSMcpTools

        class Relay:
            def __init__(self):
                self.calls = []

            def call(self, name, arguments):
                self.calls.append(name)
                return {'relayed': name}

        class Capabilities:
            tools = {'save_memory': {'host_action': 'save_memory'}}

            def definitions(self):
                return [{'function': {'name': 'save_memory', 'parameters': {
                    'type': 'object', 'properties': {'memory_key': {'type': 'string'}, 'content': {'type': 'string'}},
                    'required': ['memory_key', 'content'], 'additionalProperties': False}}}]

            def execute(self, name, arguments):
                raise AssertionError('an owner-state call must not run in the bridge')
        facade = AgentOSMcpTools(Capabilities())
        facade.relay = Relay()
        self.assertEqual(facade.call('save_memory', {'memory_key': 'k', 'content': 'v'}), {'relayed': 'save_memory'})
        self.assertEqual(facade.relay.calls, ['save_memory'])


class RelayAuthority(Harness):
    """#774 review: the relay grants nothing beyond the turn's own offered set."""

    def test_a_direct_relay_call_to_a_tool_the_turn_does_not_offer_is_refused_by_the_service(self):
        from personal_agent.cli_browser_relay import BrowserRelay, RelayClient
        seen = {}

        def work(tools):
            # No browser profile is available, so the browser tools are not offered this turn (#826:
            # the private reads now are).  The CLI can read the relay key, so it tries the socket
            # directly; the service-side facade refuses it.
            relay = BrowserRelay(tools)
            try:
                try:
                    RelayClient(relay.address).call('browser_open', {'url': 'https://example.com/', 'effect': 'read'})
                    seen['result'] = 'ran'
                except Exception as exc:
                    seen['result'] = type(exc).__name__
            finally:
                relay.close()
        self.engine.before = work
        self.script([plan('codex', 'Answer.')], goals=[True])
        self.run_work('알려줘')
        self.assertTrue(self.engine.turns[0]['native_search'])
        self.assertNotIn('browser_open', self.engine.turns[0]['offered'])
        self.assertEqual(seen['result'], 'ExecutionError')

    def test_a_relayed_owner_state_result_reaches_the_service_memo(self):
        """The CLI route's connector park reads the same typed result the direct route's memo holds."""
        from personal_agent.cli_browser_relay import BrowserRelay, RelayClient
        needs = {'needs_setup': True, 'requires': 'google-calendar'}

        class Tools:
            def __init__(self):
                self.capabilities = type('C', (), {'tools': {'calendar_query': {'host_action': 'calendar_query'}},
                                                   'memo': {}})()

            def call(self, name, arguments):
                return needs
        tools = Tools()
        relay = BrowserRelay(tools)
        try:
            RelayClient(relay.address).call('calendar_query', {'start': 's', 'end': 'e', 'timezone': 'Asia/Seoul'})
        finally:
            relay.close()
        self.assertEqual(list(tools.capabilities.memo.values()), [needs])
        # The service's own park decision reads it (#606 T5 logic, unchanged).
        self.service.connector_handoff = type('H', (), {'known': staticmethod(lambda cid: cid == 'google-calendar')})()
        self.service.attempted_only_reads = lambda job_id: True
        self.assertEqual(self.service.connector_read_need(tools.capabilities, 'job'), 'google-calendar')


class SecretaryStandard(Harness):
    """#767, #820: worker guidance holds answers to the secretary standard; the outcome judgment reads the reply."""

    def test_the_outcome_judgment_reads_no_plan_criteria(self):
        """#820: nothing the plan wrote is part of the outcome judgment."""
        self.script([plan('codex', 'Name options with current facts.')], goals=[True])
        self.run_work('추천해줘')
        [context] = self.asked_goals
        self.assertNotIn('completion_criteria', context.facts)
        self.assertNotIn('Name options', json.dumps(context.facts, ensure_ascii=False))
        self.assertEqual(context.facts['owner_request'], '추천해줘')

    def test_the_worker_guidance_and_the_judgment_state_the_standard(self):
        from personal_agent.agent_runtime import API_TOOL_GUIDANCE, CLI_TOOL_GUIDANCE, CORE_INSTRUCTIONS
        from personal_agent.conversation_handoff import GOAL_REACHED_PROPOSITION
        self.assertIn('capable personal secretary', CORE_INSTRUCTIONS)
        self.assertIn('look them up and cite the sources', CORE_INSTRUCTIONS)
        for guidance in (API_TOOL_GUIDANCE, CLI_TOOL_GUIDANCE):
            self.assertIn('ordinary conversation that needs no current facts', guidance)
        self.assertIn('capable personal secretary', GOAL_REACHED_PROPOSITION)
        self.assertIn('read in the light of the recent conversation', GOAL_REACHED_PROPOSITION)
        self.assertIn('the reply\'s own claims are not evidence', GOAL_REACHED_PROPOSITION)
        self.assertIn('current fact the observations do not show', GOAL_REACHED_PROPOSITION)

    def test_a_tool_less_direct_reply_gets_the_one_judgment_and_is_re_delegated_when_short(self):
        """#820 review P1: a direct run that asked no judgment (no external tool) is judged once, like a CLI attempt."""
        # run_agent's own execution check (#606) asks the model once more; it answers the same.
        self.transport.answers = ['일반적인 조언입니다.', '일반적인 조언입니다.']
        self.engine.answers = ['구체적인 선택지와 출처입니다.']
        self.script([plan('openai', 'Name options.'), plan('codex', 'Look them up.')], goals=[False, True])
        job, row = self.run_work('추천해줘')
        outcomes = [detail['outcome'] for _status, detail in self.events(job, 'evaluated')]
        self.assertEqual(outcomes, ['not_reached', 'reached'])
        self.assertEqual(len(self.engine.turns), 1, 'the second attempt ran')
        self.assertEqual(row['status'], 'succeeded')
        self.assertEqual(row['response'], '구체적인 선택지와 출처입니다.')
        self.assertEqual(self.asked_goals[0].facts['reply'], '일반적인 조언입니다.')
        self.assertNotIn('completion_criteria', self.asked_goals[0].facts)

    def test_a_tool_less_direct_reply_is_kept_when_the_judgment_is_unavailable(self):
        self.transport.answers = ['답입니다.', '답입니다.']
        self.script([plan('openai', 'Answer.')], goals=[])
        job, row = self.run_work('질문')
        self.assertEqual(self.events(job, 'evaluated')[-1][1]['outcome'], 'reached')
        self.assertEqual(row['status'], 'succeeded')
        self.assertEqual(row['response'], '답입니다.')

    def test_the_outcome_judgment_reads_a_long_reply_whole(self):
        """#820 review P2: no claim in a long reply is hidden from the one judgment."""
        reply = '앞부분. ' + '가' * 5000 + ' 중간에 예약을 완료했습니다. ' + '나' * 5000 + ' 끝부분.'
        self.engine.answers = [reply]
        self.script([plan('codex', 'Answer.')], goals=[True])
        self.run_work('알려줘')
        self.assertEqual(self.asked_goals[0].facts['reply'], reply)
        self.assertFalse(self.asked_goals[0].too_large())

    def test_an_owner_request_not_to_look_things_up_is_honoured_by_the_standard(self):
        from personal_agent.agent_runtime import CORE_INSTRUCTIONS
        self.assertIn('unless the owner asked you not to', CORE_INSTRUCTIONS)
        self.assertIn('never tell the worker to skip looking something up', QUESTION)


class StreamDiagnostics(unittest.TestCase):
    def test_the_end_of_a_codex_stream_is_recorded_without_content(self):
        from personal_agent.bounded_execution import cli_metadata
        raw = '\n'.join(json.dumps(line) for line in (
            {'type': 'thread.started'}, {'type': 'item.started', 'item': {'type': 'mcp_tool_call', 'tool': 'browser_open'}},
            {'type': 'error', 'message': 'stream disconnected before completion'},
            {'type': 'turn.failed', 'error': {'message': 'model   stream ended'}}))
        meta = cli_metadata('codex', raw)
        self.assertEqual(meta['stream_tail'], ['thread.started', 'item.started', 'error', 'turn.failed'])
        self.assertEqual(meta['stream_errors'], ['stream disconnected before completion', 'model stream ended'])

class StreamRedaction(unittest.TestCase):
    def test_stream_errors_are_redacted_like_failure_details(self):
        from personal_agent.bounded_execution import cli_metadata
        raw = json.dumps({'type': 'error', 'message': 'bad key sk-proj-ABCDEFGHIJKLMNOPQRSTUVWX1234 \x07 rejected'})
        [error] = cli_metadata('codex', raw)['stream_errors']
        self.assertNotIn('ABCDEFGHIJKLMNOPQRSTUVWX1234', error)



class StreamErrorsInTheTurnRecord(Harness):
    def test_a_stream_error_echoing_the_request_or_a_secret_is_not_stored(self):
        """#792 review: the stored turn record passes the service redaction, not only the pattern pass."""
        self.engine.fail = [ExecutionError('no answer', failure_class='invalid-output',
                                           meta={'stream_errors': [f'rejected: 비밀 요청 문장 그대로 반복 key {OPENAI_KEY}',
                                                                   f'bad key {OPENAI_KEY}']})]
        self.script([plan('codex', 'Answer.')], goals=[True])
        job, _row = self.run_work('비밀 요청 문장 그대로 반복')
        errors = self.store.turn_provenance(job).get('stream_errors')
        self.assertEqual(len(errors or []), 2, 'the errors are recorded, redacted')
        self.assertIn('bad key', errors[1])
        stored = json.dumps(errors, ensure_ascii=False)
        self.assertNotIn(OPENAI_KEY, stored)
        self.assertNotIn('비밀 요청 문장 그대로 반복', stored)


class OwnerModelAlwaysOn(Harness):
    """#804: the profile and the current-context snapshot reach every worker and the plan call."""

    def setUp(self):
        super().setUp()
        from personal_agent.agent_runtime import MEMORY_OWNER
        from personal_agent.memory_service import MemoryService
        MemoryService(self.store, private_read_sink=MemoryService.NO_EGRESS_GUARD).remember_profile(
            MEMORY_OWNER, 'settings', 'profile.place.work', '판교 사무실')

    @mock.patch.dict('os.environ', {'TZ': 'Asia/Seoul'})  # #804: a host zone, not the CI's unset UTC
    def test_both_routes_get_the_owner_model_when_the_brief_selects_no_section(self):
        from personal_agent.agent_runtime import CURRENT_CONTEXT_HEADING, PROFILE_HEADING
        self.script([plan('codex', 'Recommend lunch.'), plan('openai', 'Recommend lunch.')],
                    goals=[True])
        self.run_work('점심 추천해줘')
        prompt = self.engine.turns[-1]['prompt']
        self.run_work('저녁 추천해줘')
        system = self.transport.bodies[0]['messages'][0]['content']
        for text in (prompt, system):
            self.assertIn(PROFILE_HEADING + '\n', text)
            self.assertIn('판교 사무실', text)
            self.assertIn(CURRENT_CONTEXT_HEADING + '\n', text)
            self.assertIn('"local_time":', text, 'the clock, with current context off')
        self.assertEqual(self.engine.turns[-1]['context']['conversation'], [], 'the first turn has no history yet')

    @mock.patch.dict('os.environ', {'TZ': 'Asia/Seoul'})  # #804: a host zone, not the CI's unset UTC
    def test_the_plan_call_reads_the_owner_model_and_selects_only_the_extra_sections(self):
        self.script([plan('codex', 'Answer.')], goals=[True])
        self.run_work('오늘 점심 추천해줘')
        context, _question, schema = self.asked_plans[0]
        self.assertIn('판교 사무실', context.facts['owner_profile'])
        self.assertIn('"local_time":', context.facts['current_context'])
        self.assertIn('always given to the worker: the owner\'s message verbatim, history', context.facts['context_sections'])
        self.assertEqual(schema['properties']['brief']['properties'], {'notes': {'type': 'string'}}, '#820: no section choice')
        self.assertFalse(context.too_large())

    def test_a_native_search_turn_offers_save_memory_and_list_memory(self):
        """#826: the Memory read is offered beside the CLI's own search."""
        self.script([plan('codex', 'Acknowledge.')], goals=[True])
        self.run_work('난 오늘 판교로 출근했어')
        turn = self.engine.turns[-1]
        self.assertTrue(turn['native_search'])
        self.assertIn('save_memory', turn['offered'])
        self.assertIn('list_memory', turn['offered'])


class OwnerModelUnit(unittest.TestCase):
    def test_an_attempt_always_carries_every_section(self):
        """#804, #820: the owner model, the conversation and the prepared answers are never a plan's choice."""
        attempt = Attempt(1, 'a', notes='g', planned=True)
        self.assertEqual(attempt.section('profile', 'P'), 'P')
        self.assertEqual(attempt.section('current_context', 'C'), 'C')
        self.assertIs(attempt.section('history', True), True)
        self.assertEqual(attempt.section('prepared', 'R'), 'R')
        self.assertEqual(set(attempt.sections), set(SECTIONS))
        self.assertIsNone(Attempt(1, 'a', planned=True).brief(), 'no notes: no notes section')

    def test_the_owner_model_facts_are_redacted_and_bounded(self):
        from personal_agent.orchestrator import CURRENT_CONTEXT_FACT_CHARS, PROFILE_FACT_CHARS
        seen = []
        engine = FixtureDecisionEngine(structured=lambda context, question, schema: seen.append(context))
        catalogue = OrchestrationUnit.catalogue(None)
        orchestration = Orchestration(ConversationJudgments(engine), catalogue, request='요청', conversation='x' * 9000,
                                      sections={'profile': '가' * 5000, 'current_context': '나' * 5000})
        orchestration.first()
        [context] = seen
        self.assertEqual(len(context.facts['owner_profile']), PROFILE_FACT_CHARS)
        self.assertEqual(len(context.facts['current_context']), CURRENT_CONTEXT_FACT_CHARS)
        self.assertFalse(context.too_large())
        orchestration = Orchestration(ConversationJudgments(engine), catalogue, request='요청')
        orchestration.first()
        self.assertEqual((seen[-1].facts['owner_profile'], seen[-1].facts['current_context']), ('none', 'none'))

    def test_the_question_leaves_the_owners_message_to_the_worker(self):
        """#820: no topic-continuation or statement-handling wording: the worker reads the message itself."""
        self.assertNotIn('brief.goal', QUESTION)
        self.assertNotIn('topic', QUESTION)
        self.assertNotIn('propose a memory', QUESTION)
        self.assertIn('it decides for itself what the message needs', QUESTION)


class StatedProfileInLookups(unittest.TestCase):
    """#804 review: an owner-stated, accepted profile fact may shape a lookup; other written values stay out (#605 N4)."""

    def test_only_an_accepted_profile_fact_is_not_a_lookup_exclusion(self):
        from personal_agent.agent_runtime import owner_stated_profile
        self.assertTrue(owner_stated_profile('profile.place.work', {'state': 'current', 'id': 'm1'}))
        self.assertFalse(owner_stated_profile('profile.place.work', {'state': 'pending', 'requires_owner_approval': True}))
        self.assertFalse(owner_stated_profile('passport', {'state': 'current', 'id': 'm2'}))

    def test_work_written_values_skips_only_accepted_profile_facts(self):
        from personal_agent.agent_runtime import work_written_values
        with tempfile.TemporaryDirectory() as tmp:
            store = QuickStore(Path(tmp) / 's')
            job = store.enqueue('판교 카카오뱅크로 출근했어', 'k1')
            stated = store.save_memory_candidate(job, 'profile.place.work', '판교 카카오뱅크')
            store.save_memory_candidate(job, 'profile.food.likes', '추론된 선호')
            store.save_memory_candidate(job, 'passport', '여권번호 M1234')
            with store.db() as db:
                db.execute("UPDATE memory_candidates SET state='accepted' WHERE id=?", (stated['id'],))
            written = work_written_values(store, job)
            self.assertNotIn('판교 카카오뱅크', written)
            self.assertIn('추론된 선호', written, 'a pending inference stays excluded')
            self.assertIn('여권번호 M1234', written)


class UnmediatedEngine(Harness):
    """ORCH-07 (#795): re-delegation honours the unmediated-engine rule ``safe_retry`` applies.

    On trusted-local AgentOS does not confine the CLI's own tools, so an
    attempt there is a possible effect unless the CLI's own report shows no
    host action.  A strict-isolated attempt is judged from its tool events only.
    """

    def failing_attempt(self, meta, before=None):
        self.engine.before = before
        self.engine.fail = [ExecutionError(INVALID_OUTPUT, failure_class='invalid-output', meta=meta)]
        self.script([plan('codex', 'Look it up.'), plan('openai', 'Answer directly.')])
        return self.run_work('알려줘', key=f'unmediated-{len(self.engine.turns)}')

    def assert_stopped_for_effect(self, job, outcome='worker_failed'):
        last = self.events(job, 'evaluated')[-1][1]
        self.assertEqual((last['outcome'], last['next'], last['stop']), (outcome, 'stop', 'effect'))
        self.assertEqual(len(self.asked_plans), 1, 'no re-plan after a possible unmediated effect')
        self.assertEqual(self.transport.bodies, [], 'no other worker ran')

    def test_a_trusted_local_attempt_recorded_unmediated_without_a_cli_report_stops_with_effect(self):
        from personal_agent.agent_runtime import ENGINE_UNMEDIATED, work_source_records
        # A killed or timed-out CLI reports no parsed stream: absent evidence is not "no action".
        for meta in (None, {'argv': ['codex', 'exec'], 'duration_ms': 1}):
            with self.subTest(meta=meta):
                self.asked_plans.clear()
                job, row = self.failing_attempt(meta)
                self.assertIn(ENGINE_UNMEDIATED, work_source_records(self.store)[job])
                self.assert_stopped_for_effect(job)
                self.assertEqual(row['status'], 'failed')

    def test_a_trusted_local_attempt_whose_cli_ran_a_host_action_stops_with_effect(self):
        for call in ({'type': 'command_execution', 'name': 'command_execution', 'status': 'completed'},
                     {'type': 'file_change', 'name': 'file_change', 'status': 'completed'},
                     {'type': 'tool_use', 'name': 'Read', 'status': 'requested'}):
            with self.subTest(call=call):
                self.asked_plans.clear()
                job, _row = self.failing_attempt(reported([call]))
                self.assert_stopped_for_effect(job)

    def test_a_trusted_local_answer_after_a_host_action_is_not_judged_or_redelegated(self):
        self.engine.meta = reported([{'type': 'command_execution', 'name': 'command_execution', 'status': 'completed'}])
        self.script([plan('codex', 'Look it up.'), plan('openai', 'Answer directly.')], goals=[False])
        job, row = self.run_work('알려줘')
        self.assert_stopped_for_effect(job, outcome='not_judged')
        self.assertEqual(self.goals, [False], 'nothing may follow, so no goal judgment was asked')
        self.assertEqual(row['response'], 'cli answer')

    def test_a_trusted_local_attempt_whose_cli_reported_no_host_action_is_redelegated(self):
        calls = [{'type': 'mcp_tool_call', 'name': 'web_search', 'status': 'completed'},
                 {'type': 'web_search', 'name': 'web_search', 'status': 'completed'},
                 {'type': 'tool_use', 'name': 'mcp__agentos__list_notes', 'status': 'requested'},
                 {'type': 'tool_use', 'name': 'WebSearch', 'status': 'requested'},
                 # Claude Code's permission layer refused it, so it did not run.
                 {'type': 'tool_use', 'name': 'Bash', 'status': 'requested'},
                 {'type': 'tool_use', 'name': 'Bash', 'status': 'denied'}]
        job, row = self.failing_attempt(reported(calls, end='result'))
        first = self.events(job, 'evaluated')[0][1]
        self.assertEqual((first['outcome'], first['next'], first['stop']), ('worker_failed', 'redelegate', None))
        self.assertEqual(row['response'], 'api answer')

    def strict(self):
        from personal_agent.bounded_execution import STRICT_PROFILE, StrictIsolatedAgentOSMcpTools
        self.store.put('subscription_isolation', {'profile': STRICT_PROFILE,
                                                  'qualified': {'codex': {'platform': sys.platform}}})
        self.assertIs(self.service.subscription_facade('codex')[0], StrictIsolatedAgentOSMcpTools)

    def test_a_strict_profile_attempt_with_only_reads_is_redelegated(self):
        self.strict()

        def read(tools):
            tools.capabilities.record('web_search', 'succeeded',
                                      json.dumps({'host_action': 'web_search', 'evidence': {'sources': ['https://a.test']}}))
        # AgentOS confined this CLI's own tools, so no CLI report is needed.
        job, row = self.failing_attempt(None, before=read)
        first = self.events(job, 'evaluated')[0][1]
        self.assertEqual((first['outcome'], first['next'], first['stop']), ('worker_failed', 'redelegate', None))
        self.assertEqual(row['status'], 'succeeded')
        self.assertEqual(row['response'], 'api answer')

    def test_a_strict_profile_attempt_that_ran_an_effect_still_stops(self):
        self.strict()

        def save(tools):
            tools.capabilities.record('save_note', 'succeeded', json.dumps({'host_action': 'save_note', 'evidence': {}}))
        job, _row = self.failing_attempt(None, before=save)
        self.assert_stopped_for_effect(job)


class CliHostActions(unittest.TestCase):
    """#795: what a CLI's own report shows about host actions, read in ``cli_metadata``'s shape."""

    def test_unobservable_reports_are_none(self):
        from personal_agent.quickstart_service import CLI_TOOL_CALLS_KEPT
        host = AgentService.cli_host_actions
        full = [{'type': 'mcp_tool_call', 'name': 'web_search', 'status': 'completed'}] * CLI_TOOL_CALLS_KEPT
        for meta in (None, {}, {'tool_calls': None}, {'tool_calls': 'x'}, reported([None]), reported(full),
                     # No end-of-turn record: a report from before #793, or a stream that stopped mid-turn.
                     {'tool_calls': []}, reported([], end='item.completed'), {'tool_calls': [], 'stream_tail': 'x'}):
            with self.subTest(meta=meta):
                self.assertIsNone(host(meta))

    def test_an_empty_malformed_or_cut_off_stream_is_unobservable(self):
        """#803 review P1: ``cli_metadata`` reports ``tool_calls: []`` for any stdout; that alone is no evidence."""
        from personal_agent.bounded_execution import cli_metadata
        started = json.dumps({'type': 'item.started', 'item': {'type': 'agent_message'}})
        for engine, raw in (('codex', ''), ('codex', 'not json\n{broken'), ('claude-code', ''),
                            ('codex', json.dumps({'type': 'turn.started'}) + '\n' + started),
                            ('claude-code', json.dumps({'type': 'system', 'subtype': 'init'}))):
            with self.subTest(engine=engine, raw=raw):
                meta = cli_metadata(engine, raw)
                self.assertEqual(meta['tool_calls'], [])
                self.assertIsNone(AgentService.cli_host_actions(meta))

    def test_bridge_calls_own_search_and_denied_calls_are_not_host_actions(self):
        host = AgentService.cli_host_actions
        self.assertEqual(host(reported([])), ())
        self.assertEqual(host(reported([{'type': 'mcp_tool_call', 'name': 'save_note', 'status': 'completed'},
                                              {'type': 'tool_use', 'name': 'mcp__agentos__save_note', 'status': 'requested'},
                                              {'type': 'web_search', 'name': 'web_search', 'status': 'completed'},
                                              {'type': 'tool_use', 'name': 'WebSearch', 'status': 'requested'}])), ())
        self.assertEqual(host(reported([{'type': 'tool_use', 'name': 'Bash', 'status': 'requested'},
                                              {'type': 'tool_use', 'name': 'Bash', 'status': 'denied'}])), ())

    def test_everything_else_is_named(self):
        host = AgentService.cli_host_actions
        self.assertEqual(host(reported([{'type': 'command_execution', 'name': 'command_execution', 'status': 'in_progress'},
                                              {'type': 'file_change', 'name': 'file_change', 'status': 'completed'},
                                              {'type': 'tool_use', 'name': 'Write', 'status': 'requested'}])),
                         ('command_execution', 'file_change', 'Write'))
        # A denial covers one call only; an MCP server other than agentos is not the bridge.
        self.assertEqual(host(reported([{'type': 'tool_use', 'name': 'Bash', 'status': 'requested'},
                                              {'type': 'tool_use', 'name': 'Bash', 'status': 'requested'},
                                              {'type': 'tool_use', 'name': 'Bash', 'status': 'denied'},
                                              {'type': 'tool_use', 'name': 'mcp__other__x', 'status': 'requested'},
                                              {'type': 'mcp_tool_call', 'name': 'other_server_tool', 'status': 'completed'}])),
                         ('Bash', 'mcp__other__x', 'other_server_tool'))

    def test_the_kept_count_and_shapes_match_cli_metadata(self):
        from personal_agent.bounded_execution import cli_metadata
        from personal_agent.quickstart_service import CLI_TOOL_CALLS_KEPT
        line = json.dumps({'type': 'item.completed', 'item': {'type': 'command_execution', 'status': 'completed'}})
        calls = cli_metadata('codex', '\n'.join([line] * (CLI_TOOL_CALLS_KEPT + 10)))['tool_calls']
        self.assertEqual(len(calls), CLI_TOOL_CALLS_KEPT)
        self.assertIsNone(AgentService.cli_host_actions({'tool_calls': calls}))
        ended = json.dumps({'type': 'turn.completed'})
        self.assertEqual(AgentService.cli_host_actions(cli_metadata('codex', line + '\n' + ended)), ('command_execution',))
        self.assertEqual(AgentService.cli_host_actions(cli_metadata('codex', json.dumps({'type': 'turn.failed'}))), ())
        claude = json.dumps({'type': 'assistant', 'message': {'content': [
            {'type': 'tool_use', 'name': 'mcp__agentos__web_search'}, {'type': 'tool_use', 'name': 'Bash'}]}})
        denied = json.dumps({'type': 'result', 'permission_denials': [{'tool_name': 'Bash'}]})
        self.assertEqual(AgentService.cli_host_actions(cli_metadata('claude-code', claude + '\n' + denied)), ())
        result = json.dumps({'type': 'result', 'subtype': 'success'})
        self.assertEqual(AgentService.cli_host_actions(cli_metadata('claude-code', claude + '\n' + result)), ('Bash',))
        self.assertIsNone(AgentService.cli_host_actions(cli_metadata('claude-code', claude)), 'no result record')



class CatalogueMatchesOffered(Harness):
    """#812 (Work 33d1d85f): a plan never briefs a context-gated tool the turn does not offer."""

    def test_a_package_alias_of_a_gated_action_is_hidden_on_every_worker(self):
        """#812 review: gating follows the host action, so an alias is hidden too, on the API workers as well."""
        from personal_agent.orchestrator import worker_catalogue
        packages = self.service.runtime_packages()
        alias = {'id': 'remember_where', 'host_action': 'propose_current_state', 'mode': 'write'}
        with mock.patch.object(self.service, 'runtime_packages',
                               return_value=[*packages, {'id': 'pkg', 'enabled': True, 'tools': [alias]}]):
            catalogue = worker_catalogue(self.service)
            for worker in catalogue.workers:
                with self.subTest(worker=worker['id']):
                    self.assertNotIn('remember_where', worker['tools'])
                    self.assertNotIn('propose_current_state', worker['tools'])
            self.service.context_observations.set_controls({'enabled': True})
            self.assertIn('remember_where', worker_catalogue(self.service).worker('openai')['tools'])

    def test_propose_current_state_is_listed_only_while_current_context_is_on(self):
        from personal_agent.orchestrator import worker_catalogue
        self.assertNotIn('propose_current_state', worker_catalogue(self.service).worker('codex')['tools'])
        self.service.context_observations.set_controls({'enabled': True})
        self.assertIn('propose_current_state', worker_catalogue(self.service).worker('codex')['tools'])


class ThinOrchestration(Harness):
    """ARCH-THIN-01 (#820), live Work 2026-09-28 16:05 KST: the owner said "점심은 이미 반포6 분짜오 먹었어".

    Observed on main 65e75e3: the plan narrowed the goal to a short acknowledgement with an empty tool
    subset; the worker acknowledged; the goal judgment (observations only) said not reached three times,
    three workers ran and the Work was stored ``failed``.  Now the owner's words, the conversation and the
    full toolset reach the worker, one judgment reads the reply, and the Work ends succeeded.
    """

    STATEMENT = '점심은 이미 반포6 분짜오 먹었어'
    ACK = '오늘 점심은 이미 반포6에서 분짜오를 드셨군요.'

    def earlier_turn(self):
        self.engine.answers = ['근처 점심으로 분짜와 국밥을 추천드려요.']
        self.run_work('점심 뭐 먹을까?')

    def test_an_owner_statement_acknowledged_ends_succeeded_after_one_attempt(self):
        self.earlier_turn()
        before = len(self.engine.turns)
        self.engine.answers = [self.ACK]
        # The plan of the live Work: notes that narrow to an acknowledgement (#826: no tool subset exists).
        self.script([plan('codex', 'Short acknowledgement only.'),
                     plan('openai', 'Other path.'), plan('codex', 'Third.', model='gpt-5.6-luna')],
                    goals=[True, False, False])
        job, row = self.run_work(self.STATEMENT)
        self.assertEqual(row['status'], 'succeeded')
        self.assertEqual(row['response'], self.ACK)
        self.assertEqual(len(self.asked_plans), 1, 'one plan call')
        self.assertEqual(len(self.asked_goals), 1, 'one outcome judgment')
        self.assertEqual(len(self.engine.turns) - before, 1, 'no re-delegation')
        self.assertEqual(self.transport.bodies, [])
        turn = self.engine.turns[-1]
        # The owner's words verbatim, with the conversation; the notes only add to them.
        self.assertEqual(turn['context']['request'], self.STATEMENT)
        self.assertEqual([m['content'] for m in turn['context']['conversation']],
                         ['점심 뭐 먹을까?', '근처 점심으로 분짜와 국밥을 추천드려요.'])
        self.assertTrue(turn['prompt'].endswith('# Current request\n' + self.STATEMENT))
        # The worker keeps its full toolset: the Memory write path stays offered.
        self.assertIn('save_memory', turn['offered'])
        # The one judgment read the reply and the conversation, not a plan-written goal.
        [judged] = self.asked_goals
        self.assertEqual(judged.facts['owner_request'], self.STATEMENT)
        self.assertEqual(judged.facts['reply'], self.ACK)
        self.assertIn('점심 뭐 먹을까?', judged.facts['recent_conversation'])
        self.assertNotIn('acknowledgement', json.dumps(judged.facts, ensure_ascii=False))
        # A succeeded Work gets the #805 owner-model upkeep, which proposes the stated fact.
        with self.store.db() as db:
            self.assertIn(job, [r['job_id'] for r in db.execute('SELECT job_id FROM owner_model_upkeep')])

    def test_a_worker_that_proposes_the_fact_ends_succeeded_and_is_not_redelegated(self):
        def propose(tools):
            tools.capabilities.record('save_memory', 'succeeded', json.dumps(
                {'host_action': 'save_memory', 'evidence': {'saved': False, 'state': 'pending',
                                                            'refused_because': 'value-not-in-owner-request'}}))
        self.engine.before = propose
        self.engine.answers = [self.ACK + ' 기억해 둘까요?']
        self.script([plan('codex', ''), plan('openai', 'Other path.')], goals=[False])
        job, row = self.run_work(self.STATEMENT)
        self.assertEqual(row['status'], 'succeeded')
        self.assertEqual(len(self.engine.turns), 1)
        self.assertEqual(self.transport.bodies, [], 'a memory proposal is never re-delegated')
        self.assertIn(self.ACK, row['response'])

    def test_a_reply_judged_short_is_still_delivered_and_the_notes_never_become_the_goal(self):
        from personal_agent.conversation_projection import TERMINAL_ANSWER_LABEL
        self.engine.answers = [self.ACK]
        self.script([plan('codex', 'Only record the state.')], goals=[False])
        job, row = self.run_work(self.STATEMENT)
        self.assertEqual(row['status'], 'failed')
        self.assertEqual(row['response'], self.ACK)
        bubble = self.service.telegram_result_text(row['response'], row['owner_cause'], row['status'])
        self.assertIn(TERMINAL_ANSWER_LABEL + '\n' + self.ACK, bubble)
        prompt = self.engine.turns[-1]['prompt']
        self.assertLess(prompt.index('Only record the state.'), prompt.index('# Current request\n' + self.STATEMENT))
        self.assertIn('never replace or narrow the owner\'s request', prompt)
