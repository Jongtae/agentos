"""AGENCY-EGRESS-01 (#605): source/destination-authorized public context composition.

Evidence class: unit and controlled local integration with fake transports.
No model, provider, network, credential or owner data is used.  Every test
asserts the *exact* outbound plan that reached the fake public transport (or
that none did) and, for a separate public task, the exact model request it
sent -- not merely the absence of one secret sentinel.
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from personal_agent import mcp_bridge
from personal_agent.agent_runtime import (DEFINITIONS, HISTORY_PREFIX, OWNER_CONVERSATION, PUBLIC_TASK_INSTRUCTIONS,
                                          PUBLIC_TASK_UNRESOLVED, WORK_SOURCES_KEY, Capabilities, egress_refusal,
                                          history_provenance, run_agent, work_sources)
from personal_agent.bounded_execution import ExecutionResult
from personal_agent.local_tools import LocalTools
from personal_agent.manifests import runtime_packages
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.subscription_engines import SubscriptionEngines

CFG = {'provider': 'compatible', 'endpoint': 'http://127.0.0.1:9999', 'model': 'fixture'}
PRIVATE = 'PRIVATE-XYZ 병원 예약 목요일'
URL = 'https://example.com/pricing'


class Wire:
    """The fake public transport: records every plan that would leave the machine."""
    def __init__(self):
        self.plans = []

    def execute(self, plan):
        self.plans.append(plan)
        if plan['tool'] == 'weather':
            return {'tool': 'weather', 'location': {'name': plan['city']}, 'sources': ['https://open-meteo.com/'],
                    'retrieved_at': 1, 'forecast': {}}
        if plan['tool'] == 'public_page_read':
            return {'tool': 'public_page_read', 'url': plan['url'], 'content': 'public page', 'sources': [plan['url']],
                    'retrieved_at': 1}
        return {'tool': plan['tool'], 'query': plan.get('query'), 'results': [], 'sources': ['https://example.org/'],
                'retrieved_at': 1}


def tool_call(name, arguments, ident='p1'):
    return {'choices': [{'message': {'content': None, 'tool_calls': [
        {'id': ident, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments, ensure_ascii=False)}}]}}]}


def answer(text='done'):
    return {'choices': [{'message': {'content': text}}]}


class PublicTaskModel:
    """Scripted public-task model: composes a call only from what its request says."""
    COMPOSE = {'오늘 뉴스 검색해줘': ('web_search', {'query': '오늘 뉴스'}),
               '대전 날씨 알려줘': ('weather', {'city': 'Daejeon', 'country': 'KR'}),
               f'{URL} 페이지 읽어줘': ('public_page_read', {'url': URL})}

    def __init__(self):
        self.bodies = []

    def __call__(self, url, body, headers=None, timeout=60):
        self.bodies.append(json.loads(json.dumps(body, ensure_ascii=False)))
        last = body['messages'][-1]
        if last['role'] == 'tool':
            return answer('public result summarised')
        planned = self.COMPOSE.get(body['messages'][1]['content'].split('\n\n')[0])
        if not planned:
            return answer('무엇을 조회할까요?')
        offered = [tool['function']['name'] for tool in body['tools']]
        # A package alias is offered under its own id with the host schema.
        return tool_call(planned[0] if planned[0] in offered else offered[0], planned[1])


class DecisionTable(unittest.TestCase):
    """Table-driven source x authority x destination decisions on ``Capabilities.execute``."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'state')
        self.wire, self.model = Wire(), PublicTaskModel()
        self.records = []

    def caps(self, labels=(), intent=None, **kwargs):
        return Capabilities(self.store, ModelAdapter(self.model), CFG, '', 'job-1',
                            lambda *event: self.records.append(event), network=self.wire,
                            inherited_provenance=set(labels), public_page_scope={URL},
                            public_intent=(lambda: intent) if intent is not None else None, **kwargs)

    # (case, inherited labels, public-task intent, action, worker args, exact outbound plans, refusal substring)
    ROWS = [
        ('clean context sends the worker query', (), None, 'web_search', {'query': 'weather radar'},
         [{'tool': 'web_search', 'query': 'weather radar'}], None),
        ('owner conversation alone is not a private store', (HISTORY_PREFIX + OWNER_CONVERSATION,), None,
         'weather', {'city': 'Daejeon', 'country': 'KR'}, [{'tool': 'weather', 'city': 'Daejeon', 'country': 'KR'}], None),
        ('earlier note listing, no public task', (HISTORY_PREFIX + 'personal-space',), None,
         'web_search', {'query': PRIVATE}, [], '이전 대화의 저장된 메모'),
        ('unrecorded legacy history stays restrictive', (HISTORY_PREFIX + 'unrecorded',), None,
         'weather', {'city': PRIVATE}, [], '출처 기록이 없는 이전 대화'),
        ('same-turn document read, no public task', ('connected-document',), None,
         'public_page_read', {'url': URL}, [], '연결 문서'),
        ('delegated memory label, no public task', ('delegated:owner-memory',), None,
         'bounded_public_research', {'mode': 'general', 'query': PRIVATE}, [], '저장된 기억'),
        ('private context: worker query discarded, request-only query sent', (HISTORY_PREFIX + 'personal-space',),
         '오늘 뉴스 검색해줘', 'web_search', {'query': PRIVATE}, [{'tool': 'web_search', 'query': '오늘 뉴스'}], None),
        ('private context: city comes from the request, not the worker', ('connected-document',),
         '대전 날씨 알려줘', 'weather', {'city': PRIVATE}, [{'tool': 'weather', 'city': 'Daejeon', 'country': 'KR'}], None),
        ('private context: approved page named in the request', ('owner-calendar',), f'{URL} 페이지 읽어줘',
         'public_page_read', {'url': URL + '?q=' + PRIVATE},
         [{'tool': 'public_page_read', 'url': URL, 'approved_urls': [URL]}], None),
        ('private context: request that only points at earlier material asks instead', (HISTORY_PREFIX + 'personal-space',),
         '그거 검색해줘', 'web_search', {'query': PRIVATE}, [], PUBLIC_TASK_UNRESOLVED),
    ]

    def test_decision_table(self):
        for case, labels, intent, action, args, outbound, refusal in self.ROWS:
            with self.subTest(case):
                self.wire.plans.clear(); self.model.bodies.clear()
                caps = self.caps(labels, intent)
                if refusal:
                    with self.assertRaises(ValueError) as raised:
                        caps.execute(action, args)
                    self.assertIn(refusal, str(raised.exception))
                else:
                    result = caps.execute(action, args)
                    if intent is not None:
                        self.assertEqual(result['composed_by'], 'agentos-public-task')
                self.assertEqual(self.wire.plans, outbound)
                # Nothing the worker wrote reached the wire from a private context.
                if labels and any(not label.endswith(OWNER_CONVERSATION) for label in labels):
                    self.assertNotIn('PRIVATE-XYZ', json.dumps(self.wire.plans, ensure_ascii=False))

    def test_the_public_task_model_request_carries_only_the_owner_request_and_one_tool(self):
        caps = self.caps((HISTORY_PREFIX + 'personal-space', 'connected-document'), '오늘 뉴스 검색해줘')
        caps.evidence.append({'tool': 'read_file', 'result': {'content': PRIVATE}})
        caps.execute('web_search', {'query': PRIVATE})
        first = self.model.bodies[0]
        self.assertEqual([m['role'] for m in first['messages']], ['system', 'user'])
        self.assertTrue(first['messages'][0]['content'].endswith(PUBLIC_TASK_INSTRUCTIONS))
        self.assertEqual(first['messages'][1]['content'], '오늘 뉴스 검색해줘')
        self.assertEqual([tool['function']['name'] for tool in first['tools']], ['web_search'])
        self.assertNotIn('PRIVATE-XYZ', json.dumps(self.model.bodies, ensure_ascii=False))
        # The tool description is AgentOS's own declaration, never a package's.
        host = next(d for d in DEFINITIONS if d['function']['name'] == 'web_search')
        self.assertEqual(first['tools'][0]['function']['description'], host['function']['description'])

    def test_a_package_alias_is_governed_by_its_host_action(self):
        packages = runtime_packages([{'version': 1, 'id': 'news', 'enabled': True, 'roles': [],
                                      'tools': [{'id': 'news_search', 'host_action': 'web_search', 'mode': 'read_only'}]}])
        refused = self.caps((HISTORY_PREFIX + 'personal-space',), packages=packages)
        with self.assertRaises(ValueError):
            refused.execute('news_search', {'query': PRIVATE})
        served = self.caps((HISTORY_PREFIX + 'personal-space',), '오늘 뉴스 검색해줘', packages=packages)
        served.execute('news_search', {'query': PRIVATE})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '오늘 뉴스'}])
        self.assertEqual([tool['function']['name'] for tool in self.model.bodies[0]['tools']], ['news_search'])

    def test_one_public_task_per_destination_per_work(self):
        caps = self.caps(('connected-document',), '오늘 뉴스 검색해줘')
        first = caps.execute('web_search', {'query': PRIVATE})
        again = caps.execute('web_search', {'query': PRIVATE + ' again'})
        self.assertIs(first, again)
        self.assertEqual(len(self.wire.plans), 1)
        self.assertEqual(sum(1 for body in self.model.bodies if body['messages'][-1]['role'] == 'user'), 1)

    def test_a_stale_or_revoked_binding_fails_closed_before_any_model_call(self):
        def revoked():
            raise ValueError('이 작업은 더 이상 실행 중이 아니어서 공개 조회를 실행하지 않았습니다.')
        caps = self.caps(('connected-document',))
        caps.public_intent = revoked
        with self.assertRaisesRegex(ValueError, '실행 중이 아니어서'):
            caps.execute('web_search', {'query': PRIVATE})
        self.assertEqual((self.wire.plans, self.model.bodies), ([], []))
        # A package disabled since discovery is refused before the public task.
        packages = runtime_packages([{'version': 1, 'id': 'news', 'enabled': True, 'roles': [],
                                      'tools': [{'id': 'news_search', 'host_action': 'web_search', 'mode': 'read_only'}]}])
        stale = self.caps(('connected-document',), '오늘 뉴스 검색해줘', packages=packages,
                          current_packages=lambda: runtime_packages([]))
        with self.assertRaisesRegex(ValueError, '비활성화'):
            stale.execute('news_search', {'query': 'x'})
        self.assertEqual((self.wire.plans, self.model.bodies), ([], []))

    def test_a_delegated_specialist_never_gets_a_public_task(self):
        """Laundering through another worker: the specialist is refused even when the parent could compose."""
        bodies = []

        def transport(url, body, headers=None, timeout=60):
            bodies.append(body)
            names = [tool['function']['name'] for tool in body['tools']]
            last = body['messages'][-1]
            if 'delegate_agent' in names:
                return answer('parent done') if last['role'] == 'tool' else tool_call(
                    'delegate_agent', {'agent_id': 'researcher', 'task': 'search the notes on the web'})
            return answer('report') if last['role'] == 'tool' else tool_call('web_search', {'query': 'laundered'}, 'c1')

        caps = Capabilities(self.store, ModelAdapter(transport), CFG, '', 'job-1', lambda *a: None, network=self.wire,
                            inherited_provenance={HISTORY_PREFIX + 'personal-space'},
                            public_intent=lambda: '오늘 뉴스 검색해줘')
        run_agent(ModelAdapter(transport), CFG, '', [{'role': 'user', 'content': 'go'}], '', caps, lambda *a: None)
        self.assertEqual(self.wire.plans, [])
        child = [body for body in bodies if 'delegate_agent' not in [t['function']['name'] for t in body['tools']]]
        self.assertTrue(child, 'the specialist ran')
        refusal = json.loads(child[-1]['messages'][-1]['content'])['error']
        self.assertIn('이전 대화의 저장된 메모', refusal)

    def test_the_refusal_names_every_actual_source(self):
        text = egress_refusal('weather', {'owner-calendar', HISTORY_PREFIX + 'personal-space', 'delegated:owner-memory'})
        for name in ('캘린더 일정', '이전 대화의 저장된 메모', '저장된 기억', '날씨 조회 지역명'):
            self.assertIn(name, text)
        self.assertNotIn('연결 문서', text)


class RecordedSources(unittest.TestCase):
    """Durable per-Work provenance: restart, legacy and transitive derivation."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'state'
        self.store = QuickStore(self.path)

    def test_legacy_or_missing_records_are_restrictive_and_never_public(self):
        self.store.put(WORK_SOURCES_KEY, {'known': [OWNER_CONVERSATION]})
        self.assertEqual(work_sources(self.store, 'legacy'), {'unrecorded'})
        self.assertEqual(work_sources(self.store, None), {'unrecorded'})
        self.assertEqual(work_sources(self.store, 'known'), {OWNER_CONVERSATION})
        self.assertEqual(work_sources(self.store, 'known', document_jobs={'known'}), {OWNER_CONVERSATION, 'connected-document'})

    def test_tool_events_widen_a_record_and_survive_a_restart(self):
        self.store.put(WORK_SOURCES_KEY, {'w1': [OWNER_CONVERSATION]})
        with self.store.db() as db:
            db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                       ('w1', 'news_notes', 'succeeded', json.dumps({'host_action': 'list_notes'}), 1))
        reopened = QuickStore(self.path)
        labels = history_provenance(reopened, [{'job_id': 'w1', 'role': 'assistant'}])
        self.assertEqual(labels, {HISTORY_PREFIX + OWNER_CONVERSATION, HISTORY_PREFIX + 'personal-space'})


class ServiceComposition(unittest.TestCase):
    """The same decisions driven through ``AgentService.run_one`` on both routes."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'state')
        self.wire, self.bodies, self.cli_refusals = Wire(), [], []

    def api(self, main_script):
        def transport(url, body, headers=None, timeout=60):
            self.bodies.append(json.loads(json.dumps(body, ensure_ascii=False)))
            if body['messages'][0]['content'].endswith(PUBLIC_TASK_INSTRUCTIONS):
                return PublicTaskModel()(url, body)
            return main_script(body['messages'])
        self.service = AgentService(self.store, adapter=ModelAdapter(transport))
        self.service.local_tools = self.wire
        self.store.put('model', CFG)
        self.store.put('model_test', {'ok': True, 'tools_ok': True, 'time': 9999999999,
                                      'fingerprint': self.service.model_fingerprint(CFG)})

    def cli(self):
        refusals = self.cli_refusals

        class Cli:
            def execute(self, engine, prompt, tools, **kwargs):
                try:
                    tools.call('web_search', {'query': 'today news'})
                except Exception as exc:
                    refusals.append(str(exc))
                return ExecutionResult('engine answer', engine, 0)

        self.service = AgentService(self.store, adapter=ModelAdapter(lambda *a: answer()),
                                    subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/cli', clock=lambda: 1),
                                    execution_adapter=Cli())
        self.service.local_tools = self.wire
        self.service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})

    def turns(self, *texts):
        for text in texts:
            self.sent = getattr(self, 'sent', 0) + 1
            self.store.enqueue(text, f'k{self.sent}')
            self.assertTrue(self.service.run_one())

    @staticmethod
    def leaky(messages):
        """A worker that puts the latest earlier assistant answer into its search query."""
        last = messages[-1]
        if last['role'] == 'tool':
            return answer('done')
        if last['role'] == 'user' and '검색' in last['content']:
            prior = [m['content'] for m in messages if m['role'] == 'assistant']
            return tool_call('web_search', {'query': (prior[-1] if prior else 'news')[:80]})
        return answer('hello back')

    def test_independent_lookup_after_private_work_sends_only_the_request_derived_query(self):
        self.api(self.leaky)
        self.turns(f'/note {PRIVATE}', '/notes', '오늘 뉴스 검색해줘')
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '오늘 뉴스'}])
        public = [body for body in self.bodies if body['messages'][0]['content'].endswith(PUBLIC_TASK_INSTRUCTIONS)]
        self.assertEqual([m['content'] for m in public[0]['messages'][1:]], ['오늘 뉴스 검색해줘'])
        self.assertNotIn('PRIVATE-XYZ', json.dumps(public, ensure_ascii=False))
        job = self.store.jobs()[0]
        events = [e for e in self.store.task_events(job['id']) if e['tool'] == 'web_search' and e['status'] == 'succeeded']
        self.assertTrue(any('agentos-public-task' in json.dumps(e['trace']) for e in events))

    def test_a_derived_reply_keeps_the_label_after_the_source_leaves_the_window(self):
        """Summaries/repetitions: a reply produced while private material was shown is itself private."""
        self.api(self.leaky)
        self.turns(f'/note {PRIVATE}', '/notes', '방금 목록 다시 말해줘')
        records = self.store.config(WORK_SOURCES_KEY, {})
        derived = self.store.jobs()[0]['id']
        self.assertIn(HISTORY_PREFIX + 'personal-space', records[derived])
        # Drop the two source Works from the window: the derived reply still closes egress.
        with self.store.db() as db:
            db.execute("DELETE FROM messages WHERE job_id!=?", (derived,))
        self.bodies.clear()
        self.turns('뉴스 검색해줘')
        # The worker's own query was not sent; only a separate public task ran
        # (and, the request naming nothing concrete, it sent nothing).
        self.assertEqual(self.wire.plans, [])
        self.assertTrue([b for b in self.bodies if b['messages'][0]['content'].endswith(PUBLIC_TASK_INSTRUCTIONS)])

    def test_public_only_follow_up_uses_the_shown_public_context(self):
        self.api(lambda messages: tool_call('weather', {'city': 'Daejeon', 'country': 'KR'})
                 if messages[-1]['role'] == 'user' and '비' in messages[-1]['content']
                 else answer('done' if messages[-1]['role'] == 'tool' else '네, 대전이군요.'))
        self.turns('나는 대전에 있어.', '아직 비가 내려?')
        self.assertEqual(self.wire.plans, [{'tool': 'weather', 'city': 'Daejeon', 'country': 'KR'}])
        self.assertFalse([b for b in self.bodies if b['messages'][0]['content'].endswith(PUBLIC_TASK_INSTRUCTIONS)])

    def test_rollback_restrictive_mode_disables_composition(self):
        self.api(self.leaky)
        self.store.put('egress_composition', {'mode': 'restrictive'})
        self.turns('hello', '오늘 뉴스 검색해줘')
        self.assertEqual(self.wire.plans, [])
        self.assertFalse([b for b in self.bodies if b['messages'][0]['content'].endswith(PUBLIC_TASK_INSTRUCTIONS)])

    def test_cli_unrecorded_legacy_history_stays_closed(self):
        self.cli()
        with self.store.db() as db:
            db.execute('INSERT INTO messages(role,content,channel,created,workspace_id,job_id) VALUES (?,?,?,?,?,?)',
                       ('assistant', PRIVATE, 'http', 0, None, 'legacy-job'))
        self.turns('오늘 뉴스 검색해줘')
        self.assertEqual(self.wire.plans, [])
        self.assertIn('출처 기록이 없는 이전 대화', self.cli_refusals[0])
        self.assertIn('/search', self.cli_refusals[0])

    def test_cli_explicit_search_preflight_still_serves_a_tainted_conversation(self):
        self.cli()
        self.turns(f'/note {PRIVATE}', '/notes', '/search 오늘 뉴스')
        self.assertEqual(self.wire.plans[0], {'tool': 'web_search', 'query': '오늘 뉴스'})
        self.assertEqual(len(self.wire.plans), 1, 'the CLI session itself was refused')
        self.assertIn('이전 대화의 저장된 메모', self.cli_refusals[-1])


class BridgeRehydration(unittest.TestCase):
    """One small integration test through the real stdio bridge ``serve`` loop."""

    def serve(self, record, argv_provenance=()):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / 'state')
        job = store.enqueue('오늘 뉴스 검색해줘', 'k1')
        with store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job,))
        store.put(WORK_SOURCES_KEY, {job: record})
        plans = []
        lines = '\n'.join(json.dumps(r) for r in [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'web_search', 'arguments': {'query': 'today news'}}},
        ]) + '\n'
        out = io.StringIO()
        with mock.patch.object(LocalTools, 'execute', lambda self, plan: plans.append(plan) or {'results': [], 'sources': []}), \
             mock.patch.object(sys, 'stdin', io.StringIO(lines)), contextlib.redirect_stdout(out):
            mcp_bridge.serve(str(store.root), job, list(argv_provenance))
        replies = [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]
        events = [e for e in store.task_events(job) if e['tool'] == 'web_search']
        return plans, replies[-1], events

    def test_a_second_bridge_without_argv_labels_rehydrates_the_history_sources(self):
        plans, reply, events = self.serve([OWNER_CONVERSATION, HISTORY_PREFIX + 'personal-space'])
        self.assertEqual(plans, [])
        self.assertIn('error', reply)
        self.assertIn('이전 대화의 저장된 메모', json.dumps(events[-1]['trace'], ensure_ascii=False))

    def test_owner_conversation_alone_leaves_the_bridge_open(self):
        plans, reply, _events = self.serve([OWNER_CONVERSATION, HISTORY_PREFIX + OWNER_CONVERSATION])
        self.assertEqual(plans, [{'tool': 'web_search', 'query': 'today news'}])
        self.assertIn('result', reply)


if __name__ == '__main__':
    unittest.main()
