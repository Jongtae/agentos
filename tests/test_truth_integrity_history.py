"""Stored conversation, Evidence and fallback text stay truth-qualified (#494).

#476 keeps an unverified model sentence out of the terminal bubble and #486
out of the task card.  The same sentence is also stored in ``messages`` and
read back by the web API, project views and the next turn's model context,
and there it was unqualified.  These tests drive whole turns through
``AgentService`` and assert on what each reader actually receives:

* the stored text is preserved byte-for-byte (nothing is deleted);
* every reader of it sees the Work's typed outcome next to it;
* a later model turn reads that outcome in front of the earlier claim;
* Evidence keeps setup-required/truncated so "none found" is not "not
  fully searched";
* AgentOS's own fallback never claims completion;
* a wholly failed delegation is ``failed``, a partial one ``partial``.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from personal_agent.agent_runtime import (DELEGATE_FAILED, FALLBACK_UNDESCRIBED, QUALIFIER_NOTES,
                                          evidence_qualifiers, fallback_response, evidence_summary, turn_context)
from personal_agent.calendar import CALENDAR_SPEC, CALENDAR_WRITE_SPEC, CalendarConnector
from personal_agent.connector_contract import ConnectorRegistry, ConnectorState
from personal_agent.conversation_projection import (CONTEXT_QUALIFIER, TERMINAL_PARTIAL_HEADER,
                                                    context_message, qualify_transcript)
from personal_agent.google_calendar import CALENDAR_READ_SCOPE, CALENDAR_WRITE_SCOPE
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from test_agency_loop import goal_engine

CHAT = 909
GENERATION = 'g1'
CONNECTOR_OWNER = f'telegram:{CHAT}'
CLAIM = '9월 25일 오전 10시에 병원 예약 일정을 등록했습니다.'
DRAFT = {'summary': '병원 예약', 'start': '2026-09-25T10:00:00+09:00',
         'end': '2026-09-25T11:00:00+09:00', 'timezone': 'Asia/Seoul'}
WEB = Path(__file__).parents[1] / 'src' / 'personal_agent' / 'web' / 'app.js'


class TruthIntegrityTestCase(unittest.TestCase):
    """One Telegram owner, a scripted model, a recorded outbound seam."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parent))
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(Path(self.temp.name) / 'data')
        self.sent = []
        self.plan = []
        self.child_plan = []
        self.text = '완료했습니다.'
        self.turn = 0
        # #657: when set, the parent ends with a finish claim citing every result it was shown.
        self.claim = False
        self.model_requests = []   # the messages every parent model turn received

        def transport(url, body=None, headers=None, timeout=60):
            if url.endswith('/sendMessage'):
                self.sent.append(body['text'])
                return {'ok': True, 'result': {'message_id': len(self.sent)}}
            if url.endswith('/getMe'):
                return {'ok': True, 'result': {'username': 'owner_test_bot'}}
            if url.endswith('/getWebhookInfo'):
                return {'ok': True, 'result': {'url': ''}}
            return {'ok': True, 'result': []}

        def model(url, body, headers=None, timeout=60):
            tools = [t.get('function', {}).get('name') or t.get('name') for t in body.get('tools', [])]
            if 'agentos_connection_probe' in tools:
                return {'message': {'content': '', 'tool_calls': [
                    {'id': 'probe', 'function': {'name': 'agentos_connection_probe', 'arguments': {}}}]}}
            parent = 'delegate_agent' in tools
            if parent:
                self.model_requests.append(json.loads(json.dumps(body.get('messages', []))))
            plan = self.plan if parent else self.child_plan
            if plan:
                name, arguments = plan.pop(0)
                self.turn += 1
                return {'message': {'content': '', 'tool_calls': [
                    {'id': f'call-{self.turn}', 'function': {'name': name, 'arguments': arguments}}]}}
            refs = [json.loads(m['content']).get('ref') for m in body.get('messages', [])
                    if m.get('role') == 'tool' and m.get('content', '').startswith('{')]
            if parent and self.claim and any(refs):
                self.claim = False
                return {'message': {'content': '', 'tool_calls': [
                    {'id': 'finish', 'function': {'name': 'finish', 'arguments': {
                        'status': 'done', 'evidence_refs': [ref for ref in refs if ref], 'summary': self.text}}}]}}
            return {'message': {'content': self.text if parent else '전문 보고서'}}

        self.service = AgentService(self.store, ModelAdapter(model), transport, calendar=self.calendar())
        self.service.save_model({'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434',
                                 'model': 'test-model', 'api_key': ''})
        self.assertTrue(self.service.test_model()['ok'])
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': GENERATION})

    def calendar(self):
        self.calendar_calls = []

        class Provider:
            def query(inner, start, end, timezone, max_results):
                self.calendar_calls.append('query')
                return [{'id': 'ev1', 'summary': '팀 회의', 'version': '"etag1"', 'start': start, 'end': end}]

            def create(inner, payload, idempotency_key):
                self.calendar_calls.append('create')
                return {'id': 'new1', 'version': '"etag2"'}

        registry = ConnectorRegistry(self.store, (CALENDAR_SPEC, CALENDAR_WRITE_SPEC))
        for spec, scope in ((CALENDAR_SPEC, CALENDAR_READ_SCOPE), (CALENDAR_WRITE_SPEC, CALENDAR_WRITE_SCOPE)):
            registry.transition(CONNECTOR_OWNER, spec.connector_id, ConnectorState.CONNECTED,
                                granted_scopes=(scope,))
        return CalendarConnector(self.store, Provider(), registry=registry)

    def claim_completion(self):
        """#657: the model claims completion and the judgment finds it shown."""
        self.claim = True
        self.service.use_decision_engine(goal_engine(True))

    def ask(self, message):
        job_id = self.store.enqueue(message, f'ask-{self.turn}-{len(self.sent)}-{message}',
                                    channel=f'telegram:{GENERATION}', chat_id=CHAT)
        self.service.run_one()
        before = len(self.sent)
        self.service.deliver_one()
        return self.store.job(job_id), (self.sent[before] if len(self.sent) > before else None)

    def assistant_row(self, job_id, rows=None):
        rows = self.store.history() if rows is None else rows
        return next(row for row in rows if row['job_id'] == job_id and row['role'] == 'assistant')

    def card(self, job_id):
        return next(task for task in self.service.task_progress(job_id)['tasks'] if task['id'] == job_id)

    def connect_folder(self, files):
        root = Path(self.temp.name) / 'docs'
        root.mkdir()
        for name, text in files.items():
            (root / name).write_text(text, encoding='utf-8')
        self.service.save_roots({'paths': [str(root)]})

    def calendar_false_claim(self):
        self.plan = [('calendar_draft_create', DRAFT)]
        self.text = CLAIM
        return self.ask('모레 오전 10시에 병원 예약 잡아줘')


class TranscriptQualificationTests(TruthIntegrityTestCase):
    """The issue's executed example, now through every reader of `messages`."""

    def test_the_calendar_false_claim_is_preserved_but_qualified_in_the_transcript(self):
        job, bubble = self.calendar_false_claim()
        self.assertEqual(job['status'], 'partial')
        row = self.assistant_row(job['id'])
        # Preserved: the text is exactly what the model wrote (nothing deleted).
        self.assertIn(CLAIM, row['content'])
        # Qualified: the reader gets the Work's outcome and cause with it.
        self.assertEqual(row['qualifier']['outcome'], 'partial')
        self.assertIs(row['qualifier']['verified'], False)
        self.assertEqual(row['qualifier']['label'], '일부 완료')
        self.assertIn('소유자가 이 미리보기를 승인해야 실제 일정에 반영됩니다.', row['qualifier']['cause'])
        # The bubble keeps its own #476 rule; nothing reached the calendar.
        self.assertTrue(bubble.startswith(TERMINAL_PARTIAL_HEADER))
        self.assertNotIn('등록했습니다', bubble)
        self.assertEqual(self.calendar_calls, [])

    def test_the_home_conversation_and_project_view_carry_the_same_qualifier(self):
        workspace = self.store.create_workspace('병원', '')
        self.plan = [('calendar_draft_create', DRAFT)]
        self.text = CLAIM
        job_id = self.store.enqueue('모레 오전 10시에 병원 예약 잡아줘', 'ws-ask',
                                    channel=f'telegram:{GENERATION}', chat_id=CHAT,
                                    workspace_id=workspace['id'])
        self.service.run_one()
        home = self.assistant_row(job_id, self.service.home()['conversation'])
        project = self.assistant_row(job_id, self.store.workspace_detail(workspace['id'])['messages'])
        for row in (home, project):
            self.assertIn(CLAIM, row['content'])
            self.assertEqual(row['qualifier']['outcome'], 'partial')
        # The task card uses the same typed qualifier, so the surfaces agree.
        self.assertEqual(self.card(job_id)['qualifier']['outcome'], 'partial')
        # A partial result saved to the project keeps its outcome too.
        saved = self.store.save_workspace_result(workspace['id'], job_id)
        self.assertEqual(saved['results'][0]['qualifier']['outcome'], 'partial')

    def test_what_is_stored_is_unchanged(self):
        """Non-goal: the stored message text is not rewritten."""
        job, _bubble = self.calendar_false_claim()
        with self.store.db() as db:
            stored = db.execute("SELECT content FROM messages WHERE job_id=? AND role='assistant'",
                                (job['id'],)).fetchone()['content']
        self.assertEqual(stored, job['response'])
        self.assertIn(CLAIM, stored)
        self.assertNotIn('AgentOS record', stored)

    def test_a_succeeded_turn_and_owner_turns_are_not_qualified(self):
        """Opposing pin: qualifying everything would pass the tests above."""
        self.plan = [('calendar_query', {'start': '2026-09-25T00:00:00+09:00',
                                         'end': '2026-09-26T00:00:00+09:00', 'timezone': 'Asia/Seoul'})]
        self.text = '팀 회의 하나가 있습니다.'
        self.claim_completion()
        job, bubble = self.ask('모레 일정 뭐 있어?')
        self.assertEqual(job['status'], 'succeeded', job.get('error'))
        self.assertEqual(bubble, self.text)
        self.assertIsNone(self.assistant_row(job['id'])['qualifier'])
        self.assertIsNone(self.card(job['id'])['qualifier'])
        user = next(row for row in self.store.history() if row['job_id'] == job['id'] and row['role'] == 'user')
        self.assertIsNone(user['qualifier'])

    def test_the_qualifier_survives_a_restart(self):
        """Restart continuity reads the durable Work outcome, not process memory."""
        job, _bubble = self.calendar_false_claim()
        reopened = QuickStore(Path(self.temp.name) / 'data')
        reopened.recover()
        self.assertEqual(self.assistant_row(job['id'], reopened.history())['qualifier']['outcome'], 'partial')

    def test_an_interrupted_work_qualifies_its_stored_text(self):
        job_id = self.store.enqueue('긴 작업', 'interrupted-ask', channel='web')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job_id,))
            db.execute('INSERT INTO messages(role,content,channel,created,workspace_id,job_id) VALUES (?,?,?,?,?,?)',
                       ('assistant', '보고서를 저장했습니다.', 'web', 1.0, None, job_id))
        self.store.recover()
        row = self.assistant_row(job_id)
        self.assertEqual(row['content'], '보고서를 저장했습니다.')
        self.assertEqual(row['qualifier']['outcome'], 'interrupted')


class ModelContextTests(TruthIntegrityTestCase):
    """An unobserved claim must not re-enter the model's context as fact."""

    def later_turn_context(self):
        self.plan = []
        self.text = '네.'
        self.ask('그 일정 확인됐지?')
        return self.model_requests[-1]

    def test_the_next_turn_reads_the_earlier_claim_with_its_outcome(self):
        self.calendar_false_claim()
        messages = self.later_turn_context()
        earlier = [m for m in messages if m['role'] == 'assistant' and CLAIM in (m.get('content') or '')]
        self.assertEqual(len(earlier), 1, messages)
        self.assertTrue(earlier[0]['content'].startswith(CONTEXT_QUALIFIER.format(outcome='partial')))
        # The owner can still refer to it: the text itself is there in full.
        self.assertIn(CLAIM, earlier[0]['content'])

    def test_a_succeeded_earlier_reply_enters_context_unchanged(self):
        self.text = '안녕하세요.'
        self.ask('안녕')
        messages = self.later_turn_context()
        earlier = [m for m in messages if m['role'] == 'assistant' and m.get('content') == '안녕하세요.']
        self.assertEqual(len(earlier), 1, messages)

    def test_the_qualifier_adds_no_cause_or_payload_to_model_context(self):
        """Only the typed outcome travels; the cause stays on owner surfaces."""
        self.calendar_false_claim()
        messages = self.later_turn_context()
        earlier = next(m for m in messages if m['role'] == 'assistant' and CLAIM in (m.get('content') or ''))
        self.assertNotIn('소유자가 이 미리보기를', earlier['content'].split('\n', 1)[0])

    def test_the_cli_route_prompt_uses_the_same_policy(self):
        rows = qualify_transcript([
            {'role': 'user', 'content': '잡아줘', 'work_outcome': 'partial'},
            {'role': 'assistant', 'content': CLAIM, 'work_outcome': 'partial', 'work_error': 'x'},
            {'role': 'user', 'content': '됐지?'}])
        context = turn_context([context_message(row) for row in rows], 'cli')
        self.assertEqual(context['conversation'][0]['content'], '잡아줘')
        self.assertTrue(context['conversation'][1]['content'].startswith('[AgentOS record:'))


class EvidenceQualifierTests(TruthIntegrityTestCase):
    """"Not found" and "not fully searched" stay different in durable Evidence."""

    def find_event(self, job_id):
        return [row for row in self.store.task_events(job_id) if row['tool'] == 'find_files'][-1]

    def test_a_search_with_no_folder_connected_is_recorded_as_setup_required(self):
        self.plan = [('find_files', {'query': '급여'})]
        self.text = '급여 파일이 없습니다.'
        job, _bubble = self.ask('급여 파일 찾아줘')
        event = self.find_event(job['id'])
        self.assertEqual(event['trace']['evidence']['qualifiers'], ['setup-required'])
        labels = self.store.evidence_summary(job['id'])
        self.assertNotIn('내 컴퓨터의 자료 확인', labels)
        self.assertIn('연결 설정이 필요해 확인하지 못한 자료 있음', labels)

    def test_a_capped_search_is_recorded_as_truncated(self):
        self.connect_folder({f'급여-{index}.txt': '급여 명세' for index in range(25)})
        self.plan = [('find_files', {'query': '급여'})]
        self.text = '급여 파일을 찾았습니다.'
        job, _bubble = self.ask('급여 파일 찾아줘')
        event = self.find_event(job['id'])
        self.assertEqual(event['trace']['evidence']['qualifiers'], ['truncated'])
        self.assertIn('한도에 걸려 일부만 확인함', self.store.evidence_summary(job['id']))

    def test_a_complete_search_carries_no_qualifier(self):
        """Opposing pin."""
        self.connect_folder({'pay.txt': '급여 명세'})
        self.plan = [('find_files', {'query': '급여'})]
        self.text = '급여 파일 한 건을 찾았습니다.'
        job, _bubble = self.ask('급여 파일 찾아줘')
        self.assertNotIn('qualifiers', self.find_event(job['id'])['trace']['evidence'])
        self.assertEqual(self.store.evidence_summary(job['id']), ['내 컴퓨터의 자료 확인'])

    def test_qualifiers_are_typed_by_result_shape_not_by_tool(self):
        """No per-tool branch: any tool returning the flag is covered."""
        for name in ('find_files', 'future_connector_search'):
            self.assertEqual(evidence_qualifiers({'truncated': True}), ['truncated'])
            self.assertEqual(evidence_summary(name, {'needs_setup': True})['qualifiers'], ['setup-required'])
        self.assertEqual(evidence_qualifiers({'results': [], 'read_failures': [{'url': 'u'}]}), ['partial'])
        self.assertEqual(evidence_qualifiers({'truncated': 'yes'}), [], 'only a typed True flag qualifies')
        self.assertEqual(evidence_qualifiers(None), [])


class ResearchNet:
    """A public network whose second search result cannot be read."""

    def execute(self, plan):
        if plan['tool'] == 'web_search':
            return {'tool': 'web_search', 'retrieved_at': 1, 'results': [
                {'url': 'https://example.com/a', 'title': 'A', 'snippet': ''},
                {'url': 'https://example.com/b', 'title': 'B', 'snippet': ''}]}
        if plan['url'].endswith('/b'):
            raise ValueError('공개 페이지가 정상 응답하지 않았습니다.')
        return {'tool': 'public_page_read', 'url': plan['url'], 'retrieved_at': 2,
                'content': 'Model A headphones. Shipping fee is 3,000 KRW for all domestic orders.'}


class IncompleteEvidenceOutcomeTests(TruthIntegrityTestCase):
    """Incomplete Evidence makes the Work `partial` even when the model writes text.

    Review of this PR: the qualifier was consulted only by the fallback, so a
    normal reply ("there are no such files") after a capped search made the
    Work `succeeded`, went out unqualified and re-entered context as fact.
    """

    def assert_partial_and_qualified(self, job, bubble, claim):
        self.assertEqual(job['status'], 'partial', job.get('error'))
        self.assertNotIn(claim, bubble)
        row = self.assistant_row(job['id'])
        self.assertIn(claim, row['content'], 'the reply is preserved')
        self.assertEqual(row['qualifier']['outcome'], 'partial')
        self.assertEqual(self.card(job['id'])['qualifier']['outcome'], 'partial')
        self.plan, self.text = [], '네.'
        self.ask('그럼 없는 거지?')
        earlier = [m for m in self.model_requests[-1]
                   if m['role'] == 'assistant' and claim in (m.get('content') or '')]
        self.assertEqual(len(earlier), 1)
        self.assertTrue(earlier[0]['content'].startswith(CONTEXT_QUALIFIER.format(outcome='partial')))

    def test_a_capped_search_with_no_hits_and_a_reply_is_partial(self):
        # 501 non-matching files: the 500-file visit cap stops the search with no hits.
        self.connect_folder({f'note-{index}.txt': '회의 메모' for index in range(501)})
        self.plan = [('find_files', {'query': '급여'})]
        self.text = '급여 파일은 없습니다.'
        job, bubble = self.ask('급여 파일 찾아줘')
        self.assertIn(QUALIFIER_NOTES['truncated'], job['error'])
        self.assert_partial_and_qualified(job, bubble, self.text)

    def test_research_with_unread_pages_and_a_reply_is_partial(self):
        self.service.local_tools = ResearchNet()
        self.plan = [('bounded_public_research', {'mode': 'product_comparison', 'query': 'headphones'})]
        self.text = '두 제품을 모두 비교했습니다.'
        job, bubble = self.ask('헤드폰 비교해줘')
        event = [row for row in self.store.task_events(job['id'])
                 if row['tool'] == 'bounded_public_research'][-1]
        self.assertEqual(event['status'], 'succeeded', 'the call itself ran')
        self.assertEqual(event['trace']['evidence']['qualifiers'], ['partial'])
        self.assertIn(QUALIFIER_NOTES['partial'], job['error'])
        self.assert_partial_and_qualified(job, bubble, self.text)

    def test_a_complete_search_with_a_reply_stays_succeeded(self):
        """Opposing pin."""
        self.connect_folder({'pay.txt': '급여 명세'})
        self.plan = [('find_files', {'query': '급여'})]
        self.text = '급여 파일 한 건을 찾았습니다.'
        self.claim_completion()
        job, bubble = self.ask('급여 파일 찾아줘')
        self.assertEqual(job['status'], 'succeeded', job.get('error'))
        self.assertEqual(bubble, self.text)
        self.assertIsNone(self.assistant_row(job['id'])['qualifier'])

    def test_setup_required_is_its_own_parked_state(self):
        """Owner decision 2026-09-25 (#505): setup-required is neither failed nor partial."""
        self.plan = [('find_files', {'query': '급여'})]
        self.text = '폴더를 먼저 연결해 주세요.'
        job, bubble = self.ask('급여 파일 찾아줘')
        self.assertEqual(job['status'], 'awaiting_connection', job.get('error'))
        self.assertIsNone(job['error'])
        self.assertIn('Mac에서 계속', bubble)


class FallbackTextTests(TruthIntegrityTestCase):
    """AgentOS's own words when the model returns no text after a tool."""

    def test_an_unhandled_tool_is_not_answered_with_a_completion_claim(self):
        self.plan = [('calendar_query', {'start': '2026-09-25T00:00:00+09:00',
                                         'end': '2026-09-26T00:00:00+09:00', 'timezone': 'Asia/Seoul'})]
        self.text = ''
        job, bubble = self.ask('모레 일정 뭐 있어?')
        self.assertEqual(job['response'], FALLBACK_UNDESCRIBED)
        # #657: nothing claimed completion, so the Work is partial; AgentOS's
        # own truth header is the only "완료" in the bubble.
        self.assertEqual(job['status'], 'partial')
        self.assertTrue(bubble.startswith(TERMINAL_PARTIAL_HEADER))
        for text in (job['response'], bubble[len(TERMINAL_PARTIAL_HEADER):]):
            self.assertNotIn('완료했습니다', text)

    def test_an_unconfigured_search_is_not_reported_as_finding_nothing(self):
        self.plan = [('find_files', {'query': '급여'})]
        self.text = ''
        job, _bubble = self.ask('급여 파일 찾아줘')
        # #505 parks the Work with the folder handoff instead of a fallback.
        self.assertIn('아직 파일을 찾지 않았습니다', job['response'])
        self.assertNotIn('일치하는 파일이 없습니다', job['response'])
        # The fallback text itself still says "not checked" for any caller.
        self.assertEqual(fallback_response([('find_files', {'files': [], 'needs_setup': True})], []),
                         QUALIFIER_NOTES['setup-required'])

    def test_a_capped_search_says_it_is_incomplete(self):
        self.connect_folder({f'급여-{index}.txt': '급여 명세' for index in range(25)})
        self.plan = [('find_files', {'query': '급여'})]
        self.text = ''
        job, _bubble = self.ask('급여 파일 찾아줘')
        self.assertIn('찾은 파일:', job['response'])
        self.assertIn(QUALIFIER_NOTES['truncated'], job['response'])


class DelegationOutcomeTests(TruthIntegrityTestCase):
    """A wholly failed delegation is not reported as a partly completed one."""

    def delegate(self):
        self.plan = [('delegate_agent', {'agent_id': 'researcher', 'task': '급여 자료를 검토해 줘'})]
        self.text = '검토 결과를 정리했습니다.'
        return self.ask('급여 자료 검토를 전문가에게 맡겨줘')

    def test_a_wholly_failed_delegation_is_failed(self):
        self.connect_folder({'pay.txt': '급여 명세'})
        # The specialist's only step fails, so it accomplished nothing.
        self.child_plan = [('read_file', {'root_id': 'no-such-root', 'path': 'x.txt'})]
        job, bubble = self.delegate()
        self.assertEqual(job['status'], 'failed')
        self.assertIn(DELEGATE_FAILED, job['error'])
        self.assertNotIn(TERMINAL_PARTIAL_HEADER, bubble)
        self.assertNotIn('정리했습니다', bubble)
        # Diagnostic material stays inspectable without upgrading the outcome.
        card = self.card(job['id'])
        self.assertEqual(card['qualifier']['outcome'], 'failed')
        self.assertEqual(job['response'], self.text)
        self.assertEqual(self.assistant_row(job['id'])['qualifier']['outcome'], 'failed')

    def test_a_partly_completed_delegation_stays_partial(self):
        """Opposing pin (#492 review): half a real report is `partial`."""
        self.connect_folder({'pay.txt': '급여 명세'})
        self.child_plan = [('find_files', {'query': '급여'}),
                           ('read_file', {'root_id': 'no-such-root', 'path': 'x.txt'})]
        job, _bubble = self.delegate()
        self.assertEqual(job['status'], 'partial')
        self.assertTrue(self.card(job['id'])['result_available'])
        self.assertNotIn(DELEGATE_FAILED, job['error'])


class WebTranscriptRenderingTests(unittest.TestCase):
    """The web turn renders from the typed qualifier, not from wording."""

    def test_unverified_answer_follows_the_typed_qualifier(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node is needed for JavaScript behaviour checks')
        script = r"""
const assert=require('node:assert/strict');
const ui=require(process.argv[1]);ui.setLanguage('ko');
const q=outcome=>({outcome,verified:false});
const partial=ui.unverifiedAnswer({status:'partial',qualifier:q('partial'),response:'일정을 등록했습니다.'});
assert.equal(partial.notice,'확인된 결과가 아니므로 그대로 신뢰하지 마세요.');
assert.equal(partial.hidden,'');
const failed=ui.unverifiedAnswer({status:'failed',qualifier:q('failed'),response:'보고서를 정리했습니다.'});
assert.deepEqual(failed,{notice:'',hidden:'보고서를 정리했습니다.'});
assert.equal(ui.unverifiedAnswer({status:'succeeded',qualifier:null,response:'답변'}),null);
assert.equal(ui.unverifiedAnswer({status:'failed',qualifier:q('failed'),response:''}),null);
// Wording alone never qualifies: no typed qualifier, no label.
assert.equal(ui.unverifiedAnswer({status:'succeeded',response:'확인 필요 실패 일부'}),null);
// A failed Work's preserved text is merged in for the disclosure, not as the result.
const merged=ui.mergeTaskProgress({tasks:[{id:'f',status:'failed',status_kind:'attention',qualifier:q('failed'),error:'원인'}]},null,[{id:'f',response:'초안'}]).tasks[0];
assert.equal(merged.response,'초안');
assert.equal(ui.taskOutcome(merged).title,'완료하지 못함');
assert.equal(ui.taskOutcome(merged).text,'원인');
ui.setLanguage('en');
assert.equal(ui.t('확인되지 않은 답변 보기'),'Show unverified answer');
"""
        subprocess.run([node, '-e', script, str(WEB)], check=True, capture_output=True, text=True, timeout=20)


if __name__ == '__main__':
    unittest.main()
