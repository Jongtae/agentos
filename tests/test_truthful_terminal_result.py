"""A failed or partial turn must not hand the owner the model's claim as the result.

TEST-FIRST-USER-01 / #472 watched a synthetic first user read, as the last
Telegram bubble of a turn whose tool call had just been refused:

    "내일 일정은 팀 회의 하나입니다."

The Work was `failed`. No calendar was read. The web card said 확인 필요 and
carried the real cause; Telegram carried the model's sentence, because
`telegram_result_text` fell back to `error` only when `response` was empty
and never saw the outcome at all (#476).

#752 (owner contract change): a failed or partial Work's AI answer reaches
the owner, but never *as* the result.  #847 (owner observation 2026-09-28):
the answer is the message; one closing note follows it - the Work's
``owner_note``: a count of the steps not confirmed, a withheld step's own
next step (approve, log in), the worker's question - never a header, a
tool name or a tool error.  Step detail stays in 상세 (``error``,
``owner_cause``).  A failed state-changing step still never reads as done.

The last bubble is what people read, so these are end-to-end through
`run_one` + `deliver_one` with an injected Telegram transport, asserting on
the text that actually reached the owner.
"""
import json
import tempfile
import time
import unittest
from pathlib import Path

from personal_agent.conversation_projection import (TERMINAL_FAILED_HEADER, TERMINAL_FAILED_NOTE,
                                                    TERMINAL_INTERRUPTED_NOTE, TERMINAL_NEXT_ACTION,
                                                    TERMINAL_PARTIAL_HEADER, TERMINAL_VERIFIED_LABEL)
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from test_agency_loop import goal_engine

CHAT = 4242
GENERATION = 'g1'


class TerminalResultTestCase(unittest.TestCase):
    """One Telegram owner, one scripted model, one recorded outbound seam."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(Path(self.temp.name) / 'data')
        self.sent = []
        self.cards = []         # every task-card text the owner saw, in order
        self.plan = []          # [(tool, arguments_mapping), ...] consumed in order
        self.text = '완료했습니다.'
        self.turn = 0
        # #657: when set, the model ends with a finish claim citing every
        # result it was shown (see `claim_completion`).
        self.claim = False

        def transport(url, body=None, headers=None, timeout=60):
            if url.endswith('/sendMessage'):
                self.sent.append(body['text'])
                return {'ok': True, 'result': {'message_id': len(self.sent)}}
            if url.endswith('/editMessageText'):
                self.cards.append(body['text'])
                return {'ok': True, 'result': {'message_id': body['message_id']}}
            if url.endswith('/getMe'):
                return {'ok': True, 'result': {'username': 'owner_test_bot'}}
            if url.endswith('/getWebhookInfo'):
                return {'ok': True, 'result': {'url': ''}}
            if url.endswith('/getUpdates'):
                return {'ok': True, 'result': []}
            return {'ok': True, 'result': {}}

        def model(url, body, headers=None, timeout=60):
            tools = [t.get('function', {}).get('name') or t.get('name')
                     for t in body.get('tools', [])]
            if 'agentos_connection_probe' in tools:
                return {'message': {'content': '', 'tool_calls': [
                    {'id': 'probe',
                     'function': {'name': 'agentos_connection_probe', 'arguments': {}}}]}}
            if self.plan:
                name, arguments = self.plan.pop(0)
                self.turn += 1
                return {'message': {'content': '', 'tool_calls': [
                    {'id': f'call-{self.turn}',
                     'function': {'name': name, 'arguments': arguments}}]}}
            refs = [json.loads(m['content']).get('ref') for m in body.get('messages', [])
                    if m.get('role') == 'tool' and m.get('content', '').startswith('{')]
            if self.claim and any(refs):
                self.claim = False
                return {'message': {'content': '', 'tool_calls': [
                    {'id': 'finish', 'function': {'name': 'finish', 'arguments': {
                        'status': 'done', 'evidence_refs': [ref for ref in refs if ref], 'summary': self.text}}}]}}
            return {'message': {'content': self.text}}

        self.service = AgentService(self.store, ModelAdapter(model), transport)
        self.service.save_model({'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434',
                                 'model': 'test-model', 'api_key': ''})
        self.assertTrue(self.service.test_model()['ok'])
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT,
                                    'generation': GENERATION})

    def claim_completion(self):
        """#657: the model claims completion and the judgment finds it shown."""
        self.claim = True
        self.service.use_decision_engine(goal_engine(True))

    def ask(self, message, card=False):
        """Run one Telegram turn and return the job plus the terminal bubble."""
        job_id = self.store.enqueue(message, f'ask-{len(self.sent)}',
                                    channel=f'telegram:{GENERATION}', chat_id=CHAT)
        if card:
            # A card sent before #958 (nothing sends one now).  A carded job is
            # held back for the cancel grace window; age it past that so this
            # turn runs, without touching the window itself.
            created=time.time() - 60
            self.store.save_task_card(job_id, CHAT, 700, 'queued')
            with self.store.db() as db:
                db.execute('UPDATE jobs SET created=? WHERE id=?',(created, job_id))
                db.execute('UPDATE telegram_task_cards SET created=? WHERE job_id=?',(created, job_id))
        self.service.run_one()
        before = len(self.sent)
        self.service.deliver_one()
        job = self.store.job(job_id)
        bubble = self.sent[before] if len(self.sent) > before else None
        return job, bubble

    def assertAnswerFirst(self, bubble, job, claim):
        """#847: the answer, then one closing note (the Work's owner_note) - no header, no tool names."""
        self.assertTrue(bubble.startswith(job['response']), bubble[:60])
        self.assertIn(claim, bubble)
        self.assertEqual(bubble.count(claim), 1)
        self.assertTrue(job['owner_note'], 'a failed/partial Work records its closing note')
        self.assertTrue(bubble.endswith('\n\n' + job['owner_note']), bubble)
        for machinery in (TERMINAL_FAILED_HEADER, TERMINAL_PARTIAL_HEADER, TERMINAL_NEXT_ACTION, '완료하지 못한 부분',
                          '확인되지 않았어요', 'AI 답변'):
            self.assertNotIn(machinery, bubble)
        for tool, _arguments in self.plan:
            self.assertNotIn(tool, bubble, 'no tool id in the bubble')
        # The note is one sentence or a few, never a labelled block.
        self.assertNotIn('\n', job['owner_note'])

    def card(self, job):
        return next(task for task in self.service.task_progress(job['id'])['tasks'] if task['id'] == job['id'])

    def connect_folder(self, secret='SECRET 급여 연 1억 2천'):
        root = Path(self.temp.name) / 'docs'
        root.mkdir(exist_ok=True)
        (root / 'pay.txt').write_text(secret, encoding='utf-8')
        self.service.save_roots({'paths': [str(root)]})
        return root


class FailedTurnTests(TerminalResultTestCase):
    """A failed READ does not withhold the answer (#752); the answer comes first, then one note (#847)."""

    def test_a_failed_calendar_query_labels_the_claimed_schedule_after_the_failure(self):
        """#476 case 1. Calendar is not configured, so the tool refuses."""
        self.plan = [('calendar_query', {'start': '2026-09-24T00:00:00+09:00',
                                                    'end': '2026-09-25T00:00:00+09:00',
                                                    'timezone': 'Asia/Seoul'})]
        self.text = '내일 일정은 팀 회의 하나입니다.'
        job, bubble = self.ask('내일 일정 뭐 있어?')
        self.assertEqual(job['status'], 'failed', job.get('error'))
        self.assertIsNotNone(bubble)
        self.assertAnswerFirst(bubble, job, '팀 회의 하나입니다')

    def test_a_failed_file_read_labels_the_claimed_summary_after_the_failure(self):
        """#476 case 4."""
        self.connect_folder()
        self.plan = [('read_file', {'root_id': 'no-such-root',
                                               'path': 'missing.txt'})]
        self.text = '출장 계획 요약: 9월 3일 출발, 9월 7일 귀국입니다.'
        job, bubble = self.ask('내 출장 계획 파일 요약해줘')
        self.assertEqual(job['status'], 'failed', job.get('error'))
        self.assertAnswerFirst(bubble, job, '9월 3일 출발')
        self.assertEqual(job['owner_note'], TERMINAL_FAILED_NOTE, 'a tool error is counted, never spoken')

    def test_a_refused_research_request_labels_the_comparison_after_the_refusal(self):
        """#476 case 3 — a refused public read, then an apparent answer.

        Since #654 a private context no longer closes public search, so the
        refusal here is the page read outside the owner's approved scope.
        """
        self.connect_folder()
        self.plan = [
            ('find_files', {'query': '급여'}),
            ('public_page_read', {'url': 'https://example.com/headphones/compare'}),
        ]
        self.text = '관찰됨: Model A 30시간 재생. 확인되지 않음: 가격·재고.'
        job, bubble = self.ask('노이즈캔슬링 헤드폰 비교해줘')
        self.assertEqual(job['status'], 'partial', job.get('error'))
        self.assertAnswerFirst(bubble, job, '관찰됨')
        self.assertEqual(job['owner_note'], '한 단계는 확인하지 못했어요.')


class PartialTurnTests(TerminalResultTestCase):
    def partial_turn(self, claim):
        """One tool completes, one state-changing action fails without effect -> `partial`.

        The calendar draft fails with ``needs_setup`` and ``effect: none``:
        nothing was changed; the answer claiming the draft is delivered below
        what did not complete, under the unverified label (#820).
        """
        self.connect_folder()
        self.plan = [
            ('find_files', {'query': '급여'}),          # succeeds
            ('calendar_draft_cancel', {'event_id': 'ev1',
                                                  'event_version': '"etag1"'}),  # refused, no effect
        ]
        self.text = claim
        return self.ask('내일 팀 회의 취소해줘')

    def test_a_partial_turn_is_not_announced_as_a_completed_result(self):
        """#476 case 2. The model said a draft existed; none was created."""
        job, bubble = self.partial_turn('팀 회의 취소 초안을 만들었습니다. 승인해 주세요.')
        self.assertEqual(job['status'], 'partial', job.get('error'))
        self.assertNotIn('처리가 끝났습니다', bubble)
        # #847: the answer first, then the one note; the old header is gone.
        self.assertNotIn('일부 단계만 완료했습니다', bubble)
        self.assertTrue(bubble.endswith('\n\n한 단계는 확인하지 못했어요.'), bubble)

    def test_a_partial_turn_delivers_a_claim_of_an_action_that_did_not_run_after_the_truth(self):
        """#476 case 2 / #820: the draft action did nothing; the answer is still delivered.

        The answer comes first; the closing note says a step was not
        confirmed (#847), so the claim never reads as a result.
        """
        claim = '팀 회의 취소 초안을 만들었습니다. 승인해 주세요.'
        job, bubble = self.partial_turn(claim)
        self.assertEqual(job['status'], 'partial')
        self.assertAnswerFirst(bubble, job, '초안을 만들었습니다')
        self.assertEqual(job['response'], claim, 'the text must be preserved, not deleted')

    def test_a_partial_turn_names_what_did_not_complete(self):
        job, bubble = self.partial_turn('초안을 만들었습니다.')
        self.assertTrue(job['error'], 'the job carries no cause to report')
        # #598 X1: the same observed cause, in owner words; the technical
        # cause with the tool id stays on the Work record for Task detail.
        self.assertTrue(job['owner_cause'])
        self.assertIn('일정 초안: Google Calendar가 로컬에 구성되어 있지 않습니다.', job['owner_cause'])
        self.assertIn('calendar_draft_cancel', job['error'])
        # #847: with the answer delivered, the bubble carries neither the
        # tool id nor the tool's error; the step is counted and stays in 상세.
        self.assertNotIn('calendar_draft_cancel', bubble)
        self.assertNotIn('Google Calendar가 로컬에 구성되어 있지 않습니다', bubble)
        self.assertNotIn(job['owner_cause'], bubble)
        self.assertEqual(job['owner_note'], '한 단계는 확인하지 못했어요.')
        self.assertTrue(bubble.endswith('\n\n' + job['owner_note']), bubble)


class DeliveredAnswerTests(TerminalResultTestCase):
    """#820: the AI's answer is always delivered, on both surfaces, under the truth header.

    #752 / #488 withheld it after a failed state-changing action; that protected no
    pilot invariant the header and cause do not.  #818: a memory write held as a
    pending candidate is a proposal, not a failure.
    """

    def test_a_memory_write_that_errored_delivers_the_answer_after_the_failure_on_both_surfaces(self):
        self.plan = [('save_memory', {'memory_key': 'inferred-preference', 'content': 'x' * 4001})]
        self.text = '취향을 기억해 두었습니다.'
        job, bubble = self.ask('이건 기억하지 마. 그냥 방금 이야기만 정리해 줘', card=True)
        self.assertEqual(job['status'], 'failed', job.get('error'))
        self.assertEqual(job['response'], self.text)
        # Telegram: the answer first, then the note that the request was not finished (#847).
        self.assertAnswerFirst(bubble, job, '기억해 두었습니다')
        self.assertEqual(job['owner_note'], TERMINAL_FAILED_NOTE)
        # The web serves the same answer, in the jobs and in the transcript.
        [served] = [row for row in self.service.owner_jobs(self.store.jobs()) if row['id'] == job['id']]
        self.assertEqual(served['response'], self.text)
        transcript = [row['content'] for row in self.service.home()['conversation'] if row.get('job_id') == job['id']
                      and row.get('role') == 'assistant']
        self.assertEqual(transcript, [self.text])
        card = self.card(job)
        self.assertEqual(card['status_label'], '확인 필요')
        self.assertTrue(card['result_available'])
        # Nothing was saved: the failure stays the Work's truthful outcome.
        self.assertEqual(self.store.memories(), [])

    def test_a_direct_memory_save_does_not_withhold_the_answer(self):
        """#918: the owner's worker saves at once; the answer is delivered as said and the notice follows it."""
        self.plan = [('save_memory', {'memory_key': 'inferred-preference', 'content': '모델이 추론한 값'})]
        self.text = '정리해 드릴게요.'
        self.claim_completion()
        job, bubble = self.ask('이건 기억하지 마. 그냥 방금 이야기만 정리해 줘', card=True)
        self.assertEqual(job['status'], 'succeeded', job.get('error'))
        self.assertEqual(bubble, self.text, 'the answer as said; the notice below it tells what was remembered')
        self.assertTrue(self.card(job)['result_available'])
        self.assertEqual([row['content'] for row in self.store.memories()], ['모델이 추론한 값'])
        self.assertEqual(self.store.memory_candidates(include_decided=True), [])

    def test_the_same_failed_status_with_only_a_failed_read_is_delivered(self):
        self.plan = [('calendar_query', {'start': '2026-09-24T00:00:00+09:00',
                                         'end': '2026-09-25T00:00:00+09:00', 'timezone': 'Asia/Seoul'})]
        self.text = '내일 일정은 팀 회의 하나입니다.'
        job, bubble = self.ask('내일 일정 뭐 있어?')
        self.assertEqual(job['status'], 'failed')
        self.assertTrue(self.card(job)['result_available'])
        self.assertAnswerFirst(bubble, job, self.text)
        [served] = [row for row in self.service.owner_jobs(self.store.jobs()) if row['id'] == job['id']]
        self.assertEqual(served['response'], self.text, 'the web keeps a read-only failure answer')


class SucceededTurnTests(TerminalResultTestCase):
    def test_a_succeeded_turn_still_delivers_the_model_answer_unchanged(self):
        """The opposing pin. Without it, refusing everything passes this file."""
        self.connect_folder()
        self.plan = [('find_files', {'query': '급여'})]
        self.text = '급여 파일 한 건을 찾았습니다.'
        self.claim_completion()
        job, bubble = self.ask('급여 파일 찾아줘')
        self.assertEqual(job['status'], 'succeeded', job.get('error'))
        self.assertEqual(bubble, self.text)

    def test_a_turn_with_no_tool_call_is_unaffected(self):
        self.text = '안녕하세요. 무엇을 도와드릴까요?'
        job, bubble = self.ask('안녕')
        self.assertEqual(job['status'], 'succeeded', job.get('error'))
        self.assertEqual(bubble, self.text)


class SurfaceConsistencyTests(TerminalResultTestCase):
    def test_telegram_shows_the_answer_exactly_where_the_web_offers_it(self):
        """The two surfaces disagreed, and that was the defect.

        #752: for a failed read both surfaces offer the answer - the web
        card sets `result_available` and Telegram shows it under the label.
        """
        self.plan = [('calendar_query', {'start': '2026-09-24T00:00:00+09:00',
                                                    'end': '2026-09-25T00:00:00+09:00',
                                                    'timezone': 'Asia/Seoul'})]
        self.text = '내일 일정은 팀 회의 하나입니다.'
        job, bubble = self.ask('내일 일정 뭐 있어?')
        card = self.card(job)
        self.assertEqual(card['status_label'], '확인 필요')
        self.assertTrue(card['result_available'])
        self.assertAnswerFirst(bubble, job, self.text)
        # ...and the card carries the technical cause with the exact id; the
        # bubble carries the step's own owner-facing next step (#598 X1, #847).
        self.assertEqual(card['error'], job['error'])
        self.assertNotIn(job['owner_cause'], bubble)
        self.assertIn(job['error'].split(': ', 1)[1].split('. ')[0], bubble)
        self.assertNotIn('calendar_query', bubble)

    def test_a_partial_turn_agrees_across_both_surfaces(self):
        """Both surfaces deliver the answer and both flag attention (#752, #820)."""
        self.connect_folder()
        self.plan = [('find_files', {'query': '급여'}),
                     ('calendar_draft_cancel', {'event_id': 'ev1',
                                                'event_version': '"etag1"'})]
        self.text = '취소 초안을 만들었습니다.'
        job, bubble = self.ask('내일 팀 회의 취소해줘')
        self.assertEqual(job['status'], 'partial')
        card = self.card(job)
        self.assertEqual(card['status_label'], '확인 필요')
        self.assertTrue(card['result_available'], 'the web offers it exactly as Telegram does')
        self.assertEqual(card['error'], job['error'])
        self.assertAnswerFirst(bubble, job, self.text)

    def test_the_card_above_a_partial_bubble_does_not_announce_a_result(self):
        """Independent review of #486 found the bubble alone was not enough.

        The task card sits directly above it and `update_task_card` is called
        with the same outcome, so a partial turn was edited to read
        '처리가 끝났습니다. 아래 결과를 확인하세요.' -- the exact framing #476
        is about -- above a bubble that withholds the claim (#752).
        """
        self.connect_folder()
        self.plan = [('find_files', {'query': '급여'}),
                     ('calendar_draft_cancel', {'event_id': 'ev1',
                                                'event_version': '"etag1"'})]
        self.text = '취소 초안을 만들었습니다.'
        job, bubble = self.ask('내일 팀 회의 취소해줘', card=True)
        self.assertEqual(job['status'], 'partial')
        self.assertTrue(self.cards, 'the card was never updated')
        # Exact, not a substring: '일부 단계만 완료했습니다. 아래 결과를 확인하세요.'
        # would satisfy a loose assertion while re-making the claim.
        self.assertEqual(self.cards[-1], '일부 단계만 완료했습니다. 아래 안내를 확인하세요.')
        # #847: the bubble is the answer, then the note.
        self.assertTrue(bubble.startswith(self.text), bubble)

    def test_the_card_above_a_succeeded_bubble_still_announces_the_result(self):
        """The opposing pin for the card."""
        self.connect_folder()
        self.plan = [('find_files', {'query': '급여'})]
        self.text = '급여 파일 한 건을 찾았습니다.'
        self.claim_completion()
        job, bubble = self.ask('급여 파일 찾아줘', card=True)
        self.assertEqual(job['status'], 'succeeded', job.get('error'))
        # #581: the card no longer frames the answer as "처리가 끝났습니다 →
        # 결과 상태 보기"; it states the Work outcome and the answer follows.
        self.assertEqual(self.cards[-1], '요청을 처리했어요.')
        self.assertEqual(bubble, self.text)

    def test_an_interrupted_turn_claims_no_completed_step_and_no_web_result(self):
        """`interrupted` is set on any restarted running job, even a no-tool one.

        `task_progress` offers the stored text for succeeded/partial/failed
        only, so the bubble must not point the owner at a web result that is
        not there, and must not claim steps completed that may never have run.
        """
        # #820/#847: an answer it has is delivered first, then the one interrupted note.
        text = AgentService.telegram_result_text('모두 처리했습니다.', '중단됨', 'interrupted')
        self.assertEqual(text, '모두 처리했습니다.\n\n' + TERMINAL_INTERRUPTED_NOTE)
        self.assertEqual(TERMINAL_INTERRUPTED_NOTE, '중간에 멈춰서 끝까지 확인하지 못했어요.')
        text = AgentService.telegram_result_text(None, '중단됨', 'interrupted')
        self.assertNotIn('일부 단계만', text)
        # A literal, not the constants: asserting against TERMINAL_* would
        # mutate the expectation along with the code and pin nothing. The whole
        # bubble is compared because the header itself must not re-make the
        # web-record claim that the trailing line no longer makes.
        self.assertEqual(text, '이 요청은 중단되었습니다. 자동으로 다시 실행하지 않았습니다.'
                         '\n\n중단됨\n\nAgentOS 웹에서 실행 기록과 다음 단계를 확인하세요.')

    def test_a_partial_turn_with_no_text_points_at_no_web_record_either(self):
        """The same rule one branch over.

        `result_available` requires a response, so a partial turn whose model
        returned nothing (or whose answer is withheld) has no web result to
        offer, and the bubble must not send the owner to look for one.
        """
        for response in ('', '   ', None):
            with self.subTest(response=response):
                text = AgentService.telegram_result_text(response, '원인', 'partial')
                self.assertEqual(text, '일부 단계만 완료했습니다.\n\n원인'
                                 '\n\nAgentOS 웹에서 실행 기록과 다음 단계를 확인하세요.')

    def test_the_failure_bubble_offers_a_next_action_only_without_an_answer(self):
        """#752: a withheld/absent answer gets the next-action pointer; a shown answer does not."""
        for response in ('', None):
            with self.subTest(response=response):
                text = AgentService.telegram_result_text(response, '원인', 'failed')
                self.assertEqual(text, '이 요청은 완료하지 못했습니다.\n\n원인'
                                 '\n\nAgentOS 웹에서 실행 기록과 다음 단계를 확인하세요.')
        self.plan = [('calendar_query', {'start': '2026-09-24T00:00:00+09:00',
                                                    'end': '2026-09-25T00:00:00+09:00',
                                                    'timezone': 'Asia/Seoul'})]
        self.text = '내일 일정은 팀 회의 하나입니다.'
        job, bubble = self.ask('내일 일정 뭐 있어?')
        self.assertAnswerFirst(bubble, job, self.text)
        self.assertNotIn('다음 단계를 확인하세요', bubble)


class UnsupportedTextNeverTerminalTests(TerminalResultTestCase):
    """The general property, stated directly on the renderer.

    The end-to-end cases above each pin one scenario. This pins the rule they
    share, so a future scenario nobody wrote a test for is covered too: the
    model text of a failed/partial turn is followed by exactly one closing
    note, and the technical cause (tool ids) never enters the bubble (#847).
    """

    CLAIM = '일정을 만들었고 메일도 보냈습니다.'

    def assertAnswerThenNote(self, text, note):
        self.assertTrue(text.startswith(self.CLAIM + '\n\n'), text)
        self.assertEqual(text[len(self.CLAIM) + 2:], note)
        for machinery in (TERMINAL_FAILED_HEADER, TERMINAL_PARTIAL_HEADER, TERMINAL_NEXT_ACTION, '완료하지 못한 도구 실행',
                          'calendar_query', 'read_file', 'AI 답변'):
            self.assertNotIn(machinery, text)

    def test_a_failed_outcome_renders_the_model_text_then_one_note(self):
        for cause in ('완료하지 못한 도구 실행 — calendar_query: 거부', '', None):
            with self.subTest(cause=cause):
                text = AgentService.telegram_result_text(self.CLAIM, cause, 'failed')
                self.assertAnswerThenNote(text, TERMINAL_FAILED_NOTE)
        text = AgentService.telegram_result_text(self.CLAIM, '완료하지 못한 도구 실행 — calendar_query: 거부', 'failed',
                                                 note='요청하신 작업은 끝내지 못했어요. 승인이 필요합니다.')
        self.assertAnswerThenNote(text, '요청하신 작업은 끝내지 못했어요. 승인이 필요합니다.')

    def test_a_partial_outcome_renders_the_model_text_then_one_note(self):
        for cause in ('완료하지 못한 도구 실행 — read_file: 거부', '', None):
            with self.subTest(cause=cause):
                text = AgentService.telegram_result_text(self.CLAIM, cause, 'partial', verified='찾은 파일:\n- a.txt')
                self.assertAnswerThenNote(text, '일부 단계는 확인하지 못했어요.')
                self.assertNotIn(TERMINAL_VERIFIED_LABEL, text)
        text = AgentService.telegram_result_text(self.CLAIM, None, 'partial', note='한 단계는 확인하지 못했어요.')
        self.assertAnswerThenNote(text, '한 단계는 확인하지 못했어요.')

    def test_a_withheld_answer_never_renders_the_model_text(self):
        """A withheld answer reaches the renderer as ``None``; nothing of it appears."""
        for outcome in ('failed', 'partial'):
            with self.subTest(outcome=outcome):
                text = AgentService.telegram_result_text(None, '원인', outcome, note='한 단계는 확인하지 못했어요.')
                self.assertNotIn('확인하지 못했어요', text)
                self.assertIn('원인', text)
                self.assertTrue(text.endswith(TERMINAL_NEXT_ACTION), text)

    def test_an_unknown_status_keeps_the_previous_behaviour(self):
        """Statuses this rule does not know about must not change silently."""
        for status in (None, 'succeeded', 'queued', 'something-new'):
            with self.subTest(status=status):
                self.assertEqual(
                    AgentService.telegram_result_text(self.CLAIM, 'x', status), self.CLAIM)

    def test_an_empty_response_still_reports_the_failure(self):
        self.assertIn('완료하지 못했습니다',
                      AgentService.telegram_result_text('', 'cause', 'failed'))
        self.assertIn('완료하지 못했습니다',
                      AgentService.telegram_result_text('', 'cause', None))


if __name__ == '__main__':
    unittest.main()
