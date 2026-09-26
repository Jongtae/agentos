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
from personal_agent.agent_runtime import (lookup_words, PUBLIC_TASK_NO_JUDGMENT, PUBLIC_TASK_SEARCH_HINT, LOOKUP_JUDGMENTS_PER_WORK, ENGINE_UNMEDIATED, HISTORY_PREFIX, OWNER_CONVERSATION, PUBLIC_TASK_PLACE,
                                          PUBLIC_TASK_UNRESOLVED, WORK_SOURCES_KEY, Capabilities, egress_refusal,
                                          history_provenance, run_agent, work_sources)
from personal_agent.bounded_execution import ExecutionResult
from personal_agent.conversation_handoff import LOOKUP_WITHHOLD_QUESTION, ConversationJudgments
from personal_agent.decision import (OUTCOME_DECIDED, BinaryDecision, FixtureDecisionEngine, SelectionSetDecision,
                                     fixture_confidence)
from personal_agent.local_tools import LocalTools
from personal_agent.manifests import runtime_packages
from personal_agent.providers import ModelAdapter, ProviderError
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.subscription_engines import SubscriptionEngines

from lookup_judgment import ordinary_lookup_judgment

CFG = {'provider': 'compatible', 'endpoint': 'http://127.0.0.1:9999', 'model': 'fixture'}
PRIVATE = 'PRIVATE-XYZ'
PASSPORT = 'M1234567'
URL = 'https://example.com/pricing'


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


class DecisionTable(unittest.TestCase):
    """Table-driven source x authority x destination decisions on ``Capabilities.execute``."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'state')
        self.wire = Wire()

    def caps(self, labels=(), permitted=None, excluded=(), **kwargs):
        sources = None if permitted is None else (lambda: {'permitted': list(permitted), 'excluded': list(excluded)})
        kwargs.setdefault('public_page_scope', {URL})
        # These rows are about provenance and permitted text; the judgment is
        # (as if) configured and calls every term ordinary.
        kwargs.setdefault('lookup_sensitivity', judged_ordinary)
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


@ordinary_lookup_judgment
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


@ordinary_lookup_judgment
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


def flagging(*withheld):
    """A fixture DecisionEngine that answers the #605 lookup judgment correctly:
    it withholds exactly the listed terms (casefolded) of the term list it is shown."""
    marked = {term.casefold() for term in withheld}

    def choose_many(context, candidates, question):
        if question != LOOKUP_WITHHOLD_QUESTION:
            return None
        terms = dict(part.split(' = ', 1) for part in context.facts['terms'].split('; '))
        chosen = [label for label in candidates if terms[label].casefold() in marked]
        return SelectionSetDecision(OUTCOME_DECIDED, chosen, candidates, fixture_confidence(1.0))
    return FixtureDecisionEngine(choose_many=choose_many)


def sensitivity_asked(engine):
    return [entry for entry in engine.asked if entry[0] == 'choose_many' and entry[3] == LOOKUP_WITHHOLD_QUESTION]


def judged_ordinary(message, terms):
    """A judgment that calls every term ordinary: isolates the deterministic rules."""
    return ConversationJudgments(flagging()).lookup_term_sensitivity(message, terms)


class RoundFindings(unittest.TestCase):
    """PR #622 re-reviews @ 5e660bf (N1-N6, F3) and @ fc07521 (R1-R9): actual outbound arguments."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'state'
        self.store = QuickStore(self.path)
        self.wire = Wire()

    def caps(self, labels=(), permitted=(), excluded=(), current=None, engine=None, work=None, **kwargs):
        def sources():
            return {'permitted': list(permitted), 'excluded': list(excluded),
                    'current': current if current is not None else (list(permitted) or [''])[-1]}
        judge = ConversationJudgments(engine).lookup_term_sensitivity if engine is not None else judged_ordinary
        kwargs.setdefault('lookup_sensitivity', judge)
        return Capabilities(self.store, None, CFG, '', work or next_work(), lambda *e: None, network=self.wire,
                            inherited_provenance=set(labels), lookup_sources=sources, **kwargs)

    NOTES = (HISTORY_PREFIX + 'personal-space',)

    # -- R1/R6: reformatted current-message values are judged in the whole term list
    EXPLOITS = [
        ('여권번호 M12345678로 병원 예약 검색해줘', 'M 1234 5678 병원', ('m', '1234', '5678'), '병원'),
        ('여권번호 M12345678로 병원 예약 검색해줘', 'M-12345678 병원', ('m', '12345678'), '병원'),
        ('여권번호 M12345678로 병원 예약 검색해줘', '12345678 병원', ('12345678',), '병원'),
        ('010-1234-5678 번호로 병원 예약 검색해줘', '01012345678 병원', ('01012345678',), '병원'),
        ('여권번호 M12345678로 병원 예약 검색해줘', '엠 일이삼사오육칠팔 병원', ('엠', '일이삼사오육칠팔'), '병원'),
        ('이혼소송 때문에 강남 변호사 찾아줘', '이 혼 소 송 강남 변호사', ('이', '혼', '소', '송'), '강남 변호사'),
    ]

    def test_r1_every_reformatted_exploit_is_judged_and_withheld_in_one_call(self):
        for message, proposal, flagged, sent in self.EXPLOITS:
            with self.subTest(proposal):
                self.wire.plans.clear()
                engine = flagging(*flagged)
                self.caps((), [message], engine=engine).execute('web_search', {'query': proposal})
                self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': sent}])
                asked = sensitivity_asked(engine)
                self.assertEqual(len(asked), 1, 'one judgment per lookup')
                self.assertEqual(asked[0][1].facts['terms'].count(' = '), len(lookup_words(proposal)),
                                 'the whole outbound term list is judged')
                self.assertEqual(set(asked[0][1].facts), {'owner_message', 'terms'}, 'no history, Memory or files')

    def test_r1_an_ordinary_region_and_place_still_go_out(self):
        engine = flagging()
        self.caps((), ['성남 병원 찾아줘'], engine=engine).execute('web_search', {'query': '성남 병원'})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '성남 병원'}])
        self.assertEqual(len(sensitivity_asked(engine)), 1)

    def test_r1_the_judgment_is_cached_within_the_work_and_capped(self):
        engine = flagging()
        caps = self.caps((), ['성남 병원 찾아줘'], engine=engine)
        caps.execute('web_search', {'query': '성남 병원'})
        caps.execute('web_search', {'query': '성남 병원'})
        self.assertEqual(len(sensitivity_asked(engine)), 1, 'same message and term list: judged once')
        self.wire.plans.clear()
        many = ' '.join(f'w{index}' for index in range(20))
        caps.execute('web_search', {'query': many})
        judged = sensitivity_asked(engine)[-1][1].facts['terms'].count(' = ')
        self.assertEqual(judged, 12)
        self.assertEqual(self.wire.plans[0]['query'].split(), [f'w{index}' for index in range(12)],
                         'terms beyond the judged cap are never sent')

    def test_r1_no_judgment_when_every_word_comes_from_earlier_permitted_text(self):
        engine = flagging()
        self.caps((), ['성남에 있어', '여기 찾아줘'], engine=engine).execute('web_search', {'query': '성남'})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '성남'}])
        self.assertEqual(sensitivity_asked(engine), [])

    # -- R4: no usable judgment -> no current-message content
    def test_r4_unavailable_abstaining_or_malformed_judgment_sends_no_current_content(self):
        abstain = FixtureDecisionEngine(choose_many=lambda c, cands, q: SelectionSetDecision(
            OUTCOME_DECIDED, [], cands, fixture_confidence(0.2)))
        malformed = FixtureDecisionEngine(choose_many=lambda c, cands, q: SelectionSetDecision(
            OUTCOME_DECIDED, ['not-a-term'], cands, fixture_confidence(1.0)))
        release_unsure = FixtureDecisionEngine(choose_many=lambda c, cands, q: SelectionSetDecision(
            OUTCOME_DECIDED, [], cands, fixture_confidence(0.7)))  # P3-3: below the 0.75 binary threshold
        for name, judge, reason in (
                ('none', None, 'unavailable'),
                ('unavailable', ConversationJudgments(FixtureDecisionEngine()).lookup_term_sensitivity, 'unavailable'),
                ('abstaining', ConversationJudgments(abstain).lookup_term_sensitivity, 'uncertain'),
                ('malformed', ConversationJudgments(malformed).lookup_term_sensitivity, 'uncertain'),
                ('release-all below the binary threshold', ConversationJudgments(release_unsure).lookup_term_sensitivity, 'uncertain')):
            with self.subTest(name):
                self.wire.plans.clear()
                caps = self.caps((), [f'내 여권번호 {SECRET_ID}로 성남 병원 검색해줘'], lookup_sensitivity=judge)
                with self.assertRaises(ValueError) as raised:
                    caps.execute('web_search', {'query': f'성남 병원 {SECRET_ID}'})
                # D2: the truthful reason, not "retype it in the request".
                self.assertEqual(str(raised.exception), PUBLIC_TASK_NO_JUDGMENT[reason] + PUBLIC_TASK_SEARCH_HINT)
                self.assertEqual(self.wire.plans, [])
                # Words from earlier permitted text may still go out.
                earlier = self.caps((), ['성남에 있어', f'여권번호 {SECRET_ID} 병원 검색해줘'], lookup_sensitivity=judge)
                earlier.execute('web_search', {'query': f'성남 병원 {SECRET_ID}'})
                self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '성남'}])

    # -- R2: clean-context weather
    def test_r2_clean_weather_sends_the_transliteration_and_a_validated_country(self):
        engine = flagging()
        self.caps((), ['나는 대전에 있어. 비 와?'], engine=engine).execute('weather', {'city': 'Daejeon', 'country': 'kr'})
        self.assertEqual(self.wire.plans, [{'tool': 'weather', 'city': 'Daejeon', 'country': 'KR'}])
        self.assertIn('term-2 = KR', sensitivity_asked(engine)[0][1].facts['terms'], 'the country passes the same judgment')
        for country in ('Korea', 'ZZ', 'QX', 'K1'):
            with self.subTest(country=country):
                self.wire.plans.clear()
                self.caps((), ['나는 대전에 있어. 비 와?']).execute('weather', {'city': 'Daejeon', 'country': country})
                self.assertEqual(self.wire.plans, [{'tool': 'weather', 'city': 'Daejeon'}],
                                 'not an ISO 3166-1 alpha-2 code (P3-1): omitted')

    def test_r2_private_weather_keeps_owner_wording_only(self):
        with self.assertRaisesRegex(ValueError, '지역명은 소유자가'):
            self.caps(('connected-document',), ['나는 대전에 있어']).execute('weather', {'city': 'Daejeon', 'country': 'KR'})
        self.assertEqual(self.wire.plans, [])

    def test_r2_a_flagged_place_is_not_sent(self):
        with self.assertRaisesRegex(ValueError, '지역명은 소유자가'):
            self.caps((), ['우리집 정자동 비 와?'], engine=flagging('Jeongja')).execute('weather', {'city': 'Jeongja'})
        self.assertEqual(self.wire.plans, [])

    # -- R3: calendar drafts are private-store writes
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
                     lookup_sources=lambda: lookup_sources(QuickStore(self.path), job),
                     lookup_sensitivity=judged_ordinary).execute('web_search', {'query': f'{SECRET_ID} 병원'})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'}])

    # -- R5: the binding is rechecked after the judgment
    def test_r5_a_work_cancelled_during_the_judgment_sends_nothing(self):
        state = {'running': True}

        def sources():
            if not state['running']:
                raise ValueError('이 작업은 더 이상 실행 중이 아니어서 공개 조회를 실행하지 않았습니다.')
            return {'permitted': ['성남 병원 찾아줘'], 'excluded': [], 'current': '성남 병원 찾아줘'}

        def judge(message, terms):
            state['running'] = False  # the owner cancels while the judgment runs
            return judged_ordinary(message, terms)

        caps = Capabilities(self.store, None, CFG, '', 'job-1', lambda *e: None, network=self.wire,
                            lookup_sources=sources, lookup_sensitivity=judge)
        with self.assertRaisesRegex(ValueError, '실행 중이 아니어서'):
            caps.execute('web_search', {'query': '성남 병원'})
        self.assertEqual(self.wire.plans, [])

    # -- R7: short digit runs are not treated as pieces of a saved value
    def test_r7_a_short_number_is_not_a_piece_of_a_saved_value(self):
        self.caps(('owner-memory',), ['3일 서울 날씨 검색해줘'], [SECRET_ID]).execute('web_search', {'query': '3일 서울 날씨'})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '3일 서울 날씨'}])
        self.wire.plans.clear()
        self.caps(('owner-memory',), ['5678 서울 검색해줘'], [SECRET_ID]).execute('web_search', {'query': '5678 서울'})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '서울'}])

    # -- R8: the attempt claim is atomic across processes
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

    # -- R9: the decision audit append is safe across processes
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

    # -- round three, kept
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
                    # The judgment (wrongly) calls everything ordinary: only
                    # the exclusion can stop it.
                    self.caps(('owner-memory',), [request], [value]).execute('web_search', {'query': proposal})
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


class RoundFiveFindings(unittest.TestCase):
    """PR #622 re-review @ 6a878c1 (P2-1, P2-4, P3-2) and owner decisions D1-D3."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'state'
        self.store = QuickStore(self.path)
        self.wire = Wire()

    def caps(self, labels=(), permitted=(), excluded=(), judge=judged_ordinary, **kwargs):
        def sources():
            return {'permitted': list(permitted), 'excluded': list(excluded), 'current': list(permitted)[-1]}
        return Capabilities(self.store, None, CFG, '', next_work(), lambda *e: None, network=self.wire,
                            inherited_provenance=set(labels), lookup_sources=sources, lookup_sensitivity=judge, **kwargs)

    # -- P2-1: a clean-context query keeps its punctuation
    def test_p2_1_clean_queries_keep_the_worker_string(self):
        # Exactly what is sent under the P1-A separator policy: the ASCII
        # operator allowlist survives; the currency symbol does not.
        for query, sent in (('Python 3.13 release notes', 'Python 3.13 release notes'),
                            ('"C++20" modules site:cppreference.com', '"C++20" modules site:cppreference.com'),
                            ('node.js -deno', 'node.js -deno'),
                            ('₩50,000 이하 이어폰', '50,000 이하 이어폰')):
            with self.subTest(query):
                self.wire.plans.clear()
                self.caps((), ['검색해줘']).execute('web_search', {'query': query})
                self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': sent}])

    def test_p2_1_only_withheld_spans_are_removed(self):
        self.caps((), [f'{SECRET_ID} 가진 사람 node.js 강좌 검색해줘'],
                  judge=ConversationJudgments(flagging(SECRET_ID)).lookup_term_sensitivity).execute(
            'web_search', {'query': f'node.js -deno {SECRET_ID} "강좌"'})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': 'node.js -deno "강좌"'}])

    # -- P2-4: sticky withheld set, order-insensitive cache, per-Work cap
    def test_p2_4_a_reordered_retry_cannot_resample_the_judgment(self):
        answers = [[SECRET_ID], []]  # flags the value once, then misses it

        def choose_many(context, candidates, question):
            terms = dict(part.split(' = ', 1) for part in context.facts['terms'].split('; '))
            marked = {term.casefold() for term in answers.pop(0)} if answers else set()
            return SelectionSetDecision(OUTCOME_DECIDED, [l for l in candidates if terms[l].casefold() in marked],
                                        candidates, fixture_confidence(1.0))
        engine = FixtureDecisionEngine(choose_many=choose_many)
        caps = self.caps((), [f'여권번호 {SECRET_ID} 병원 근처 검색해줘'],
                         judge=ConversationJudgments(engine).lookup_term_sensitivity)
        caps.execute('web_search', {'query': f'{SECRET_ID} 병원'})
        caps.execute('web_search', {'query': f'병원 근처 {SECRET_ID}'})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'},
                                           {'tool': 'web_search', 'query': '병원 근처'}])

    def test_p2_4_the_cache_ignores_term_order_and_judgments_are_capped(self):
        engine = flagging()
        caps = self.caps((), ['성남 병원 약국 찾아줘'], judge=ConversationJudgments(engine).lookup_term_sensitivity)
        caps.execute('web_search', {'query': '성남 병원'})
        caps.execute('web_search', {'query': '병원 성남'})
        self.assertEqual(len(sensitivity_asked(engine)), 1, 'the same term set is judged once')
        for index in range(LOOKUP_JUDGMENTS_PER_WORK + 2):
            try:
                caps.execute('web_search', {'query': f'성남 약국 w{index}'})
            except ValueError as exc:
                self.assertEqual(str(exc), PUBLIC_TASK_NO_JUDGMENT['budget'] + PUBLIC_TASK_SEARCH_HINT)
        self.assertEqual(len(sensitivity_asked(engine)), LOOKUP_JUDGMENTS_PER_WORK)

    # -- P3-2: private-context weather city is deduplicated/ordered/capped
    def test_p3_2_private_weather_city_follows_the_private_rules(self):
        self.caps(('connected-document',), ['분당구 정자동 날씨 알려줘']).execute('weather', {'city': '정자동 분당구 정자동'})
        self.assertEqual(self.wire.plans, [{'tool': 'weather', 'city': '분당구 정자동'}])

    # -- D1: an owner-typed /search string is sent as typed
    def test_d1_the_typed_search_string_is_sent_without_the_judgment_once(self):
        typed = '이혼소송 강남 변호사 "상담 비용"'
        caps = self.caps((), [f'/search {typed}'], judge=None)  # no judgment at all
        result = caps.execute('web_search', {'query': typed})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': typed}])
        self.assertTrue(result['explicit_owner_query'])
        # The same string again is an ordinary lookup: no judgment, nothing leaves.
        with self.assertRaises(ValueError):
            caps.execute('web_search', {'query': typed})
        self.assertEqual(len(self.wire.plans), 1)

    def test_d1_rewritten_words_are_not_covered_and_saved_values_still_leave_out(self):
        rewritten = self.caps((), ['/search 이혼소송 강남 변호사'], judge=None)
        with self.assertRaises(ValueError) as raised:
            rewritten.execute('web_search', {'query': '이혼소송 강남 변호사 추천'})
        self.assertIn('민감 정보 판단', str(raised.exception))
        self.assertEqual(self.wire.plans, [])
        saved = self.caps(('owner-memory',), [f'/search {SECRET_ID} 병원'], [SECRET_ID], judge=None)
        saved.execute('web_search', {'query': f'{SECRET_ID} 병원'})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'}])


TAG_ID = ''.join(chr(0xE0000 + ord(ch)) for ch in SECRET_ID)  # invisible Unicode TAG characters


class RoundSixFindings(unittest.TestCase):
    """PR #622 re-review @ 81596b5: P1-A separator channel, P2-B glue, P3 durable state."""

    MESSAGE = f'여권번호 {SECRET_ID} 기억해 둬. 그리고 병원 검색해줘'
    SAVED = [f'여권번호 {SECRET_ID}']

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'state'
        self.store = QuickStore(self.path)
        self.wire = Wire()

    def caps(self, permitted=None, excluded=None, judge=judged_ordinary, work=None, **kwargs):
        permitted = [self.MESSAGE] if permitted is None else permitted
        excluded = self.SAVED if excluded is None else excluded

        def sources():
            return {'permitted': list(permitted), 'excluded': list(excluded), 'current': permitted[-1]}
        return Capabilities(self.store, None, CFG, '', work or next_work(), lambda *e: None, network=self.wire,
                            lookup_sources=sources, lookup_sensitivity=judge, **kwargs)

    # -- P1-A: only admissible separators leave; the final string is re-checked
    def test_p1_a_separator_channel_exploits_are_closed(self):
        cases = [
            ('invisible TAG characters after a kept word', {}, 'web_search', {'query': '병원 ' + TAG_ID},
             {'tool': 'web_search', 'query': '병원'}),
            ('TAG characters with no judgment and an earlier permitted word',
             {'permitted': ['약국 알려줘', self.MESSAGE], 'judge': None}, 'web_search', {'query': '약국 ' + TAG_ID},
             {'tool': 'web_search', 'query': '약국'}),
            ('a symbol run', {}, 'web_search', {'query': '병원 !@#$%^&*('}, {'tool': 'web_search', 'query': '병원'}),
            ('zero-width and format characters between words', {}, 'web_search',
             {'query': '병\u200b원\u2060 \u200d\ufeff검색'}, {'tool': 'web_search', 'query': '병 원 검색'}),
            ('private-use and unassigned characters', {}, 'web_search', {'query': '병원 \ue000\U000f0000\U0001fffe'},
             {'tool': 'web_search', 'query': '병원'}),
            ('weather city with TAG characters', {}, 'weather', {'city': 'Seoul' + TAG_ID, 'country': 'KR'},
             {'tool': 'weather', 'city': 'Seoul', 'country': 'KR'}),
        ]
        for case, options, action, args, sent in cases:
            with self.subTest(case):
                self.wire.plans.clear()
                self.caps(**options).execute(action, args)
                self.assertEqual(self.wire.plans, [sent])
                self.assertTrue(all(ord(ch) < 0xE0000 for ch in json.dumps(self.wire.plans, ensure_ascii=False)))

    def test_p1_a_separators_are_capped_per_separator_and_in_total(self):
        self.caps(permitted=['검색해줘']).execute('web_search', {'query': 'a.-+#:/b c(),&"d ' + ' '.join('e' * 1 + '.' + 'f' for _ in range(10))})
        sent = self.wire.plans[0]['query']
        self.assertIn('a.-+b', sent, 'at most 3 operator characters per separator')
        self.assertLessEqual(sum(1 for ch in sent if not ch.isalnum() and not ch.isspace()), 12)

    # -- P2-B: removing a word never glues its neighbours
    def test_p2_b_removal_does_not_glue_neighbours(self):
        self.caps().execute('web_search', {'query': '병원 M123-여권번호-456-여권번호-78'})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'}])
        self.wire.plans.clear()
        self.caps(permitted=['이혼 변호사 알려줘'], excluded=[],
                  judge=ConversationJudgments(flagging('zz')).lookup_term_sensitivity).execute(
            'web_search', {'query': '이-zz-혼 변호사'})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '이 혼 변호사'}])

    def test_p2_b_the_explicit_search_string_is_rechecked_too(self):
        typed = '병원 M123-여권번호-456-여권번호-78'
        self.caps(permitted=[f'/search {typed}'], judge=None).execute('web_search', {'query': typed})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'}])

    # -- P3: explicit use, judgment cap and withheld set are durable per Work
    def test_p3_state_holds_across_two_processes_of_the_same_work(self):
        typed = '성남 병원'
        first = self.caps(permitted=[f'/search {typed}'], judge=None, work='w-explicit')
        first.execute('web_search', {'query': typed})
        second = self.caps(permitted=[f'/search {typed}'], judge=None, work='w-explicit')  # another bridge
        with self.assertRaises(ValueError):
            second.execute('web_search', {'query': typed})
        self.assertEqual(len(self.wire.plans), 1, 'D1 is once per Work, not per process')

        engine = flagging()
        a = self.caps(permitted=['성남 약국 찾아줘'], excluded=[], work='w-cap',
                      judge=ConversationJudgments(engine).lookup_term_sensitivity)
        for index in range(LOOKUP_JUDGMENTS_PER_WORK):
            a.execute('web_search', {'query': f'성남 약국 a{index}'})
        b = self.caps(permitted=['성남 약국 찾아줘'], excluded=[], work='w-cap',
                      judge=ConversationJudgments(engine).lookup_term_sensitivity)
        with self.assertRaises(ValueError) as raised:
            b.execute('web_search', {'query': '성남 약국 b0'})
        self.assertIn('한도', str(raised.exception))
        self.assertEqual(len(sensitivity_asked(engine)), LOOKUP_JUDGMENTS_PER_WORK)

        self.wire.plans.clear()
        flag = self.caps(permitted=[f'{SECRET_ID} 병원 찾아줘'], excluded=[], work='w-sticky',
                         judge=ConversationJudgments(flagging(SECRET_ID)).lookup_term_sensitivity)
        flag.execute('web_search', {'query': f'{SECRET_ID} 병원'})
        miss = self.caps(permitted=[f'{SECRET_ID} 병원 찾아줘'], excluded=[], work='w-sticky',
                         judge=ConversationJudgments(flagging()).lookup_term_sensitivity)  # a judge that misses
        miss.execute('web_search', {'query': f'병원 근처 {SECRET_ID[1:5]}-{SECRET_ID[5:]}'})
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '병원'},
                                           {'tool': 'web_search', 'query': '병원 근처'}])
        stored = json.dumps(self.store.config('work_lookup_state', {}))
        self.assertIn('w-sticky', stored)
        self.assertNotIn('12345678', stored, 'only keyed digests are stored')
        self.assertNotIn('1234', stored)

    def test_a_route_without_multi_selection_says_so(self):
        from personal_agent.decision_adapters import JevDecisionEngine
        jev = ConversationJudgments(JevDecisionEngine(lambda: 'key')).lookup_term_sensitivity
        with self.assertRaises(ValueError) as raised:
            self.caps(permitted=['성남 병원 찾아줘'], excluded=[], judge=jev).execute('web_search', {'query': '성남 병원'})
        self.assertTrue(str(raised.exception).startswith(PUBLIC_TASK_NO_JUDGMENT['unsupported']))
        self.assertEqual(self.wire.plans, [])


class NoEngineEndToEnd(unittest.TestCase):
    """P2-5/D2/D3: no usable judgment, end to end, with the owner-visible text."""

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
    def searching(query):
        def script(messages):
            if messages[-1]['role'] == 'tool':
                return answer('done')
            return calls(tool_call('web_search', {'query': query}))
        return script

    def owner_visible(self, job):
        with self.store.db() as db:
            rows = [row['content'] for row in db.execute("SELECT content FROM messages WHERE job_id=? AND role='assistant'", (job['id'],))]
        return '\n'.join(rows) + '\n' + str(job.get('error') or '')

    def test_api_route_without_an_engine_tells_the_owner_why(self):
        service = self.api(self.searching('성남 병원'))
        job = self.turn(service, '성남 병원 찾아줘')
        self.assertEqual(self.wire.plans, [])
        self.assertIn(PUBLIC_TASK_NO_JUDGMENT['unavailable'], self.owner_visible(job))
        self.assertIn('설정 › 대화 해석', self.owner_visible(job))
        self.assertIn(job['status'], ('failed', 'partial'))

    def test_api_route_explicit_search_goes_out_without_an_engine(self):
        service = self.api(self.searching('성남 병원'))
        job = self.turn(service, '/search 성남 병원')
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '성남 병원'}])
        self.assertEqual(job['status'], 'succeeded')

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

    def test_cli_route_without_an_engine_refuses_with_the_truthful_text(self):
        service, refusals = self.cli(('web_search', {'query': '성남 병원'}))
        self.turn(service, '성남 병원 찾아줘')
        self.assertEqual(self.wire.plans, [])
        self.assertEqual(refusals, [PUBLIC_TASK_NO_JUDGMENT['unavailable'] + PUBLIC_TASK_SEARCH_HINT])

    def test_cli_route_host_preflight_sends_an_explicit_search_as_typed(self):
        service, _ = self.cli(None)
        job = self.turn(service, '/search 이혼소송 강남 변호사')
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '이혼소송 강남 변호사'}])
        self.assertEqual(job['status'], 'succeeded')

    def test_d3_bridge_with_a_cli_decision_route_fails_closed_with_the_truthful_text(self):
        job = self.store.enqueue('성남 병원 찾아줘', 'b1')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job,))
            db.execute('INSERT INTO messages(role,content,channel,created,workspace_id,job_id) VALUES (?,?,?,?,?,?)',
                       ('user', '성남 병원 찾아줘', 'web', 1, None, job))
        self.store.put(WORK_SOURCES_KEY, {job: [OWNER_CONVERSATION]})
        self.store.put('decision_route', {'transport': 'subscription_cli', 'engine': 'claude-code',
                                          'model_policy': 'engine_default', 'fingerprint': 'x'})
        lines = '\n'.join(json.dumps(r) for r in [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'web_search', 'arguments': {'query': '성남 병원'}}},
        ]) + '\n'
        out = io.StringIO()
        with mock.patch.object(mcp_bridge, 'LocalTools', lambda: self.wire), \
             mock.patch('personal_agent.decision_routes.DecisionRoutes._cli_engine',
                        side_effect=AssertionError('no decision CLI may run inside the bridge')), \
             mock.patch.object(sys, 'stdin', io.StringIO(lines)), contextlib.redirect_stdout(out):
            mcp_bridge.serve(str(self.store.root), job, [])
        reply = [json.loads(line) for line in out.getvalue().splitlines() if line.strip()][-1]
        self.assertEqual(self.wire.plans, [])
        self.assertTrue(reply['result']['isError'])
        self.assertEqual(reply['result']['content'][0]['text'], PUBLIC_TASK_NO_JUDGMENT['bridge'] + PUBLIC_TASK_SEARCH_HINT)


class CurrentMessageSensitivity(unittest.TestCase):
    """N3 through ``AgentService.run_one`` (direct API route) with a fixture DecisionEngine."""

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
        def script(messages):
            done = sum(1 for m in messages if m['role'] == 'assistant' and m.get('tool_calls'))
            if done >= len(batches):
                return answer('done')
            return calls(*[tool_call(name, args, f'c{done}-{index}') for index, (name, args) in enumerate(batches[done])])
        return script

    SEARCH = ('web_search', {'query': f'성남 병원 {SECRET_ID}'})
    SAVE = ('save_memory', {'memory_key': 'passport', 'content': SECRET_ID})

    def test_search_before_save_no_save_and_same_batch(self):
        cases = {'search before save': ([self.SEARCH], [self.SAVE]), 'no save': ([self.SEARCH],),
                 'same batch': ([self.SEARCH, self.SAVE],)}
        for case, batches in cases.items():
            with self.subTest(case):
                self.wire.plans.clear()
                engine = flagging(SECRET_ID)
                self.api(self.steps(*batches), engine)
                self.turn(f'여권번호 {SECRET_ID} 기억해 두고 성남 병원 검색해줘')
                self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '성남 병원'}])
                self.assertEqual(len(sensitivity_asked(engine)), 1)

    def test_ordinary_region_and_place_still_go_out(self):
        engine = flagging(SECRET_ID)
        self.api(self.steps([('web_search', {'query': '성남 병원'})]), engine)
        self.turn('성남 병원 찾아줘')
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': '성남 병원'}])
        self.assertEqual(len(sensitivity_asked(engine)), 1)

    def test_no_decision_engine_sends_no_current_message_content(self):
        self.api(self.steps([self.SEARCH]))
        self.turn(f'내 여권번호 {SECRET_ID}로 성남 병원 검색해줘')
        self.assertEqual(self.wire.plans, [])


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
