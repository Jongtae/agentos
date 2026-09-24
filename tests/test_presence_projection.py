"""PRESENCE-CONV-01 / #510: owner-visible conversation projection.

Transcript fixtures through the real Telegram ingest path with a recorded
outbound seam.  Every assertion is about what the paired owner would see -
bubble count and order, sends vs edits - mapped to the Work/Event state
underneath.  Evidence class: automated synthetic/fixture only.  The
scripted model and fixture DecisionEngine stand in for providers; nothing
here claims live behavior.
"""
import tempfile
import time
import unittest
from pathlib import Path

from personal_agent.conversation_handoff import INTENT_UNSUPPORTED, UNSUPPORTED_CAPABILITY_TEXT
from personal_agent.conversation_projection import (BLOCKER_NO_AI_ROUTE, TERMINAL_FAILED_HEADER,
                                                    TERMINAL_PARTIAL_HEADER, terminal_text)
from personal_agent.decision import (OUTCOME_DECIDED, FixtureDecisionEngine, SelectionDecision,
                                     fixture_confidence)
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import TELEGRAM_ACK_AFTER_SECONDS, AgentService
from personal_agent.quickstart_store import QuickStore

CHAT = 4242
GENERATION = 'g1'
#: Names that must never become the assistant's speaking identity.
INTERNAL_IDENTITIES = ('ollama', 'test-model', 'codex', 'claude', 'gpt', 'google-gmail', 'google-calendar',
                       'find_files', 'web_search', 'subscription', 'mcp')


class ProjectionTestCase(unittest.TestCase):
    """One paired owner, one scripted model, every outbound Telegram call recorded."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parent))
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(Path(self.temp.name) / 'data')
        self.outbound = []      # ('send'|'edit', text) in the order the owner would see them
        self.text = '완료했습니다.'
        self.plan = []
        self.update_id = 100

        def transport(url, body=None, headers=None, timeout=60):
            if url.endswith('/sendMessage'):
                self.outbound.append(('send', body['text']))
                return {'ok': True, 'result': {'message_id': len(self.outbound)}}
            if url.endswith('/editMessageText'):
                self.outbound.append(('edit', body['text']))
                return {'ok': True, 'result': {'message_id': body['message_id']}}
            if url.endswith('/getMe'):
                return {'ok': True, 'result': {'username': 'owner_test_bot'}}
            return {'ok': True, 'result': {}}

        def model(url, body, headers=None, timeout=60):
            tools = [t.get('function', {}).get('name') or t.get('name') for t in body.get('tools', [])]
            if 'agentos_connection_probe' in tools:
                return {'message': {'content': '', 'tool_calls': [
                    {'id': 'probe', 'function': {'name': 'agentos_connection_probe', 'arguments': {}}}]}}
            if self.plan:
                name, arguments = self.plan.pop(0)
                return {'message': {'content': '', 'tool_calls': [
                    {'id': f'call-{len(self.plan)}', 'function': {'name': name, 'arguments': arguments}}]}}
            return {'message': {'content': self.text}}

        self.transport, self.model_transport = transport, model
        self.service = AgentService(self.store, ModelAdapter(model), transport)
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': GENERATION, 'cursor': 0})

    def connect_model(self):
        self.service.save_model({'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434',
                                 'model': 'test-model', 'api_key': ''})
        self.assertTrue(self.service.test_model()['ok'])

    def receive(self, text):
        """The owner sends one Telegram message; returns the job id."""
        self.update_id += 1
        self.service.ingest_update({'update_id': self.update_id, 'message': {
            'from': {'id': CHAT}, 'chat': {'id': CHAT, 'type': 'private'}, 'text': text}}, GENERATION)
        return self.store.jobs()[0]['id']

    def turn(self, text):
        """One complete owner turn: receive, run, deliver.  Returns (job, bubbles)."""
        before = len(self.outbound)
        job_id = self.receive(text)
        self.service.run_one()
        self.service.deliver_one()
        return self.store.job(job_id), self.outbound[before:]

    def age(self, job_id, seconds):
        with self.store.db() as db:
            db.execute('UPDATE jobs SET created=? WHERE id=?', (time.time() - seconds, job_id))

    def assistant_messages(self, job_id):
        with self.store.db() as db:
            return [row['content'] for row in db.execute(
                "SELECT content FROM messages WHERE job_id=? AND role='assistant' ORDER BY id", (job_id,))]

    def assertOneVoice(self, bubbles):
        for _kind, text in bubbles:
            lowered = text.casefold()
            for name in INTERNAL_IDENTITIES:
                self.assertNotIn(name, lowered, f'{name!r} must not speak to the owner: {text!r}')


class ShortWorkTests(ProjectionTestCase):
    """Matrix row A: a trivial request → one useful answer, no lifecycle bubbles."""

    def test_a_short_request_is_one_bubble_and_still_one_inspectable_work(self):
        self.connect_model()
        self.text = '오늘 오후에는 비 소식이 없습니다.'
        job, bubbles = self.turn('오늘 오후 날씨 어때?')
        self.assertEqual(bubbles, [('send', self.text)])
        self.assertOneVoice(bubbles)
        # The kernel record is intact: Work succeeded, transcript rows exist, no card was ever sent.
        self.assertEqual(job['status'], 'succeeded')
        self.assertEqual(self.assistant_messages(job['id']), [self.text])
        self.assertIsNone(self.store.task_card(job['id']))
        self.assertEqual(self.store.job(job['id'])['delivery'], 'sent')

    def test_no_acknowledgement_is_sent_for_work_that_finished_in_time(self):
        self.connect_model()
        job, _bubbles = self.turn('짧은 질문')
        self.assertEqual(self.service.acknowledge_long_work(now=time.time() + TELEGRAM_ACK_AFTER_SECONDS + 1), [])
        self.assertIsNone(self.store.task_card(job['id']))


class LongWorkTests(ProjectionTestCase):
    """Matrix row G: one acknowledgement, then only owner-relevant changes."""

    def test_long_work_gets_one_card_then_the_answer_and_no_per_event_edits(self):
        self.connect_model()
        # Three tool events in one turn; the owner must not see three updates.
        self.plan = [('web_search', {'query': '제주 항공권'}), ('web_search', {'query': '제주 숙소'}),
                     ('web_search', {'query': '제주 렌터카'})]
        self.text = '항공권, 숙소, 렌터카를 비교한 결과입니다.'
        job_id = self.receive('제주 여행 준비 자료 조사해줘')
        self.assertEqual(self.outbound, [], 'nothing is said when the request arrives')
        # The Work is still waiting after the acknowledgement delay (the worker was busy).
        self.age(job_id, TELEGRAM_ACK_AFTER_SECONDS + 1)
        self.assertEqual(self.service.acknowledge_long_work(), [job_id])
        self.assertEqual(self.outbound, [('send', '요청을 받았습니다. 곧 시작할게요.')])
        self.assertEqual(self.service.acknowledge_long_work(), [], 'acknowledged once')
        self.service.run_one()
        self.service.deliver_one()
        job = self.store.job(job_id)
        self.assertEqual(job['status'], 'succeeded', job.get('error'))
        with self.store.db() as db:
            events = db.execute("SELECT COUNT(*) AS n FROM tool_events WHERE job_id=? AND tool!='model'", (job_id,)).fetchone()['n']
        self.assertGreaterEqual(events, 3, 'the Events exist internally')
        kinds = [kind for kind, _ in self.outbound]
        # Card, its two state edits (running: the cancel button goes away;
        # terminal), and the answer.  Event count did not become message count.
        self.assertEqual(self.outbound[0], ('send', '요청을 받았습니다. 곧 시작할게요.'))
        self.assertEqual(self.outbound[-1][0], 'send')
        self.assertTrue(self.outbound[-1][1].startswith(self.text), self.outbound[-1][1])
        self.assertEqual(kinds.count('send'), 2)
        self.assertLessEqual(kinds.count('edit'), 2)
        self.assertOneVoice(self.outbound)

    def test_the_acknowledgement_reflects_running_work_and_offers_no_cancel(self):
        self.connect_model()
        job_id = self.receive('진행 중인 긴 요청')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job_id,))
        self.age(job_id, TELEGRAM_ACK_AFTER_SECONDS + 1)
        self.assertEqual(self.service.acknowledge_long_work(), [job_id])
        self.assertEqual(self.outbound, [('send', '요청을 처리하고 있어요.')])
        self.assertEqual(self.store.task_card(job_id)['state'], 'running')

    def test_only_this_owner_s_natural_language_work_is_acknowledged(self):
        other = self.store.enqueue('web request', 'web-1', channel='web')
        command = self.receive('/notes')
        self.age(other, 60)
        self.age(command, 60)
        self.assertEqual(self.service.acknowledge_long_work(), [])
        self.assertEqual(self.outbound, [])


class BlockedTurnTests(ProjectionTestCase):
    """Matrix row B and #477: a truthful failure with a next action, said once."""

    def test_no_ai_route_gets_one_useful_answer_then_a_reminder(self):
        job, bubbles = self.turn('안녕, 뭐 할 수 있어?')
        self.assertEqual(job['status'], 'failed', 'the Work did not run; that stays true')
        self.assertEqual(len(bubbles), 1)
        first = bubbles[0][1]
        self.assertIn('아직 AI가 연결되지 않아', first)
        self.assertIn('메모', first)
        self.assertIn('AgentOS 설정', first)
        self.assertNotIn('구독 엔진', first)
        self.assertNotIn('/note', first)
        self.assertNotIn(TERMINAL_FAILED_HEADER, first, 'the projected reply is the whole bubble')
        self.assertNotIn('AgentOS 웹에서 실행 기록', first, 'the web console is not the default next action')
        # The same blocker again: one short reminder, not the same failure again.
        job2, bubbles2 = self.turn('그럼 내일 일정은?')
        self.assertEqual(job2['status'], 'failed')
        self.assertEqual(len(bubbles2), 1)
        self.assertLess(len(bubbles2[0][1]), len(first))
        self.assertIn('AI가 아직 연결되지 않아', bubbles2[0][1])
        self.assertEqual(self.store.config('conversation_blocker')[f'telegram:{CHAT}']['kind'], BLOCKER_NO_AI_ROUTE)
        # Resolving the blocker resets it: after a successful turn the full explanation would return.
        self.connect_model()
        job3, bubbles3 = self.turn('이제 되니?')
        self.assertEqual(job3['status'], 'succeeded')
        self.assertEqual(bubbles3, [('send', self.text)])
        self.assertNotIn(f'telegram:{CHAT}', self.store.config('conversation_blocker', {}))
        self.assertOneVoice(bubbles + bubbles2 + bubbles3)

    def test_the_transcript_shows_the_projected_reply_and_the_task_keeps_the_plain_cause(self):
        job, bubbles = self.turn('도와줘')
        self.assertEqual(self.assistant_messages(job['id']), [bubbles[0][1]])
        # Task/Evidence detail keeps the technical cause; the conversation does not lead with it.
        self.assertIn('모델 또는 구독 엔진', job['error'])
        self.assertNotIn('구독 엔진', bubbles[0][1])

    def test_a_pending_delivery_after_restart_falls_back_to_the_generic_truthful_text(self):
        job_id = self.receive('도와줘')
        self.service.run_one()
        restarted = AgentService(QuickStore(Path(self.temp.name) / 'data'), ModelAdapter(self.model_transport), self.transport)
        before = len(self.outbound)
        restarted.deliver_one()
        text = self.outbound[before][1]
        # The process-local projection is gone; the generic truthful bubble goes out instead.
        self.assertTrue(text.startswith(TERMINAL_FAILED_HEADER))
        self.assertIn('모델 또는 구독 엔진', text)


class UnsupportedCapabilityTests(ProjectionTestCase):
    """#478: a request for something not offered is understood, not searched."""

    def judged(self, mapping):
        engine = FixtureDecisionEngine(choose=lambda context, candidates, question: SelectionDecision(
            OUTCOME_DECIDED, mapping.get(context.facts.get('owner_message'), 'none-of-these'),
            candidates, fixture_confidence()) if context.purpose == 'unsupported-capability' else None)
        self.service.use_decision_engine(engine)
        return engine

    def test_reply_and_read_body_requests_get_the_truthful_boundary_and_run_nothing(self):
        engine = self.judged({'예약 확인 메일에 답장 보내줘': 'mail-send', '그 메일 내용 좀 보여줘': 'mail-read-body'})
        for text, key in (('예약 확인 메일에 답장 보내줘', 'mail-send'), ('그 메일 내용 좀 보여줘', 'mail-read-body')):
            with self.subTest(text=text):
                decision = self.service.classify_intent(text)
                self.assertEqual(decision.intent, INTENT_UNSUPPORTED)
                self.assertFalse(decision.executes)
                job, bubbles = self.turn(text)
                self.assertEqual(job['status'], 'succeeded', 'a truthful boundary answer is a completed turn')
                self.assertEqual(bubbles, [('send', UNSUPPORTED_CAPABILITY_TEXT[key])])
        self.assertTrue(all(item[0] == 'choose' for item in engine.asked))

    def test_a_none_of_these_judgment_leaves_the_cues_to_decide(self):
        self.judged({})
        decision = self.service.classify_intent('메일에서 예산 관련 내용 찾아줘')
        self.assertEqual(decision.intent, 'mail-search')

    def test_without_a_provider_the_cues_decide_as_before(self):
        # Unavailable judgment: the pre-existing rule still claims the search.
        decision = self.service.classify_intent('예약 확인 메일에 답장 보내줘')
        self.assertEqual(decision.intent, 'mail-search')


class TerminalTextTests(unittest.TestCase):
    """Rows H/I at the renderer level; transcript-level partial cases live in
    tests/test_truthful_terminal_result.py (#476) and are unchanged."""

    def test_partial_separates_verified_from_unverified_and_keeps_the_truth_header(self):
        text = terminal_text('모델이 쓴 문장', '캘린더 조회 거부', 'partial')
        self.assertTrue(text.startswith(TERMINAL_PARTIAL_HEADER))
        self.assertIn('캘린더 조회 거부', text)
        self.assertNotIn('모델이 쓴 문장', text)

    def test_a_specific_next_action_replaces_only_the_web_pointer(self):
        text = terminal_text(None, '연결이 끊어졌습니다', 'failed', next_action='다시 연결한 뒤 같은 요청을 보내 주세요.')
        self.assertEqual(text, TERMINAL_FAILED_HEADER + '\n\n연결이 끊어졌습니다\n\n다시 연결한 뒤 같은 요청을 보내 주세요.')


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
