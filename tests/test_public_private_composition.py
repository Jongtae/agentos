"""AGENCY-EGRESS-01 (#605): source/destination-authorized public context composition.

Evidence class: unit and controlled local integration with fake transports.
No model, provider, network, credential or owner data is used.  Every test
asserts the *actual* outbound arguments that reached the fake public
transport (or that none did), not merely the absence of one secret sentinel.
Owner decisions on #605 (2026-09-26) define the F2/F4 cases.
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
from personal_agent.agent_runtime import (ENGINE_UNMEDIATED, HISTORY_PREFIX, OWNER_CONVERSATION, PUBLIC_TASK_PLACE,
                                          PUBLIC_TASK_UNRESOLVED, WORK_SOURCES_KEY, Capabilities, egress_refusal,
                                          history_provenance, run_agent, work_sources)
from personal_agent.bounded_execution import ExecutionResult
from personal_agent.conversation_handoff import (LOOKUP_SENSITIVE_ANY_PROPOSITION, LOOKUP_SENSITIVE_TERM_PROPOSITION,
                                                 ConversationJudgments)
from personal_agent.decision import OUTCOME_DECIDED, BinaryDecision, FixtureDecisionEngine, fixture_confidence
from personal_agent.local_tools import LocalTools
from personal_agent.manifests import runtime_packages
from personal_agent.providers import ModelAdapter, ProviderError
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.subscription_engines import SubscriptionEngines

CFG = {'provider': 'compatible', 'endpoint': 'http://127.0.0.1:9999', 'model': 'fixture'}
PRIVATE = 'PRIVATE-XYZ'
PASSPORT = 'M1234567'
URL = 'https://example.com/pricing'


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


class DecisionTable(unittest.TestCase):
    """Table-driven source x authority x destination decisions on ``Capabilities.execute``."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'state')
        self.wire = Wire()

    def caps(self, labels=(), permitted=None, excluded=(), **kwargs):
        sources = None if permitted is None else (lambda: {'permitted': list(permitted), 'excluded': list(excluded)})
        kwargs.setdefault('public_page_scope', {URL})
        return Capabilities(self.store, None, CFG, '', 'job-1', lambda *e: None, network=self.wire,
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

    def api(self, script):
        self.service = AgentService(self.store, adapter=ModelAdapter(lambda url, body, *a, **k: script(body['messages'])))
        self.service.local_tools = self.wire
        self.store.put('model', CFG)
        self.store.put('model_test', {'ok': True, 'tools_ok': True, 'time': 9999999999,
                                      'fingerprint': self.service.model_fingerprint(CFG)})

    def cli(self, script):
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

    def test_rollback_restrictive_mode_refuses(self):
        self.api(self.worker(lambda request, prior: '병원'))
        self.store.put('egress_composition', {'mode': 'restrictive'})
        self.turns('hello', '병원 검색해줘')
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
    """One small integration test through the real stdio bridge ``serve`` loop."""

    def serve(self, record, query, message='search today news'):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        store = QuickStore(Path(tmp.name) / 'state')
        job = store.enqueue(message, 'k1')
        with store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job,))
            db.execute('INSERT INTO messages(role,content,channel,created,workspace_id,job_id) VALUES (?,?,?,?,?,?)',
                       ('user', message, 'web', 1, None, job))
        store.put(WORK_SOURCES_KEY, {job: record})
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


SECRET_ID = 'M12345678'


def sensitivity_engine(sensitive=(SECRET_ID,)):
    """A fixture DecisionEngine: a term is sensitive exactly when listed here."""
    marked = {term.casefold() for term in sensitive}

    def judge(context, proposition):
        if proposition == LOOKUP_SENSITIVE_ANY_PROPOSITION:
            terms = [part.split(' = ', 1)[1] for part in context.facts['terms'].split('; ')]
            answer = any(term.casefold() in marked for term in terms)
        elif proposition == LOOKUP_SENSITIVE_TERM_PROPOSITION:
            answer = context.facts['term'].casefold() in marked
        else:
            return None
        return BinaryDecision(OUTCOME_DECIDED, answer, fixture_confidence(1.0))
    return FixtureDecisionEngine(judge=judge)


def sensitivity_asked(engine):
    return [entry for entry in engine.asked if entry[0] == 'judge' and entry[2] in
            (LOOKUP_SENSITIVE_ANY_PROPOSITION, LOOKUP_SENSITIVE_TERM_PROPOSITION)]


def judged_ordinary(message, terms):
    """A (wrong) judgment that calls every term ordinary: isolates the deterministic exclusion."""
    return ConversationJudgments(sensitivity_engine(())).lookup_term_sensitivity(message, terms)


class RoundThreeFindings(unittest.TestCase):
    """PR #622 scoped re-review @ 5e660bf, findings N1-N6 and F3 (actual outbound arguments)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'state')
        self.wire = Wire()

    def caps(self, labels=(), permitted=(), excluded=(), current=None, record=None, **kwargs):
        def sources():
            return {'permitted': list(permitted), 'excluded': list(excluded),
                    'current': current if current is not None else (list(permitted) or [''])[-1]}
        return Capabilities(self.store, None, CFG, '', 'job-1', record or (lambda *e: None), network=self.wire,
                            inherited_provenance=set(labels), lookup_sources=sources, **kwargs)

    NOTES = (HISTORY_PREFIX + 'personal-space',)

    def test_n1_a_word_extending_a_permitted_word_sends_only_the_permitted_word(self):
        for proposal in ('병원이혼 병원소송 근처우울', '병원ab 병원cd'):
            with self.subTest(proposal):
                self.wire.plans.clear()
                self.caps(self.NOTES, ['병원 찾아줘']).execute('web_search', {'query': proposal})
                self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'}])

    def test_n4_a_reformatted_saved_value_is_excluded_in_every_spelling(self):
        saved = {'M12345678': ['M1234-5678 병원', 'M1234 5678 병원', 'm12345678 병원', 'Ｍ１２３４５６７８ 병원', '5678 병원'],
                 'M1234-5678': ['M12345678 병원', 'm1234 병원']}
        for value, proposals in saved.items():
            for proposal in proposals:
                with self.subTest(saved=value, proposal=proposal):
                    self.wire.plans.clear()
                    request = f'여권 {proposal} 기억해 두고 병원 검색해줘'
                    # The request itself carries the value, and the judgment is
                    # (wrongly) "ordinary": only the exclusion can stop it.
                    self.caps(('owner-memory',), [request], [value],
                              lookup_sensitivity=judged_ordinary).execute('web_search', {'query': proposal})
                    self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'}])

    def test_n5_words_are_deduplicated_ordered_by_permitted_text_and_capped(self):
        earlier, current = '성남에 있어', '여기 병원 찾아줘 내과 소아과 치과 안과 피부과 정형외과 한의원'
        caps = self.caps(self.NOTES, [earlier, current])
        caps.execute('web_search', {'query': '한의원 병원 성남 병원 성남 치과 안과 내과 소아과 피부과 정형외과'})
        sent = self.wire.plans[0]['query'].split()
        self.assertEqual(sent, ['성남', '병원', '내과', '소아과', '치과', '안과', '피부과', '정형외과'])
        self.assertEqual(len(set(sent)), len(sent))

    def test_n6_weather_needs_the_owner_wording_in_a_clean_context_too(self):
        clean = self.caps((), ['나는 대전에 있어. 비 와?'])
        with self.assertRaisesRegex(ValueError, '지역명은 소유자가'):
            clean.execute('weather', {'city': 'Daejeon', 'country': 'KR'})
        self.assertEqual(self.wire.plans, [])
        clean.execute('weather', {'city': '대전', 'country': 'KR'})
        self.assertEqual(self.wire.plans, [{'tool': 'weather', 'city': '대전'}])

    def test_f3_the_attempt_is_durable_across_a_restarted_bridge(self):
        def record(tool, status, detail):
            with self.store.db() as db:
                db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                           ('job-1', tool, status, detail, 1))
        self.wire.fail = True
        with self.assertRaises((ValueError, ProviderError)):
            self.caps(self.NOTES, ['병원 뉴스'], record=record).execute('web_search', {'query': '병원'})
        self.wire.fail = False
        restarted = self.caps(self.NOTES, ['병원 뉴스'], record=record)  # a new process: empty memo
        with self.assertRaisesRegex(ValueError, '이미 한 번 시도'):
            restarted.execute('web_search', {'query': '뉴스'})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'}])
        with self.store.db() as db:
            row = db.execute("SELECT detail FROM tool_events WHERE status='requested'").fetchone()
        self.assertEqual(json.loads(row[0])['composed_by'], 'agentos-public-task')


class CurrentMessageSensitivity(unittest.TestCase):
    """N3 and the owner decision: the existing DecisionEngine judges which words of
    the owner's current message are sensitive, on every lookup that includes them."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'state')
        self.wire = Wire()

    def api(self, script, engine=None):
        self.service = AgentService(self.store, adapter=ModelAdapter(lambda url, body, *a, **k: script(body['messages'])))
        self.service.local_tools = self.wire
        if engine is not None:
            self.service.use_decision_engine(engine)
        self.store.put('model', CFG)
        self.store.put('model_test', {'ok': True, 'tools_ok': True, 'time': 9999999999,
                                      'fingerprint': self.service.model_fingerprint(CFG)})

    def turn(self, text):
        self.store.enqueue(text, f'k{len(self.store.jobs())}')
        self.assertTrue(self.service.run_one())

    @staticmethod
    def steps(*batches):
        """A worker that runs ``batches`` (lists of tool calls) one model step each, then answers."""
        def script(messages):
            done = sum(1 for m in messages if m['role'] == 'assistant' and m.get('tool_calls'))
            if done >= len(batches):
                return answer('done')
            return calls(*[tool_call(name, args, f'c{done}-{index}') for index, (name, args) in enumerate(batches[done])])
        return script

    SEARCH = ('web_search', {'query': f'성남 병원 {SECRET_ID}'})
    SAVE = ('save_memory', {'memory_key': 'passport', 'content': SECRET_ID})

    def test_search_before_save_in_a_later_step(self):
        engine = sensitivity_engine()
        self.api(self.steps([self.SEARCH], [self.SAVE]), engine)
        self.turn(f'여권번호 {SECRET_ID} 기억해 두고 성남 병원 검색해줘')
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '성남 병원'}])

    def test_no_save_at_all(self):
        engine = sensitivity_engine()
        self.api(self.steps([self.SEARCH]), engine)
        self.turn(f'내 여권번호 {SECRET_ID}로 성남 병원 예약하는 법 검색해줘')
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '성남 병원'}])
        asked = sensitivity_asked(engine)
        self.assertEqual(set(asked[0][1].facts), {'owner_message', 'terms'}, 'no history, Memory or files')

    def test_same_batch_search_first(self):
        engine = sensitivity_engine()
        self.api(self.steps([self.SEARCH, self.SAVE]), engine)
        self.turn(f'여권번호 {SECRET_ID} 기억해 두고 성남 병원 검색해줘')
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '성남 병원'}])

    def test_ordinary_region_and_place_still_go_out(self):
        """The opposing case: "성남 병원" is judged ordinary and is sent."""
        engine = sensitivity_engine()
        self.api(self.steps([('web_search', {'query': '성남 병원'})]), engine)
        self.turn('성남 병원 찾아줘')
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '성남 병원'}])
        self.assertTrue(sensitivity_asked(engine), 'asked because the lookup includes the current message')

    def test_the_judgment_is_not_asked_when_no_current_words_leave(self):
        engine = sensitivity_engine()
        self.api(self.steps([('web_search', {'query': 'today news'})]), engine)
        self.turn('오늘 소식 검색해줘')
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': 'today news'}])
        self.assertEqual(sensitivity_asked(engine), [])

    def test_unavailable_or_abstaining_judgment_fails_safe(self):
        abstain = FixtureDecisionEngine(judge=lambda context, proposition: BinaryDecision(
            OUTCOME_DECIDED, False, fixture_confidence(0.2)))
        for engine in (None, abstain):
            with self.subTest(engine=engine):
                self.wire.plans.clear()
                self.api(self.steps([self.SEARCH]), engine)
                self.turn(f'내 여권번호 {SECRET_ID}로 성남 병원 예약하는 법 검색해줘')
                self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '성남 병원'}],
                                 'the value is withheld; ordinary words still go out')


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
                mcp_bridge.serve(str(store.root), job_id, [], judge=judged_ordinary)

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
