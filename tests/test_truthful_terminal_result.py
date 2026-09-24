"""A failed or partial turn must not hand the owner the model's claim as the result.

TEST-FIRST-USER-01 / #472 watched a synthetic first user read, as the last
Telegram bubble of a turn whose tool call had just been refused:

    "내일 일정은 팀 회의 하나입니다."

The Work was `failed`. No calendar was read. The web card said 확인 필요 and
carried the real cause; Telegram carried the model's sentence, because
`telegram_result_text` fell back to `error` only when `response` was empty
and never saw the outcome at all (#476).

The last bubble is what people read, so these are end-to-end through
`run_one` + `deliver_one` with an injected Telegram transport, asserting on
the text that actually reached the owner.
"""
import json
import tempfile
import time
import unittest
from pathlib import Path

from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import TELEGRAM_CARD_GRACE_SECONDS, AgentService
from personal_agent.quickstart_store import QuickStore

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
            return {'message': {'content': self.text}}

        self.service = AgentService(self.store, ModelAdapter(model), transport)
        self.service.save_model({'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434',
                                 'model': 'test-model', 'api_key': ''})
        self.assertTrue(self.service.test_model()['ok'])
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT,
                                    'generation': GENERATION})

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

    def connect_folder(self, secret='SECRET 급여 연 1억 2천'):
        root = Path(self.temp.name) / 'docs'
        root.mkdir(exist_ok=True)
        (root / 'pay.txt').write_text(secret, encoding='utf-8')
        self.service.save_roots({'paths': [str(root)]})
        return root


class FailedTurnTests(TerminalResultTestCase):
    def test_a_failed_calendar_query_does_not_deliver_a_claimed_schedule(self):
        """#476 case 1. Calendar is not configured, so the tool refuses."""
        self.plan = [('calendar_query', {'start': '2026-09-24T00:00:00+09:00',
                                                    'end': '2026-09-25T00:00:00+09:00',
                                                    'timezone': 'Asia/Seoul'})]
        self.text = '내일 일정은 팀 회의 하나입니다.'
        job, bubble = self.ask('내일 일정 뭐 있어?')
        self.assertIn(job['status'], ('failed', 'partial'), job['status'])
        self.assertIsNotNone(bubble)
        self.assertNotIn('팀 회의 하나입니다', bubble,
                         'the model claimed a schedule the tool never read')

    def test_a_failed_file_read_does_not_deliver_a_claimed_summary(self):
        """#476 case 4."""
        self.connect_folder()
        self.plan = [('read_file', {'root_id': 'no-such-root',
                                               'path': 'missing.txt'})]
        self.text = '출장 계획 요약: 9월 3일 출발, 9월 7일 귀국입니다.'
        job, bubble = self.ask('내 출장 계획 파일 요약해줘')
        self.assertIn(job['status'], ('failed', 'partial'), job['status'])
        self.assertNotIn('9월 3일 출발', bubble,
                         'the model summarised a file it never read')

    def test_a_refused_research_request_does_not_deliver_a_comparison(self):
        """#476 case 3 — the #448 refusal, then an apparent answer."""
        root = self.connect_folder()
        self.plan = [
            ('find_files', {'query': '급여'}),
            ('bounded_public_research', {'mode': 'product_comparison',
                                                    'query': 'noise cancelling headphones'}),
        ]
        self.text = '관찰됨: Model A 30시간 재생. 확인되지 않음: 가격·재고.'
        job, bubble = self.ask('노이즈캔슬링 헤드폰 비교해줘')
        self.assertIn(job['status'], ('failed', 'partial'), job['status'])
        self.assertNotIn('관찰됨', bubble,
                         'research was refused; the model still reported a comparison')


class PartialTurnTests(TerminalResultTestCase):
    def partial_turn(self, claim):
        """One tool completes, one is refused -> `partial`."""
        self.connect_folder()
        self.plan = [
            ('find_files', {'query': '급여'}),          # succeeds
            ('calendar_draft_cancel', {'event_id': 'ev1',
                                                  'event_version': '"etag1"'}),  # refused
        ]
        self.text = claim
        return self.ask('내일 팀 회의 취소해줘')

    def test_a_partial_turn_is_not_announced_as_a_completed_result(self):
        """#476 case 2. The model said a draft existed; none was created."""
        job, bubble = self.partial_turn('팀 회의 취소 초안을 만들었습니다. 승인해 주세요.')
        self.assertEqual(job['status'], 'partial', job.get('error'))
        self.assertNotIn('처리가 끝났습니다', bubble)
        self.assertTrue(bubble.startswith('일부 단계만 완료했습니다.'), bubble[:60])

    def test_a_partial_turn_does_not_push_the_unverified_text_at_the_owner(self):
        """Kept, but not delivered as the answer.

        An earlier version of this fix showed the text under an "unverified"
        marker. The research case killed that: `find_files` completed and
        `bounded_public_research` was refused, so the comparison the model
        wrote rested on *nothing* that completed, and a label does not make
        it exposable. Which sentence rests on the completed tool cannot be
        decided here, so the bubble reports the outcome and points at the
        record instead.

        The text is not destroyed -- it stays in `response` and the web card
        still offers it under 확인 필요.
        """
        claim = '팀 회의 취소 초안을 만들었습니다. 승인해 주세요.'
        job, bubble = self.partial_turn(claim)
        self.assertEqual(job['status'], 'partial')
        self.assertNotIn(claim, bubble)
        self.assertIn('확인된 결과가 아니므로', bubble)
        self.assertEqual(job['response'], claim, 'the text must be preserved, not deleted')

    def test_a_partial_turn_names_what_did_not_complete(self):
        job, bubble = self.partial_turn('초안을 만들었습니다.')
        self.assertTrue(job['error'], 'the job carries no cause to report')
        self.assertIn(job['error'], bubble,
                      'the bubble must carry the observed cause, not only a header')


class SucceededTurnTests(TerminalResultTestCase):
    def test_a_succeeded_turn_still_delivers_the_model_answer_unchanged(self):
        """The opposing pin. Without it, refusing everything passes this file."""
        self.connect_folder()
        self.plan = [('find_files', {'query': '급여'})]
        self.text = '급여 파일 한 건을 찾았습니다.'
        job, bubble = self.ask('급여 파일 찾아줘')
        self.assertEqual(job['status'], 'succeeded', job.get('error'))
        self.assertEqual(bubble, self.text)

    def test_a_turn_with_no_tool_call_is_unaffected(self):
        self.text = '안녕하세요. 무엇을 도와드릴까요?'
        job, bubble = self.ask('안녕')
        self.assertEqual(job['status'], 'succeeded', job.get('error'))
        self.assertEqual(bubble, self.text)


class SurfaceConsistencyTests(TerminalResultTestCase):
    def test_telegram_shows_no_result_exactly_where_the_web_offers_none(self):
        """The two surfaces disagreed, and that was the defect.

        `task_progress` sets `result_available` False for `failed` and True
        for `partial`. Telegram used to deliver the model's text for both.
        """
        self.plan = [('calendar_query', {'start': '2026-09-24T00:00:00+09:00',
                                                    'end': '2026-09-25T00:00:00+09:00',
                                                    'timezone': 'Asia/Seoul'})]
        self.text = '내일 일정은 팀 회의 하나입니다.'
        job, bubble = self.ask('내일 일정 뭐 있어?')
        card = next(task for task in self.service.task_progress(job['id'])['tasks']
                    if task['id'] == job['id'])
        self.assertEqual(card['status_label'], '확인 필요')
        self.assertFalse(card['result_available'])
        self.assertNotIn(self.text, bubble)
        # ...and the cause the web card carries is the one Telegram carries.
        self.assertEqual(card['error'], job['error'])
        self.assertIn(job['error'], bubble)

    def test_a_partial_turn_agrees_across_both_surfaces(self):
        """Neither surface presents the text as the answer; both flag attention.

        They differ in one deliberate way: the web still *offers* the text
        behind 확인 필요 (`result_available` stays True for `partial`, so
        nothing is destroyed and the owner can read it on purpose), while
        Telegram does not push it into the bubble. That is the distinction
        between preserving useful text and asserting it.
        """
        self.connect_folder()
        self.plan = [('find_files', {'query': '급여'}),
                     ('calendar_draft_cancel', {'event_id': 'ev1',
                                                'event_version': '"etag1"'})]
        self.text = '취소 초안을 만들었습니다.'
        job, bubble = self.ask('내일 팀 회의 취소해줘')
        self.assertEqual(job['status'], 'partial')
        card = next(task for task in self.service.task_progress(job['id'])['tasks']
                    if task['id'] == job['id'])
        self.assertEqual(card['status_label'], '확인 필요')
        self.assertTrue(card['result_available'], 'the web must still offer the text')
        self.assertEqual(card['error'], job['error'])
        self.assertNotIn(self.text, bubble, 'Telegram must not push it as the answer')

    def test_the_card_above_a_partial_bubble_does_not_announce_a_result(self):
        """Independent review of #486 found the bubble alone was not enough.

        The task card sits directly above it and `update_task_card` is called
        with the same outcome, so a partial turn was edited to read
        '처리가 끝났습니다. 아래 결과를 확인하세요.' -- the exact framing #476
        is about -- above a bubble that then declines to show any result.
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
        job, bubble = self.ask('급여 파일 찾아줘', card=True)
        self.assertEqual(job['status'], 'succeeded', job.get('error'))
        self.assertEqual(self.cards[-1], '처리가 끝났습니다. 아래 결과를 확인하세요.')
        self.assertEqual(bubble, self.text)

    def test_an_interrupted_turn_claims_no_completed_step_and_no_web_result(self):
        """`interrupted` is set on any restarted running job, even a no-tool one.

        `task_progress` offers the stored text for succeeded/partial only, so
        the bubble must not point the owner at a web result that is not there,
        and must not claim steps completed that may never have run.
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

        `result_available` is `bool(response) and status in (succeeded, partial)`,
        so a partial turn whose model returned nothing has no web result to
        offer, and the bubble must not send the owner to look for one.
        """
        for response in ('', '   ', None):
            with self.subTest(response=response):
                text = AgentService.telegram_result_text(response, '원인', 'partial')
                self.assertEqual(text, '일부 단계만 완료했습니다.\n\n원인'
                                 '\n\nAgentOS 웹에서 실행 기록과 다음 단계를 확인하세요.')

    def test_the_failure_bubble_offers_a_next_action(self):
        self.plan = [('calendar_query', {'start': '2026-09-24T00:00:00+09:00',
                                                    'end': '2026-09-25T00:00:00+09:00',
                                                    'timezone': 'Asia/Seoul'})]
        self.text = '내일 일정은 팀 회의 하나입니다.'
        _job, bubble = self.ask('내일 일정 뭐 있어?')
        self.assertIn('다음 단계를 확인하세요', bubble)


class UnsupportedTextNeverTerminalTests(TerminalResultTestCase):
    """The general property, stated directly on the renderer.

    The end-to-end cases above each pin one scenario. This pins the rule they
    share, so a future scenario nobody wrote a test for is covered too.
    """

    CLAIM = '일정을 만들었고 메일도 보냈습니다.'

    def test_a_failed_outcome_never_renders_the_model_text(self):
        for cause in ('완료하지 못한 도구 실행 — calendar_query: 거부', '', None):
            with self.subTest(cause=cause):
                text = AgentService.telegram_result_text(self.CLAIM, cause, 'failed')
                self.assertNotIn(self.CLAIM, text)
                self.assertIn('완료하지 못했습니다', text)

    def test_a_partial_outcome_never_renders_the_model_text(self):
        for cause in ('완료하지 못한 도구 실행 — read_file: 거부', '', None):
            with self.subTest(cause=cause):
                text = AgentService.telegram_result_text(self.CLAIM, cause, 'partial')
                self.assertNotIn(self.CLAIM, text)
                self.assertIn('일부 단계만 완료했습니다', text)

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
