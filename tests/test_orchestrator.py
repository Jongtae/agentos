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
                                              ExecutionError, ExecutionResult, private_read_actions, turn_actions)
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


def plan(worker, goal, *, model='', context=SECTIONS, criteria=('the answer states it',), tools=None, reason='fits'):
    return {'worker': worker, 'model': model,
            'brief': {'goal': goal, 'context': list(context), 'completion_criteria': list(criteria)},
            'tools_mode': 'worker_default' if tools is None else 'subset', 'tools': list(tools or ()),
            'reason': reason}


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

    def execute(self, engine, prompt, tools, **kwargs):
        offered = sorted(tools._offered())
        self.turns.append({'engine': engine, 'prompt': prompt, 'model': kwargs.get('model'),
                           'native_search': tools.native_search, 'reason': tools.native_search_reason,
                           'only': None if tools.only is None else sorted(tools.only), 'offered': offered,
                           'context': kwargs.get('context')})
        if self.before:
            self.before(tools)
        if self.fail:
            raise self.fail.pop(0)
        return ExecutionResult(self.answers.pop(0) if self.answers else 'cli answer', engine, 0)

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
        self.plans, self.goals = [], []
        self.asked_plans = []

    def script(self, plans, goals=()):
        """The Judgment AI: ``plans`` answer the plan calls in order, ``goals`` the CLI goal judgments."""
        self.plans, self.goals = list(plans), list(goals)

        def structured(context, question, schema):
            self.asked_plans.append((context, question, schema))
            if not self.plans:
                return None
            item = self.plans.pop(0)
            return item if isinstance(item, StructuredDecision) or item is None else decided(item)

        def judge(context, proposition):
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

    def events(self, job, status=None):
        with self.store.db() as db:
            rows = db.execute('SELECT status,detail FROM tool_events WHERE job_id=? AND tool=? ORDER BY id',
                              (job, EVENT_TOOL)).fetchall()
        return [(row['status'], json.loads(row['detail'])) for row in rows if status is None or row['status'] == status]


class RoutingAndBriefs(Harness):
    def test_different_requests_go_to_different_workers_and_models_with_their_own_briefs(self):
        self.script([plan('codex', 'Find and compare the two options the owner named; cite each source.',
                          model='gpt-5.6-luna'),
                     plan('openai', 'Rewrite the owner\'s paragraph in a warmer tone, same meaning.',
                          context=('profile',))],
                    goals=[True])
        first, row = self.run_work('이 두 가지 비교해줘')
        self.assertEqual(row['status'], 'succeeded')
        self.assertEqual(len(self.engine.turns), 1)
        turn = self.engine.turns[0]
        self.assertEqual((turn['engine'], turn['model']), ('codex', 'gpt-5.6-luna'))
        self.assertIn('# Brief for this attempt', turn['prompt'])
        self.assertIn('Find and compare the two options', turn['prompt'])
        self.assertIn('Done when:\n- the answer states it', turn['prompt'])
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
        self.assertEqual((planned['worker'], planned['model'], planned['sections']), ('openai', None, ['profile']))

    def test_the_brief_selects_the_context_sections_the_worker_receives(self):
        self.store.put('model', self.store.config('model', {}))
        self.script([plan('codex', 'Answer from general knowledge.', context=())], goals=[True])
        self.store.enqueue('앞선 질문', 'orch-history')
        self.engine.answers = ['first']
        self.service.use_decision_engine(UnavailableDecisionEngine())
        self.assertTrue(self.service.run_one())
        self.script([plan('codex', 'Answer from general knowledge.', context=())], goals=[True])
        self.run_work('다음 질문')
        context = self.engine.turns[-1]['context']
        self.assertEqual(context['conversation'], [], 'history was not selected')
        self.assertNotIn('profile', context)
        self.assertEqual(context['brief'].splitlines()[0], 'Goal: Answer from general knowledge.')


class Redelegation(Harness):
    def test_a_shortfall_is_redelegated_with_an_adjusted_brief_to_another_worker(self):
        self.script([plan('codex', 'Look it up.'), plan('openai', 'Explain it step by step with the definition first.')],
                    goals=[False])
        job, row = self.run_work('이것 좀 알려줘')
        self.assertEqual(row['status'], 'succeeded')
        self.assertEqual(row['response'], 'api answer', 'the owner gets the attempt that reached the goal')
        self.assertEqual(len(self.engine.turns), 1)
        self.assertTrue(self.transport.bodies)
        self.assertIn('An earlier attempt did not meet this goal', self.transport.bodies[0]['messages'][0]['content'])
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
        self.script([plan('codex', f'Try path {n}.') for n in range(5)], goals=[False] * 5)
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

    def test_a_later_attempt_keeps_this_works_private_reads(self):
        """Review P2-1: attempt 1 read notes; attempt 2 on a CLI with its usual tools
        gets no own web search, no private-read-and-search pair, and a size/digest-only envelope."""
        def read_notes(tools):
            if len(self.engine.turns) == 1:
                tools.capabilities.record('list_notes', 'succeeded',
                                          json.dumps({'host_action': 'list_notes', 'evidence': {'count': 1}}))
        self.engine.before = read_notes
        self.script([plan('codex', 'Read the saved notes.', tools=('list_notes',)), plan('codex', 'Answer from them.')],
                    goals=[False, True])
        job, row = self.run_work('메모 확인해줘')
        self.assertEqual(len(self.engine.turns), 2)
        first, second = self.engine.turns
        self.assertIsNone(second['only'], 'worker_default')
        self.assertFalse(second['native_search'])
        self.assertEqual(second['reason'], 'private_turn')
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
        self.engine.fail = [ExecutionError('usage limit', failure_class='usage-limit')]
        self.script([plan('codex', 'Look it up.'), plan('openai', 'Answer directly.')])
        job, row = self.run_work('알려줘')
        self.assertEqual(row['status'], 'succeeded')
        self.assertEqual(row['response'], 'api answer')
        first = self.events(job, 'evaluated')[0][1]
        self.assertEqual((first['outcome'], first['next']), ('worker_failed', 'redelegate'))

    def test_a_failed_worker_without_a_new_plan_fails_as_before(self):
        self.engine.fail = [ExecutionError('usage limit', failure_class='usage-limit')]
        self.script([plan('codex', 'Look it up.')])
        job, row = self.run_work('알려줘')
        self.assertEqual(row['status'], 'failed')
        self.assertEqual(self.events(job, 'evaluated')[-1][1]['stop'], 'replan_failed')


class Fallback(Harness):
    def assert_default_raw_run(self, job, code):
        [turn] = self.engine.turns
        self.assertEqual((turn['engine'], turn['model']), ('codex', None))
        self.assertNotIn('# Brief for this attempt', turn['prompt'])
        self.assertIsNone(turn['only'])
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
                          (plan('codex', 'x', tools=('list_notes', 'calendar_query')), 'tools'),
                          (plan('codex', '   '), 'brief')):
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


class PerRequestTools(Harness):
    def test_notes_with_search_off_or_search_without_notes_never_both(self):
        self.script([plan('codex', 'Read the owner\'s saved notes and list the matching ones.', tools=('list_notes',)),
                     plan('codex', 'Search the public web.', tools=('web_search',))], goals=[True, True])
        self.run_work('메모에서 찾아줘')
        self.run_work('검색해줘')
        notes, search = self.engine.turns
        self.assertFalse(notes['native_search'])
        self.assertEqual(notes['reason'], 'orchestrated_private_tools')
        self.assertEqual(notes['offered'], ['list_notes'])
        self.assertTrue(search['native_search'])
        self.assertEqual(search['offered'], [], 'the CLI\'s own search replaces the bridge search')
        private = private_read_actions()
        for turn in (notes, search):
            self.assertFalse(turn['native_search'] and set(turn['offered']) & private)

    def test_the_bridge_and_the_claude_allowlist_carry_only_the_subset(self):
        self.assertEqual(turn_actions(BOUNDED_PROFILE, native_search=False, only={'list_notes'}), ('list_notes',))
        self.assertEqual(turn_actions(BOUNDED_PROFILE, native_search=True, only={'list_notes'}), ())
        adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runner=lambda *a, **k: None,
                                          runtime_root=self.tmp / 'turns')
        config = self.tmp / 'mcp.json'
        config.write_text(json.dumps({'mcpServers': {'agentos': {'args': []}}}))
        argv = adapter.command('claude-code', '/runtime/claude', 'p', config, only=frozenset({'list_notes'}))
        self.assertEqual(argv[-1], 'mcp__agentos__list_notes')
        argv = adapter.command('claude-code', '/runtime/claude', 'p', config, native_search=True,
                               only=frozenset({'web_search'}))
        self.assertEqual(argv[-1], 'WebSearch', 'no private read pre-approved next to the CLI\'s own search')
        seen = {}

        class Done:
            returncode = 0
            stdout = json.dumps({'item': {'type': 'agent_message', 'text': 'done'}})

        def runner(argv, **kwargs):
            seen['args'] = json.loads((Path(kwargs['cwd']) / 'agentos-mcp.json').read_text())['mcpServers']['agentos']['args']
            return Done()
        adapter = BoundedExecutionAdapter(finder=lambda name: '/runtime/' + name, runner=runner,
                                          runtime_root=self.tmp / 'turns2', codex_home=self.tmp)
        from personal_agent.agent_runtime import Capabilities
        tools = AgentOSMcpTools(Capabilities(self.store, None, {}, '', 'job', lambda *a: None, document_access=False))
        tools.only = frozenset({'list_notes'})
        adapter.execute('codex', 'prompt', tools)
        self.assertIn('--only=list_notes', seen['args'])

    def test_the_bridge_process_serves_only_the_subset(self):
        job = self.store.enqueue('메모', 'bridge-only')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job,))
        requests = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
                    {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}]
        out = io.StringIO()
        with mock.patch.object(sys, 'stdin', io.StringIO(''.join(json.dumps(r) + '\n' for r in requests))), \
                mock.patch.object(sys, 'stdout', out):
            mcp_bridge.serve(str(self.store.root), job, only=frozenset({'list_notes'}))
        replies = [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]
        self.assertEqual([tool['name'] for tool in replies[1]['result']['tools']], ['list_notes'])


class PlannerHistory(Harness):
    def test_rows_withheld_from_a_worker_are_withheld_from_the_planner(self):
        """Review P1: document-job rows and rows of a Work that read a private store never reach the plan call."""
        from personal_agent.agent_runtime import WORK_SOURCES_KEY
        jobs = []
        for text, answer in (('문서 질문', 'DOCUMENT-ANSWER'), ('메모 질문', 'NOTES-ANSWER'), ('일반 질문', 'PLAIN-ANSWER')):
            self.engine.answers = [answer]
            jobs.append(self.run_work(text)[0])
        document, notes, plain = jobs
        self.store.put('file_workspace_document_jobs', [document])
        records = self.store.config(WORK_SOURCES_KEY, {})
        records[notes] = [*records[notes], 'history:personal-space']
        self.store.put(WORK_SOURCES_KEY, records)
        self.script([plan('codex', 'Answer.')], goals=[True])
        self.run_work('이어서')
        excerpt = self.asked_plans[-1][0].facts['recent_conversation']
        self.assertIn('PLAIN-ANSWER', excerpt)
        self.assertIn('일반 질문', excerpt)
        for withheld in ('DOCUMENT-ANSWER', '문서 질문', 'NOTES-ANSWER', '메모 질문'):
            self.assertNotIn(withheld, excerpt)

    def test_a_work_without_a_source_record_is_withheld(self):
        from personal_agent.agent_runtime import WORK_SOURCES_KEY
        self.engine.answers = ['UNRECORDED-ANSWER']
        earlier, _row = self.run_work('예전 질문')
        records = self.store.config(WORK_SOURCES_KEY, {})
        records.pop(earlier)
        self.store.put(WORK_SOURCES_KEY, records)
        self.assertEqual(self.service.planner_history(
            [{'role': 'assistant', 'content': 'x', 'job_id': earlier}, {'role': 'user', 'content': 'now'}], ()), [])


class Preflight(Harness):
    def test_an_explicit_search_preflight_honours_a_subset_without_web_search(self):
        """Review P2: the /search preflight is a web_search call; a subset without it skips it."""
        self.script([plan('codex', 'Answer from the saved notes.', tools=('list_notes',))], goals=[True])
        job, row = self.run_work('/search 서울 날씨')
        self.assertEqual(row['status'], 'succeeded')
        self.assertEqual(len(self.engine.turns), 1)
        with self.store.db() as db:
            tools = [r['tool'] for r in db.execute('SELECT tool FROM tool_events WHERE job_id=?', (job,))]
        self.assertNotIn('web_search', tools)

    def test_the_preflight_still_runs_with_the_usual_tools(self):
        self.script([plan('codex', 'Search it.')], goals=[True])
        job, _row = self.run_work('/search 서울 날씨')
        with self.store.db() as db:
            scopes = [json.loads(r['detail']).get('scope') for r in db.execute(
                "SELECT detail FROM tool_events WHERE job_id=? AND tool='web_search'", (job,))]
        self.assertIn('subscription-preflight', scopes)


class Pinned(Harness):
    def test_spliced_private_material_keeps_the_default_worker(self):
        self.store.save_note = None
        with self.store.db() as db:
            db.execute('INSERT INTO notes VALUES (?,?,?)', ('n1', 'a saved note', 1.0))
        self.script([plan('codex', 'Summarize the notes.')], goals=[True])
        self.run_work('/summarize')
        [(_context, _question, schema)] = self.asked_plans
        self.assertEqual(schema['properties']['worker']['enum'], ['codex'], 'only the approved destination')


class CatalogueData(Harness):
    def test_catalogue_lists_configured_routes_with_models_tiers_and_availability(self):
        from personal_agent.orchestrator import worker_catalogue
        catalogue = worker_catalogue(self.service)
        codex, openai = catalogue.worker('codex'), catalogue.worker('openai')
        self.assertTrue(codex['default'] and codex['available'])
        self.assertIn('gpt-5.6-luna', codex['models'])
        self.assertIn('list_notes', codex['private_tools'])
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


class OrchestrationUnit(unittest.TestCase):
    def catalogue(self):
        workers = [{'id': 'a', 'kind': 'subscription', 'name': 'A', 'destination': '', 'default': True, 'available': True,
                    'reason': '', 'native_search': True, 'browser': False, 'cost': 'c', 'latency': 'l',
                    'default_model': '', 'models': ['m1'], 'model_tiers': {'m1': 'lowest-cost'},
                    'tools': ['list_notes', 'web_search'], 'private_tools': ['list_notes']},
                   {'id': 'b', 'kind': 'api', 'name': 'B', 'destination': '', 'default': False, 'available': True,
                    'reason': '', 'native_search': False, 'browser': False, 'cost': 'c', 'latency': 'l',
                    'default_model': 'm2', 'models': ['m2'], 'model_tiers': {}, 'tools': ['weather'], 'private_tools': []},
                   {'id': 'c', 'kind': 'api', 'name': 'C', 'destination': '', 'default': False, 'available': False,
                    'reason': 'no_api_key', 'native_search': False, 'browser': False, 'cost': 'c', 'latency': 'l',
                    'default_model': '', 'models': [], 'model_tiers': {}, 'tools': [], 'private_tools': []}]
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
        ok, _ = orchestration.validate(plan('b', 'g', tools=('weather',)), candidates, 1)
        self.assertEqual((ok.worker, ok.tools), ('b', frozenset({'weather'})))
        for data, what in ((plan('c', 'g'), 'worker'), (plan('zz', 'g'), 'worker'), (plan('a', 'g', model='m2'), 'model'),
                           (plan('b', 'g', tools=('list_notes',)), 'tools'), ({'worker': 'a'}, 'shape'),
                           (plan('a', 'g', context=('everything',)), 'sections')):
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

    def test_pinned_offers_only_the_default(self):
        self.assertEqual([row['id'] for row in self.catalogue().available(pinned=True)], ['a'])

    def test_the_question_and_catalogue_name_no_request(self):
        rendered = render_catalogue(self.catalogue().available())
        self.assertIn('list_notes (private read)', rendered)
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

    def test_attempt_native_search_never_pairs_with_a_private_read(self):
        private = private_read_actions()
        for tools in (None, set(), {'web_search'}, {'list_notes'}, {'list_notes', 'web_search'}, {'weather'}):
            attempt = Attempt(1, 'a', goal='g', tools=tools, planned=True)
            enabled, _reason = attempt.native_search(True, '', private)
            offered = set(turn_actions(BOUNDED_PROFILE, enabled, None if tools is None else frozenset(tools)))
            with self.subTest(tools=tools):
                self.assertFalse(enabled and offered & private)
        self.assertEqual(Attempt(1, 'a').native_search(False, 'private_turn', private), (False, 'private_turn'))

    def test_attempts_history_is_bounded(self):
        orchestration, _events, _engine = self.orchestration(None)
        orchestration.orchestrated = True
        for n in range(3):
            orchestration.history.append((Attempt(n + 1, 'a', goal='g' * 500, planned=True), 'not_reached', 'y' * 900, 'z' * 900))
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
        context = turn_context([{'role': 'user', 'content': 'the request'}], 'cli', brief='Goal: g')
        text = render_turn_prompt(context)
        self.assertLess(text.index('# Brief for this attempt'), text.index('# Current request'))
        self.assertTrue(text.endswith('# Current request\nthe request'))
        self.assertNotIn('brief', turn_context([{'role': 'user', 'content': 'r'}], 'cli'))


if __name__ == '__main__':
    unittest.main()
