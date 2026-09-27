"""A failed or partial turn must not hand the owner the model's claim as the result.

TEST-FIRST-USER-01 / #472 watched a synthetic first user read, as the last
Telegram bubble of a turn whose tool call had just been refused:

    "내일 일정은 팀 회의 하나입니다."

The Work was `failed`. No calendar was read. The web card said 확인 필요 and
carried the real cause; Telegram carried the model's sentence, because
`telegram_result_text` fell back to `error` only when `response` was empty
and never saw the outcome at all (#476).

#752 (owner contract change): a failed or partial Work's AI answer reaches
the owner, but never *as* the result.  The truth header and what did not
complete come first; the model's text follows only under
`TERMINAL_ANSWER_LABEL`.  The answer is withheld on every surface (Telegram
and the web card agree) only when a state-changing action failed, was
withheld or left incomplete in that Work: the answer may claim that action
(#476, #488).  A failed read does not withhold it.

The last bubble is what people read, so these are end-to-end through
`run_one` + `deliver_one` with an injected Telegram transport, asserting on
the text that actually reached the owner.
"""
import json
import tempfile
import time
import unittest
from pathlib import Path

from personal_agent.conversation_projection import (TERMINAL_ANSWER_LABEL, TERMINAL_FAILED_HEADER,
                                                    TERMINAL_NEXT_ACTION, TERMINAL_PARTIAL_HEADER,
                                                    TERMINAL_VERIFIED_LABEL)
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import TELEGRAM_CARD_GRACE_SECONDS, AgentService
from personal_agent.quickstart_store import QuickStore
from test_agency_loop import goal_engine

CHAT = 4242
GENERATION = 'g1'


class TerminalResultTestCase(unittest.TestCase):
    """One Telegram owner, one scripted model, one recorded outbound seam."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parent))
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
            # A carded job is held back for the cancel grace window; age it past
            # that so this turn runs, without touching the window itself.
            self.service.create_task_card(job_id, message, CHAT)
            with self.store.db() as db:
                created=time.time() - TELEGRAM_CARD_GRACE_SECONDS - 1
                db.execute('UPDATE jobs SET created=? WHERE id=?',(created, job_id))
                db.execute('UPDATE telegram_task_cards SET created=? WHERE job_id=?',(created, job_id))
        self.service.run_one()
        before = len(self.sent)
        self.service.deliver_one()
        job = self.store.job(job_id)
        bubble = self.sent[before] if len(self.sent) > before else None
        return job, bubble

    def assertLabelled(self, bubble, header, cause, claim):
        """#752: header, then the cause, then the label, then the model text - in that order, once."""
        self.assertTrue(bubble.startswith(header), bubble[:60])
        self.assertLess(bubble.index(cause), bubble.index(TERMINAL_ANSWER_LABEL), bubble)
        self.assertLess(bubble.index(TERMINAL_ANSWER_LABEL), bubble.index(claim), bubble)
        self.assertEqual(bubble.count(claim), 1, 'the claim is never stated above the label')
        self.assertNotIn(TERMINAL_NEXT_ACTION, bubble)

    def card(self, job):
        return next(task for task in self.service.task_progress(job['id'])['tasks'] if task['id'] == job['id'])

    def connect_folder(self, secret='SECRET 급여 연 1억 2천'):
        root = Path(self.temp.name) / 'docs'
        root.mkdir(exist_ok=True)
        (root / 'pay.txt').write_text(secret, encoding='utf-8')
        self.service.save_roots({'paths': [str(root)]})
        return root


class FailedTurnTests(TerminalResultTestCase):
    """A failed READ does not withhold the answer (#752); it is labelled below what failed."""

    def test_a_failed_calendar_query_labels_the_claimed_schedule_after_the_failure(self):
        """#476 case 1. Calendar is not configured, so the tool refuses."""
        self.plan = [('calendar_query', {'start': '2026-09-24T00:00:00+09:00',
                                                    'end': '2026-09-25T00:00:00+09:00',
                                                    'timezone': 'Asia/Seoul'})]
        self.text = '내일 일정은 팀 회의 하나입니다.'
        job, bubble = self.ask('내일 일정 뭐 있어?')
        self.assertEqual(job['status'], 'failed', job.get('error'))
        self.assertIsNotNone(bubble)
        self.assertFalse(self.service.answer_withheld(job), 'a failed read does not withhold the answer')
        self.assertLabelled(bubble, TERMINAL_FAILED_HEADER, job['owner_cause'], '팀 회의 하나입니다')

    def test_a_failed_file_read_labels_the_claimed_summary_after_the_failure(self):
        """#476 case 4."""
        self.connect_folder()
        self.plan = [('read_file', {'root_id': 'no-such-root',
                                               'path': 'missing.txt'})]
        self.text = '출장 계획 요약: 9월 3일 출발, 9월 7일 귀국입니다.'
        job, bubble = self.ask('내 출장 계획 파일 요약해줘')
        self.assertEqual(job['status'], 'failed', job.get('error'))
        self.assertFalse(self.service.answer_withheld(job))
        self.assertLabelled(bubble, TERMINAL_FAILED_HEADER, job['owner_cause'], '9월 3일 출발')

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
        self.assertFalse(self.service.answer_withheld(job))
        self.assertLabelled(bubble, TERMINAL_PARTIAL_HEADER, job['owner_cause'], '관찰됨')


class PartialTurnTests(TerminalResultTestCase):
    def partial_turn(self, claim):
        """One tool completes, one state-changing action fails without effect -> `partial`.

        The calendar draft fails with ``needs_setup`` and ``effect: none``:
        nothing was changed, so an answer claiming the draft is withheld (#752).
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
        self.assertTrue(bubble.startswith('일부 단계만 완료했습니다.'), bubble[:60])

    def test_a_partial_turn_withholds_a_claim_of_an_action_that_did_not_run(self):
        """#476 case 2 / #752: the draft action did nothing, so the answer claiming it is withheld.

        The bubble keeps the verified portion, what did not complete and the
        next action; the text is preserved on the Work.
        """
        claim = '팀 회의 취소 초안을 만들었습니다. 승인해 주세요.'
        job, bubble = self.partial_turn(claim)
        self.assertEqual(job['status'], 'partial')
        self.assertTrue(self.service.answer_withheld(job))
        self.assertTrue(bubble.startswith(TERMINAL_PARTIAL_HEADER), bubble[:60])
        self.assertNotIn(TERMINAL_ANSWER_LABEL, bubble)
        self.assertNotIn('초안을 만들었습니다', bubble)
        self.assertTrue(bubble.endswith(TERMINAL_NEXT_ACTION), bubble)
        self.assertEqual(job['response'], claim, 'the text must be preserved, not deleted')

    def test_a_partial_turn_names_what_did_not_complete(self):
        job, bubble = self.partial_turn('초안을 만들었습니다.')
        self.assertTrue(job['error'], 'the job carries no cause to report')
        # #598 X1: the same observed cause, in owner words; the technical
        # cause with the tool id stays on the Work record for Task detail.
        self.assertTrue(job['owner_cause'])
        self.assertIn(job['owner_cause'], bubble,
                      'the bubble must carry the observed cause, not only a header')
        self.assertIn('calendar_draft_cancel', job['error'])
        self.assertNotIn('calendar_draft_cancel', bubble)
        # #752: the tool reason is cut to its first sentence in the bubble.
        self.assertIn('Google Calendar가 로컬에 구성되어 있지 않습니다.', bubble)
        self.assertNotIn('먼저 캘린더를 연결해 주세요', bubble)
        # With the answer withheld, the verified portion (#598 H1) is stated before what did not complete.
        self.assertIn(TERMINAL_VERIFIED_LABEL, bubble)
        self.assertLess(bubble.index('pay.txt'), bubble.index(job['owner_cause']))


class WithheldAnswerTests(TerminalResultTestCase):
    """#752 / #488: a failed state-changing action keeps the answer withheld on both surfaces."""

    def test_a_refused_memory_write_withholds_the_answer_on_telegram_and_the_web_card(self):
        self.plan = [('save_memory', {'memory_key': 'inferred-preference', 'content': '모델이 추론한 값'})]
        self.text = '취향을 기억해 두었습니다.'
        job, bubble = self.ask('이건 기억하지 마. 그냥 방금 이야기만 정리해 줘', card=True)
        self.assertEqual(job['status'], 'failed', job.get('error'))
        self.assertEqual(job['response'], self.text, 'withheld, not deleted')
        self.assertTrue(self.service.answer_withheld(job))
        # Telegram: header, cause, next action - no label and no claimed save.
        self.assertTrue(bubble.startswith(TERMINAL_FAILED_HEADER), bubble[:60])
        self.assertIn(job['owner_cause'], bubble)
        self.assertTrue(bubble.endswith(TERMINAL_NEXT_ACTION), bubble)
        self.assertNotIn(TERMINAL_ANSWER_LABEL, bubble)
        self.assertNotIn('기억해 두었습니다', bubble)
        # The web card agrees: no result is offered.
        card = self.card(job)
        self.assertEqual(card['status_label'], '확인 필요')
        self.assertFalse(card['result_available'])
        self.assertEqual(self.store.memories(), [])

    def test_the_same_failed_status_with_only_a_failed_read_is_not_withheld(self):
        """The opposing pin: the status alone never decides withholding."""
        self.plan = [('calendar_query', {'start': '2026-09-24T00:00:00+09:00',
                                         'end': '2026-09-25T00:00:00+09:00', 'timezone': 'Asia/Seoul'})]
        self.text = '내일 일정은 팀 회의 하나입니다.'
        job, bubble = self.ask('내일 일정 뭐 있어?')
        self.assertEqual(job['status'], 'failed')
        self.assertFalse(self.service.answer_withheld(job))
        self.assertTrue(self.card(job)['result_available'])
        self.assertIn(TERMINAL_ANSWER_LABEL, bubble)


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
        self.assertLabelled(bubble, TERMINAL_FAILED_HEADER, job['owner_cause'], self.text)
        # ...and the cause the web card carries is the one Telegram carries,
        # Telegram in owner words (#598 X1) and the card with the exact id.
        self.assertEqual(card['error'], job['error'])
        self.assertIn(job['owner_cause'], bubble)
        self.assertIn(job['error'].split(': ', 1)[1].split('. ')[0], bubble)
        self.assertNotIn('calendar_query', bubble)

    def test_a_partial_turn_agrees_across_both_surfaces(self):
        """Both surfaces withhold a claim of an action that did not run, and both flag attention (#752)."""
        self.connect_folder()
        self.plan = [('find_files', {'query': '급여'}),
                     ('calendar_draft_cancel', {'event_id': 'ev1',
                                                'event_version': '"etag1"'})]
        self.text = '취소 초안을 만들었습니다.'
        job, bubble = self.ask('내일 팀 회의 취소해줘')
        self.assertEqual(job['status'], 'partial')
        card = self.card(job)
        self.assertEqual(card['status_label'], '확인 필요')
        self.assertFalse(card['result_available'], 'the web withholds it exactly as Telegram does')
        self.assertEqual(card['error'], job['error'])
        self.assertNotIn(self.text, bubble)
        self.assertNotIn(TERMINAL_ANSWER_LABEL, bubble)

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
        self.assertNotIn(self.text, bubble)

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
        text = AgentService.telegram_result_text('모두 처리했습니다.', '중단됨', 'interrupted')
        self.assertNotIn('모두 처리했습니다', text)
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
        _job, bubble = self.ask('내일 일정 뭐 있어?')
        self.assertIn(TERMINAL_ANSWER_LABEL, bubble)
        self.assertNotIn('다음 단계를 확인하세요', bubble)


class UnsupportedTextNeverTerminalTests(TerminalResultTestCase):
    """The general property, stated directly on the renderer.

    The end-to-end cases above each pin one scenario. This pins the rule they
    share, so a future scenario nobody wrote a test for is covered too: the
    model text of a failed/partial turn appears only after the truth header,
    the cause and `TERMINAL_ANSWER_LABEL` (#752).
    """

    CLAIM = '일정을 만들었고 메일도 보냈습니다.'

    def assertOnlyAfterTheLabel(self, text, header, cause):
        self.assertTrue(text.startswith(header), text)
        label = text.index(TERMINAL_ANSWER_LABEL)
        self.assertNotIn(self.CLAIM, text[:label])
        self.assertTrue(text.endswith(TERMINAL_ANSWER_LABEL + '\n' + self.CLAIM), text)
        if cause:
            self.assertLess(text.index(cause), label)
        self.assertNotIn(TERMINAL_NEXT_ACTION, text)

    def test_a_failed_outcome_renders_the_model_text_only_after_the_label(self):
        for cause in ('완료하지 못한 도구 실행 — calendar_query: 거부', '', None):
            with self.subTest(cause=cause):
                text = AgentService.telegram_result_text(self.CLAIM, cause, 'failed')
                self.assertIn('완료하지 못했습니다', text)
                self.assertOnlyAfterTheLabel(text, TERMINAL_FAILED_HEADER, cause)

    def test_a_partial_outcome_renders_the_model_text_only_after_the_label(self):
        for cause in ('완료하지 못한 도구 실행 — read_file: 거부', '', None):
            with self.subTest(cause=cause):
                text = AgentService.telegram_result_text(self.CLAIM, cause, 'partial', verified='찾은 파일:\n- a.txt')
                self.assertIn('일부 단계만 완료했습니다', text)
                self.assertOnlyAfterTheLabel(text, TERMINAL_PARTIAL_HEADER, cause)
                self.assertNotIn(TERMINAL_VERIFIED_LABEL, text)

    def test_a_withheld_answer_never_renders_the_model_text(self):
        """A withheld answer reaches the renderer as ``None``; nothing of it appears."""
        for outcome in ('failed', 'partial'):
            with self.subTest(outcome=outcome):
                text = AgentService.telegram_result_text(None, '원인', outcome)
                self.assertNotIn(TERMINAL_ANSWER_LABEL, text)
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
