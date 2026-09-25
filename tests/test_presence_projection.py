"""PRESENCE-CONV-01 / #510: owner-visible conversation projection.

Transcript fixtures through the real Telegram ingest path with a recorded
outbound seam.  Every assertion is about what the paired owner would see -
bubble count and order, sends vs edits - mapped to the Work/Event state
underneath.  Evidence class: automated synthetic/fixture only.  The
scripted model and fixture DecisionEngine stand in for providers; nothing
here claims live behavior.
"""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from personal_agent.conversation_handoff import (FOLLOWUP_REFERENCE, FOLLOWUP_RETRY,
                                                    INTENT_UNSUPPORTED, UNSUPPORTED_CAPABILITY_TEXT)
from personal_agent.conversation_projection import (BLOCKER_NO_AI_ROUTE, TERMINAL_FAILED_HEADER,
                                                    TERMINAL_PARTIAL_HEADER, terminal_text)
from personal_agent.decision import (OUTCOME_DECIDED, FixtureDecisionEngine, SelectionDecision,
                                     UnavailableDecisionEngine, fixture_confidence)
from personal_agent.providers import ModelAdapter, ProviderError
from personal_agent.quickstart_service import (TELEGRAM_ACK_AFTER_SECONDS, TELEGRAM_CARD_GRACE_SECONDS,
                                               AgentService)
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

    def age_card(self, job_id, seconds):
        with self.store.db() as db:
            db.execute('UPDATE telegram_task_cards SET created=? WHERE job_id=?',
                       (time.time() - seconds, job_id))

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
        # This test asserts conversation/card projection, not live search
        # availability. Keep its three tool Events deterministic and offline.
        self.service.local_tools = SimpleNamespace(execute=lambda plan: {
            'results': [{'title': 'fixture', 'url': 'https://example.test/result', 'snippet': 'fixture result'}],
            'sources': ['https://example.test/result'], 'retrieved_at': time.time(),
        })
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
        self.age_card(job_id, TELEGRAM_CARD_GRACE_SECONDS + 1)
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

    def test_running_work_gets_native_presence_and_no_processing_card(self):
        """#581 replaces the running-Work card with typing/draft presence."""
        self.connect_model()
        job_id = self.receive('진행 중인 긴 요청')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job_id,))
        self.age(job_id, TELEGRAM_ACK_AFTER_SECONDS + 1)
        self.assertEqual(self.service.acknowledge_long_work(), [])
        self.assertEqual(self.outbound, [], 'no "요청을 처리하고 있어요" bubble')
        self.assertIsNone(self.store.task_card(job_id))

    def test_only_this_owner_s_natural_language_work_is_acknowledged(self):
        other = self.store.enqueue('web request', 'web-1', channel='web')
        command = self.receive('/notes')
        self.age(other, 60)
        self.age(command, 60)
        self.assertEqual(self.service.acknowledge_long_work(), [])
        self.assertEqual(self.outbound, [])

    def test_card_is_reconciled_if_work_finishes_while_telegram_accepts_it(self):
        self.connect_model()
        job_id = self.receive('긴 요청을 처리해 줘')
        self.age(job_id, TELEGRAM_ACK_AFTER_SECONDS + 1)
        original = self.service.telegram_transport
        raced = False
        delivery_thread = None

        def transport(url, body=None, headers=None, timeout=60):
            nonlocal raced, delivery_thread
            if url.endswith('/editMessageText') and body.get('message_id') == -1:
                raise ProviderError('card reservation has no remote message id yet')
            if (not raced and url.endswith('/sendMessage')
                    and body.get('text') == '요청을 받았습니다. 곧 시작할게요.'):
                raced = True
                # Model the Work finishing during Telegram's send.
                with self.store.db() as db:
                    db.execute("UPDATE jobs SET status='succeeded',response=?,delivery='pending' WHERE id=?",
                               (self.text,job_id))
                self.service.update_task_card(self.store.job(job_id),'succeeded')
                delivery_thread = threading.Thread(target=self.service.deliver_one)
                delivery_thread.start()
                delivery_thread.join(timeout=0.05)
                self.assertTrue(delivery_thread.is_alive(), 'terminal delivery waits for card reconciliation')
            return original(url, body, headers, timeout)

        self.service.telegram_transport = transport
        self.assertEqual(self.service.acknowledge_long_work(), [job_id])
        delivery_thread.join(timeout=2)
        self.assertFalse(delivery_thread.is_alive())
        self.assertEqual(self.store.job(job_id)['status'], 'succeeded')
        self.assertEqual(self.store.task_card(job_id)['state'], 'succeeded', self.outbound)
        self.assertEqual([kind for kind, _text in self.outbound], ['send', 'edit', 'send'])
        self.assertEqual(self.outbound[0][1], '요청을 받았습니다. 곧 시작할게요.')
        self.assertEqual(self.outbound[1][1], '요청을 처리했어요.')
        self.assertTrue(self.outbound[2][1].startswith(self.text))

    def test_in_flight_card_reservation_is_not_expired_by_the_grace_check(self):
        job_id = self.receive('오래 걸릴 요청')
        self.age(job_id, TELEGRAM_ACK_AFTER_SECONDS + 1)
        original = self.service.telegram_transport
        attempted = []

        def transport(url, body=None, headers=None, timeout=60):
            if url.endswith('/sendMessage') and body.get('text') == '요청을 받았습니다. 곧 시작할게요.':
                with self.store.db() as db:
                    db.execute('UPDATE telegram_task_cards SET created=? WHERE job_id=?',
                               (time.time() - TELEGRAM_CARD_GRACE_SECONDS - 1, job_id))
                attempted.append(self.service.run_one())
            return original(url, body, headers, timeout)

        self.service.telegram_transport = transport
        self.assertEqual(self.service.acknowledge_long_work(), [job_id])
        self.assertEqual(attempted, [False])
        self.assertEqual(self.store.job(job_id)['status'], 'queued')

    def test_uncertain_card_send_is_not_retried_and_does_not_strand_work(self):
        job_id = self.receive('오래 걸릴 요청')
        self.age(job_id, TELEGRAM_ACK_AFTER_SECONDS + 1)
        sends = []

        def uncertain(url, body=None, headers=None, timeout=60):
            if url.endswith('/sendMessage'):
                sends.append(body['text'])
                raise ProviderError('response lost')
            return self.transport(url, body, headers, timeout)

        self.service.telegram_transport = uncertain
        self.assertEqual(self.service.acknowledge_long_work(), [])
        card = self.store.task_card(job_id)
        self.assertEqual(card['message_id'], -2)
        self.assertEqual(self.service.acknowledge_long_work(), [])
        self.assertEqual(len(sends), 1)
        self.age_card(job_id, TELEGRAM_CARD_GRACE_SECONDS + 1)
        self.assertTrue(self.service.run_one(), 'unknown acknowledgement must not block the queued Work')

    def test_uncertain_card_can_be_adopted_from_owner_cancel_callback(self):
        job_id = self.receive('오래 걸릴 요청')
        self.age(job_id, TELEGRAM_ACK_AFTER_SECONDS + 1)

        def uncertain(url, body=None, headers=None, timeout=60):
            if url.endswith('/sendMessage'):
                raise ProviderError('response lost')
            return self.transport(url, body, headers, timeout)

        self.service.telegram_transport = uncertain
        self.assertEqual(self.service.acknowledge_long_work(), [])
        self.assertFalse(self.service.run_one(), 'keep a short cancellation window while delivery is uncertain')
        self.service.ingest_callback({'id': 'cb-1', 'from': {'id': CHAT}, 'data': f'p7c:{job_id}',
                                      'message': {'message_id': 909, 'chat': {'id': CHAT, 'type': 'private'}}},
                                     GENERATION)
        self.assertEqual(self.store.job(job_id)['status'], 'cancelled')
        self.assertEqual(self.store.task_card(job_id)['message_id'], 909)


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
        self.assertIn('Gmail 연결과 판단 기능 설정이 모두 필요', first)
        self.assertNotIn('/note', first)
        self.assertNotIn(TERMINAL_FAILED_HEADER, first, 'the projected reply is the whole bubble')
        self.assertNotIn('AgentOS 웹에서 실행 기록', first, 'the web console is not the default next action')
        note, note_bubbles = self.turn('/note 커피는 따뜻하게')
        self.assertEqual(note['status'], 'succeeded')
        self.assertEqual(len(note_bubbles), 1)
        self.assertEqual(self.store.config('conversation_blocker')[f'telegram:{CHAT}']['kind'], BLOCKER_NO_AI_ROUTE)
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
        self.assertOneVoice(bubbles + note_bubbles + bubbles2 + bubbles3)

    def test_the_transcript_shows_the_projected_reply_and_the_task_keeps_the_plain_cause(self):
        job, bubbles = self.turn('도와줘')
        self.assertEqual(self.assistant_messages(job['id']), [bubbles[0][1]])
        # Task/Evidence detail keeps the technical cause; the conversation does not lead with it.
        self.assertIn('모델 또는 구독 엔진', job['error'])
        self.assertNotIn('구독 엔진', bubbles[0][1])

    def test_a_pending_blocked_reply_survives_restart_with_its_projection(self):
        job_id = self.receive('도와줘')
        self.service.run_one()
        projected = self.assistant_messages(job_id)[0]
        self.assertEqual(self.store.blocked_delivery_reply(job_id), projected)
        self.assertNotIn('delivery_projection', self.store.history()[0])
        restarted = AgentService(QuickStore(Path(self.temp.name) / 'data'), ModelAdapter(self.model_transport), self.transport)
        before = len(self.outbound)
        restarted.deliver_one()
        text = self.outbound[before][1]
        self.assertEqual(text, projected)
        self.assertNotIn(TERMINAL_FAILED_HEADER, text)
        self.assertIn('지금 바로 되는 일', text)
        self.assertIn('모델 또는 구독 엔진', self.store.job(job_id)['error'])



class ContinuityTests(ProjectionTestCase):
    """#511: semantic follow-up judgment + deterministic replay safety."""

    def retry_engine(self):
        engine = FixtureDecisionEngine(choose=lambda context, candidates, question: SelectionDecision(
            OUTCOME_DECIDED, FOLLOWUP_RETRY, candidates, fixture_confidence())
            if context.purpose == 'conversation-followup' else None)
        self.service.use_decision_engine(engine)
        return engine

    def test_decision_engine_retry_replays_the_failed_work_once(self):
        first, first_bubbles = self.turn('원래 요청을 처리해줘')
        self.assertEqual(first['status'], 'failed')
        self.connect_model()
        engine = self.retry_engine()
        self.text = '원래 요청을 다시 처리한 결과입니다.'

        retried, bubbles = self.turn('자 다시 되니?')

        self.assertEqual(retried['status'], 'succeeded', retried.get('error'))
        self.assertEqual(retried['relation_kind'], 'retry')
        self.assertEqual(retried['related_job_id'], first['id'])
        self.assertEqual(bubbles, [('send', self.text)])
        followup = [asked for asked in engine.asked if asked[1].purpose == 'conversation-followup']
        self.assertEqual(len(followup), 1)
        self.assertEqual(followup[0][1].facts['owner_message'], '자 다시 되니?')
        self.assertNotIn('원래 요청을 처리해줘', repr(followup[0][1].facts))
        event = next(item for item in self.store.task_events(retried['id'])
                     if item['tool'] == 'conversation_continuity')
        self.assertTrue(event['trace']['executed'])
        self.assertEqual(event['trace']['relation'], 'retry')
        self.assertOneVoice(first_bubbles + bubbles)

    def test_retry_judgment_cannot_replay_unknown_external_effect(self):
        first, _ = self.turn('원래 요청을 처리해줘')
        self.assertEqual(first['status'], 'failed')
        with self.store.db() as db:
            db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                       (first['id'], 'calendar_draft_create', 'failed',
                        json.dumps({'effect':'unknown','state':'outcome-unknown'}), time.time()))
        self.connect_model()
        self.retry_engine()
        self.text = '이 문장은 실행되면 안 됩니다.'

        retried, bubbles = self.turn('그거 다시 해줘')

        self.assertEqual(retried['status'], 'succeeded')
        self.assertEqual(retried['relation_kind'], 'retry')
        self.assertEqual(retried['related_job_id'], first['id'])
        self.assertEqual(len(bubbles), 1)
        self.assertIn('외부 결과가 불확실', bubbles[0][1])
        self.assertNotIn(self.text, bubbles[0][1])
        event = next(item for item in self.store.task_events(retried['id'])
                     if item['tool'] == 'conversation_continuity')
        self.assertFalse(event['trace']['executed'])
        self.assertIn('외부 결과가 불확실', event['trace']['reason'])


class UnsupportedCapabilityTests(ProjectionTestCase):
    """#478: a request for something not offered is understood, not searched."""

    def judged(self, mapping):
        engine = FixtureDecisionEngine(choose=lambda context, candidates, question: SelectionDecision(
            OUTCOME_DECIDED, mapping.get(context.facts.get('owner_message'), 'none-of-these'),
            candidates, fixture_confidence()) if context.purpose == 'unsupported-capability' else None)
        self.service.use_decision_engine(engine)
        return engine

    def test_reply_and_read_body_requests_get_the_truthful_boundary_and_run_nothing(self):
        engine = self.judged({'메일 확인 답장 보내': 'mail-send', '메일 보여 mail-body': 'mail-read-body'})
        for text, key in (('예약 확인 메일에 답장 보내줘', 'mail-send'), ('그 메일 내용 좀 보여줘', 'mail-read-body')):
            with self.subTest(text=text):
                decision = self.service.classify_intent(text)
                self.assertEqual(decision.intent, INTENT_UNSUPPORTED)
                self.assertFalse(decision.executes)
                job, bubbles = self.turn(text)
                self.assertEqual(job['status'], 'succeeded', 'a truthful boundary answer is a completed turn')
                self.assertEqual(bubbles, [('send', UNSUPPORTED_CAPABILITY_TEXT[key])])
        self.assertTrue(all(item[0] == 'choose' for item in engine.asked))

    def test_mail_boundary_judgment_receives_cues_without_private_search_terms(self):
        engine = self.judged({})
        request = '내 메일에서 HIV 검사 결과 찾아줘'
        self.service.classify_intent(request)
        facts = engine.asked[-1][1].facts
        self.assertIn('메일', facts['owner_message'])
        self.assertNotIn('HIV', facts['owner_message'])
        self.assertNotIn('검사', facts['owner_message'])

    def test_local_note_with_mail_words_never_sends_its_private_text_to_judgment(self):
        engine = self.judged({})
        request = '내 메일로 보낼 PIN 4832를 메모해 둬'
        self.service.classify_intent(request)
        self.assertEqual(engine.asked, [], 'local note with mail/action words must not reach any judgment')

    def test_mail_action_followup_uses_content_free_recent_mail_focus(self):
        engine = self.judged({'최근 메일 검색 reply': 'mail-send'})
        first = self.service.classify_intent('메일에서 숙소 예약 확인 메일 찾아줘')
        self.assertEqual(first.intent, 'mail-search')
        self.service.conversation_focus.record(first)
        followup = self.service.classify_intent('reply to it')
        self.assertEqual(followup.intent, INTENT_UNSUPPORTED)
        self.assertEqual(followup.argument, 'mail-send')
        context = engine.asked[-1][1]
        self.assertEqual(context.facts['owner_message'], '최근 메일 검색 reply')

    def test_minimized_judgment_preserves_body_vs_metadata_request_kind(self):
        engine = self.judged({'메일 읽어 mail-body': 'mail-read-body',
                              '메일 읽어 mail-metadata': 'none-of-these'})
        body = self.service.classify_intent('메일 본문 읽어줘')
        metadata = self.service.classify_intent('메일 제목 읽어줘')
        self.assertEqual(body.intent, INTENT_UNSUPPORTED)
        self.assertEqual(metadata.intent, 'mail-search')
        self.assertIn('mail-body', engine.asked[-2][1].facts['owner_message'])
        self.assertIn('mail-metadata', engine.asked[-1][1].facts['owner_message'])

    def test_mixed_calendar_and_unsupported_mail_action_executes_neither(self):
        engine = self.judged({})
        decision = self.service.classify_intent('내일 오후 3시 회의를 예약하고 참석자에게 이메일 보내줘')
        self.assertEqual(decision.intent, 'ambiguous')
        self.assertFalse(decision.executes)
        self.assertIn('메일은 보내지 않으며', decision.clarification)
        self.assertEqual(engine.asked, [])


    def test_a_none_of_these_judgment_leaves_the_cues_to_decide(self):
        self.judged({})
        decision = self.service.classify_intent('메일에서 예산 관련 내용 찾아줘')
        self.assertEqual(decision.intent, 'mail-search')

    def test_local_note_turn_is_not_sent_to_decision_engine(self):
        engine = self.judged({})
        decision = self.service.classify_intent('/note 커피는 따뜻하게')
        self.assertEqual(decision.intent, 'note-create')
        self.assertEqual(engine.asked, [])

    def test_unavailable_judgment_does_not_fall_through_to_mail_search_cues(self):
        self.service.use_decision_engine(UnavailableDecisionEngine())
        request = '예약 확인 메일에 답장 보내줘'
        decision = self.service.classify_intent(request)
        self.assertEqual(decision.intent, 'ambiguous')
        self.assertFalse(decision.executes)
        self.assertIn('판단 기능을 사용할 수 없어', decision.clarification)
        self.assertIn('메일을 검색하거나 다른 처리를 하지 않았습니다', decision.clarification)
        job, bubbles = self.turn(request)
        self.assertEqual(job['status'], 'succeeded')
        self.assertEqual(bubbles, [('send', decision.clarification)])
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM tool_events WHERE job_id=?',
                                        (job['id'],)).fetchone()[0], 0)


class AcknowledgementSchedulingTests(ProjectionTestCase):
    def test_acknowledgement_deadline_runs_independently_of_telegram_long_poll(self):
        polling = threading.Event()
        release_poll = threading.Event()
        acknowledged = threading.Event()

        def blocked_poll():
            polling.set()
            release_poll.wait(timeout=3)

        self.service.poll_telegram = blocked_poll
        self.service.acknowledge_long_work = acknowledged.set
        self.service.start()
        try:
            self.assertTrue(polling.wait(timeout=1))
            self.assertTrue(acknowledged.wait(timeout=1))
        finally:
            self.service.stop.set()
            release_poll.set()
            for thread in self.service.threads:
                thread.join(timeout=1)


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


class TruthfulRepliesTests(unittest.TestCase):
    """#598 at the renderer level: verified portion, unknown outcome, owner words, particles."""

    def test_partial_states_the_verified_portion_before_the_unfinished_one(self):
        from personal_agent.conversation_projection import TERMINAL_VERIFIED_LABEL
        text = terminal_text('모델이 쓴 문장', '완료하지 못한 부분 — 파일 읽기: 거부', 'partial', verified='찾은 파일:\n- a.txt')
        self.assertTrue(text.startswith(TERMINAL_PARTIAL_HEADER))
        self.assertLess(text.index(TERMINAL_VERIFIED_LABEL), text.index('a.txt'))
        self.assertLess(text.index('a.txt'), text.index('파일 읽기: 거부'))
        self.assertNotIn('모델이 쓴 문장', text)

    def test_verified_never_appears_for_failed_interrupted_or_succeeded(self):
        from personal_agent.conversation_projection import TERMINAL_VERIFIED_LABEL
        for outcome in ('failed', 'interrupted', 'succeeded', None):
            with self.subTest(outcome=outcome):
                self.assertNotIn(TERMINAL_VERIFIED_LABEL, terminal_text('답', '원인', outcome, verified='찾은 파일'))

    def test_the_verified_portion_is_bounded(self):
        from personal_agent.conversation_projection import TERMINAL_VERIFIED_CHARS, TERMINAL_VERIFIED_MORE, verified_portion
        long = verified_portion(['가' * (TERMINAL_VERIFIED_CHARS + 50)])
        self.assertTrue(long.endswith(TERMINAL_VERIFIED_MORE))
        self.assertIsNone(verified_portion(['', '  ', None]))

    def test_unknown_delivers_the_effect_statement_never_the_model_text(self):
        from personal_agent.conversation_projection import TERMINAL_UNKNOWN_EFFECT, turn_qualifier
        self.assertEqual(terminal_text('일정을 만들었습니다.', '확인할 수 없습니다.', 'unknown'), '확인할 수 없습니다.')
        self.assertEqual(terminal_text('일정을 만들었습니다.', None, 'unknown'), TERMINAL_UNKNOWN_EFFECT)
        self.assertEqual(turn_qualifier('unknown')['outcome'], 'unknown')
        self.assertIsNone(turn_qualifier('succeeded'))

    def test_owner_cause_uses_labels_and_a_generic_fallback(self):
        from personal_agent.conversation_projection import owner_cause
        text = owner_cause([('find_files', '한도에서 멈춤'), ('pkg.custom_tool', None), ('find_files', '한도에서 멈춤')])
        self.assertEqual(text, '완료하지 못한 부분 — 파일 찾기: 한도에서 멈춤 · 도구 실행')
        self.assertIsNone(owner_cause([]))

    def test_object_particle_follows_the_final_sound(self):
        from personal_agent.conversation_projection import object_particle
        cases = {'Google Calendar 일정 만들기': '를', 'Gmail': '을', '캘린더': '를', '일정': '을',
                 'Google Drive': '를', 'Notion': '을', 'Office 365': '를', '폴더(읽기)': '를', '': '을(를)', '✓': '을(를)'}
        for word, particle in cases.items():
            with self.subTest(word=word):
                self.assertEqual(object_particle(word), particle)


class ConversationContinuityTests(ProjectionTestCase):
    """PRESENCE-CONT-01 / #511 continuity through the real Telegram worker."""

    @staticmethod
    def relation_engine(mapping):
        def choose(context, candidates, question):
            if context.purpose == 'conversation-followup':
                return SelectionDecision(
                    OUTCOME_DECIDED,
                    mapping.get(context.facts.get('owner_message'), 'none-of-these'),
                    candidates,
                    fixture_confidence(),
                )
            return SelectionDecision(OUTCOME_DECIDED, 'none-of-these', candidates, fixture_confidence())
        return FixtureDecisionEngine(choose=choose)

    def test_failed_work_retry_is_decided_by_the_decision_engine_and_replays_the_original_request(self):
        first, _ = self.turn('오늘 계획을 정리해줘')
        self.assertEqual(first['status'], 'failed')

        self.connect_model()
        seen = []
        original = self.service.adapter.transport

        def capture(url, body, headers=None, timeout=60):
            if url.endswith('/api/chat') and not any(
                    (tool.get('function', {}).get('name') or tool.get('name')) == 'agentos_connection_probe'
                    for tool in body.get('tools', [])):
                seen.append([m['content'] for m in body.get('messages', []) if m.get('role') == 'user'][-1])
                return {'message': {'content': '다시 처리했습니다.'}}
            return original(url, body, headers, timeout)

        self.service.adapter.transport = capture
        engine = self.relation_engine({'자 다시 되니?': FOLLOWUP_RETRY})
        self.service.use_decision_engine(engine)
        second, bubbles = self.turn('자 다시 되니?')

        self.assertEqual(second['status'], 'succeeded')
        self.assertEqual(seen[-1], '오늘 계획을 정리해줘')
        self.assertEqual(second['relation_kind'], FOLLOWUP_RETRY)
        self.assertEqual(second['related_job_id'], first['id'])
        self.assertTrue(any(
            kind == 'send' and '다시 처리했습니다.' in text for kind, text in bubbles
        ))
        asked = [item for item in engine.asked if item[0] == 'choose']
        self.assertEqual(asked[-1][1].purpose, 'conversation-followup')
        self.assertEqual(asked[-1][1].facts['previous_status'], 'failed')

    def test_retry_chain_always_replays_the_oldest_canonical_request(self):
        first, _ = self.turn('원래 요청')
        self.assertEqual(first['status'], 'failed')
        self.connect_model()
        self.service.use_decision_engine(self.relation_engine({'다시 해줘': FOLLOWUP_RETRY}))

        def failing(url, body, headers=None, timeout=60):
            if url.endswith('/api/chat'):
                raise ProviderError('fixture provider failure')
            return {'ok': True, 'result': {}}

        self.service.adapter.transport = failing
        second, _ = self.turn('다시 해줘')
        self.assertEqual(second['status'], 'failed')
        self.assertEqual(second['relation_kind'], FOLLOWUP_RETRY)
        self.assertEqual(second['related_job_id'], first['id'])

        seen = []
        def succeeding(url, body, headers=None, timeout=60):
            if url.endswith('/api/chat'):
                seen.append([m['content'] for m in body.get('messages', []) if m.get('role') == 'user'][-1])
                return {'message': {'content': '성공'}}
            return {'ok': True, 'result': {}}

        self.service.adapter.transport = succeeding
        third, _ = self.turn('다시 해줘')
        self.assertEqual(third['status'], 'succeeded')
        self.assertEqual(seen[-1], '원래 요청')
        self.assertEqual(third['relation_kind'], FOLLOWUP_RETRY)
        self.assertEqual(third['related_job_id'], second['id'])
        continuity = [e for e in self.store.task_events(third['id'])
                      if e['tool'] == 'conversation_continuity']
        self.assertEqual(continuity[-1]['trace']['source_work_id'], first['id'])

    def test_unknown_external_effect_is_never_retried(self):
        first, _ = self.turn('외부 작업을 해줘')
        self.assertEqual(first['status'], 'failed')
        with self.store.db() as db:
            db.execute(
                'INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                (first['id'], 'calendar_draft_create', 'failed',
                 '{"effect":"unknown","state":"outcome-unknown"}', time.time()),
            )
        self.service.use_decision_engine(self.relation_engine({'그거 다시 해줘': FOLLOWUP_RETRY}))
        second, bubbles = self.turn('그거 다시 해줘')

        self.assertEqual(second['status'], 'succeeded')
        self.assertEqual(second['relation_kind'], FOLLOWUP_RETRY)
        self.assertEqual(second['related_job_id'], first['id'])
        self.assertIn('외부 결과가 불확실', second['response'])
        self.assertIn('실제 결과를 확인', second['response'])
        self.assertTrue(any('외부 결과가 불확실' in text for _kind, text in bubbles))
        event = [e for e in self.store.task_events(second['id'])
                 if e['tool'] == 'conversation_continuity'][-1]
        self.assertFalse(event['trace']['executed'])

    def test_local_note_correction_never_reaches_the_remote_followup_judge(self):
        first, _ = self.turn('이전 요청')
        self.assertEqual(first['status'], 'failed')
        engine = self.relation_engine({'아니, sk-live-secret을 메모해줘': FOLLOWUP_REFERENCE})
        self.service.use_decision_engine(engine)

        note, _ = self.turn('아니, sk-live-secret을 메모해줘')
        self.assertEqual(note['status'], 'succeeded')
        self.assertIn('sk-live-secret', [row['content'] for row in self.store.notes()])
        self.assertFalse(any(
            item[0] == 'choose' and item[1].purpose == 'conversation-followup'
            for item in engine.asked
        ))

    def test_generic_memory_save_followup_stays_out_of_remote_judgment(self):
        first, _ = self.turn('이전 요청')
        engine = self.relation_engine({'아니 이걸 저장해줘': FOLLOWUP_REFERENCE})
        self.service.use_decision_engine(engine)
        self.assertIsNone(self.service.continuity_relation(
            '아니 이걸 저장해줘', current_work_id='different-work'))
        self.assertFalse(any(
            item[0] == 'choose' and item[1].purpose == 'conversation-followup'
            for item in engine.asked
        ))

    def test_package_write_alias_blocks_retry_by_recorded_host_action(self):
        first, _ = self.turn('원래 요청')
        self.assertEqual(first['status'], 'failed')
        with self.store.db() as db:
            db.execute(
                'INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                (first['id'], 'remember', 'succeeded',
                 '{"host_action":"save_note","evidence":{"state":"saved"}}', time.time()),
            )
        allowed, reason = self.service.safe_retry(self.store.job(first['id']))
        self.assertFalse(allowed)
        self.assertIn('상태를 바꾸는 작업', reason)

    def test_requeued_focused_work_does_not_create_a_self_continuity_link(self):
        first, _ = self.turn('원래 요청')
        engine = self.relation_engine({'다시 해줘': FOLLOWUP_RETRY})
        self.service.use_decision_engine(engine)
        self.assertIsNone(self.service.continuity_relation(
            '다시 해줘', current_work_id=first['id']))
        self.assertFalse(any(
            item[0] == 'choose' and item[1].purpose == 'conversation-followup'
            for item in engine.asked
        ))

    def test_retry_prompt_survives_private_document_history_filtering(self):
        private_turn, _ = self.turn('/note private document marker')
        self.store.put('file_workspace_document_jobs', [private_turn['id']])
        first, _ = self.turn('원래 요청')
        self.assertEqual(first['status'], 'failed')

        self.connect_model()
        self.service.use_decision_engine(self.relation_engine({'다시 해줘': FOLLOWUP_RETRY}))
        self.service.document_boundary = lambda _config=None: {'requires_approval': True}
        seen = []
        original = self.service.adapter.transport

        def capture(url, body, headers=None, timeout=60):
            if url.endswith('/api/chat') and not any(
                    (tool.get('function', {}).get('name') or tool.get('name')) == 'agentos_connection_probe'
                    for tool in body.get('tools', [])):
                seen.append([m['content'] for m in body.get('messages', []) if m.get('role') == 'user'][-1])
                return {'message': {'content': '성공'}}
            return original(url, body, headers, timeout)

        self.service.adapter.transport = capture
        second, _ = self.turn('다시 해줘')
        self.assertEqual(second['status'], 'succeeded')
        self.assertEqual(seen[-1], '원래 요청')

    def test_reference_relation_is_attributable_without_replaying_the_old_work(self):
        self.connect_model()
        first, _ = self.turn('오로라 결과를 설명해줘')
        self.assertEqual(first['status'], 'succeeded')
        self.service.use_decision_engine(self.relation_engine({'그걸 파일로 저장해줘': FOLLOWUP_REFERENCE}))
        seen = []
        original = self.service.adapter.transport

        def capture(url, body, headers=None, timeout=60):
            if url.endswith('/api/chat') and not any(
                    (tool.get('function', {}).get('name') or tool.get('name')) == 'agentos_connection_probe'
                    for tool in body.get('tools', [])):
                seen.append([m['content'] for m in body.get('messages', []) if m.get('role') == 'user'][-1])
            return original(url, body, headers, timeout)

        self.service.adapter.transport = capture
        second, _ = self.turn('그걸 파일로 저장해줘')
        self.assertEqual(second['relation_kind'], FOLLOWUP_REFERENCE)
        self.assertEqual(second['related_job_id'], first['id'])
        self.assertEqual(seen[-1], '그걸 파일로 저장해줘')
        detail = self.service.task_progress(second['id'])['selected']
        self.assertEqual(detail['relation'], {'kind': FOLLOWUP_REFERENCE, 'work_id': first['id']})



class SettingsRecoveryAddressTests(ProjectionTestCase):
    def test_recovery_address_uses_the_bound_server_port_before_connector_redirects(self):
        self.service.calendar_oauth = SimpleNamespace(redirect_uri='http://localhost:8787/oauth/calendar/callback')
        self.service.local_server_port = 9041
        expected = 'http://127.0.0.1:9041/'
        self.assertEqual(self.service.local_settings_url(), expected)
        self.assertEqual(self.service.projection.settings_url(), expected)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
