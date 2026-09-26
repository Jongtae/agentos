"""AGENCY-LOOP-01 (#606): goal -> tool -> observation, bounded and truthful.

Evidence class: model-free.  A scripted model transport and a fake public
network replace only the provider and the wire; `run_agent`, `Capabilities`,
the service worker (`AgentService.run_one`) and, for the CLI route, the real
MCP bridge process run unchanged.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from personal_agent.agent_runtime import (BUDGET_CODES, GOAL_NOT_CLAIMED, GOAL_NOT_SHOWN, GOAL_UNJUDGED, WORK_STOP_KEEP,
                                          WORK_STOP_KEY, WORK_STOPPED, Capabilities, ToolError, WorkBudget,
                                          outcome_from_events, recovered, render_turn_prompt, run_agent,
                                          turn_context)
from personal_agent.bounded_execution import ExecutionResult
from personal_agent.conversation_handoff import ConversationJudgments
from personal_agent.conversation_projection import report_statement, terminal_text
from personal_agent.decision import OUTCOME_DECIDED, BinaryDecision, FixtureDecisionEngine, fixture_confidence
from personal_agent.providers import ModelAdapter, ProviderError
from personal_agent.quickstart_service import AgentService, subscription_public_lookup_query
from personal_agent.quickstart_store import QuickStore
from personal_agent.subscription_engines import SubscriptionEngines

ROOT = Path(__file__).resolve().parents[1]
CFG = {'provider': 'compatible', 'endpoint': 'https://openrouter.ai/api/v1', 'model': 'test-model'}
FORECAST = {'tool': 'weather', 'location': {'name': 'Seongnam-si', 'admin1': 'Gyeonggi-do', 'country': 'South Korea'},
            'forecast': {'timezone': 'Asia/Seoul',
                         'current': {'time': '2026-09-26T10:00', 'temperature_2m': 21, 'apparent_temperature': 20,
                                     'precipitation': 0, 'wind_speed_10m': 5},
                         'current_units': {'temperature_2m': '°C', 'apparent_temperature': '°C',
                                           'precipitation': 'mm', 'wind_speed_10m': 'km/h'},
                         'daily': {'time': ['2026-09-26', '2026-09-27'], 'temperature_2m_min': [15, 14],
                                   'temperature_2m_max': [24, 22], 'precipitation_probability_max': [10, 70]},
                         'daily_units': {'temperature_2m_min': '°C', 'temperature_2m_max': '°C',
                                         'precipitation_probability_max': '%'}},
            'sources': ['https://api.open-meteo.com/v1/forecast', 'https://open-meteo.com/']}
NOT_FOUND = '도시를 찾지 못했습니다. 도시와 국가를 함께 알려 주세요.'


def call(ident, name, **args):
    return {'id': ident, 'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}


def finish(ident, *refs, summary='끝났습니다.', status='done', **extra):
    """A scripted SEC-LOOP-01 (#657) completion claim naming the tool call ids ``refs``."""
    return {'tool_calls': [call(ident, 'finish', status=status, evidence_refs=list(refs), summary=summary, **extra)]}


def finish_observed(ident, summary='끝났습니다.', status='done', **extra):
    """A scripted completion claim citing every ``ref`` the model was shown.

    For routes whose provider assigns the tool call ids (the refs are then
    only known from the tool results the loop returned).
    """
    def build(body):
        refs = []
        for message in body.get('messages', []):
            if message.get('role') != 'tool':continue
            try:ref = json.loads(message.get('content') or '{}').get('ref')
            except (AttributeError, ValueError):ref = None
            if ref:refs.append(ref)
        return finish(ident, *refs, summary=summary, status=status, **extra)
    return build


def goal_engine(answer=True):
    """A DecisionEngine that answers only the completion judgment (#657).

    ``answer`` is True/False, None (unavailable) or a callable of the
    judgment's facts.  Every other purpose stays unavailable, as it is on an
    installation without a decision provider.
    """
    def judge(context, proposition):
        if context.purpose != 'goal-reached':return None
        value = answer(context.facts) if callable(answer) else answer
        return None if value is None else BinaryDecision(OUTCOME_DECIDED, bool(value), fixture_confidence())
    return FixtureDecisionEngine(judge=judge)


def judgments(answer=True):
    return ConversationJudgments(goal_engine(answer))


class Script:
    """A compatible-API transport answering from a list of scripted messages."""

    def __init__(self, *messages):
        self.messages = list(messages)
        self.bodies = []

    def __call__(self, url, body, headers=None, timeout=60):
        self.bodies.append(json.loads(json.dumps(body)))  # the loop mutates its message list
        message = self.messages.pop(0) if self.messages else {'content': '끝났습니다.'}
        if callable(message):message = message(body)
        return {'choices': [{'message': message}]}


class Network:
    """The public wire: weather is not found, search answers."""

    def __init__(self, weather=None, search=True):
        self.plans = []
        self.weather, self.search = weather, search

    def execute(self, plan):
        self.plans.append(plan)
        if plan['tool'] == 'weather':
            if self.weather is None:raise ValueError(NOT_FOUND)
            return self.weather
        if not self.search:raise ProviderError('웹 검색 결과를 가져오지 못했습니다. 잠시 후 다시 요청하세요.')
        return {'tool': 'web_search', 'query': plan['query'], 'retrieved_at': 1,
                'results': [{'title': 'Seongnam forecast', 'url': 'https://weather.example/seongnam', 'snippet': 'Sat 22°C'}],
                'sources': ['https://weather.example/seongnam']}


class Clock:
    def __init__(self):self.now = 100.0
    def __call__(self):return self.now


class LoopUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = QuickStore(Path(self.tmp.name) / 'data')
        self.events = []

    def record(self, tool, status, detail):
        self.events.append((tool, status, detail))

    def caps(self, transport, network=None, **kwargs):
        return Capabilities(self.store, ModelAdapter(transport), CFG, '', 'job', self.record,
                            network=network or Network(), **kwargs)

    def failed(self):
        return [json.loads(detail) for tool, status, detail in self.events if status == 'failed' and tool != 'model']

    def test_recovery_after_an_effect_free_read_failure_succeeds_and_keeps_the_failure(self):
        script = Script({'tool_calls': [call('1', 'weather', city='Seongnam', country='KR')]},
                        {'tool_calls': [call('2', 'web_search', query='Seongnam weather tomorrow')]},
                        finish('3', '2', summary='내일 성남은 22°C입니다.'))
        caps = self.caps(script, judgments=judgments(True))
        result = run_agent(caps.adapter, CFG, '', [{'role': 'user', 'content': '내일 성남 날씨'}], '', caps, self.record)
        self.assertEqual(result.outcome, 'succeeded')
        # The failed attempt reached the model as a typed observation and stays
        # in the log; #657 follows it with one "different path" turn.
        observation = json.loads(script.bodies[1]['messages'][-2]['content'])
        self.assertIn('Path check', script.bodies[1]['messages'][-1]['content'])
        self.assertEqual(observation, {'error': NOT_FOUND, 'code': 'tool_failed', 'retry': 'permanent', 'effect': 'none'})
        self.assertEqual([row['code'] for row in self.failed()], ['tool_failed'])

    def test_failed_write_is_not_erased_by_a_later_read(self):
        script = Script({'tool_calls': [call('1', 'save_note', content=' ')]},
                        {'tool_calls': [call('2', 'list_notes')]},
                        {'content': '메모를 확인했습니다.'})
        caps = self.caps(script)
        result = run_agent(caps.adapter, CFG, '', [{'role': 'user', 'content': '메모 저장하고 보여줘'}], '', caps, self.record)
        self.assertEqual(result.outcome, 'partial')

    def test_identical_call_guard_has_a_stable_code(self):
        script = Script({'tool_calls': [call('1', 'list_notes')]}, {'tool_calls': [call('2', 'list_notes')]},
                        {'content': '없습니다.'})
        caps = self.caps(script)
        run_agent(caps.adapter, CFG, '', [{'role': 'user', 'content': '메모'}], '', caps, self.record)
        self.assertEqual([row['code'] for row in self.failed()], ['duplicate_call'])

    def test_attempt_budget_is_shared_with_a_delegated_specialist(self):
        budget = WorkBudget(attempts=3)
        # The specialist lists notes until the Work's attempt budget refuses it.
        script = Script({'tool_calls': [call('a', 'list_notes')]},
                        {'tool_calls': [call('b', 'find_files', query='x')]},
                        {'tool_calls': [call('c', 'list_roots')]},
                        {'content': '보고서'})
        caps = self.caps(script, budget=budget)
        report = caps.execute('delegate_agent', {'agent_id': 'reviewer', 'task': '검토'})
        self.assertEqual(budget.attempts_used, 3)  # the delegation itself + two specialist calls
        self.assertIn('attempt_budget', {row['code'] for row in self.failed()})
        self.assertEqual(report['outcome'], 'partial')
        with self.assertRaises(ToolError) as refused:caps.execute('list_notes', {})
        self.assertEqual(refused.exception.code, 'attempt_budget')

    def test_turn_budget_ends_the_run_and_keeps_what_was_observed(self):
        script = Script(*[{'tool_calls': [call(str(i), 'find_files', query=f'q{i}')]} for i in range(20)])
        caps = self.caps(script, budget=WorkBudget(turns=3))
        result = run_agent(caps.adapter, CFG, '', [{'role': 'user', 'content': '찾아줘'}], '', caps, self.record)
        self.assertEqual(len(script.bodies), 3)
        self.assertEqual(result.outcome, 'partial')
        self.assertIn('모델 호출 한도', result.content)

    def test_deadline_uses_an_injected_clock(self):
        clock = Clock()
        caps = self.caps(Script(), budget=WorkBudget(seconds=10, clock=clock))
        caps.execute('list_notes', {})
        clock.now += 11
        with self.assertRaises(ToolError) as refused:caps.execute('list_notes', {})
        self.assertEqual(refused.exception.code, 'deadline_exceeded')
        self.assertIn('deadline', BUDGET_CODES)

    def test_stop_is_checked_before_the_next_model_turn_and_call(self):
        stopped = [False]
        script = Script({'tool_calls': [call('1', 'list_notes')]}, {'content': 'unused'})
        original = script.__call__

        def transport(url, body, headers=None, timeout=60):
            stopped[0] = True  # the owner presses Stop while the first model turn runs
            return original(url, body, headers, timeout)
        caps = self.caps(transport, budget=WorkBudget(stop=lambda: stopped[0]))
        with self.assertRaisesRegex(ProviderError, WORK_STOPPED):
            run_agent(caps.adapter, CFG, '', [{'role': 'user', 'content': '메모'}], '', caps, self.record)
        self.assertEqual([row['code'] for row in self.failed()], ['stopped'])
        self.assertIn(('model', 'stopped'), [(tool, status) for tool, status, _ in self.events])

    def test_a_durable_stop_reaches_a_capabilities_built_without_a_budget(self):
        # The CLI's MCP bridge builds its own Capabilities in another process.
        caps = Capabilities(self.store, None, {}, '', 'job', self.record, network=Network())
        caps.execute('list_notes', {})
        self.store.append_config_list(WORK_STOP_KEY, 'job', WORK_STOP_KEEP)
        with self.assertRaises(ToolError) as refused:caps.execute('list_notes', {})
        self.assertEqual(refused.exception.code, 'stopped')

    def test_the_free_router_retry_spends_a_turn_and_checks_stop(self):
        stopped = [False]

        class Limited:
            calls = 0
            def tool_turn(self, *args, **kwargs):
                Limited.calls += 1
                stopped[0] = True
                raise ProviderError('rate limited', status=429)
        caps = self.caps(Script(), budget=WorkBudget(stop=lambda: stopped[0]))
        config = {**CFG, 'model': 'openrouter/free'}
        with self.assertRaisesRegex(ProviderError, WORK_STOPPED):
            run_agent(Limited(), config, '', [{'role': 'user', 'content': '안녕'}], '', caps, self.record)
        self.assertEqual(Limited.calls, 1)

    def test_calendar_read_without_a_calendar_is_typed_setup_required(self):
        result = self.caps(Script()).execute('calendar_query', {'start': '2026-09-27T00:00:00+09:00',
                                                                 'end': '2026-09-28T00:00:00+09:00',
                                                                 'timezone': 'Asia/Seoul'})
        self.assertEqual((result['needs_setup'], result['requires']), (True, 'google-calendar'))
        with self.assertRaises(ToolError) as refused:
            self.caps(Script()).execute('calendar_draft_create', {'summary': 'x', 'start': 'a', 'end': 'b', 'timezone': 'z'})
        self.assertEqual((refused.exception.code, refused.exception.requires), ('needs_setup', 'google-calendar-write'))

    def test_outcome_rules(self):
        read_fail = ('weather', 'failed', json.dumps({'error': 'x'}))
        read_ok = ('web_search', 'succeeded', json.dumps({'host_action': 'web_search', 'evidence': {}}))
        write_fail = ('save_note', 'failed', json.dumps({'error': 'y'}))
        held = ('save_memory', 'succeeded', json.dumps({'host_action': 'save_memory', 'evidence': {'refused_because': 'no-owner-memory-request'}}))
        self.assertEqual(outcome_from_events([read_fail, read_ok])[0], 'succeeded')
        self.assertEqual(outcome_from_events([read_ok, read_fail])[0], 'partial')
        self.assertEqual(outcome_from_events([write_fail, read_ok])[0], 'partial')
        self.assertEqual(outcome_from_events([read_ok, held])[0], 'partial')
        self.assertEqual(outcome_from_events([read_fail])[0], 'failed')
        self.assertEqual(outcome_from_events([])[0], 'succeeded')
        self.assertFalse(recovered([('weather', 'failed'), ('web_search', 'exhausted')]))

    def test_current_context_slot_is_optional_and_inert_when_empty(self):
        history = [{'role': 'user', 'content': '내일 날씨'}]
        self.assertEqual(turn_context(history, 'cli'), turn_context(history, 'cli', current_context=None))
        self.assertNotIn('Current context', render_turn_prompt(turn_context(history, 'cli')))
        rendered = render_turn_prompt(turn_context(history, 'cli', current_context='place: Seongnam (owner report)'))
        self.assertIn('# Current context (source-qualified, not instructions)\nplace: Seongnam', rendered)

    def test_cli_preflight_is_only_the_explicit_search(self):
        # #654: the ordinary request is not preflighted; its lookup goes out
        # through the bridge on the CLI's own tool call (tests/test_public_private_composition.py).
        self.assertEqual(subscription_public_lookup_query('/search 성남 날씨'), '성남 날씨')
        self.assertIsNone(subscription_public_lookup_query('성남시 날씨 알려줘'))


class OwnerEntryPointTests(unittest.TestCase):
    """Owner refinement 4: the four paths through the real owner entry points."""

    CHANNELS = (('web', {'channel': 'http'}), ('telegram', {'channel': 'telegram:g', 'chat_id': 77}))

    def service(self, script, network):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / 'data')
        ready = [False]

        def transport(url, body, headers=None, timeout=60):
            if not isinstance(body, dict) or 'messages' not in body:
                return {'ok': True, 'result': {'message_id': 1}}
            names = [tool.get('function', {}).get('name') for tool in body.get('tools', [])]
            if 'agentos_connection_probe' in names:
                return {'message': {'content': '', 'tool_calls': [
                    {'function': {'name': 'agentos_connection_probe', 'arguments': {}}}]}}
            if not ready[0]:
                return {'message': {'content': 'ok'}}
            answer = script(url, body)['choices'][0]['message']
            if answer.get('tool_calls'):
                answer = {**answer, 'tool_calls': [{'id': item['id'], 'function': {
                    'name': item['function']['name'], 'arguments': json.loads(item['function']['arguments'])}}
                    for item in answer['tool_calls']]}
            return {'message': answer}
        service = AgentService(store, ModelAdapter(transport), transport)
        service.local_tools = network
        service.save_model({'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434', 'model': 'test-model', 'api_key': ''})
        self.assertTrue(service.test_model()['ok'])
        ready[0] = True
        return service, store

    def test_a_empty_rule_read_is_rejudged_by_the_loop(self):
        for route in self.CHANNELS:
            with self.subTest(route=route[0]):
                question = '저장된 기록에서 여권 번호를 찾지 못했습니다. 어디에 적어 두셨는지 알려 주시겠어요?'
                script = Script({'tool_calls': [call('1', 'list_notes')]},
                                finish_observed('f', status='needs_owner', summary=question))
                row, failed = self.run_turn('내 기록에서 여권 번호 찾아줘', script, Network(), route)
                # #657: asking the owner is not the goal reached; the question reaches the owner.
                self.assertEqual(row['status'], 'partial')
                self.assertIn('찾지 못했습니다', row['response'])
                self.assertIn('확인이 필요한 질문: ' + question, row['owner_cause'])
                self.assertEqual(failed, [])
                # Re-judgment: the loop saw AgentOS's observation, not a handler payload.
                sent = script.bodies[0]['messages'][-1]['content']
                self.assertIn('found no matching saved item', sent)
                self.assertIn('ask the owner', sent)

    def test_b_rule_clarification_is_asked_by_the_loop(self):
        for route in self.CHANNELS:
            with self.subTest(route=route[0]):
                question = '개인 공간에서 어떤 내용을 찾을까요?'
                script = Script({'content': question}, {'content': question})
                row, failed = self.run_turn('개인 공간에서 찾아줘', script, Network(), route)
                self.assertEqual(row['status'], 'succeeded')
                self.assertEqual(row['response'], question)
                self.assertEqual(failed, [])
                self.assertIn('could not tell what to look for', script.bodies[0]['messages'][-1]['content'])

    def test_c_recovery_that_fully_satisfies_the_request_succeeds(self):
        for route in self.CHANNELS:
            with self.subTest(route=route[0]):
                script = Script({'tool_calls': [call('1', 'weather', city='Seongnam', country='KR')]},
                                {'tool_calls': [call('2', 'weather', city='Seongnam-si', country='KR')]},
                                finish_observed('f', summary='내일(2026-09-27, Asia/Seoul) 성남은 최저 14°C, 최고 22°C입니다.'))
                network = Network()
                calls = []
                def weather_after_one_miss(plan, original=network.execute):
                    calls.append(plan)
                    if plan['tool'] == 'weather' and len(calls) > 1:return FORECAST
                    return original(plan)
                network.execute = weather_after_one_miss
                row, failed = self.run_turn('내일 성남 날씨 알려줘', script, network, route, engine=goal_engine(True))
                self.assertEqual(row['status'], 'succeeded')
                self.assertIn('2026-09-27', row['response'])
                self.assertEqual([event['trace']['code'] for event in failed], ['tool_failed'])

    def test_d_final_failure_after_caps_and_alternatives(self):
        for route in self.CHANNELS:
            with self.subTest(route=route[0]):
                cities = ('Seongnam', 'Seongnam-si', 'Sungnam', 'Seongnam City', 'Bundang', 'Pangyo',
                          'Seongnam KR', 'Seongnam Gyeonggi', 'Seongnam-si Gyeonggi', 'Sujeong')
                script = Script(*[{'tool_calls': [call(str(i), 'weather', city=city, country='KR')]}
                                  for i, city in enumerate(cities)])
                row, failed = self.run_turn('내일 성남 날씨 알려줘', script, Network(), route)
                self.assertEqual(row['status'], 'failed')
                self.assertIn('모델 호출 한도', row['error'])
                self.assertEqual(len(script.bodies), 9)
                self.assertGreaterEqual(len(failed), 6)
                with_messages = [m for m in self._messages(row['id'])]
                self.assertTrue(with_messages[-1].startswith('이 요청은 완료하지 못했습니다'))

    def _messages(self, job_id):
        store = self._store
        return [row['content'] for row in store.history() if row.get('job_id') == job_id and row['role'] == 'assistant']

    def run_turn(self, text, script, network, route, engine=None):
        service, store = self.service(script, network)
        if engine is not None:service.use_decision_engine(engine)
        self._store = store
        job = store.enqueue(text, f'agency-{route[0]}', **route[1])
        self.assertTrue(service.run_one())
        row = store.job(job)
        failed = [event for event in store.task_events(job) if event['status'] == 'failed' and event['tool'] != 'model']
        return row, failed



class ProviderNetwork:
    """A public wire whose search answer depends on the provider the model chose."""

    def __init__(self, answers):
        self.answers, self.plans = answers, []

    def execute(self, plan):
        self.plans.append(plan)
        provider = plan.get('provider') or 'default'
        rows = self.answers[provider]
        return {'tool': 'web_search', 'query': plan['query'], 'provider': provider, 'retrieved_at': 1,
                'results': rows, 'sources': [row['url'] for row in rows]}


UNRELATED = [{'title': 'Leadership seminar tickets', 'url': 'https://events.example/seminar', 'snippet': 'Sat 10am'}]
MATCHING = [{'title': 'When Leaders Make the Difference (2nd edition)', 'url': 'https://books.example/item/42',
             'snippet': 'Author A. Writer, hardcover'}]


class AlternativesAndCompletionTests(unittest.TestCase):
    """SEC-LOOP-01 (#657): different paths after a failed one; `succeeded` only on observed evidence.

    Evidence class: model-free.  The model transport is scripted and the
    completion judgment is a fixture DecisionEngine; `run_agent`,
    `Capabilities` and `ConversationJudgments.goal_reached` run unchanged.
    """

    REQUEST = [{'role': 'user', 'content': '"When Leaders Make the Difference" 책 찾아줘'}]

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'data')
        self.events = []

    def record(self, tool, status, detail):
        self.events.append((tool, status, detail))

    def run_script(self, script, network=None, answer=True, **kwargs):
        caps = Capabilities(self.store, ModelAdapter(script), CFG, '', 'job', self.record,
                            network=network or Network(), judgments=judgments(answer) if answer != 'none' else None,
                            **kwargs)
        return run_agent(caps.adapter, CFG, '', self.REQUEST, '', caps, self.record), caps

    def failed_codes(self):
        return [json.loads(detail).get('code') for tool, status, detail in self.events
                if status == 'failed' and tool != 'model']

    def concluded(self):
        rows = [json.loads(detail) for tool, status, detail in self.events if (tool, status) == ('model', 'concluded')]
        self.assertEqual(len(rows), 1)
        return rows[0]

    @staticmethod
    def tool_reply(body, ident):
        return next(json.loads(m['content']) for m in body['messages'] if m.get('tool_call_id') == ident)

    def test_irrelevant_results_then_the_same_search_is_refused_and_a_provider_switch_runs(self):
        network = ProviderNetwork({'default': UNRELATED, 'other': MATCHING})
        script = Script({'tool_calls': [call('1', 'web_search', query='When Leaders Make the Difference')]},
                        # The model repeats the same path: case and spacing do not make it new.
                        {'tool_calls': [call('2', 'web_search', query='  when leaders   make the DIFFERENCE ')]},
                        {'tool_calls': [call('3', 'web_search', query='When Leaders Make the Difference', provider='other')]},
                        finish('f', '3', summary='2판 하드커버를 찾았습니다: https://books.example/item/42'))
        result, _caps = self.run_script(script, network)
        self.assertEqual(result.outcome, 'succeeded')
        # The repeat never reached the wire; the switched provider did.
        self.assertEqual([plan.get('provider') for plan in network.plans], [None, 'other'])
        self.assertEqual(self.failed_codes(), ['repeat_path'])
        refusal = self.tool_reply(script.bodies[2], '2')
        self.assertEqual((refusal['code'], refusal['retry']), ('repeat_path', 'permanent'))
        # The failed path earned one explicit "different path" turn.
        self.assertEqual(script.bodies[2]['messages'][-1]['role'], 'system')
        self.assertIn('Path check', script.bodies[2]['messages'][-1]['content'])
        # Evidence: one alternative, its kind, and the claim with its ref.
        self.assertEqual(result.alternatives, [{'kind': 'provider_switch', 'action': 'web_search'}])
        running = [json.loads(detail) for tool, status, detail in self.events if status == 'running']
        self.assertEqual([row.get('alternative') for row in running], [None, 'provider_switch'])
        self.assertEqual(self.concluded()['alternatives_tried'], {'count': 1, 'kinds': {'provider_switch': 1}})
        self.assertEqual(self.concluded()['claim'], {'status': 'done', 'evidence_refs': ['3']})
        self.assertEqual(self.concluded()['judgment'], 'yes')

    def test_a_rewritten_query_is_a_different_path(self):
        network = ProviderNetwork({'default': MATCHING})
        script = Script({'tool_calls': [call('1', 'web_search', query='leaders difference book')]},
                        {'tool_calls': [call('2', 'web_search', query='leaders difference book', locale='ko-KR')]},
                        {'tool_calls': [call('3', 'web_search', query='"When Leaders Make the Difference"')]},
                        finish('f', '3'))
        result, _caps = self.run_script(script, network)
        self.assertEqual(len(network.plans), 3)
        self.assertEqual(self.failed_codes(), [])
        self.assertEqual(result.outcome, 'succeeded')

    def test_a_tool_that_succeeds_without_showing_the_goal_never_succeeds(self):
        # The search "works" but only lists an unrelated event; the model says done anyway.
        network = ProviderNetwork({'default': UNRELATED})
        shown = lambda facts: 'books.example/item' in facts['observations']
        script = Script({'tool_calls': [call('1', 'web_search', query='When Leaders Make the Difference')]},
                        finish('f1', '1', summary='찾았습니다.'),
                        finish('f2', '1', summary='찾았습니다.'))
        result, _caps = self.run_script(script, network, answer=shown)
        self.assertEqual(result.outcome, 'partial')
        # The first "not shown" answer returned the claim once so another path could be taken.
        self.assertEqual(self.tool_reply(script.bodies[2], 'f1')['code'], 'goal_not_observed')
        self.assertIn(GOAL_NOT_SHOWN, result.report['unknown'])
        self.assertEqual(self.concluded()['judgment'], 'no')

    def test_a_plain_reply_after_tools_is_checked_once_and_never_succeeds_without_a_claim(self):
        network = ProviderNetwork({'default': MATCHING})
        script = Script({'tool_calls': [call('1', 'web_search', query='When Leaders Make the Difference')]},
                        {'content': '장바구니에 담았습니다.'},
                        {'content': '네, 완료했습니다.'})
        result, _caps = self.run_script(script, network)
        self.assertIn('Completion check', script.bodies[2]['messages'][-1]['content'])
        self.assertEqual(result.outcome, 'partial')
        # The answer stays the draft the check followed; nothing claimed it.
        self.assertTrue(result.content.startswith('장바구니에 담았습니다.'))
        self.assertIn(GOAL_NOT_CLAIMED, result.report['unknown'])
        self.assertIsNone(self.concluded()['claim'])

    def test_a_claim_citing_a_failed_or_unknown_observation_is_rejected(self):
        script = Script({'tool_calls': [call('1', 'weather', city='Seongnam', country='KR')]},
                        {'tool_calls': [call('2', 'web_search', query='Seongnam weather tomorrow')]},
                        finish('f1', '1', summary='내일 22°C입니다.'),
                        finish('f2', 'nope', summary='내일 22°C입니다.'),
                        finish('f3', '2', summary='내일 22°C입니다.'))
        result, _caps = self.run_script(script)
        self.assertEqual(self.tool_reply(script.bodies[3], 'f1')['code'], 'failed_ref')
        self.assertEqual(self.tool_reply(script.bodies[4], 'f2')['code'], 'unknown_ref')
        self.assertEqual(result.outcome, 'succeeded')
        rejected = [json.loads(detail)['code'] for tool, status, detail in self.events if status == 'claim_rejected']
        self.assertEqual(rejected, ['failed_ref', 'unknown_ref'])
        # The failed weather read stays in the Evidence and the report.
        self.assertEqual(self.failed_codes(), ['tool_failed'])
        self.assertEqual(result.report['failed'], [['weather', NOT_FOUND]])

    def test_a_done_claim_without_evidence_is_rejected(self):
        script = Script({'tool_calls': [call('1', 'list_notes')]},
                        finish('f1', summary='없습니다.'),
                        finish('f2', '1', summary='저장된 메모가 없습니다.'))
        result, _caps = self.run_script(script)
        self.assertEqual(self.tool_reply(script.bodies[2], 'f1')['code'], 'no_evidence')
        self.assertEqual(result.outcome, 'succeeded')

    def test_no_decision_engine_is_partial_and_says_completion_is_unknown(self):
        for answer in ('none', None):
            with self.subTest(answer=answer):
                self.events.clear()
                script = Script({'tool_calls': [call('1', 'web_search', query='When Leaders Make the Difference')]},
                                finish('f', '1', summary='찾았습니다.'))
                result, _caps = self.run_script(script, ProviderNetwork({'default': MATCHING}), answer=answer)
                self.assertEqual(result.outcome, 'partial')
                self.assertEqual(result.content.split('\n\n')[0], '찾았습니다.')
                self.assertIn(GOAL_UNJUDGED, result.report['unknown'])
                self.assertEqual(self.concluded()['judgment'], 'unavailable')

    def test_needs_owner_is_partial_and_carries_its_question(self):
        script = Script({'tool_calls': [call('1', 'list_notes')]},
                        finish('f', '1', status='needs_owner', summary='여권 번호를 어디에 적어 두셨나요?'))
        result, _caps = self.run_script(script)
        self.assertEqual(result.outcome, 'partial')
        self.assertEqual(result.report['question'], '여권 번호를 어디에 적어 두셨나요?')
        # requested / observed / failed / unknown stay separate fields of one typed report.
        self.assertEqual(result.report['requested'], self.REQUEST[0]['content'])
        self.assertEqual(result.report['observed'], ['저장된 메모 0개를 확인했습니다.'])
        self.assertEqual(result.report['failed'], [])
        self.assertIn('확인이 필요한 질문: 여권 번호를 어디에 적어 두셨나요?', report_statement(result.report))

    def test_alternative_nudges_are_bounded_by_the_work_budget(self):
        cities = ('Seongnam', 'Seongnam-si', 'Sungnam', 'Bundang')
        script = Script(*[{'tool_calls': [call(str(i), 'weather', city=city, country='KR')]} for i, city in enumerate(cities)],
                        {'content': '찾지 못했습니다.'})
        budget = WorkBudget()
        result, _caps = self.run_script(script, budget=budget)
        nudges = [m for m in script.bodies[-1]['messages'] if m['role'] == 'system' and m['content'].startswith('Path check')]
        self.assertEqual((len(nudges), budget.nudges_used), (2, 2))
        self.assertEqual(result.outcome, 'failed')
        # Each different city after a failure is a recorded route change.
        self.assertEqual(self.concluded()['alternatives_tried']['count'], 3)

    def test_a_missing_authority_is_not_nudged_toward_another_path(self):
        script = Script({'tool_calls': [call('1', 'calendar_draft_create', summary='x', start='a', end='b', timezone='z')]},
                        {'content': '캘린더 연결이 필요합니다.'})
        self.run_script(script)
        self.assertFalse(any(m['role'] == 'system' and m['content'].startswith('Path check')
                             for m in script.bodies[-1]['messages']))

    def test_secrets_and_saved_private_values_are_redacted_before_the_judgment(self):
        """Pilot boundary 1: the judgment provider may be separate; it never reads a secret."""
        secret, private = 'stored-fixture-secret-9f8e7d6c', 'M12345678'
        with self.store.db() as db:
            db.execute('INSERT INTO notes VALUES (?,?,?)', ('n1', f'여권 {private} / 키 {secret}', 1))
            db.execute('INSERT INTO notes VALUES (?,?,?)', ('n2', '공항 3시', 2))
        seen = []
        script = Script({'tool_calls': [call('1', 'list_notes')]}, finish('f', '1', summary='메모를 찾았습니다.'))
        caps = Capabilities(self.store, ModelAdapter(script), CFG, '', 'job', self.record, network=Network(),
                            judgments=judgments(lambda facts: seen.append(dict(facts)) or True),
                            secret_redactor=lambda text: text.replace(secret, '[redacted]'),
                            lookup_sources=lambda: {'permitted': [], 'excluded': [private]})
        result = run_agent(caps.adapter, CFG, '', [{'role': 'user', 'content': f'메모 찾아줘 {secret}'}], '', caps, self.record)
        self.assertEqual(result.outcome, 'succeeded')
        [facts] = seen
        judged = json.dumps(facts, ensure_ascii=False)
        self.assertNotIn(secret, judged)
        self.assertNotIn(private, judged)
        self.assertIn('공항 3시', facts['observations'], 'only the excluded values are removed')
        self.assertIn('[redacted]', facts['owner_request'])

    def test_the_whole_request_reaches_the_judgment_and_its_last_part_counts(self):
        """A long request is never cut: an unmet requirement at its end keeps the Work from succeeding."""
        request = '다음 조건을 모두 확인해 줘. ' + '앞부분 조건은 이미 충족됐습니다. ' * 60 + '마지막 조건: 영수증 번호 R-7788이 보여야 합니다.'
        self.assertGreater(len(request), 800)
        seen = []
        shown = lambda facts: seen.append(dict(facts)) or 'R-7788' in facts['observations']
        network = ProviderNetwork({'default': MATCHING})
        script = Script({'tool_calls': [call('1', 'web_search', query='receipt')]},
                        finish('f1', '1', summary='확인했습니다.'), finish('f2', '1', summary='확인했습니다.'))
        caps = Capabilities(self.store, ModelAdapter(script), CFG, '', 'job', self.record, network=network,
                            judgments=judgments(shown))
        result = run_agent(caps.adapter, CFG, '', [{'role': 'user', 'content': request}], '', caps, self.record)
        self.assertNotEqual(result.outcome, 'succeeded')
        self.assertEqual(seen[0]['owner_request'], request)
        self.assertTrue(seen[0]['owner_request'].endswith('R-7788이 보여야 합니다.'))

    def test_a_long_request_is_not_rejected_by_the_decision_size_bound(self):
        from personal_agent.decision import MAX_CONTEXT_CHARS, DecisionContext
        request = '가' * 11000
        context = DecisionContext('goal-reached', {'owner_request': request, 'observations': 'x'},
                                  max_chars=MAX_CONTEXT_CHARS + len(request))
        self.assertFalse(context.too_large())
        self.assertTrue(DecisionContext('other', {'owner_message': request}).too_large())

    def test_an_omitted_provider_is_the_default_so_naming_it_is_a_repeat(self):
        class Registry:
            def default(self):return 'alpha'
            def options(self):return [{'id': 'alpha', 'label': 'A'}, {'id': 'beta', 'label': 'B'}]
        network = ProviderNetwork({'default': UNRELATED, 'alpha': UNRELATED, 'beta': MATCHING})
        network.providers = Registry()
        script = Script({'tool_calls': [call('1', 'web_search', query='leaders')]},
                        {'tool_calls': [call('2', 'web_search', query='leaders', provider='alpha', locale='')]},
                        {'tool_calls': [call('3', 'web_search', query='leaders', provider='beta')]},
                        finish('f', '3'))
        result, _caps = self.run_script(script, network)
        self.assertEqual(self.failed_codes(), ['repeat_path'])
        self.assertEqual(len(network.plans), 2)
        # The refused call is no alternative; the real switch is one.
        self.assertEqual(result.alternatives, [{'kind': 'provider_switch', 'action': 'web_search'}])

    def test_finish_is_loop_internal_and_never_offered_to_a_cli_bridge(self):
        caps = Capabilities(self.store, None, CFG, '', 'job', self.record, network=Network())
        self.assertNotIn('finish', {row['function']['name'] for row in caps.definitions()})
        script = Script({'content': '안녕하세요.'}, {'content': '안녕하세요.'})
        result, _caps = self.run_script(script)
        self.assertIn('finish', {row['function']['name'] for row in script.bodies[0]['tools']})
        # Ordinary conversation: no tool ran, nothing to claim, no judgment asked.
        self.assertEqual(result.outcome, 'succeeded')
        self.assertFalse([row for row in self.events if row[1] == 'concluded'])


class AgencyReportEntryPointTests(unittest.TestCase):
    """#657: the owner report states requested / observed / failed / unknown / next separately."""

    CHANNELS = OwnerEntryPointTests.CHANNELS
    service = OwnerEntryPointTests.service
    run_turn = OwnerEntryPointTests.run_turn

    def test_a_partial_finish_reaches_the_owner_as_a_typed_report(self):
        route = self.CHANNELS[1]
        script = Script({'tool_calls': [call('1', 'weather', city='Seongnam', country='KR')]},
                        {'tool_calls': [call('2', 'web_search', query='Seongnam weather tomorrow')]},
                        finish_observed('f', status='partial', summary='내일 성남은 22°C로 보입니다.',
                                        unknown=['내일 강수 확률'], next='날씨 예보 페이지를 열어 강수 확률을 확인하기'))
        row, failed = self.run_turn('내일 성남 날씨랑 비 올 확률 알려줘', script, Network(), route)
        self.assertEqual(row['status'], 'partial')
        self.assertEqual([event['trace']['code'] for event in failed], ['tool_failed'])
        bubble = terminal_text(row['response'], row['owner_cause'], 'partial', verified=row['owner_verified'])
        # One bubble, in order: the truth header, what was observed (AgentOS's
        # rendering of the search result), what failed, what stayed unknown,
        # and the proposed next step.
        parts = ['일부 단계만 완료했습니다.', '확인된 부분:', 'https://weather.example/seongnam',
                 '날씨 조회: ' + NOT_FOUND, '확인하지 못한 부분: 내일 강수 확률',
                 '다음 단계 제안: 날씨 예보 페이지를 열어 강수 확률을 확인하기']
        positions = [bubble.find(part) for part in parts]
        self.assertNotIn(-1, positions, bubble)
        self.assertEqual(positions, sorted(positions), bubble)
        # The model's own sentence is not presented as observed.
        self.assertNotIn('22°C로 보입니다', bubble)
        with self._store.db() as db:
            concluded = [json.loads(detail) for (detail,) in db.execute(
                "SELECT detail FROM tool_events WHERE job_id=? AND tool='model' AND status='concluded'", (row['id'],))]
        self.assertEqual(concluded[0]['claim']['status'], 'partial')
        self.assertEqual(len(concluded[0]['claim']['evidence_refs']), 1)
        self.assertEqual(concluded[0]['alternatives_tried'], {'count': 1, 'kinds': {'route_change': 1}})

    def test_the_service_redacts_its_stored_secrets_before_the_judgment(self):
        """Pilot boundary 1 through the shipped wiring: `AgentService._redact_known_secrets`."""
        token = 'fixture-telegram-token-7d6c5b4a'
        network = Network()
        original = network.execute

        def leaky(plan):
            result = original(plan)
            return {**result, 'results': [{**row, 'snippet': f'{row["snippet"]} {token}'} for row in result['results']]}
        network.execute = leaky
        seen = []
        engine = goal_engine(lambda facts: seen.append(dict(facts)) or True)
        script = Script({'tool_calls': [call('1', 'web_search', query='Seongnam weather tomorrow')]},
                        finish_observed('f', summary='내일 성남은 22°C입니다.'))
        service, store = self.service(script, network)
        store.secret('telegram_token', token)
        service.use_decision_engine(engine)
        self._store = store
        job = store.enqueue('내일 성남 날씨', 'agency-secret', channel='http')
        self.assertTrue(service.run_one())
        self.assertEqual(store.job(job)['status'], 'succeeded')
        [facts] = seen
        self.assertIn('Sat 22°C', facts['observations'])
        self.assertNotIn(token, json.dumps(facts, ensure_ascii=False))

    def test_a_judged_done_finish_succeeds_through_the_service(self):
        route = self.CHANNELS[0]
        script = Script({'tool_calls': [call('1', 'web_search', query='Seongnam weather tomorrow')]},
                        finish_observed('f', summary='내일 성남은 22°C입니다.'))
        row, _failed = self.run_turn('내일 성남 날씨', script, Network(), route, engine=goal_engine(True))
        self.assertEqual(row['status'], 'succeeded')
        self.assertTrue(row['response'].startswith('내일 성남은 22°C입니다.'))


class CalendarReadHandoffTests(unittest.TestCase):
    """T5: a model-chosen calendar read with no connection parks one durable handoff."""

    def test_unconnected_calendar_read_parks_the_work_once(self):
        from cryptography.fernet import Fernet
        from personal_agent.quickstart import configured_service
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / 'data')
        service = configured_service(store, {'AGENTOS_CALENDAR_LOCAL_ONLY': '1',
                                             'AGENTOS_CALENDAR_CLIENT_ID': 'calendar-client',
                                             'AGENTOS_CALENDAR_CLIENT_SECRET': 'fixture-secret',
                                             'AGENTOS_CALENDAR_LOCAL_PORT': '8799',
                                             'AGENTOS_CALENDAR_ENCRYPTION_KEY': Fernet.generate_key().decode()})
        script = Script({'tool_calls': [call('1', 'calendar_query', start='2026-09-27T00:00:00+09:00',
                                             end='2026-09-28T00:00:00+09:00', timezone='Asia/Seoul')]},
                        {'content': '내일 일정은 팀 회의 하나입니다.'})

        def transport(url, body, headers=None, timeout=60):
            names = [tool.get('function', {}).get('name') for tool in body.get('tools', [])]
            if 'agentos_connection_probe' in names:
                return {'message': {'content': '', 'tool_calls': [
                    {'function': {'name': 'agentos_connection_probe', 'arguments': {}}}]}}
            if len(body.get('messages', [])) <= 2 and not names:
                return {'message': {'content': 'ok'}}
            answer = script(url, body)['choices'][0]['message']
            if answer.get('tool_calls'):
                answer = {'content': '', 'tool_calls': [{'id': item['id'], 'function': {
                    'name': item['function']['name'], 'arguments': json.loads(item['function']['arguments'])}}
                    for item in answer['tool_calls']]}
            return {'message': answer}
        service.adapter = ModelAdapter(transport)
        service.save_model({'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434', 'model': 'test-model', 'api_key': ''})
        self.assertTrue(service.test_model()['ok'])
        job = store.enqueue('내일 일정 뭐 있어?', 'agency-calendar')
        self.assertTrue(service.run_one())
        row = store.job(job)
        self.assertEqual(row['status'], 'awaiting_connection')
        self.assertNotIn('팀 회의', row['response'])
        self.assertEqual(service.resume_index.parked_for(service.connector_owner_id(row)), ('google-calendar',))
        self.assertEqual(service.resume_index.record('google-calendar')['work_id'], job)


class BridgeCli:
    """A scripted CLI that drives the REAL AgentOS MCP bridge process.

    The bridge runs unmodified (`python -m personal_agent.mcp_bridge`) and
    records its own tool events; nothing in it reaches the network here.
    """

    def __init__(self, calls, answer):
        self.calls, self.answer, self.replies = calls, answer, []

    def execute(self, engine, prompt, tools, **_kwargs):
        caps = tools.capabilities
        env = os.environ.copy()
        env['PYTHONPATH'] = os.pathsep.join(filter(None, (str(ROOT / 'src'), env.get('PYTHONPATH'))))
        process = subprocess.Popen([sys.executable, '-m', 'personal_agent.mcp_bridge', '--data', str(caps.store.root),
                                    '--job', caps.job_id], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   text=True, env=env)
        try:
            for index, (name, args) in enumerate(self.calls, 1):
                process.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': index, 'method': 'tools/call',
                                                'params': {'name': name, 'arguments': args}}) + '\n')
                process.stdin.flush()
                self.replies.append(json.loads(process.stdout.readline()))
        finally:
            process.stdin.close()
            process.wait(timeout=30)
            process.stdout.close()
        return ExecutionResult(self.answer, engine, 0)


class CliBrokerOutcomeTests(unittest.TestCase):
    """T3: a zero CLI exit cannot erase a failed attempt; a later read can recover it.

    The Work already holds a Memory candidate with the words the CLI then
    proposes for a public search, so the bridge refuses that search before any
    network use (#605 N4 durable exclusion, kept by #654): a real, effect-free
    failed read.  No sensitivity judgment is involved.
    """

    REQUEST = '성남 약속 메모가 있는지 확인해줘'

    def run_cli(self, calls, answer):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / 'data')
        cli = BridgeCli(calls, answer)
        service = AgentService(store, subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/codex',
                                                                               clock=lambda: 1),
                               execution_adapter=cli)
        service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        job = store.enqueue(self.REQUEST, 'agency-cli', channel='telegram:g', chat_id=77)
        store.save_memory_candidate(job, 'appointment', 'Seongnam appointment', work_id=job)
        self.assertTrue(service.run_one())
        failed = [event for event in store.task_events(job) if event['status'] == 'failed']
        return store.job(job), failed, cli

    def test_c_cli_recovery_succeeds_and_keeps_the_failed_attempt(self):
        row, failed, cli = self.run_cli([('web_search', {'query': 'Seongnam appointment'}), ('list_notes', {})],
                                        '저장된 메모에는 성남 약속이 없습니다.')
        self.assertTrue(cli.replies[0]['result']['isError'])
        self.assertEqual(row['status'], 'succeeded')
        self.assertEqual(row['response'], '저장된 메모에는 성남 약속이 없습니다.')
        self.assertEqual([event['tool'] for event in failed], ['web_search'])

    def test_d_cli_zero_exit_after_only_failures_is_failed(self):
        row, failed, cli = self.run_cli([('web_search', {'query': 'Seongnam appointment'})],
                                        '확인했습니다.')
        self.assertEqual(row['status'], 'failed')
        self.assertEqual(row['response'], '확인했습니다.')
        self.assertEqual([event['tool'] for event in failed], ['web_search'])
        self.assertIn('공개 조회에 보낼 수 있는 내용이 남지 않았습니다', row['owner_cause'] or '')


if __name__ == '__main__':
    unittest.main()
