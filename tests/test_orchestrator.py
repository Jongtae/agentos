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
#: A bundled listing without the ranked gpt-6-luna (codex-cli 0.153.4 shape).
BUNDLED = ('gpt-5.6-terra', 'gpt-5.6-luna', 'gpt-5.5')
SEARCH_TOOLS = ('bounded_public_research', 'web_search')


def plan(worker, goal, *, model='', context=SECTIONS, criteria=('the answer states it',), tools=None, reason='fits',
         tools_reason=None):
    return {'worker': worker, 'model': model,
            'brief': {'goal': goal, 'context': list(context), 'completion_criteria': list(criteria)},
            'tools_mode': 'worker_default' if tools is None else 'subset', 'tools': list(tools or ()),
            'tools_reason': ('only these tools are needed' if tools is not None else '') if tools_reason is None
            else tools_reason,
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
        self.meta = None

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

    def script(self, plans, goals=(), owner_questions=()):
        """The Judgment AI: ``plans`` answer the plan calls in order, ``goals`` the CLI goal judgments,
        ``owner_questions`` the #740 owner-input judgments."""
        self.plans, self.goals, self.owner_questions = list(plans), list(goals), list(owner_questions)
        self.asked_owner_input = []

        def structured(context, question, schema):
            self.asked_plans.append((context, question, schema))
            if not self.plans:
                return None
            item = self.plans.pop(0)
            return item if isinstance(item, StructuredDecision) or item is None else decided(item)

        def judge(context, proposition):
            if context.purpose == 'owner-input-needed':
                self.asked_owner_input.append(context)
                if not self.owner_questions:
                    return None
                return BinaryDecision(OUTCOME_DECIDED, self.owner_questions.pop(0), fixture_confidence())
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

    def no_search(self):
        """The one subset shape that keeps private reads: the web-search tools removed (#735)."""
        return tuple(tool for tool in self.codex_tools() if tool not in SEARCH_TOOLS)

    def no_private(self):
        """The other kept shape: the private-read tools removed."""
        return tuple(tool for tool in self.codex_tools() if tool != 'list_notes')

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

    def test_a_later_attempt_keeps_this_works_private_reads(self):
        """Review P2-1: attempt 1 read notes; attempt 2 on a CLI with its usual tools
        gets no own web search, no private-read-and-search pair, and a size/digest-only envelope."""
        def read_notes(tools):
            if len(self.engine.turns) == 1:
                tools.capabilities.record('list_notes', 'succeeded',
                                          json.dumps({'host_action': 'list_notes', 'evidence': {'count': 1}}))
        self.engine.before = read_notes
        self.script([plan('codex', 'Read the saved notes.', tools=self.no_search()), plan('codex', 'Answer from them.')],
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
        self.script([plan('codex', 'Read the owner\'s saved notes and list the matching ones.', tools=self.no_search()),
                     plan('codex', 'Search the public web.', tools=self.no_private())], goals=[True, True])
        self.run_work('메모에서 찾아줘')
        self.run_work('검색해줘')
        notes, search = self.engine.turns
        self.assertFalse(notes['native_search'])
        self.assertEqual(notes['reason'], 'orchestrated_private_tools')
        self.assertIn('list_notes', notes['offered'])
        self.assertFalse(set(notes['offered']) & set(SEARCH_TOOLS))
        self.assertTrue(search['native_search'])
        self.assertNotIn('list_notes', search['offered'])
        self.assertFalse(set(search['offered']) & set(SEARCH_TOOLS), 'the CLI\'s own search replaces the bridge search')
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


class ToolsAndReplan(Harness):
    """ORCH-02 (#729): full toolset by default, learning from failed attempts, the bridge timeout."""

    def test_the_worker_keeps_its_full_toolset_unless_a_reason_narrows_it(self):
        self.assertIn('tools_mode is "worker_default"', QUESTION)
        self.script([plan('codex', 'Answer.')], goals=[True])
        job, _row = self.run_work('알려줘')
        [turn] = self.engine.turns
        self.assertIsNone(turn['only'])
        self.assertIn('weather', turn['offered'], 'the full offered toolset, not a subset')
        context, _question, schema = self.asked_plans[0]
        self.assertIn('tools_reason', schema['required'])
        descriptions = context.facts['tool_descriptions']
        self.assertIn('- bounded_public_research: ', descriptions)
        self.assertIn('- list_notes: ', descriptions)
        self.assertTrue(all(len(line) < 260 for line in descriptions.splitlines()), 'one line per tool')
        self.assertIsNone(self.events(job, 'planned')[0][1]['tools_reason'])

    def test_a_subset_without_a_stated_reason_becomes_the_full_toolset(self):
        self.script([plan('codex', 'Answer.', tools=self.no_search(), tools_reason='')], goals=[True])
        job, _row = self.run_work('알려줘')
        self.assertIsNone(self.engine.turns[0]['only'])
        planned = self.events(job, 'planned')[0][1]
        self.assertIsNone(planned['tools'])
        self.assertEqual(planned['tools_replaced'], {'requested': sorted(self.no_search()), 'why': 'no_reason'})

    def test_a_subset_with_a_reason_is_kept_and_recorded(self):
        self.script([plan('codex', 'Read the notes.', tools=self.no_search(), tools_reason='keep private reads apart')],
                    goals=[True])
        job, _row = self.run_work('메모 봐줘')
        self.assertEqual(self.engine.turns[0]['only'], sorted(self.no_search()))
        planned = self.events(job, 'planned')[0][1]
        self.assertEqual((planned['tools_reason'], planned['tools_replaced']), ('keep private reads apart', None))

    def test_only_the_two_separation_shapes_survive_validation(self):
        """#735 (Work a8e6aa7b): every one-tool subset became the full toolset."""
        cases = {('bounded_public_research',): 'shape', ('web_search',): 'shape', ('list_notes',): 'shape',
                 ('weather', 'web_search'): 'shape', ('calendar_query',): 'not_offered'}
        for tools, why in cases.items():
            with self.subTest(tools=tools):
                self.engine.turns.clear()
                self.script([plan('codex', 'Answer.', tools=tools)], goals=[True])
                job, _row = self.run_work('알려줘', key=f'shape-{tools}')
                self.assertIsNone(self.engine.turns[0]['only'])
                self.assertEqual(self.events(job, 'planned')[0][1]['tools_replaced']['why'], why)
        for tools in (self.no_search(), self.no_private()):
            with self.subTest(kept=tools):
                self.engine.turns.clear()
                self.script([plan('codex', 'Answer.', tools=tools)], goals=[True])
                job, _row = self.run_work('알려줘', key=f'kept-{tools}')
                self.assertEqual(self.engine.turns[0]['only'], sorted(tools))
                self.assertIsNone(self.events(job, 'planned')[0][1]['tools_replaced'])

    def test_a_replan_never_repeats_a_failed_combination_and_sees_the_incomplete_call(self):
        def hang(tools):
            # The bridge recorded the call as running; the CLI closed the connection before a result.
            tools.capabilities.record('bounded_public_research', 'running', json.dumps(
                {'scope': 'subscription-mcp-bridge', 'host_action': 'bounded_public_research'}))
        self.engine.before = hang
        subset = plan('codex', 'Research it.', tools=('bounded_public_research',))
        self.script([subset, dict(subset)], goals=[False])
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

    def test_a_changed_tool_set_is_allowed_after_a_failure(self):
        self.script([plan('codex', 'Research it.', tools=self.no_private()), plan('codex', 'Use all tools.')],
                    goals=[False, True])
        job, row = self.run_work('조사해줘')
        self.assertEqual(len(self.engine.turns), 2)
        self.assertIsNone(self.engine.turns[1]['only'])
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
        self.engine.meta = {'native_searches': [{'id': 'n1', 'state': 'succeeded', 'queries': ['q'], 'results': []}]}
        self.engine.answers = ['about forty minutes by car']
        self.script([plan('codex', 'Answer it.'), plan('openai', 'Answer it another way.')])

        def judge(context, proposition):
            seen.append(dict(context.facts))
            return BinaryDecision(OUTCOME_DECIDED, False, fixture_confidence())
        self.service.decision_engine._judge = judge
        self.run_work('얼마나 걸려?')
        observations = seen[0]['observations']
        self.assertIn("The worker's final answer (model-stated, not an observation):\nabout forty minutes by car",
                      observations)
        self.assertIn('"sources": []', observations)
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
                                           meta={'unsupported_model': 'gpt-5.6-luna'})]
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
        self.engine.fail = [ExecutionError('rejected: ' + context, failure_class='request-rejected', reason=context)]
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
                                           meta={'unsupported_model': 'gpt-5.6-luna'})]
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


class SubsetCategories(unittest.TestCase):
    """#735 review: a subset removes a whole category or it is replaced."""

    WORKER = {'tools': ['bounded_public_research', 'list_memory', 'list_notes', 'weather', 'web_search'],
              'private_tools': ['list_memory', 'list_notes']}

    def keep(self, removed, reason='keep them apart'):
        from personal_agent.orchestrator import subset_or_default
        return subset_or_default(self.WORKER, [tool for tool in self.WORKER['tools'] if tool not in removed], reason)

    def test_whole_categories_are_kept(self):
        self.assertEqual(self.keep({'list_memory', 'list_notes'})[1], None)
        self.assertEqual(self.keep({'web_search', 'bounded_public_research'})[1], None)

    def test_a_partial_private_category_is_replaced(self):
        self.assertEqual(self.keep({'list_notes'}), (None, {'requested': ['bounded_public_research', 'list_memory',
                                                                         'weather', 'web_search'], 'why': 'shape'}))

    def test_a_partial_search_category_is_replaced(self):
        self.assertEqual(self.keep({'web_search'})[1]['why'], 'shape')
        self.assertEqual(self.keep({'bounded_public_research'})[1]['why'], 'shape')

    def test_a_category_plus_anything_else_is_replaced(self):
        self.assertEqual(self.keep({'web_search', 'bounded_public_research', 'weather'})[1]['why'], 'shape')


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
                                   '--profile=trusted-local', '--only=bounded_public_research'],
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
    def test_the_planner_reads_the_conversation_a_worker_is_shown(self):
        """#740: only document-job rows are withheld; rows of a Work that used the browser or a private store stay."""
        from personal_agent.agent_runtime import PRIVATE_PROVENANCE, WORK_SOURCES_KEY
        jobs = []
        # The document job sits between the others, so only its exclusion keeps it out of the last four rows.
        for text, answer in (('페이지 질문', 'BROWSER-ANSWER'), ('문서 질문', 'DOCUMENT-ANSWER'),
                             ('메모 질문', 'NOTES-ANSWER')):
            self.engine.answers = [answer]
            jobs.append(self.run_work(text)[0])
        browser, document, notes = jobs
        self.store.put('file_workspace_document_jobs', [document])
        records = self.store.config(WORK_SOURCES_KEY, {})
        records[browser] = [*records[browser], PRIVATE_PROVENANCE['browser_read']]
        records[notes] = [*records[notes], 'history:personal-space']
        self.store.put(WORK_SOURCES_KEY, records)
        self.script([plan('codex', 'Answer.')], goals=[True])
        self.run_work('이어서')
        excerpt = self.asked_plans[-1][0].facts['recent_conversation']
        for shown in ('BROWSER-ANSWER', '페이지 질문', 'NOTES-ANSWER', '메모 질문'):
            self.assertIn(shown, excerpt)
        for withheld in ('DOCUMENT-ANSWER', '문서 질문'):
            self.assertNotIn(withheld, excerpt)
        self.assertNotIn('이어서', excerpt, 'the current request is not part of the excerpt')

    def test_a_work_without_a_source_record_is_shown_and_secrets_stay_redacted(self):
        from personal_agent.agent_runtime import WORK_SOURCES_KEY
        self.engine.answers = [f'UNRECORDED-ANSWER {OPENAI_KEY}']
        earlier, _row = self.run_work('예전 질문')
        records = self.store.config(WORK_SOURCES_KEY, {})
        records.pop(earlier)
        self.store.put(WORK_SOURCES_KEY, records)
        rows = [{'role': 'assistant', 'content': 'x', 'job_id': earlier}, {'role': 'user', 'content': 'now'}]
        self.assertEqual(self.service.planner_history(rows, ()), rows[:1])
        self.script([plan('codex', 'Answer.')], goals=[True])
        self.run_work('이어서')
        excerpt = self.asked_plans[-1][0].facts['recent_conversation']
        self.assertIn('UNRECORDED-ANSWER', excerpt)
        self.assertNotIn(OPENAI_KEY, excerpt)

    def test_the_plan_question_resolves_the_request_from_the_conversation(self):
        self.assertIn('resolve what it refers to', QUESTION)
        self.assertIn('select history when the request continues it', QUESTION)


class OwnerQuestion(Harness):
    """#740: a worker's question the request needs is the reply, not a shortfall to re-delegate."""

    def test_a_needed_question_stops_redelegation_and_is_delivered(self):
        self.engine.answers = ['PLAIN-EARLIER']
        self.run_work('앞선 질문')
        question = '어디에서 출발하시나요?'
        self.engine.answers = [question]
        self.script([plan('codex', 'Answer.'), plan('openai', 'Other path.')], goals=[False], owner_questions=[True])
        job, row = self.run_work('얼마나 걸려?')
        self.assertEqual(len(self.engine.turns), 2, 'one attempt for this Work')
        self.assertEqual(self.transport.bodies, [], 'not re-delegated')
        self.assertEqual(len(self.asked_plans), 1)
        self.assertEqual(row['status'], 'succeeded')
        self.assertEqual(row['response'], question)
        last = self.events(job, 'evaluated')[-1][1]
        self.assertEqual((last['outcome'], last['next'], last['stop']), ('owner_needed', 'stop', 'owner'))
        [context] = self.asked_owner_input
        self.assertEqual(context.facts['owner_request'], '얼마나 걸려?')
        self.assertIn(question, context.facts['worker_answer'])
        self.assertIn('PLAIN-EARLIER', context.facts['recent_conversation'])

    def test_a_question_after_a_tool_ran_is_stored_like_a_direct_route_needs_owner_finish(self):
        """Review P1: an attempt that called a tool is never stored as succeeded on a question;
        partial when a tool result was observed, failed otherwise, with the answer as the report's question."""
        from personal_agent.conversation_projection import REPORT_QUESTION_LABEL
        question = '두 결과 중 어느 쪽으로 할까요?'

        def search(tools):
            tools.capabilities.record('web_search', 'succeeded',
                                      json.dumps({'host_action': 'web_search', 'evidence': {'sources': ['https://a.test']}}))
        self.engine.before = search
        self.engine.answers = [question]
        self.script([plan('codex', 'Answer.')], goals=[False], owner_questions=[True])
        job, row = self.run_work('찾아줘')
        self.assertEqual(self.events(job, 'evaluated')[-1][1]['stop'], 'owner')
        self.assertEqual(row['status'], 'partial')
        self.assertIn(REPORT_QUESTION_LABEL + ' ' + question, row['owner_cause'])
        self.assertNotIn(GOAL_NOT_SHOWN, row['owner_cause'])

        def failing(tools):
            tools.capabilities.record('web_search', 'failed', json.dumps({'host_action': 'web_search', 'error': 'x'}))
        self.engine.before = failing
        self.engine.answers = [question]
        self.script([plan('codex', 'Answer.')], goals=[False], owner_questions=[True])
        _job, row = self.run_work('다시 찾아줘')
        self.assertEqual(row['status'], 'failed')
        self.assertIn(question, row['owner_cause'])

    def test_an_owner_stop_skips_the_owner_input_judgment(self):
        from personal_agent.orchestrator import OWNER_NEEDED as _OWNER, NOT_REACHED as _NOT
        stopped = mock.Mock(interrupted=lambda: 'stop', remaining=lambda: 300, turns=4, turns_used=0)
        judged = mock.Mock(outcome='yes')
        judgments = mock.Mock(goal_reached=lambda *a, **k: mock.Mock(outcome='no'),
                              owner_input_needed=mock.Mock(return_value=judged))
        orchestration = Orchestration(judgments, Catalogue([], {}, ''), request='r', budget=None)
        self.assertEqual(orchestration.evaluate_answer('어디서요?', ''), _OWNER)
        self.assertTrue(orchestration.owner_question)
        orchestration.budget = stopped
        self.assertFalse(orchestration.owner_input_needed('어디서요?'))
        orchestration.budget = mock.Mock(interrupted=lambda: None, remaining=lambda: 0)
        self.assertFalse(orchestration.owner_input_needed('어디서요?'), 'the deadline has passed')
        orchestration.budget = None
        judgments.owner_input_needed.return_value = mock.Mock(outcome='no')
        self.assertEqual(orchestration.evaluate_answer('어디서요?', ''), _NOT)
        self.assertFalse(orchestration.owner_question)

    def test_an_unneeded_question_is_still_redelegated(self):
        self.engine.answers = ['어디에서 출발하시나요?']
        self.script([plan('codex', 'Answer.'), plan('openai', 'Resolve it from the conversation.')],
                    goals=[False], owner_questions=[False])
        job, row = self.run_work('얼마나 걸려?')
        self.assertEqual(row['response'], 'api answer')
        self.assertEqual([detail['outcome'] for _s, detail in self.events(job, 'evaluated')],
                         ['not_reached', 'reached'])

    def test_no_owner_input_judgment_when_the_goal_was_reached(self):
        self.script([plan('codex', 'Answer.')], goals=[True], owner_questions=[True])
        self.run_work('알려줘')
        self.assertEqual(self.asked_owner_input, [])


class Preflight(Harness):
    def test_an_explicit_search_preflight_honours_a_subset_without_web_search(self):
        """Review P2: the /search preflight is a web_search call; a subset without it skips it."""
        self.script([plan('codex', 'Answer from the saved notes.', tools=self.no_search())], goals=[True])
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
        self.assertEqual((ok.worker, ok.tools, ok.replaced), ('b', None, None), 'the full set is no subset')
        ok, _ = orchestration.validate(plan('a', 'g', tools=('web_search',)), candidates, 1)
        self.assertEqual((ok.tools, ok.replaced), (frozenset({'web_search'}), None), 'private reads removed')
        ok, _ = orchestration.validate(plan('b', 'g', tools=('list_notes',)), candidates, 1)
        self.assertEqual((ok.tools, ok.replaced), (None, {'requested': ['list_notes'], 'why': 'not_offered'}))
        for data, what in ((plan('c', 'g'), 'worker'), (plan('zz', 'g'), 'worker'), (plan('a', 'g', model='m2'), 'model'),
                           ({'worker': 'a'}, 'shape'),
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
