"""AGENCY-EGRESS-01 (#605) composition under the SEC-PILOT-01 (#654) pilot posture.

Evidence class: unit and controlled local integration with fake transports.
No model, provider, network, credential or owner data is used.  Every test
asserts the *actual* outbound arguments that reached the fake public
transport (or that none did), not merely the absence of one secret sentinel.

What remains after #654 is deterministic only: saved or written private
values are redacted in every spelling, a private context (a private document
or store shares the Work) is composed from owner-worded permitted text with
one attempt per destination, the document-sharing grant and the provenance
refusals hold.  No per-request sensitivity judgment, per-Work lookup cap or
`/search` requirement exists on either route.
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
from personal_agent.agent_runtime import (ENGINE_UNMEDIATED, HISTORY_PREFIX, LOOKUP_QUERY_MAX, OWNER_CONVERSATION,
                                          PUBLIC_TASK_PLACE, PUBLIC_TASK_UNRESOLVED, WORK_SOURCES_KEY, Capabilities,
                                          egress_refusal, history_provenance, run_agent, work_sources)
from personal_agent.bounded_execution import ExecutionResult
from personal_agent.decision import FixtureDecisionEngine
from personal_agent.local_tools import LocalTools
from personal_agent.manifests import runtime_packages
from personal_agent.providers import ModelAdapter, ProviderError
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.subscription_engines import SubscriptionEngines

CFG = {'provider': 'compatible', 'endpoint': 'http://127.0.0.1:9999', 'model': 'fixture'}
PRIVATE = 'PRIVATE-XYZ'
PASSPORT = 'M1234567'
SECRET_ID = 'M12345678'
URL = 'https://example.com/pricing'
#: An ordinary Korean book-title request and the worker's own query for it
#: (a rewrite with added words: the author and a purchase intent).
BOOK_REQUEST = '불편한 편의점 책 어디서 살 수 있는지 찾아줘'
BOOK_QUERY = '불편한 편의점 김호연 도서 구매'


_WORKS = iter(range(1, 1 << 30))


def next_work():
    """A fresh Work id: the one-attempt budget is durable per Work (#605 F3)."""
    return f'job-{next(_WORKS)}'


class Wire:
    """The fake public transport: records every plan that would leave the machine."""
    def __init__(self, fail=False):
        self.plans, self.fail = [], fail

    def execute(self, plan):
        self.plans.append(dict(plan))
        if self.fail:
            raise ProviderError('웹 검색 결과를 가져오지 못했습니다.')
        if plan['tool'] == 'weather':
            return {'tool': 'weather', 'location': {'name': plan['city']}, 'sources': ['https://open-meteo.com/'],
                    'retrieved_at': 1, 'forecast': {}}
        if plan['tool'] == 'public_page_read':
            return {'tool': 'public_page_read', 'url': plan['url'], 'content': 'public page', 'sources': [plan['url']],
                    'retrieved_at': 1}
        return {'tool': plan['tool'], 'query': plan.get('query'), 'results': [], 'sources': ['https://example.org/'],
                'retrieved_at': 1}


def tool_call(name, arguments, ident='p1'):
    return {'id': ident, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments, ensure_ascii=False)}}


def calls(*items):
    return {'choices': [{'message': {'content': None, 'tool_calls': list(items)}}]}


def answer(text='done'):
    return {'choices': [{'message': {'content': text}}]}


def multi_selections(engine):
    """Every ``choose_many`` (the removed lookup judgment's envelope) the fixture engine was asked."""
    return [entry for entry in engine.asked if entry[0] == 'choose_many']


class DecisionTable(unittest.TestCase):
    """Table-driven source x authority x destination decisions on ``Capabilities.execute``."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'state')
        self.wire = Wire()

    def caps(self, labels=(), permitted=None, excluded=(), **kwargs):
        sources = None if permitted is None else (lambda: {'permitted': list(permitted), 'excluded': list(excluded)})
        kwargs.setdefault('public_page_scope', {URL})
        return Capabilities(self.store, None, CFG, '', next_work(), lambda *e: None, network=self.wire,
                            inherited_provenance=set(labels), lookup_sources=sources, **kwargs)

    NOTES = (HISTORY_PREFIX + 'personal-space',)
    # (case, labels, permitted text, excluded text, action, worker args, exact outbound plans, refusal substring)
    ROWS = [
        ('clean context sends the worker arguments', (), None, (), 'web_search', {'query': 'weather radar'},
         [{'tool': 'web_search', 'query': 'weather radar'}], None),
        ('owner conversation alone is not a private store', (HISTORY_PREFIX + OWNER_CONVERSATION,), None, (),
         'weather', {'city': 'Daejeon', 'country': 'KR'}, [{'tool': 'weather', 'city': 'Daejeon', 'country': 'KR'}], None),
        ('private context without a lookup resolver refuses and names the source', NOTES, None, (),
         'web_search', {'query': PRIVATE}, [], '이전 대화의 저장된 메모'),
        ('unrecorded history refuses without a resolver', (HISTORY_PREFIX + 'unrecorded',), None, (),
         'weather', {'city': PRIVATE}, [], '출처 기록이 없는 이전 대화'),
        ('private word dropped, owner words sent', NOTES, ['병원 검색해줘'], (),
         'web_search', {'query': f'{PRIVATE} 병원'}, [{'tool': 'web_search', 'query': '병원'}], None),
        ('earlier region is permitted context (성남)', NOTES, ['성남에 있어', '여기 병원 찾아줘'], (),
         'web_search', {'query': f'성남 병원 {PRIVATE}'}, [{'tool': 'web_search', 'query': '성남 병원'}], None),
        ('passport number written to Memory is excluded even though the owner typed it', ('owner-memory',),
         [f'여권번호 {PASSPORT} 기억해 두고 병원 검색해줘'], [PASSPORT],
         'web_search', {'query': f'병원 {PASSPORT}'}, [{'tool': 'web_search', 'query': '병원'}], None),
        ('nothing permitted remains: ask, send nothing', NOTES, ['그거 검색해줘'], (),
         'web_search', {'query': PRIVATE}, [], PUBLIC_TASK_UNRESOLVED),
        ('AI-composed place name is not the owner wording', ('connected-document',), ['나는 대전에 있어'], (),
         'weather', {'city': 'Daejeon', 'country': 'KR'}, [], PUBLIC_TASK_PLACE),
        ('owner-worded place is sent; AI-composed country is dropped', ('connected-document',), ['나는 대전에 있어'], (),
         'weather', {'city': '대전', 'country': 'KR'}, [{'tool': 'weather', 'city': '대전'}], None),
        ('a longer private word does not ride on a permitted stem', NOTES, ['성남에 있어 병원 찾아줘'], (),
         'web_search', {'query': '성남정신과 병원'}, [{'tool': 'web_search', 'query': '병원'}], None),
        ('approved page in the current scope', ('owner-calendar',), [], (),
         'public_page_read', {'url': URL}, [{'tool': 'public_page_read', 'url': URL, 'approved_urls': [URL]}], None),
        ('page outside the current scope', ('owner-calendar',), [], (),
         'public_page_read', {'url': URL + '?q=' + PRIVATE}, [], '현재 승인한 공개 페이지'),
    ]

    def test_decision_table(self):
        for case, labels, permitted, excluded, action, args, outbound, refusal in self.ROWS:
            with self.subTest(case):
                self.wire.plans.clear()
                caps = self.caps(labels, permitted, excluded)
                if refusal:
                    with self.assertRaises(ValueError) as raised:
                        caps.execute(action, args)
                    self.assertIn(refusal, str(raised.exception))
                else:
                    result = caps.execute(action, args)
                    if permitted is not None:
                        # Checked arguments are exactly the transmitted arguments.
                        self.assertEqual(result['composed_by'], 'agentos-public-task')
                        self.assertEqual({'tool': action, **result['sent']}, outbound[0])
                self.assertEqual(self.wire.plans, outbound)

    def test_research_query_is_composed_the_same_way(self):
        caps = self.caps(self.NOTES, ['노트북 비교해줘'])
        with mock.patch.object(Capabilities, '_research', lambda self, mode, query: {'query': query, 'mode': mode, 'sources': []}):
            result = caps.execute('bounded_public_research', {'mode': 'product', 'query': f'노트북 {PRIVATE}'})
        self.assertEqual(result['sent'], {'query': '노트북', 'mode': 'product'})

    def test_same_batch_memory_write_is_excluded_whichever_call_comes_first(self):
        """"여권번호를 기억해 두고 병원 검색해줘" in one message, both call orders."""
        request = f'여권번호 {PASSPORT} 기억해 두고 병원 검색해줘'
        memory = tool_call('save_memory', {'memory_key': 'passport', 'content': PASSPORT}, 'm')
        search = tool_call('web_search', {'query': f'병원 {PASSPORT}'}, 's')
        for order in ((search, memory), (memory, search)):
            with self.subTest([c['function']['name'] for c in order]):
                self.wire.plans.clear()
                replies = [calls(*order), answer()]
                caps = self.caps((), [request])
                run_agent(ModelAdapter(lambda *a, **k: replies.pop(0)), CFG, '', [{'role': 'user', 'content': request}],
                          '', caps, lambda *e: None)
                self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'}])

    def test_revoked_page_scope_refuses_a_read_that_starts_afterwards(self):
        scope = {URL}
        caps = self.caps(public_page_scope=lambda: set(scope))
        caps.execute('public_page_read', {'url': URL})
        scope.clear()
        with self.assertRaisesRegex(ValueError, '승인한 공개 페이지 범위가 없습니다'):
            caps.execute('public_page_read', {'url': URL + '#again'})
        tainted = self.caps(('connected-document',), [], public_page_scope=lambda: set(scope))
        with self.assertRaisesRegex(ValueError, '현재 승인한 공개 페이지'):
            tainted.execute('public_page_read', {'url': URL})
        self.assertEqual(len(self.wire.plans), 1, 'the read before revocation is not undone, and none follows it')

    def test_budget_holds_after_failure_and_after_success(self):
        """F3: one network attempt per destination per Work, recorded before the request."""
        self.wire.fail = True
        caps = self.caps(self.NOTES, ['병원 검색 뉴스'])
        for query in ('병원', '뉴스', '병원 뉴스'):
            with self.assertRaises((ValueError, ProviderError)):
                caps.execute('web_search', {'query': query})
        self.assertEqual(len(self.wire.plans), 1)
        self.wire.fail = False; self.wire.plans.clear()
        ok = self.caps(self.NOTES, ['병원 검색 뉴스'])
        first = ok.execute('web_search', {'query': '병원'})
        self.assertIs(ok.execute('web_search', {'query': '뉴스'}), first)
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'}])

    def test_a_stale_binding_or_disabled_package_fails_closed_before_egress(self):
        def stale():
            raise ValueError('이 작업은 더 이상 실행 중이 아니어서 공개 조회를 실행하지 않았습니다.')
        caps = self.caps(self.NOTES)
        caps.lookup_sources = stale
        with self.assertRaisesRegex(ValueError, '실행 중이 아니어서'):
            caps.execute('web_search', {'query': '병원'})
        packages = runtime_packages([{'version': 1, 'id': 'news', 'enabled': True, 'roles': [],
                                      'tools': [{'id': 'news_search', 'host_action': 'web_search', 'mode': 'read_only'}]}])
        disabled = self.caps(self.NOTES, ['병원'], packages=packages, current_packages=lambda: runtime_packages([]))
        with self.assertRaisesRegex(ValueError, '비활성화'):
            disabled.execute('news_search', {'query': '병원'})
        self.assertEqual(self.wire.plans, [])

    def test_a_package_alias_is_governed_by_its_host_action(self):
        packages = runtime_packages([{'version': 1, 'id': 'news', 'enabled': True, 'roles': [],
                                      'tools': [{'id': 'news_search', 'host_action': 'web_search', 'mode': 'read_only'}]}])
        self.caps(self.NOTES, ['병원 찾아줘'], packages=packages).execute('news_search', {'query': f'{PRIVATE} 병원'})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'}])

    def test_a_delegated_specialist_never_composes_a_lookup(self):
        """Laundering through another worker: the specialist is refused even when the parent could compose."""
        bodies = []

        def transport(url, body, headers=None, timeout=60):
            bodies.append(body)
            names = [tool['function']['name'] for tool in body['tools']]
            last = body['messages'][-1]
            if 'delegate_agent' in names:
                return answer('parent done') if last['role'] == 'tool' else calls(tool_call(
                    'delegate_agent', {'agent_id': 'researcher', 'task': '병원 검색'}))
            return answer('report') if last['role'] == 'tool' else calls(tool_call('web_search', {'query': '병원'}, 'c1'))

        caps = Capabilities(self.store, ModelAdapter(transport), CFG, '', 'job-1', lambda *a: None, network=self.wire,
                            inherited_provenance=set(self.NOTES), lookup_sources=lambda: {'permitted': ['병원 검색'], 'excluded': []})
        run_agent(ModelAdapter(transport), CFG, '', [{'role': 'user', 'content': 'go'}], '', caps, lambda *a: None)
        self.assertEqual(self.wire.plans, [])
        child = [body for body in bodies if 'delegate_agent' not in [t['function']['name'] for t in body['tools']]]
        self.assertIn('이전 대화의 저장된 메모', json.loads(child[-1]['messages'][-1]['content'])['error'])

    def test_the_refusal_names_every_actual_source(self):
        text = egress_refusal('weather', {'owner-calendar', HISTORY_PREFIX + 'personal-space', 'delegated:owner-memory'})
        for name in ('캘린더 일정', '이전 대화의 저장된 메모', '저장된 기억', '날씨 조회 지역명'):
            self.assertIn(name, text)
        self.assertNotIn('연결 문서', text)


class RecordedSources(unittest.TestCase):
    """Durable per-Work provenance: restart and legacy."""

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
        labels = history_provenance(QuickStore(self.path), [{'job_id': 'w1', 'role': 'assistant'}])
        self.assertEqual(labels, {HISTORY_PREFIX + OWNER_CONVERSATION, HISTORY_PREFIX + 'personal-space'})


class ServiceComposition(unittest.TestCase):
    """The owner-decision cases through ``AgentService.run_one`` on both routes."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'state')
        self.wire, self.cli_refusals, self.sent = Wire(), [], 0

    def api(self, script, engine=None):
        self.service = AgentService(self.store, adapter=ModelAdapter(lambda url, body, *a, **k: script(body['messages'])))
        self.service.local_tools = self.wire
        if engine is not None:
            self.service.use_decision_engine(engine)
        self.store.put('model', CFG)
        self.store.put('model_test', {'ok': True, 'tools_ok': True, 'time': 9999999999,
                                      'fingerprint': self.service.model_fingerprint(CFG)})

    def cli(self, script, engine=None):
        refusals = self.cli_refusals

        class Cli:
            def execute(self, engine, prompt, tools, **kwargs):
                request = (kwargs.get('context') or {}).get('request', prompt)
                planned = script(request)
                if planned:
                    try:
                        tools.call(*planned)
                    except Exception as exc:
                        refusals.append(str(exc))
                return ExecutionResult(f'engine answer {PRIVATE}' if 'read my file' in request else 'engine answer', engine, 0)

        self.service = AgentService(self.store, adapter=ModelAdapter(lambda *a, **k: answer()),
                                    subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/cli', clock=lambda: 1),
                                    execution_adapter=Cli())
        self.service.local_tools = self.wire
        if engine is not None:
            self.service.use_decision_engine(engine)
        self.service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})

    def turns(self, *texts):
        for text in texts:
            self.sent += 1
            self.store.enqueue(text, f'k{self.sent}')
            self.assertTrue(self.service.run_one())

    @staticmethod
    def worker(query_for):
        """A worker that proposes ``query_for(request, earlier assistant texts)`` for search requests."""
        def script(messages):
            last = messages[-1]
            if last['role'] == 'tool':
                return answer('done')
            if last['role'] == 'user' and ('검색' in last['content'] or '찾아' in last['content']):
                prior = [m['content'] for m in messages if m['role'] == 'assistant']
                return calls(tool_call('web_search', {'query': query_for(last['content'], prior)}))
            if last['role'] == 'user' and '기억' in last['content']:
                return calls(tool_call('save_memory', {'memory_key': 'passport', 'content': PASSPORT}, 'm'))
            return answer('네.')
        return script

    def test_ordinary_first_search_sends_the_worker_query(self):
        self.api(self.worker(lambda request, prior: 'today news'))
        self.turns('오늘 뉴스 검색해줘')
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': 'today news'}])

    # -- #654: an ordinary request reaches web_search at once on both routes
    def test_api_route_sends_a_book_title_request_as_the_worker_composed_it(self):
        engine = FixtureDecisionEngine()
        self.api(self.worker(lambda request, prior: BOOK_QUERY), engine)
        self.turns(BOOK_REQUEST)
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': BOOK_QUERY}])
        self.assertEqual(multi_selections(engine), [], 'no lookup sensitivity judgment is asked')
        self.assertEqual(self.store.jobs()[0]['status'], 'succeeded')

    def test_cli_route_sends_a_book_title_request_as_the_worker_composed_it(self):
        engine = FixtureDecisionEngine()
        self.cli(lambda request: ('web_search', {'query': BOOK_QUERY}), engine)
        self.turns(BOOK_REQUEST)
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': BOOK_QUERY}])
        self.assertEqual(self.cli_refusals, [])
        self.assertEqual(multi_selections(engine), [], 'no lookup sensitivity judgment is asked')

    def test_region_from_earlier_conversation_is_used_without_re_asking(self):
        """"성남에 있어" -> "여기 병원 찾아줘" after private work: the region is kept, the note is not."""
        self.api(self.worker(lambda request, prior: f'성남 병원 {PRIVATE}'))
        self.turns(f'/note {PRIVATE}', '/notes', '성남에 있어', '여기 병원 찾아줘')
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '성남 병원'}])

    def test_passport_remembered_earlier_never_enters_the_search(self):
        """"여권번호를 기억해 둬" -> "병원 검색해줘"."""
        self.api(self.worker(lambda request, prior: f'병원 {PASSPORT}'))
        self.turns(f'여권번호 {PASSPORT} 기억해 둬', '병원 검색해줘')
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'}])

    def test_the_prior_private_answer_does_not_reach_search(self):
        self.api(self.worker(lambda request, prior: (prior[-1] if prior else 'news')[:80]))
        self.turns(f'/note {PRIVATE}', '/notes', '그거 검색해줘')
        self.assertEqual(self.wire.plans, [])

    def test_cli_host_read_reply_taints_the_next_cli_work(self):
        """F1: a trusted-local CLI reply may carry unmediated host reads."""
        self.cli(lambda request: ('web_search', {'query': f'{PRIVATE} news'}) if 'search' in request else None)
        self.turns('read my file', 'search the web for news')
        record = self.store.config(WORK_SOURCES_KEY, {})[self.store.jobs()[-1]['id']]
        self.assertIn(ENGINE_UNMEDIATED, record)
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': 'news'}])

    def test_cli_host_read_reply_taints_a_later_api_work_route_switch(self):
        self.cli(lambda request: None)
        self.turns('read my file')
        self.store.put('subscription_engine', {})  # the owner switches to the direct-API route
        self.api(self.worker(lambda request, prior: prior[-1][:80]))
        self.turns('그거 검색해줘')
        self.assertEqual(self.store.jobs()[0]['provider'], 'compatible', 'the second Work ran on the API route')
        self.assertEqual(self.wire.plans, [])

    def test_cli_first_turn_is_not_tainted_by_its_own_label(self):
        self.cli(lambda request: ('web_search', {'query': 'today news'}))
        self.turns('hello there')
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': 'today news'}])

    def test_cli_unrecorded_legacy_history_keeps_its_text_out(self):
        self.cli(lambda request: ('web_search', {'query': f'{PRIVATE} news'}))
        with self.store.db() as db:
            db.execute('INSERT INTO messages(role,content,channel,created,workspace_id,job_id) VALUES (?,?,?,?,?,?)',
                       ('assistant', PRIVATE, 'http', 0, None, 'legacy-job'))
        self.turns('search news')
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': 'news'}])


class BridgeRehydration(unittest.TestCase):
    """Small integration tests through the real stdio bridge ``serve`` loop."""

    def serve(self, record, query, message='search today news', before=None):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / 'state')
        job = store.enqueue(message, 'k1')
        with store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job,))
            db.execute('INSERT INTO messages(role,content,channel,created,workspace_id,job_id) VALUES (?,?,?,?,?,?)',
                       ('user', message, 'web', 1, None, job))
        store.put(WORK_SOURCES_KEY, {job: record})
        if before:
            before(store)
        plans = []
        lines = '\n'.join(json.dumps(r) for r in [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'web_search', 'arguments': {'query': query}}},
        ]) + '\n'
        out = io.StringIO()
        with mock.patch.object(LocalTools, 'execute', lambda self, plan: plans.append(plan) or {'results': [], 'sources': []}), \
             mock.patch.object(sys, 'stdin', io.StringIO(lines)), contextlib.redirect_stdout(out):
            mcp_bridge.serve(str(store.root), job, [])
        return plans, [json.loads(line) for line in out.getvalue().splitlines() if line.strip()][-1]

    def test_a_bridge_without_argv_labels_rehydrates_and_composes_from_permitted_words(self):
        plans, reply = self.serve([OWNER_CONVERSATION, HISTORY_PREFIX + 'personal-space'], f'{PRIVATE} today news')
        self.assertEqual(plans, [{'tool': 'web_search', 'query': 'today news'}])
        self.assertIn('result', reply)

    def test_the_cli_unmediated_label_does_not_taint_its_own_work(self):
        plans, _reply = self.serve([OWNER_CONVERSATION, ENGINE_UNMEDIATED], 'weather radar', 'hello')
        self.assertEqual(plans, [{'tool': 'web_search', 'query': 'weather radar'}])

    def test_the_bridge_sends_an_ordinary_request_with_a_subscription_cli_decision_route(self):
        """#654: no decision CLI runs inside the bridge, and the lookup goes out anyway."""
        def route(store):
            store.put('decision_route', {'transport': 'subscription_cli', 'engine': 'claude-code',
                                         'model_policy': 'engine_default', 'fingerprint': 'x'})
        with mock.patch('personal_agent.decision_routes.DecisionRoutes._cli_engine',
                        side_effect=AssertionError('no decision CLI may run inside the bridge')):
            plans, reply = self.serve([OWNER_CONVERSATION], BOOK_QUERY, BOOK_REQUEST, before=route)
        self.assertEqual(plans, [{'tool': 'web_search', 'query': BOOK_QUERY}])
        self.assertIn('result', reply)
        self.assertFalse(reply['result'].get('isError'))


TAG_ID = ''.join(chr(0xE0000 + ord(ch)) for ch in SECRET_ID)  # invisible Unicode TAG characters


class Redaction(unittest.TestCase):
    """Deterministic redaction of saved/written values and the private-context rules (#605, kept by #654)."""

    NOTES = (HISTORY_PREFIX + 'personal-space',)
    SAVED = [f'여권번호 {SECRET_ID}']
    MESSAGE = f'여권번호 {SECRET_ID} 기억해 둬. 그리고 병원 검색해줘'

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'state'
        self.store = QuickStore(self.path)
        self.wire = Wire()

    def caps(self, labels=(), permitted=(), excluded=(), current=None, work=None, store=None, **kwargs):
        def sources():
            return {'permitted': list(permitted), 'excluded': list(excluded),
                    'current': current if current is not None else (list(permitted) or [''])[-1]}
        return Capabilities(store or self.store, None, CFG, '', work or next_work(), lambda *e: None, network=self.wire,
                            inherited_provenance=set(labels), lookup_sources=sources, **kwargs)

    def sent(self):
        return [plan.get('query', plan.get('city')) for plan in self.wire.plans]

    def check_saved(self, saved, cases, permitted=('병원 hospital 찾아줘',)):
        for query, expected in cases:
            with self.subTest(saved=saved, query=query):
                self.wire.plans.clear()
                self.caps((), list(permitted), saved).execute('web_search', {'query': query})
                self.assertEqual(self.sent(), [expected])

    # -- clean context: the worker's words go out as composed
    def test_clean_queries_keep_the_worker_string(self):
        # Exactly what is sent under the P1-A separator policy: the ASCII
        # operator allowlist survives; the currency symbol does not.
        for query, sent in (('Python 3.13 release notes', 'Python 3.13 release notes'),
                            ('"C++20" modules site:cppreference.com', '"C++20" modules site:cppreference.com'),
                            ('node.js -deno', 'node.js -deno'),
                            ('₩50,000 이하 이어폰', '50,000 이하 이어폰'),
                            (BOOK_QUERY, BOOK_QUERY)):
            with self.subTest(query):
                self.wire.plans.clear()
                self.caps((), ['검색해줘']).execute('web_search', {'query': query})
                self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': sent}])

    def test_clean_words_are_deduplicated_but_not_capped_or_counted(self):
        words = [f'w{index}' for index in range(20)]
        caps = self.caps((), ['검색해줘'], work='w-clean')
        for turn in range(8):  # more than the removed six-per-Work cap
            caps.execute('web_search', {'query': 'a b a B ' + ' '.join(words)})
        self.assertEqual(len(self.wire.plans), 8)
        self.assertEqual(self.wire.plans[-1]['query'].split(), ['a', 'b', *words])
        self.assertIsNone(self.store.config('work_lookup_state:w-clean', None), 'no durable per-Work lookup row')

    def test_a_query_is_cut_only_at_the_provider_limit(self):
        long_query = ' '.join(f'word{index:04d}' for index in range(80))  # 719 characters
        self.caps((), ['검색해줘']).execute('web_search', {'query': long_query})
        sent = self.sent()[0]
        self.assertLessEqual(len(sent), LOOKUP_QUERY_MAX)
        self.assertTrue(long_query.startswith(sent))
        self.assertGreater(len(sent.split()), 12, 'the removed 12-word cap no longer binds')

    def test_clean_weather_sends_the_transliteration_and_a_validated_country(self):
        self.caps((), ['나는 대전에 있어. 비 와?']).execute('weather', {'city': 'Daejeon', 'country': 'kr'})
        self.assertEqual(self.wire.plans, [{'tool': 'weather', 'city': 'Daejeon', 'country': 'KR'}])
        for country in ('Korea', 'ZZ', 'QX', 'K1'):
            with self.subTest(country=country):
                self.wire.plans.clear()
                self.caps((), ['나는 대전에 있어. 비 와?']).execute('weather', {'city': 'Daejeon', 'country': country})
                self.assertEqual(self.wire.plans, [{'tool': 'weather', 'city': 'Daejeon'}],
                                 'not an ISO 3166-1 alpha-2 code (P3-1): omitted')

    # -- private context: owner wording, dedupe, order, cap, one attempt
    def test_private_weather_keeps_owner_wording_only(self):
        with self.assertRaisesRegex(ValueError, '지역명은 소유자가'):
            self.caps(('connected-document',), ['나는 대전에 있어']).execute('weather', {'city': 'Daejeon', 'country': 'KR'})
        self.assertEqual(self.wire.plans, [])

    def test_private_weather_city_follows_the_private_rules(self):
        self.caps(('connected-document',), ['분당구 정자동 날씨 알려줘']).execute('weather', {'city': '정자동 분당구 정자동'})
        self.assertEqual(self.wire.plans, [{'tool': 'weather', 'city': '분당구 정자동'}])

    def test_n1_a_word_extending_a_permitted_word_sends_only_the_permitted_word(self):
        for proposal in ('병원이혼 병원소송 근처우울', '병원ab 병원cd'):
            with self.subTest(proposal):
                self.wire.plans.clear()
                self.caps(self.NOTES, ['병원 찾아줘']).execute('web_search', {'query': proposal})
                self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'}])

    def test_n5_words_are_deduplicated_ordered_by_permitted_text_and_capped(self):
        earlier, current = '성남에 있어', '여기 병원 찾아줘 내과 소아과 치과 안과 피부과 정형외과 한의원'
        self.caps(self.NOTES, [earlier, current]).execute(
            'web_search', {'query': '한의원 병원 성남 병원 성남 치과 안과 내과 소아과 피부과 정형외과'})
        sent = self.wire.plans[0]['query'].split()
        self.assertEqual(sent, ['성남', '병원', '내과', '소아과', '치과', '안과', '피부과', '정형외과'])

    def test_f3_the_attempt_is_durable_across_a_restarted_bridge(self):
        self.wire.fail = True
        with self.assertRaises((ValueError, ProviderError)):
            self.caps(self.NOTES, ['병원 뉴스'], work='f3').execute('web_search', {'query': '병원'})
        self.wire.fail = False
        with self.assertRaisesRegex(ValueError, '이미 한 번 시도'):
            self.caps(self.NOTES, ['병원 뉴스'], work='f3').execute('web_search', {'query': '뉴스'})  # a new process
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'}])

    def test_r8_two_bridge_processes_claim_one_attempt(self):
        import threading
        results, barrier = [], threading.Barrier(8)

        def claim():
            caps = Capabilities(QuickStore(self.path), None, CFG, '', 'job-1', lambda *e: None, network=self.wire)
            barrier.wait()
            results.append(caps._claim_attempt('web_search', 'web_search'))

        threads = [threading.Thread(target=claim) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), [False] * 7 + [True])

    def test_r9_audit_appends_from_two_processes_are_not_lost(self):
        import threading

        def append(worker):
            store = QuickStore(self.path)
            for index in range(25):
                store.append_config_list('decision_audit', {'worker': worker, 'index': index}, 100)

        threads = [threading.Thread(target=append, args=(worker,)) for worker in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(self.store.config('decision_audit')), 50)

    # -- explicit /search: a convenience, not a requirement
    def test_the_typed_search_string_is_sent_as_typed_every_time(self):
        typed = '이혼소송 강남 변호사 "상담 비용"'
        caps = self.caps((), [f'/search {typed}'])
        result = caps.execute('web_search', {'query': typed})
        self.assertTrue(result['explicit_owner_query'])
        again = caps.execute('web_search', {'query': typed})  # no once-per-Work claim since #654
        self.assertTrue(again['explicit_owner_query'])
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': typed}] * 2)
        self.assertIsNone(self.store.config(f'work_lookup_state:{caps.job_id}', None))

    def test_rewritten_words_go_out_and_saved_values_still_leave_out(self):
        rewritten = self.caps((), ['/search 이혼소송 강남 변호사'])
        rewritten.execute('web_search', {'query': '이혼소송 강남 변호사 추천'})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '이혼소송 강남 변호사 추천'}])
        self.wire.plans.clear()
        saved = self.caps(('owner-memory',), [f'/search {SECRET_ID} 병원'], [SECRET_ID])
        saved.execute('web_search', {'query': f'{SECRET_ID} 병원'})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'}])

    def test_the_explicit_search_string_is_rechecked_too(self):
        typed = '병원 M123-여권번호-456-여권번호-78'
        self.caps((), [f'/search {typed}'], self.SAVED).execute('web_search', {'query': typed})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'}])

    # -- saved and written values never leave, in any spelling
    def test_r3_a_calendar_draft_is_excluded_in_process_and_after_a_restart(self):
        from personal_agent.agent_runtime import lookup_sources
        from personal_agent.calendar import CALENDAR_STATE_KEY

        class Calendar:
            def draft_create(self, content, owner):
                return {'id': 'd1', 'action': 'create'}

            def preview(self, ident, owner):
                return {'summary': 'x'}

        message = f'{SECRET_ID} 치과 일정 잡고 병원 검색해줘'
        caps = self.caps((), [message], calendar=Calendar(), calendar_owner='owner')
        caps.execute('calendar_draft_create', {'summary': f'{SECRET_ID} 치과', 'start': 's', 'end': 'e', 'timezone': 'UTC'})
        caps.execute('web_search', {'query': f'{SECRET_ID} 병원'})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'}])
        # A restarted process: the draft is found through the Work's durable event.
        job = self.store.enqueue(message, 'r3')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job,))
            db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                       (job, 'calendar_draft_create', 'succeeded',
                        json.dumps({'host_action': 'calendar_draft_create', 'evidence': {'draft_id': 'd1'}}), 1))
        self.store.put(CALENDAR_STATE_KEY, {'d1': {'payload': {'summary': f'{SECRET_ID} 치과'}}})
        self.wire.plans.clear()
        Capabilities(QuickStore(self.path), None, CFG, '', job, lambda *e: None, network=self.wire,
                     lookup_sources=lambda: lookup_sources(QuickStore(self.path), job)).execute('web_search', {'query': f'{SECRET_ID} 병원'})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'}])

    def test_r7_a_short_number_is_not_a_piece_of_a_saved_value(self):
        self.caps(('owner-memory',), ['3일 서울 날씨 검색해줘'], [SECRET_ID]).execute('web_search', {'query': '3일 서울 날씨'})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '3일 서울 날씨'}])
        self.wire.plans.clear()
        self.caps(('owner-memory',), ['5678 서울 검색해줘'], [SECRET_ID]).execute('web_search', {'query': '5678 서울'})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '서울'}])

    def test_n4_a_reformatted_saved_value_is_excluded_in_every_spelling(self):
        saved = {'M12345678': ['M1234-5678 병원', 'M1234 5678 병원', 'm12345678 병원', 'Ｍ１２３４５６７８ 병원', '5678 병원'],
                 'M1234-5678': ['M12345678 병원', 'm1234 병원']}
        for value, proposals in saved.items():
            for proposal in proposals:
                with self.subTest(saved=value, proposal=proposal):
                    self.wire.plans.clear()
                    request = f'여권 {proposal} 기억해 두고 병원 검색해줘'
                    self.caps(('owner-memory',), [request], [value]).execute('web_search', {'query': proposal})
                    self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'}])

    def test_p1_c_non_ascii_digits_of_a_saved_value_never_leave(self):
        for name, query in (('Arabic-Indic', '병원 M١٢٣٤٥٦٧٨'), ('Devanagari', '병원 M१२३४५६७८'),
                            ('Bengali', '병원 M১২৩৪৫৬৭৮'), ('Thai', '병원 M๑๒๓๔๕๖๗๘'),
                            ('Extended Arabic-Indic, split', '병원 ۱۲۳۴-۵۶۷۸'), ('Fullwidth', '병원 Ｍ１２３４５６７８')):
            with self.subTest(name):
                self.wire.plans.clear()
                self.caps((), [self.MESSAGE], self.SAVED).execute('web_search', {'query': query})
                self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'}])

    def test_no_category_digits_of_a_saved_value_never_leave(self):
        kharoshthi = ''.join(chr(0x10A40 + index) for index in range(4))  # KHAROSHTHI DIGIT ONE..FOUR
        for query in ('병원 M❶❷❸❹❺❻❼❽', '병원 M➀➁➂➃➄➅➆➇', f'병원 M{kharoshthi}', '병원 ⑤⑥⑦⑧'):
            with self.subTest(query):
                self.wire.plans.clear()
                self.caps((), [self.MESSAGE], self.SAVED).execute('web_search', {'query': query})
                self.assertEqual(self.sent(), ['병원'])

    def test_p2_d_a_split_written_value_never_leaves_and_the_over_block_is_as_stated(self):
        saved = ['김철수 상담 예약']
        for query, sent in (('김 철수 병원', '병원'), ('김-철수 병원', '병원'), ('KIM철수 병원', '병원'),
                            ('철수 병원', '병원'), ('상담소 병원', '병원'), ('담 병원', '담 병원')):
            with self.subTest(query):
                self.wire.plans.clear()
                self.caps((), ['병원 찾아줘'], saved).execute('web_search', {'query': query})
                self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': sent}])

    def test_jamo_spellings_of_a_saved_value_and_the_minimum_length(self):
        for query, sent in (('ㄱㅣㅁㅊㅓㄹㅅㅜ 병원', '병원'), ('김 병원', '김 병원'), ('김치 병원', '김치 병원')):
            with self.subTest(query):
                self.wire.plans.clear()
                self.caps((), ['병원 찾아줘'], ['김철수 상담']).execute('web_search', {'query': query})
                self.assertEqual(self.sent(), [sent])

    def test_jamo_and_suffix_variants_of_a_saved_value(self):
        self.check_saved(['김철수'], [('ㄱㅣㅁㅊㅓㄹㅅㅜ님 병원', '병원'), ('김ㅊㅓㄹㅅㅜ에게 병원', '병원'),
                                     ('기ㅁ처ㄹ수씨 병원', '병원'), ('김철수님 병원', '병원'), ('김철수에게 병원', '병원')])
        self.check_saved(['여권번호'], [('ㅇㅕㄱㅝㄴ번호를 병원', '병원')])
        self.check_saved(['kimchulsoo'], [('mrkimchulsoo hospital', 'hospital'), ('kimchulsoos hospital', 'hospital'),
                                          ('kímchulsoo hospital', 'hospital'), ('KÏMCHÜLSOO hospital', 'hospital')])
        for value in ('이수', '김이수'):
            self.check_saved([value], [('ㅇ ㅣ ㅅ ㅜ 병원', '병원')])
        self.check_saved(['닭갈비집'], [('ㄷㅏㄹㄱㄱㅏㄹㅂㅣ 병원', '병원'), ('닭갈비 병원', '병원')])
        self.check_saved(['Łukasz'], [('lukasz hospital', 'hospital')])
        self.check_saved(['lukasz'], [('Łukasz hospital', 'hospital')])
        self.check_saved(['Øster'], [('oster hospital', 'hospital')])

    def test_the_documented_over_blocking(self):
        for saved, query, sent in ((['20250315'], '2025 세법 개정', '세법 개정'),
                                   (['여권번호'], '여권 번호 재발급 방법', '재발급 방법'),
                                   (['010-2412-5678'], '버스 2412', '버스')):
            with self.subTest(query):
                self.wire.plans.clear()
                self.caps((), ['검색해줘'], saved).execute('web_search', {'query': query})
                self.assertEqual(self.sent(), [sent])
        with self.assertRaises(ValueError):
            self.caps((), ['서울 날씨 알려줘'], ['서울 병원 예약 메모']).execute('weather', {'city': '서울'})

    # -- separators: only admissible characters leave; the final string is re-checked
    def test_p1_a_separator_channel_exploits_are_closed(self):
        cases = [
            ('invisible TAG characters after a kept word', {}, 'web_search', {'query': '병원 ' + TAG_ID},
             {'tool': 'web_search', 'query': '병원'}),
            ('TAG characters next to an earlier permitted word', {'permitted': ['약국 알려줘', MESSAGE_]},
             'web_search', {'query': '약국 ' + TAG_ID}, {'tool': 'web_search', 'query': '약국'}),
            ('a symbol run', {}, 'web_search', {'query': '병원 !@#$%^&*('}, {'tool': 'web_search', 'query': '병원'}),
            ('zero-width and format characters between words', {}, 'web_search',
             {'query': '병​원⁠ ‍﻿검색'}, {'tool': 'web_search', 'query': '병 원 검색'}),
            ('private-use and unassigned characters', {}, 'web_search', {'query': '병원 \U000f0000\U0001fffe'},
             {'tool': 'web_search', 'query': '병원'}),
            ('weather city with TAG characters', {}, 'weather', {'city': 'Seoul' + TAG_ID, 'country': 'KR'},
             {'tool': 'weather', 'city': 'Seoul', 'country': 'KR'}),
        ]
        for case, options, action, args, sent in cases:
            with self.subTest(case):
                self.wire.plans.clear()
                self.caps((), options.get('permitted', [self.MESSAGE]), self.SAVED).execute(action, args)
                self.assertEqual(self.wire.plans, [sent])
                self.assertTrue(all(ord(ch) < 0xE0000 for ch in json.dumps(self.wire.plans, ensure_ascii=False)))

    def test_p1_a_separators_are_capped_per_separator_and_in_total(self):
        self.caps((), ['검색해줘']).execute('web_search', {'query': 'a.-+#:/b c(),&"d ' + ' '.join('e' * 1 + '.' + 'f' for _ in range(10))})
        sent = self.wire.plans[0]['query']
        self.assertIn('a.-+b', sent, 'at most 3 operator characters per separator')
        self.assertLessEqual(sum(1 for ch in sent if not ch.isalnum() and not ch.isspace()), 12)

    def test_p2_b_removal_does_not_glue_neighbours(self):
        self.caps((), [self.MESSAGE], self.SAVED).execute('web_search', {'query': '병원 M123-여권번호-456-여권번호-78'})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'}])
        self.wire.plans.clear()
        self.caps((), ['이혼 변호사 알려줘'], ['zz']).execute('web_search', {'query': '이-zz-혼 변호사'})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '이 혼 변호사'}])


MESSAGE_ = Redaction.MESSAGE


class PilotPostureEndToEnd(unittest.TestCase):
    """#654 on both routes, end to end: no engine, no judgment, no `/search` needed."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'state')
        self.wire = Wire()

    def api(self, script):
        service = AgentService(self.store, adapter=ModelAdapter(lambda url, body, *a, **k: script(body['messages'])))
        service.local_tools = self.wire
        self.store.put('model', CFG)
        self.store.put('model_test', {'ok': True, 'tools_ok': True, 'time': 9999999999,
                                      'fingerprint': service.model_fingerprint(CFG)})
        return service

    def turn(self, service, text):
        self.store.enqueue(text, f'k{len(self.store.jobs())}')
        self.assertTrue(service.run_one())
        return self.store.jobs()[0]

    @staticmethod
    def steps(*batches):
        def script(messages):
            done = sum(1 for m in messages if m['role'] == 'assistant' and m.get('tool_calls'))
            if done >= len(batches):
                return answer('done')
            return calls(*[tool_call(name, args, f'c{done}-{index}') for index, (name, args) in enumerate(batches[done])])
        return script

    def cli(self, planned):
        refusals, wire = [], self.wire

        class Cli:
            def execute(self, engine, prompt, tools, **kwargs):
                if planned:
                    try:
                        tools.call(*planned)
                    except Exception as exc:
                        refusals.append(str(exc))
                return ExecutionResult('engine answer', engine, 0)

        service = AgentService(self.store, adapter=ModelAdapter(lambda *a, **k: answer()),
                               subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/cli', clock=lambda: 1),
                               execution_adapter=Cli())
        service.local_tools = wire
        service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        return service, refusals

    def test_api_route_without_an_engine_sends_the_request_at_once(self):
        service = self.api(self.steps([('web_search', {'query': '성남 병원'})]))
        job = self.turn(service, '성남 병원 찾아줘')
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '성남 병원'}])
        self.assertEqual(job['status'], 'succeeded')

    def test_api_route_explicit_search_still_goes_out_as_typed(self):
        service = self.api(self.steps([('web_search', {'query': '성남 병원'})]))
        job = self.turn(service, '/search 성남 병원')
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '성남 병원'}])
        self.assertEqual(job['status'], 'succeeded')

    def test_cli_route_without_an_engine_sends_the_request_at_once(self):
        service, refusals = self.cli(('web_search', {'query': '성남 병원'}))
        job = self.turn(service, '성남 병원 찾아줘')
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '성남 병원'}])
        self.assertEqual(refusals, [])
        self.assertEqual(job['status'], 'succeeded')

    def test_cli_route_host_preflight_sends_an_explicit_search_as_typed(self):
        service, _ = self.cli(None)
        job = self.turn(service, '/search 이혼소송 강남 변호사')
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '이혼소송 강남 변호사'}])
        self.assertEqual(job['status'], 'succeeded')

    SEARCH = ('web_search', {'query': f'성남 병원 {SECRET_ID}'})
    SAVE = ('save_memory', {'memory_key': 'passport', 'content': SECRET_ID})

    def test_a_value_saved_in_the_same_turn_is_redacted_deterministically(self):
        cases = {'save then search': ([self.SAVE], [self.SEARCH]), 'same batch': ([self.SEARCH, self.SAVE],)}
        for case, batches in cases.items():
            with self.subTest(case):
                self.wire.plans.clear()
                service = self.api(self.steps(*batches))
                self.turn(service, f'여권번호 {SECRET_ID} 기억해 두고 성남 병원 검색해줘')
                self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '성남 병원'}])

    def test_an_unsaved_value_the_owner_typed_goes_out_under_the_pilot_posture(self):
        """The removed judgment is not replaced by a rule: what the owner typed and did not save is sent."""
        service = self.api(self.steps([self.SEARCH]))
        self.turn(service, f'내 여권번호 {SECRET_ID}로 성남 병원 검색해줘')
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': f'성남 병원 {SECRET_ID}'}])


class BridgeWrites(unittest.TestCase):
    """N2: a CLI ``save_note`` served by the real bridge labels its Work durably."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'state')
        self.wire = Wire()

    def test_a_bridge_note_keeps_the_owner_row_out_of_a_later_lookup(self):
        wire, store = self.wire, self.store

        def bridge(job_id, name, arguments):
            lines = '\n'.join(json.dumps(r) for r in [
                {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
                {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}},
            ]) + '\n'
            with mock.patch.object(mcp_bridge, 'LocalTools', lambda: wire), \
                 mock.patch.object(sys, 'stdin', io.StringIO(lines)), contextlib.redirect_stdout(io.StringIO()):
                mcp_bridge.serve(str(store.root), job_id, [])

        class Cli:
            def execute(self, engine, prompt, tools, **kwargs):
                request = (kwargs.get('context') or {}).get('request', prompt)
                job_id = tools.capabilities.job_id
                if 'keep' in request:
                    bridge(job_id, 'save_note', {'content': f'{SECRET_ID} 병원'})
                elif '검색' in request:
                    bridge(job_id, 'web_search', {'query': f'{SECRET_ID} 병원'})
                return ExecutionResult('engine answer', engine, 0)

        service = AgentService(self.store, adapter=ModelAdapter(lambda *a, **k: answer()),
                               subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/cli', clock=lambda: 1),
                               execution_adapter=Cli())
        service.local_tools = self.wire
        service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        # An ordinary CLI Work (not the built-in /note intent) whose engine saves a note.
        for index, text in enumerate((f'please keep {SECRET_ID} 병원 for me', '병원 검색해줘')):
            self.store.enqueue(text, f'k{index}')
            self.assertTrue(service.run_one())
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'}])
        first = self.store.jobs()[-1]
        self.assertEqual(first['provider'], 'subscription', 'the note was saved by the CLI through the bridge')
        self.assertIn('personal-space', work_sources(self.store, first['id']))


if __name__ == '__main__':
    unittest.main()
