"""EGRESS-OPEN-01 (#826): the per-Work information-use audit and the invariants kept beside the opened egress.

Owner decision (2026-09-28): owner-private reads and web search may share a
Work; in exchange every Work shows which owner information it used and where
it went.  The audit is derived from AgentOS's own records (turn provenance,
tool events, decision audit), stores references and short labels, never
payloads, and passes the stored-secret redaction.

Evidence class: unit and controlled local integration with injected model and
CLI transports, fake public networks and temporary stores.  No model,
provider, network, credential or owner data is used.
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from personal_agent import information_use, mcp_bridge
from personal_agent.bounded_execution import CLI_PROFILES, BOUNDED_PROFILE, ExecutionResult
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.subscription_engines import SubscriptionEngines

CFG = {'provider': 'compatible', 'endpoint': 'http://127.0.0.1:9999', 'model': 'fixture'}
STORED_SECRET = 'LEAKYSECRET0826VALUE'
MEMORY_VALUE = '합정 분짜집 비밀메뉴'
FILE_TEXT = '프로젝트 오로라 예산 4200'
PROFILE_VALUE = '땅콩 알레르기'


class Wire:
    def __init__(self):
        self.plans = []

    def execute(self, plan):
        self.plans.append(dict(plan))
        return {'tool': plan['tool'], 'results': [{'url': 'https://example.org/a', 'title': 'a'}],
                'sources': ['https://example.org/a'], 'retrieved_at': 1}


def tool_call(name, arguments, ident):
    return {'id': ident, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments, ensure_ascii=False)}}


def steps(*batches, final='done'):
    def script(messages):
        done = sum(1 for m in messages if m['role'] == 'assistant' and m.get('tool_calls'))
        if done >= len(batches):
            return {'choices': [{'message': {'content': final}}]}
        return {'choices': [{'message': {'content': None, 'tool_calls': [
            tool_call(name, args, f'c{done}-{index}') for index, (name, args) in enumerate(batches[done])]}}]}
    return script


class SectionReferences(unittest.TestCase):
    """What the owner-model sections of a turn referred to: keys, refs and labels, never values."""

    def test_keys_refs_and_labels_are_read_from_the_rendered_sections(self):
        profile = 'profile.allergy: 땅콩 (saved 2026-09-01)\nprofile.place.home: 성남 (saved 2026-09-02)'
        context = ('Refs are opaque.\n' + json.dumps({'local_time': '2026-09-28T12:00+09:00 Mon', 'timezone': 'Asia/Seoul',
                   'hypotheses': [{'ref': 'state:1', 'predicate': 'work_mode', 'value': 'remote'}],
                   'anchors': [{'ref': 'profile:home', 'label': '집'}]}, ensure_ascii=False))
        prepared = 'Prepared for you.\n' + json.dumps({'items': [{'ref': 'prep:9', 'answer': 'secret answer text'}]})
        refs = information_use.section_references(profile, context, prepared,
                                                  [{'kind': '파일', 'ref': 'a.md', 'label': 'a.md', 'content': FILE_TEXT}])
        self.assertEqual(refs['profile_keys'], ['profile.allergy', 'profile.place.home'])
        self.assertEqual([row['label'] for row in refs['current_context']], ['현재 시각 (Asia/Seoul)', 'work_mode', '장소: 집'])
        self.assertEqual(refs['prepared'], ['prep:9'])
        self.assertEqual(refs['spliced'], [{'kind': '파일', 'ref': 'a.md', 'label': 'a.md'}])
        rendered = json.dumps(refs, ensure_ascii=False)
        for value in ('땅콩', '성남', 'remote', 'secret answer text', FILE_TEXT):
            self.assertNotIn(value, rendered, 'values never enter the references')

    def test_malformed_sections_give_empty_references(self):
        self.assertEqual(information_use.section_references('not a profile', 'legend only', '{broken'),
                         {'profile_keys': [], 'current_context': [], 'prepared': [], 'spliced': []})


class RecordsOnly(unittest.TestCase):
    """The audit reads only AgentOS's records: an attempted lookup that failed is still listed."""

    def test_a_failed_lookup_is_listed_as_attempted_with_the_query_it_started_with(self):
        with tempfile.TemporaryDirectory() as folder:
            store = QuickStore(Path(folder) / 'state')
            job = store.enqueue('검색', 'records-only')
            with store.db() as db:
                for status, detail in (('running', {'call_id': 'c1', 'host_action': 'web_search',
                                                    'arguments': {'query': f'병원 {STORED_SECRET}'}}),
                                       ('failed', {'call_id': 'c1', 'host_action': 'web_search', 'code': 'provider_error'})):
                    db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                               (job, 'web_search', status, json.dumps(detail), 1))
            audit = information_use.work_information_use(store, job, redact=lambda text: text.replace(STORED_SECRET, '[redacted]'))
            [lookup] = audit['sent_to']['lookups']
            self.assertEqual((lookup['status'], lookup['queries']), ('failed', ['병원 [redacted]']))
            self.assertFalse(audit['recorded'], 'no turn record: said, not invented')
            self.assertIn('웹 조회(AgentOS · 실패): "병원 [redacted]"', information_use.render_korean(audit))
            self.assertIsNone(information_use.work_information_use(store, 'no-such-work'))

    def events(self, store, job, rows):
        with store.db() as db:
            for tool, status, detail in rows:
                db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                           (job, tool, status, json.dumps(detail), 1))

    def test_source_urls_and_the_provider_pass_the_redaction(self):
        """#826 review P1: a secret literal in a result URL never reaches the audit."""
        with tempfile.TemporaryDirectory() as folder:
            store = QuickStore(Path(folder) / 'state')
            job = store.enqueue('검색', 'records-urls')
            self.events(store, job, [('web_search', 'succeeded', {'host_action': 'web_search', 'evidence': {
                'sources': [f'https://example.org/?token={STORED_SECRET}'], 'result_count': 1, 'provider': 'brave',
                'composed_by': 'agentos-public-task', 'sent': {'query': '병원'}}})])
            audit = information_use.work_information_use(store, job, redact=lambda text: text.replace(STORED_SECRET, '[redacted]'))
            self.assertNotIn(STORED_SECRET, json.dumps(audit, ensure_ascii=False))
            self.assertEqual(audit['sent_to']['lookups'][0]['sources'], ['https://example.org/?token=[redacted]'])

    def test_a_failed_preflight_query_is_recovered_from_its_running_event(self):
        """#826 review P2: the /search preflight records its query in the running event; its success
        records ``sent`` in the Evidence."""
        with tempfile.TemporaryDirectory() as folder:
            store = QuickStore(Path(folder) / 'state')
            job = store.enqueue('/search 서울 날씨', 'records-preflight')
            self.events(store, job, [
                ('web_search', 'running', {'scope': 'subscription-preflight', 'query': '서울 날씨'}),
                ('web_search', 'failed', {'scope': 'subscription-preflight', 'error': 'offline'}),
                ('web_search', 'running', {'call_id': 'c2', 'host_action': 'web_search',
                                           'arguments': {'query': '병원 token=abcdefgh12345678'}}),
                ('web_search', 'succeeded', {'call_id': 'c2', 'host_action': 'web_search',
                                             'evidence': {'sent': {'query': '병원'}, 'result_count': 0}}),
                ('web_search', 'running', {'call_id': 'c3', 'host_action': 'web_search', 'arguments': {'query': 'raw words'}}),
                ('web_search', 'succeeded', {'call_id': 'c3', 'host_action': 'web_search', 'evidence': {'result_count': 0}})])
            lookups = information_use.work_information_use(store, job)['sent_to']['lookups']
            self.assertEqual([(row['status'], row['queries']) for row in lookups],
                             [('failed', ['서울 날씨']), ('succeeded', ['병원']), ('succeeded', [])],
                             'a success shows what its Evidence says left, never the worker\'s raw arguments')


class _ServiceBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = QuickStore(self.root / 'state')
        self.wire = Wire()
        self.folder = self.root / 'docs'
        self.folder.mkdir()
        self.file_name = f'plan-{STORED_SECRET}.txt'
        (self.folder / self.file_name).write_text(FILE_TEXT, encoding='utf-8')
        self.store.secret('model_key', STORED_SECRET)

    def seed_owner(self, service):
        service.save_roots({'paths': [str(self.folder)]})
        service.memory_profile_request({'operation': 'remember', 'memory_key': 'profile.allergy', 'content': PROFILE_VALUE})
        self.store.save_memory('favorite-place', MEMORY_VALUE)

    def turn(self, service, text):
        job = self.store.enqueue(text, f'k{len(self.store.jobs())}')
        self.assertTrue(service.run_one())
        return job


class ApiRouteAudit(_ServiceBase):
    """A direct-API Work that read Memory and a file and searched the web: the audit lists each use."""

    def service(self, script):
        service = AgentService(self.store, adapter=ModelAdapter(lambda url, body, *a, **k: script(body['messages'])))
        service.local_tools = self.wire
        self.store.put('model', CFG)
        self.store.put('model_test', {'ok': True, 'tools_ok': True, 'time': 9999999999,
                                      'fingerprint': service.model_fingerprint(CFG)})
        return service

    def run_mixed_work(self):
        root_id = None
        service = self.service(lambda messages: {'choices': [{'message': {'content': 'hi'}}]})
        self.seed_owner(service)
        self.turn(service, '안녕')
        root_id = self.store.config('file_roots')[0]['id']
        service = self.service(steps([('list_memory', {}), ('read_file', {'root_id': root_id, 'path': self.file_name})],
                                     [('web_search', {'query': f'{MEMORY_VALUE} 땅콩 없는 메뉴'})]))
        job = self.turn(service, '저장한 맛집이랑 문서 보고 웹에서도 찾아줘')
        return service, job

    def test_the_audit_lists_what_was_used_where_it_went_and_what_came_back(self):
        service, job = self.run_mixed_work()
        # The owner decision: the private value went out in the query, in the same Work as the reads.
        self.assertEqual(self.wire.plans, [{'tool': 'web_search', 'query': f'{MEMORY_VALUE} 땅콩 없는 메뉴'}])
        audit = service.work_information_use(job)
        used = {row['category']: row['items'] for row in audit['used']}
        self.assertEqual(used['profile'], ['profile.allergy'])
        self.assertEqual(used['memory'], ['favorite-place', 'profile.allergy'])
        self.assertEqual(used['files'], ['plan-[redacted].txt'])
        self.assertIn('현재 시각', used['current_context'][0])
        self.assertEqual(audit['conversation_turns'], 2, 'the earlier greeting and its answer')
        [worker] = audit['sent_to']['workers']
        self.assertEqual((worker['route'], worker['provider'], worker['model']), ('direct-api', 'compatible', 'fixture'))
        self.assertTrue(audit['sent_to']['web_search_ran'])
        [lookup] = audit['sent_to']['lookups']
        self.assertEqual(lookup['queries'], [f'{MEMORY_VALUE} 땅콩 없는 메뉴'])
        self.assertFalse(lookup['cli_own_search'])
        results = {row['tool']: row for row in audit['results'] if row['status'] == 'succeeded'}
        self.assertEqual(set(results), {'list_memory', 'read_file', 'web_search'})
        self.assertEqual(results['web_search']['label'], '결과 1개, 출처 1개')
        self.assertEqual(audit['evidence_class'], information_use.EVIDENCE_CLASS)

    def test_the_audit_stores_references_not_payloads_and_never_a_secret(self):
        service, job = self.run_mixed_work()
        audit = json.dumps(service.work_information_use(job), ensure_ascii=False)
        for payload in (FILE_TEXT, PROFILE_VALUE, STORED_SECRET):
            self.assertNotIn(payload, audit)
        record = json.dumps(self.store.turn_provenance(job), ensure_ascii=False)
        self.assertNotIn(STORED_SECRET, record)
        self.assertNotIn(PROFILE_VALUE, json.dumps(self.store.turn_provenance(job)['owner_information'], ensure_ascii=False))
        # The Evidence rows the audit reads hold keys and paths, never the file text or Memory values.
        with self.store.db() as db:
            details = ' '.join(row['detail'] for row in db.execute('SELECT detail FROM tool_events WHERE job_id=?', (job,)))
        self.assertNotIn(FILE_TEXT, details)
        self.assertNotIn(PROFILE_VALUE, details)

    def test_the_task_detail_carries_the_audit(self):
        service, job = self.run_mixed_work()
        selected = service.task_progress(job)['selected']
        self.assertEqual(selected['information_use']['work_id'], job)
        self.assertNotIn('information_use', service.task_progress()['tasks'][0], 'only the detail view reads it')

    def test_in_conversation_the_worker_reads_the_audit_through_its_tool(self):
        """"이 답변에 뭘 썼어?": the worker calls information_use; no keyword route decides it (C16)."""
        service, first = self.run_mixed_work()
        service = self.service(steps([('information_use', {})], final='relayed'))
        second = self.turn(service, '이 답변에 뭘 썼어?')
        record = self.store.turn_provenance(second)
        self.assertIn('information_use', record['exposed_tools'])
        [event] = [row for row in self.store.task_events(second) if row['tool'] == 'information_use' and row['status'] == 'succeeded']
        self.assertEqual(event['trace']['evidence']['work_id'], first)
        self.assertEqual(event['trace']['evidence']['lookup_count'], 1)
        self.assertIn('profile', event['trace']['evidence']['categories'])
        self.assertNotIn(MEMORY_VALUE, json.dumps(event['trace'], ensure_ascii=False), 'categories and a count, never items')
        # #826 review P1: this Work's own audit says it read the earlier Work's record.
        used = {row['category']: row['items'] for row in service.work_information_use(second)['used']}
        self.assertEqual(len(used['records']), 1)
        self.assertTrue(used['records'][0].startswith(f'작업 {first[:12]}'))
        self.assertIn('프로필', used['records'][0])
        self.assertIn('웹 조회 1건', used['records'][0])
        reply = service.information_use_tool(self.store.job(second))({})
        self.assertEqual(reply['work_id'], first)
        self.assertTrue(reply['response'].startswith('이 답변에 쓴 정보'))
        self.assertIn(f'"{MEMORY_VALUE} 땅콩 없는 메뉴"', reply['response'])
        self.assertIn('profile.allergy', reply['response'])
        self.assertNotIn(STORED_SECRET, reply['response'])
        with self.assertRaises(ValueError):
            service.information_use_tool(self.store.job(second))({'work': 'no-such-work'})


class CliRouteAudit(_ServiceBase):
    """A trusted-local CLI Work: the CLI's own reported searches and bridge reads are in the audit."""

    def service(self, before=None, meta=None):
        test = self

        class Cli:
            def execute(self, engine, prompt, tools, **kwargs):
                test.offered = sorted(tools._offered())
                test.native = tools.native_search
                if before:
                    before(tools)
                return ExecutionResult('cli answer', engine, 0, meta or {})

        service = AgentService(self.store, adapter=ModelAdapter(lambda *a, **k: {'choices': [{'message': {'content': 'x'}}]}),
                               subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/cli', clock=lambda: 1),
                               execution_adapter=Cli())
        service.local_tools = self.wire
        service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        return service

    def test_a_cli_work_with_private_reads_and_its_own_search_is_audited(self):
        def bridge_reads(tools):
            # What the real bridge records for a CLI-chosen private read (mcp_bridge.serve).
            tools.capabilities.record('list_notes', 'succeeded', json.dumps(
                {'scope': 'subscription-mcp-bridge', 'host_action': 'list_notes', 'evidence': {'note_count': 2}}))
            tools.capabilities.record('read_file', 'succeeded', json.dumps(
                {'scope': 'subscription-mcp-bridge', 'host_action': 'read_file',
                 'evidence': {'root_id': 'r', 'path': self.file_name, 'characters': 12}}))
        meta = {'native_searches': [{'id': 'ws_1', 'state': 'succeeded', 'queries': [f'{MEMORY_VALUE} 메뉴'],
                                     'results': [{'url': 'https://example.org/menu', 'title': 'menu'}]}]}
        service = self.service(bridge_reads, meta)
        self.seed_owner(service)
        job = self.turn(service, '메모와 문서 보고 웹에서도 찾아줘')
        self.assertTrue(self.native, 'the CLI\'s own search is on')
        for name in ('list_notes', 'list_memory', 'find_files', 'read_file', 'information_use'):
            self.assertIn(name, self.offered)
        audit = service.work_information_use(job)
        used = {row['category']: row['items'] for row in audit['used']}
        self.assertEqual(used['notes'], ['메모 2개'])
        self.assertEqual(used['files'], ['plan-[redacted].txt'])
        self.assertEqual(used['profile'], ['profile.allergy'])
        [worker] = audit['sent_to']['workers']
        self.assertEqual((worker['route'], worker['engine'], worker['own_web_search']), ('subscription', 'codex', True))
        [lookup] = audit['sent_to']['lookups']
        self.assertTrue(lookup['cli_own_search'])
        self.assertEqual(lookup['queries'], [f'{MEMORY_VALUE} 메뉴'])
        self.assertEqual(lookup['sources'], ['https://example.org/menu'])
        text = information_use.render_korean(audit)
        self.assertIn('웹 조회(CLI 자체 검색): "합정 분짜집 비밀메뉴 메뉴"', text)
        self.assertIn('codex', text)

    def test_the_cli_worker_reads_the_audit_through_the_relayed_tool(self):
        service = self.service()
        first = self.turn(service, '안녕')
        seen = {}
        service = self.service(lambda tools: seen.update(reply=tools.call('information_use', {})))
        self.turn(service, '방금 답변에 뭘 썼어?')
        self.assertEqual(seen['reply']['work_id'], first)
        self.assertIn('보낸 곳', seen['reply']['response'])


class ApiEndpoint(unittest.TestCase):
    """GET /api/tasks/<id>/information-use through the shipped handler."""

    def test_the_endpoint_returns_the_audit_and_refuses_an_unknown_work(self):
        from test_pa1_memory_candidate_owner_path import _OwnerSurface

        class Surface(_OwnerSurface):
            def runTest(self):
                pass
        surface = Surface()
        surface.setUp()
        self.addCleanup(surface.doCleanups)
        job = surface.ask('안녕하세요')
        audit = surface.web('/api/tasks/' + job + '/information-use')
        self.assertEqual(audit['work_id'], job)
        self.assertTrue(audit['recorded'])
        self.assertEqual(audit['sent_to']['workers'][0]['route'], 'direct-api')
        self.assertEqual(surface.web('/api/tasks/' + job)['selected']['information_use']['work_id'], job)
        status, _detail = surface.refused('/api/tasks/no-such-work/information-use')
        self.assertEqual(status, 404)


class FolderGrantsStayEnforced(unittest.TestCase):
    """#826 offers the document tools on the trusted-local CLI; the folder grant still bounds them."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.store = QuickStore(root / 'state')
        self.granted = root / 'granted'
        self.granted.mkdir()
        (self.granted / 'ok.txt').write_text('granted text', encoding='utf-8')
        self.outside = root / 'outside'
        self.outside.mkdir()
        (self.outside / 'secret.txt').write_text('outside text', encoding='utf-8')
        AgentService(self.store).save_roots({'paths': [str(self.granted)]})
        self.root_id = self.store.config('file_roots')[0]['id']
        self.job = self.store.enqueue('문서', 'grant')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (self.job,))

    def serve(self, *calls):
        requests = [{'jsonrpc': '2.0', 'id': 0, 'method': 'initialize', 'params': {}},
                    {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}]
        requests += [{'jsonrpc': '2.0', 'id': index + 2, 'method': 'tools/call', 'params': {'name': name, 'arguments': args}}
                     for index, (name, args) in enumerate(calls)]
        out = io.StringIO()
        with mock.patch.object(sys, 'stdin', io.StringIO(''.join(json.dumps(r) + '\n' for r in requests))), \
                contextlib.redirect_stdout(out):
            mcp_bridge.serve(str(self.store.root), self.job, native_search=True)
        return {reply['id']: reply for reply in map(json.loads, out.getvalue().splitlines())}

    @staticmethod
    def refused(reply):
        return 'error' in reply or bool((reply.get('result') or {}).get('isError'))

    def test_reads_inside_the_grant_work_and_everything_else_is_refused(self):
        replies = self.serve(('read_file', {'root_id': self.root_id, 'path': 'ok.txt'}),
                             ('read_file', {'root_id': self.root_id, 'path': '../outside/secret.txt'}),
                             ('read_file', {'root_id': 'not-a-grant', 'path': 'secret.txt'}),
                             ('read_file', {'root_id': self.root_id, 'path': str(self.outside / 'secret.txt')}),
                             ('read_file', {'root_id': self.root_id, 'path': '../state/private/quickstart.db'}),
                             ('find_files', {'query': 'outside'}))
        self.assertIn('granted text', replies[2]['result']['content'][0]['text'])
        for ident in (3, 4, 5, 6):
            with self.subTest(call=ident):
                self.assertTrue(self.refused(replies[ident]))
                self.assertNotIn('outside text', json.dumps(replies[ident], ensure_ascii=False))
        found = json.loads(replies[7]['result']['content'][0]['text'])
        self.assertEqual(found['files'], [], 'a search never reaches outside the granted folder')

    def test_a_read_grant_implies_no_write_delete_move_or_send_tool(self):
        replies = self.serve()
        names = {tool['name'] for tool in replies[1]['result']['tools']}
        self.assertTrue({'find_files', 'read_file', 'list_roots'} <= names)
        declared = set(CLI_PROFILES[BOUNDED_PROFILE]['actions'])
        for forbidden in ('write_file', 'delete_file', 'move_file', 'send_file', 'send_message', 'shell'):
            self.assertNotIn(forbidden, names)
            self.assertNotIn(forbidden, declared)
        annotations = {tool['name']: tool.get('annotations', {}) for tool in replies[1]['result']['tools']}
        for name in ('find_files', 'read_file', 'list_roots', 'public_page_read'):
            self.assertTrue(annotations[name].get('readOnlyHint'), name)

    def test_a_revoked_grant_refuses_the_next_read(self):
        AgentService(self.store).save_roots({'paths': []})
        replies = self.serve(('read_file', {'root_id': self.root_id, 'path': 'ok.txt'}), ('list_roots', {}))
        self.assertTrue(self.refused(replies[2]))
        self.assertEqual(json.loads(replies[3]['result']['content'][0]['text']), {'roots': []})


class GovernanceRecords(unittest.TestCase):
    """The removed rules stay removed, and the governance records say so."""

    ROOT = Path(__file__).resolve().parents[1]

    def test_the_census_marks_every_g_row_removed_by_the_owner_decision(self):
        census = (self.ROOT / 'docs' / 'request-path-rule-census.en.md').read_text(encoding='utf-8')
        for row in ('A6', 'A7', 'A8', 'A10', 'A12', 'A13', 'A14', 'A16'):
            line = next(line for line in census.splitlines() if line.startswith(f'| {row} |'))
            self.assertIn('Removed (owner decision #826)', line, row)

    def test_agents_md_records_the_owner_decision(self):
        agents = (self.ROOT / 'AGENTS.md').read_text(encoding='utf-8')
        self.assertIn('#826', agents)
        self.assertIn('2026-09-28', agents)

    def test_the_web_ui_shows_the_section_from_the_task_detail(self):
        app = (self.ROOT / 'src' / 'personal_agent' / 'web' / 'app.js').read_text(encoding='utf-8')
        self.assertIn("traceDisclosure(task,'information',t('이 답변에 쓴 정보')", app)


if __name__ == '__main__':
    unittest.main()


from test_orchestrator import Harness, plan  # noqa: E402


class JudgmentSeesOwnerValues(Harness):
    """#826 follow-up: the owner's Judgment AI sees the Work's saved values; stored secrets stay masked."""

    def test_a_saved_value_reaches_the_outcome_judgment_and_a_secret_does_not(self):
        self.store.secret('telegram_token', STORED_SECRET)

        def save(tools):
            tools.call('save_memory', {'memory_key': 'profile.work', 'content': '판교 사무실'})
        self.engine.before = save
        self.engine.answers = [f'판교 사무실 근처 분짜 집을 추천해요. {STORED_SECRET}']
        self.script([plan('codex', 'Answer.')], goals=[True])
        job, row = self.run_work('회사 근처 점심 추천해줘')
        self.assertEqual(row['status'], 'succeeded')
        with self.store.db() as db:
            pending = [r['content'] for r in db.execute("SELECT content FROM memory_candidates WHERE state='pending'")]
        self.assertEqual(pending, ['판교 사무실'], 'the value is a value this Work saved (the #605 exclusion set)')
        [judged] = self.asked_goals
        self.assertIn('판교 사무실', judged.facts['reply'], 'no longer masked from the owner\'s Judgment AI')
        self.assertNotIn(STORED_SECRET, json.dumps(judged.facts, ensure_ascii=False), 'secrets never reach a judgment')
        self.assertNotIn(STORED_SECRET, json.dumps(self.asked_plans[0][0].facts, ensure_ascii=False))
