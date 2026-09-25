"""PRESENCE-TG-01 / #581: native Telegram presence through the real service.

Every test drives the real Telegram ingest -> worker -> delivery path with a
fake transport that records each Bot API method in order, so assertions are
about exactly what the paired owner's Telegram client would receive: the
method sequence, the number of *durable* bubbles (sendMessage), reactions,
chat actions, drafts, reply anchors and Stop outcomes, mapped to the Work
state underneath.  Time is a fake clock (the ``now=`` argument); nothing
sleeps.  Evidence class: automated synthetic/fixture only - no live Telegram
call is made and none is claimed.
"""
import html.parser
import json
import tempfile
import time
import unittest
from pathlib import Path

from personal_agent.conversation_handoff import (FOLLOWUP_CANCEL, FOLLOWUP_CORRECTION, FOLLOWUP_REFERENCE,
                                                 FOLLOWUP_RETRY, INTENT_AMBIGUOUS, INTENT_CALENDAR_CREATE,
                                                 INTENT_CONVERSATION, INTENT_NOTE_CREATE, INTENT_SETTINGS,
                                                 INTENT_UNSUPPORTED, TELEGRAM_POLL_UPDATE_KINDS, TelegramChannel)
from personal_agent.conversation_projection import TERMINAL_FAILED_HEADER
from personal_agent.decision import OUTCOME_DECIDED, FixtureDecisionEngine, SelectionDecision, fixture_confidence
from personal_agent.providers import ModelAdapter, ProviderError
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.telegram_presence import (REACTION_FOR_SEMANTICS, REACTION_SEMANTICS, TELEGRAM_REACTION_EMOJI,
                                              WAIT_CHAT_ACTION, WAIT_DRAFT, WAIT_NONE, PresenceTiming, draft_id_for,
                                              render_telegram_html, turn_gesture)

CHAT = 4242
GENERATION = 'g1'
PRESENCE_METHODS = ('setMessageReaction', 'sendChatAction', 'sendMessageDraft')


class NativePresenceTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parent))
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(Path(self.temp.name) / 'data')
        self.calls = []            # (method, body) in wire order
        self.failing = {}             # method -> exception to raise (presentation failure injection)
        self.text = '낮에 빵 먹었으면 저녁은 뜨끈한 게 좋겠다. 갈비탕이나 순두부찌개 어때?'
        self.during_model = None   # called while the model "thinks", with the running job
        self.model_error = None
        self.update_id = 100
        self.message_id = 500

        def transport(url, body=None, headers=None, timeout=60):
            method = url.rsplit('/', 1)[-1]
            self.calls.append((method, body))
            if method in self.failing:
                raise self.failing[method]
            if method == 'sendMessage':
                return {'ok': True, 'result': {'message_id': 9000 + len(self.calls)}}
            if method == 'getMe':
                return {'ok': True, 'result': {'username': 'owner_test_bot'}}
            return {'ok': True, 'result': True}

        def model(url, body, headers=None, timeout=60):
            tools = [t.get('function', {}).get('name') or t.get('name') for t in body.get('tools', [])]
            if 'agentos_connection_probe' in tools:
                return {'message': {'content': '', 'tool_calls': [
                    {'id': 'probe', 'function': {'name': 'agentos_connection_probe', 'arguments': {}}}]}}
            running = [job for job in self.store.jobs() if job['status'] == 'running']
            if self.during_model and running:
                # Once per turn: the model may be called again after a tool round.
                hook, self.during_model = self.during_model, None
                hook(running[0])
            if self.model_error:
                raise self.model_error
            return {'message': {'content': self.text}}

        self.service = AgentService(self.store, ModelAdapter(model), transport)
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': GENERATION, 'cursor': 0})

    # --- helpers -----------------------------------------------------------

    def connect_model(self):
        self.service.save_model({'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434',
                                 'model': 'test-model', 'api_key': ''})
        self.assertTrue(self.service.test_model()['ok'])
        self.calls.clear()

    def receive(self, text, sender=CHAT):
        self.update_id += 1
        self.message_id += 1
        self.service.ingest_update({'update_id': self.update_id, 'message': {
            'message_id': self.message_id, 'from': {'id': sender},
            'chat': {'id': sender, 'type': 'private'}, 'text': text}}, GENERATION)
        return self.store.jobs()[0]['id'], self.message_id

    def turn(self, text):
        job_id, message_id = self.receive(text)
        self.service.run_one()
        self.service.deliver_one()
        return self.store.job(job_id), message_id

    def methods(self):
        return [method for method, _body in self.calls]

    def sends(self):
        return [body for method, body in self.calls if method == 'sendMessage']

    def reactions(self):
        return [body for method, body in self.calls if method == 'setMessageReaction']

    def tap(self, data, message_id, sender=CHAT, callback_id='cb'):
        self.service.ingest_callback({'id': callback_id, 'from': {'id': sender}, 'data': data,
                                      'message': {'message_id': message_id, 'chat': {'id': sender, 'type': 'private'}}},
                                     GENERATION)

    def stop(self, job_id, chat=CHAT, chat_type='private'):
        return self.service.ingest_stop({'chat': {'id': chat, 'type': chat_type}, 'draft_id': draft_id_for(job_id)},
                                        GENERATION)

    def relation_engine(self, mapping):
        def choose(context, candidates, question):
            if context.purpose == 'conversation-followup':
                return SelectionDecision(OUTCOME_DECIDED, mapping.get(context.facts.get('owner_message'), 'none-of-these'),
                                         candidates, fixture_confidence())
            return SelectionDecision(OUTCOME_DECIDED, 'none-of-these', candidates, fixture_confidence())
        return FixtureDecisionEngine(choose=choose)


class ImmediateTurnTests(NativePresenceTestCase):
    def test_ordinary_question_is_reaction_then_one_answer(self):
        self.connect_model()
        job, message_id = self.turn('오늘 저녁은 뭐해 먹을까?')
        self.assertEqual(job['status'], 'succeeded')
        self.assertEqual(self.methods(), ['setMessageReaction', 'sendMessage'])
        self.assertEqual(self.reactions(), [{'chat_id': CHAT, 'message_id': message_id,
                                             'reaction': [{'type': 'emoji', 'emoji': '👍'}]}])
        [reply] = self.sends()
        self.assertEqual(reply['text'], self.text)
        self.assertEqual(reply['parse_mode'], 'HTML')
        self.assertNotIn('reply_parameters', reply, 'a reply right under its request needs no quote')
        self.assertNotIn('reply_markup', reply, 'a succeeded answer carries no lifecycle control')
        for body in self.sends():
            self.assertNotIn('처리가 끝났습니다', body['text'])
            self.assertNotIn('결과 상태 보기', json.dumps(body, ensure_ascii=False))
            self.assertNotIn('처리 중입니다', body['text'])

    def test_immediate_answer_gets_no_chat_action_or_draft(self):
        self.connect_model()
        self.during_model = lambda job: self.service.acknowledge_long_work(now=job['created'] + 0.4)
        self.turn('짧은 질문')
        self.assertNotIn('sendChatAction', self.methods())
        self.assertNotIn('sendMessageDraft', self.methods())

    def test_command_and_effect_turns_get_no_reaction(self):
        self.connect_model()
        self.turn('/notes')
        self.turn('/note 커피는 따뜻하게')
        self.assertEqual(self.reactions(), [])
        self.assertEqual(len(self.sends()), 2)

    def test_model_markdown_is_rendered_not_leaked(self):
        self.connect_model()
        self.text = '**갈비탕** 추천! `순두부` <맵지 않게> & [레시피](https://example.test/a?b=1&c=2)'
        self.turn('저녁 추천해줘')
        [reply] = self.sends()
        self.assertEqual(reply['text'], '<b>갈비탕</b> 추천! <code>순두부</code> &lt;맵지 않게&gt; &amp; '
                                        '<a href="https://example.test/a?b=1&amp;c=2">레시피</a>')
        self.assertNotIn('**', reply['text'])
        # The stored transcript keeps the model's own text (rendering is presentation).
        self.assertIn('**갈비탕**', self.store.jobs()[0]['response'])


class WaitSurfaceTests(NativePresenceTestCase):
    def test_noticeable_wait_is_typing_not_a_status_bubble(self):
        self.connect_model()
        self.during_model = lambda job: self.service.acknowledge_long_work(now=job['created'] + 2)
        job, _ = self.turn('오늘 저녁은 뭐해 먹을까?')
        self.assertEqual(self.methods(), ['setMessageReaction', 'sendChatAction', 'sendMessage'])
        self.assertEqual(self.calls[1][1], {'chat_id': CHAT, 'action': 'typing'})
        self.assertEqual(len(self.sends()), 1)
        self.assertEqual(job['status'], 'succeeded')

    def test_long_generation_uses_one_stop_able_draft_then_one_durable_answer(self):
        self.connect_model()

        def think(job):
            for offset in (6, 7, 12, 27):
                self.service.acknowledge_long_work(now=job['created'] + offset)
        self.during_model = think
        job, message_id = self.turn('제주 여행 준비 자료 조사해줘')
        drafts = [body for method, body in self.calls if method == 'sendMessageDraft']
        # First draft at 6s, refreshed once at 27s (>= 20s later); 7s and 12s are no-ops.
        self.assertEqual(len(drafts), 2)
        for body in drafts:
            self.assertEqual(body, {'chat_id': CHAT, 'draft_id': draft_id_for(job['id']), 'text': '', 'can_stop': True})
        self.assertNotIn('sendChatAction', self.methods())
        self.assertEqual(self.methods()[-1], 'sendMessage')
        [reply] = self.sends()
        self.assertEqual(reply['reply_parameters'], {'message_id': message_id, 'allow_sending_without_reply': True})
        self.assertIsNone(self.store.task_card(job['id']), 'the draft replaces the old running-Work card')

    def test_nothing_is_presented_after_the_final_answer(self):
        self.connect_model()
        job, _ = self.turn('질문')
        before = len(self.calls)
        self.service.acknowledge_long_work(now=job['created'] + 30)
        self.assertEqual(len(self.calls), before)

    def test_queued_work_keeps_one_card_that_ends_without_result_framing(self):
        self.connect_model()
        job_id, _ = self.receive('줄 서 있는 요청')
        self.service.acknowledge_long_work(now=time.time() + 10)
        with self.store.db() as db:
            db.execute('UPDATE telegram_task_cards SET created=? WHERE job_id=?', (time.time() - 10, job_id))
        self.service.run_one()
        self.service.deliver_one()
        texts = [body['text'] for method, body in self.calls if method in ('sendMessage', 'editMessageText')]
        self.assertEqual(texts[0], '요청을 받았습니다. 곧 시작할게요.')
        self.assertEqual(texts[-2], '요청을 처리했어요.')
        final_edit = [body for method, body in self.calls if method == 'editMessageText'][-1]
        self.assertEqual(final_edit['reply_markup'], {'inline_keyboard': []}, 'no 결과 상태 보기 button')
        self.assertEqual(texts[-1], self.text)


class PresentationFailureTests(NativePresenceTestCase):
    def test_rejected_or_crashing_presence_never_changes_work_or_duplicates_the_reply(self):
        for failure in (ProviderError('reaction unavailable'), RuntimeError('client bug'), TimeoutError('slow')):
            with self.subTest(failure=type(failure).__name__):
                self.calls.clear()
                self.connect_model()
                self.failing = {name: failure for name in PRESENCE_METHODS}
                self.during_model = lambda job: [self.service.acknowledge_long_work(now=job['created'] + t)
                                                 for t in (2, 6, 7)]
                job, _ = self.turn('오늘 저녁은 뭐해 먹을까?')
                self.assertEqual(job['status'], 'succeeded')
                self.assertEqual(job['delivery'], 'sent')
                self.assertEqual(len(self.sends()), 1)
                self.assertEqual(self.methods()[-1], 'sendMessage')

    def test_unsupported_draft_falls_back_to_typing(self):
        self.connect_model()
        self.failing = {'sendMessageDraft': ProviderError('method not found')}
        self.during_model = lambda job: [self.service.acknowledge_long_work(now=job['created'] + t) for t in (6, 7)]
        self.turn('긴 요청')
        self.assertEqual(self.methods().count('sendMessageDraft'), 1, 'a failed draft is not retried')
        self.assertIn('sendChatAction', self.methods())
        self.assertEqual(len(self.sends()), 1)

    def test_uncertain_final_send_is_not_resent(self):
        self.connect_model()
        self.failing = {'sendMessage': ProviderError('response lost')}
        job, _ = self.turn('질문')
        self.assertEqual(job['delivery'], 'unknown')
        self.service.deliver_one()
        self.assertEqual(len(self.sends()), 1)


class FailedTurnTests(NativePresenceTestCase):
    def failed_turn(self):
        self.connect_model()
        self.model_error = ProviderError('모델 서버에 연결할 수 없습니다.')
        return self.turn('다시 해봐')

    def test_failure_is_anchored_truthful_and_offers_bounded_recovery(self):
        job, message_id = self.failed_turn()
        self.assertEqual(job['status'], 'failed')
        [reply] = self.sends()
        self.assertTrue(reply['text'].startswith(TERMINAL_FAILED_HEADER))
        self.assertEqual(reply['reply_parameters']['message_id'], message_id)
        labels = [button['text'] for button in reply['reply_markup']['inline_keyboard'][0]]
        self.assertEqual(labels, ['다시 시도', '상세'])
        # The acknowledgement reaction came first and says only "received".
        self.assertEqual(self.methods()[0], 'setMessageReaction')

    def test_retry_control_is_owner_bound_exact_message_and_idempotent(self):
        job, source = self.failed_turn()
        reply_id = self.service.telegram_turns.get(job['id'])['reply_message_id']
        self.tap(f"p7r:{job['id']}", reply_id, sender=999, callback_id='foreign')
        self.tap(f"p7r:{job['id']}", reply_id + 1, callback_id='wrong-message')
        self.assertEqual(len(self.store.jobs()), 1, 'no retry from a foreign user or another message')
        self.tap(f"p7r:{job['id']}", reply_id, callback_id='first')
        self.tap(f"p7r:{job['id']}", reply_id, callback_id='second')
        jobs = self.store.jobs()
        self.assertEqual(len(jobs), 2, 'two taps create exactly one retry')
        retry = jobs[0]
        self.assertEqual(retry['status'], 'queued')
        self.assertEqual(retry['message'], '다시 해봐')
        self.assertEqual(retry['relation_kind'], FOLLOWUP_RETRY)
        self.assertEqual(retry['related_job_id'], job['id'])
        self.assertEqual(self.service.telegram_turns.source(retry['id']), source)
        answers = [body for method, body in self.calls if method == 'answerCallbackQuery']
        self.assertEqual([a['callback_query_id'] for a in answers], ['wrong-message', 'first', 'second'])
        self.assertEqual(answers[1]['text'], '다시 시도할게요.')
        self.assertTrue(answers[2]['show_alert'])
        edit = [body for method, body in self.calls if method == 'editMessageReplyMarkup'][-1]
        self.assertEqual(edit['reply_markup']['inline_keyboard'][0][0], {'text': '다시 시도 요청함', 'disabled': {}})

    def test_retry_from_control_runs_once_and_answers_the_original_turn(self):
        job, source = self.failed_turn()
        reply_id = self.service.telegram_turns.get(job['id'])['reply_message_id']
        self.tap(f"p7r:{job['id']}", reply_id)
        self.model_error = None
        self.service.run_one()
        self.service.deliver_one()
        retry = self.store.jobs()[0]
        self.assertEqual(retry['status'], 'succeeded')
        self.assertEqual(self.store.job(job['id'])['status'], 'failed', 'the failed Work stays failed')
        answer = self.sends()[-1]
        self.assertEqual(answer['text'], self.text)
        self.assertEqual(answer['reply_parameters']['message_id'], source)
        self.assertFalse(self.service.run_one(), 'nothing else was queued')

    def test_disabled_button_rejection_falls_back_to_removing_the_used_control(self):
        job, _ = self.failed_turn()
        reply_id = self.service.telegram_turns.get(job['id'])['reply_message_id']
        original = self.service.telegram_transport

        def reject_disabled(url, body=None, headers=None, timeout=60):
            if url.endswith('/editMessageReplyMarkup') and 'disabled' in json.dumps(body):
                self.calls.append(('editMessageReplyMarkup', body))
                raise ProviderError('field not supported')
            return original(url, body, headers, timeout)
        self.service.telegram_transport = reject_disabled
        self.tap(f"p7r:{job['id']}", reply_id)
        edits = [body for method, body in self.calls if method == 'editMessageReplyMarkup']
        self.assertEqual(len(edits), 2)
        self.assertEqual(edits[-1]['reply_markup'], {'inline_keyboard': [[{'text': '상세', 'callback_data': f"p7d:{job['id']}"}]]})
        self.assertEqual(len(self.store.jobs()), 2)

    def test_failed_work_that_attempted_an_effect_offers_no_retry(self):
        self.connect_model()
        self.model_error = ProviderError('모델 서버에 연결할 수 없습니다.')
        job_id, _ = self.receive('메모 저장하고 알려줘')
        self.service.run_one()
        with self.store.db() as db:
            db.execute("INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)",
                       (job_id, 'save_note', 'failed', '{}', time.time()))
        self.service.deliver_one()
        [reply] = self.sends()
        labels = [button['text'] for button in reply['reply_markup']['inline_keyboard'][0]]
        self.assertEqual(labels, ['상세'])
        reply_id = self.service.telegram_turns.get(job_id)['reply_message_id']
        self.tap(f'p7r:{job_id}', reply_id)
        self.assertEqual(len(self.store.jobs()), 1, 'a forged retry tap is refused by safe_retry')

    def test_details_are_an_on_demand_alert_not_a_new_bubble(self):
        job, _ = self.failed_turn()
        reply_id = self.service.telegram_turns.get(job['id'])['reply_message_id']
        before = len(self.sends())
        self.tap(f"p7d:{job['id']}", reply_id)
        self.assertEqual(len(self.sends()), before)
        answer = [body for method, body in self.calls if method == 'answerCallbackQuery'][-1]
        self.assertTrue(answer['show_alert'])
        self.assertTrue(answer['text'].startswith('작업 상태: 완료하지 못함'))
        self.assertNotIn('다시 해봐', answer['text'])

    def test_every_owner_tap_is_answered_even_when_stale_or_consumed(self):
        """No spinner is left behind: consumed approval / retry / detail taps are acknowledged."""
        for index, data in enumerate(('p7a:gone:approve', 'v1c:gone:deny', 'p7r:gone', 'p7d:gone', 'p7v:gone')):
            self.tap(data, 1, callback_id=f'stale-{index}')
        answers = [body for method, body in self.calls if method == 'answerCallbackQuery']
        self.assertEqual([a['callback_query_id'] for a in answers], [f'stale-{i}' for i in range(5)])
        self.assertTrue(all(a['text'] == '처리할 수 있는 요청이 아닙니다.' for a in answers))
        self.assertEqual(self.sends(), [])
        self.assertEqual(self.store.jobs(), [])

    def test_blocked_turn_has_no_retry_control(self):
        job, _ = self.turn('안녕, 뭐 할 수 있어?')   # no AI route connected
        self.assertEqual(job['status'], 'failed')
        [reply] = self.sends()
        self.assertNotIn('reply_markup', reply)


class StopTests(NativePresenceTestCase):
    def test_stop_on_running_work_ends_drafts_and_never_claims_cancellation(self):
        self.connect_model()
        outcomes = []

        def think(job):
            self.service.acknowledge_long_work(now=job['created'] + 6)
            outcomes.append(self.stop(job['id']))
            for offset in (7, 30):
                self.service.acknowledge_long_work(now=job['created'] + offset)
        self.during_model = think
        job, message_id = self.turn('긴 조사 부탁해')
        self.assertEqual(outcomes, ['running'])
        self.assertEqual(self.methods().count('sendMessageDraft'), 1, 'no draft after Stop')
        self.assertNotIn('sendChatAction', self.methods())
        self.assertEqual(job['status'], 'succeeded', 'running Work was not cancelled and says so')
        notice, answer = self.sends()
        self.assertEqual(notice['text'], AgentService.STOP_RUNNING_TEXT)
        self.assertIn('취소하지 못했어요', notice['text'])
        self.assertNotIn('취소했', notice['text'])
        self.assertEqual(notice['reply_parameters']['message_id'], message_id)
        self.assertEqual(answer['text'], self.text, 'the real result is still delivered once')

    def test_stop_after_an_effect_was_recorded_still_does_not_claim_cancellation(self):
        self.connect_model()
        outcomes = []

        def think(job):
            with self.store.db() as db:
                db.execute("INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)",
                           (job['id'], 'save_note', 'succeeded', '{}', time.time()))
            outcomes.append(self.stop(job['id']))
        self.during_model = think
        job, _ = self.turn('메모 남기고 정리해줘')
        self.assertEqual(outcomes, ['running'])
        self.assertEqual(self.store.job(job['id'])['status'], 'succeeded')
        self.assertFalse(any('멈췄어요. 이 요청은 실행하지' in body['text'] for body in self.sends()))

    def test_stop_on_queued_work_cancels_it_through_the_state_machine(self):
        job_id, _ = self.receive('아직 시작 전인 요청')
        self.assertEqual(self.stop(job_id), 'cancelled')
        self.assertEqual(self.store.job(job_id)['status'], 'cancelled')
        self.assertFalse(self.service.run_one(), 'cancelled Work never runs')
        [notice] = self.sends()
        self.assertEqual(notice['text'], AgentService.STOP_CANCELLED_TEXT)

    def test_stop_for_finished_work_or_foreign_chat_changes_nothing(self):
        self.connect_model()
        job, _ = self.turn('질문')
        before = len(self.calls)
        self.assertEqual(self.stop(job['id']), 'finished')
        queued, _ = self.receive('다른 요청')
        self.assertIsNone(self.stop(queued, chat=999))
        self.assertIsNone(self.stop(queued, chat_type='group'))
        self.assertIsNone(self.service.ingest_stop({'chat': {'id': CHAT, 'type': 'private'}, 'draft_id': 'x'}, GENERATION))
        self.assertIsNone(self.service.ingest_stop({'chat': {'id': CHAT, 'type': 'private'},
                                                    'draft_id': draft_id_for(queued)}, 'old-generation'))
        self.assertEqual(self.store.job(queued)['status'], 'queued')
        self.assertEqual(len(self.calls), before)

    def test_stop_update_arrives_through_the_poll_loop_and_advances_the_cursor(self):
        self.store.secret('telegram_token', '123:TOKEN')
        job_id, _ = self.receive('시작 전 요청')
        cursor = self.store.config('telegram')['cursor']
        original = self.service.telegram_transport

        def updates(url, body=None, headers=None, timeout=60):
            if url.endswith('/getUpdates'):
                self.assertIn('stopped_message_generation', body['allowed_updates'])
                return {'ok': True, 'result': [{'update_id': cursor, 'stopped_message_generation': {
                    'chat': {'id': CHAT, 'type': 'private'}, 'draft_id': draft_id_for(job_id)}}]}
            return original(url, body, headers, timeout)
        self.service.telegram_transport = updates
        self.service.poll_telegram()
        self.assertEqual(self.store.job(job_id)['status'], 'cancelled')
        self.assertEqual(self.store.config('telegram')['cursor'], cursor + 1)


class AnchorTests(NativePresenceTestCase):
    def test_reply_is_anchored_when_a_newer_owner_turn_arrived_first(self):
        self.connect_model()
        first, first_message = self.receive('첫 번째 질문')
        with self.store.db() as db:
            db.execute('UPDATE jobs SET created=created-1 WHERE id=?', (first,))
        self.receive('두 번째 질문')
        self.service.run_one()
        self.service.deliver_one()
        reply = self.sends()[0]
        self.assertEqual(reply['reply_parameters']['message_id'], first_message)


class ReactionSemanticsTests(unittest.TestCase):
    def test_every_mapped_reaction_is_a_documented_telegram_reaction(self):
        for semantics in REACTION_SEMANTICS:
            self.assertIn(REACTION_FOR_SEMANTICS[semantics], TELEGRAM_REACTION_EMOJI, semantics)

    def test_typed_decisions_map_deterministically_and_unknown_is_no_reaction(self):
        self.assertEqual(turn_gesture(intent=INTENT_CONVERSATION).reaction, '👍')
        self.assertEqual(turn_gesture(relation=FOLLOWUP_CORRECTION).reaction, '👌')
        self.assertEqual(turn_gesture(relation=FOLLOWUP_RETRY).reaction, '👍')
        self.assertEqual(turn_gesture(relation=FOLLOWUP_REFERENCE).reaction, '👍')
        self.assertEqual(turn_gesture(semantics='celebrate').reaction, '🎉')
        for gesture in (turn_gesture(relation=FOLLOWUP_CANCEL), turn_gesture(intent=INTENT_CALENDAR_CREATE),
                        turn_gesture(intent=INTENT_NOTE_CREATE), turn_gesture(intent=INTENT_SETTINGS),
                        turn_gesture(intent=INTENT_AMBIGUOUS), turn_gesture(intent=INTENT_UNSUPPORTED),
                        turn_gesture(intent=INTENT_CONVERSATION, executes=False),
                        turn_gesture(semantics='sarcasm'), turn_gesture(relation='unknown'), turn_gesture()):
            self.assertIsNone(gesture.reaction)

    def test_poll_includes_the_stop_update_kind(self):
        self.assertIn('stopped_message_generation', TELEGRAM_POLL_UPDATE_KINDS)


class CorrectionReactionTests(NativePresenceTestCase):
    def test_a_decision_engine_correction_gets_the_okay_reaction(self):
        self.connect_model()
        self.turn('오늘 저녁 메뉴 추천해줘')
        self.service.use_decision_engine(self.relation_engine({'아니 국물 말고': FOLLOWUP_CORRECTION}))
        _job, message_id = self.turn('아니 국물 말고')
        self.assertEqual(self.reactions()[-1], {'chat_id': CHAT, 'message_id': message_id,
                                                'reaction': [{'type': 'emoji', 'emoji': '👌'}]})


class TimingTests(unittest.TestCase):
    def test_thresholds_choose_the_smallest_surface(self):
        timing = PresenceTiming()
        self.assertEqual(timing.wait_surface(0.5), WAIT_NONE)
        self.assertEqual(timing.wait_surface(2), WAIT_CHAT_ACTION)
        self.assertEqual(timing.wait_surface(6), WAIT_DRAFT)
        self.assertEqual(timing.wait_surface(6, durable_surface=True), WAIT_CHAT_ACTION)
        self.assertEqual(timing.wait_surface(6, draft_available=False), WAIT_CHAT_ACTION)

    def test_draft_ids_are_stable_and_non_zero(self):
        self.assertEqual(draft_id_for('a'), draft_id_for('a'))
        for value in ('a', 'b', '', 'x' * 100):
            self.assertTrue(1 <= draft_id_for(value) < 2 ** 31)


class _TagChecker(html.parser.HTMLParser):
    ALLOWED = {'b', 'i', 'code', 'pre', 'a'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []

    def handle_starttag(self, tag, attrs):
        assert tag in self.ALLOWED, tag
        self.stack.append(tag)

    def handle_endtag(self, tag):
        assert self.stack and self.stack.pop() == tag, tag


class RenderTests(unittest.TestCase):
    def valid(self, text):
        checker = _TagChecker()
        checker.feed(render_telegram_html(text))
        checker.close()
        self.assertEqual(checker.stack, [], text)

    def test_common_model_markdown(self):
        self.assertEqual(render_telegram_html('# 제목\n- 하나\n* 둘\n*기울임* 과 __굵게__'),
                         '<b>제목</b>\n• 하나\n• 둘\n<i>기울임</i> 과 <b>굵게</b>')
        self.assertEqual(render_telegram_html('```python\nx = 1 < 2\n```'), '<pre>x = 1 &lt; 2</pre>')
        self.assertEqual(render_telegram_html('2 * 3 * 4'), '2 * 3 * 4')

    def test_output_is_always_balanced_valid_telegram_html(self):
        for text in ('**a [b** c](https://x.test)', '**unclosed', '`a **b` c**', '*a **b* c**', '<b>raw</b>',
                     '[x](javascript:alert(1))', '```\nunterminated', '** **', '__a *b__ c*', '&amp; &', ''):
            with self.subTest(text=text):
                self.valid(text)
        self.assertNotIn('<a', render_telegram_html('[x](javascript:alert(1))'))
        self.assertEqual(render_telegram_html('<b>raw</b>'), '&lt;b&gt;raw&lt;/b&gt;')


class ChannelWireTests(unittest.TestCase):
    def test_presence_method_bodies_follow_bot_api_10_3(self):
        log = []

        def transport(url, body, headers, timeout=15):
            log.append((url.rsplit('/', 1)[-1], body, timeout))
            return {'ok': True, 'result': True}
        channel = TelegramChannel(lambda: transport, lambda: 'BOT:TOKEN')
        channel.set_message_reaction(1, 2, '👍')
        channel.send_chat_action(1)
        channel.send_message_draft(1, 77)
        channel.send_message(1, 'x', parse_mode='HTML', reply_to=5)
        channel.edit_message_reply_markup(1, 5, {'inline_keyboard': []})
        channel.answer_callback_query('c', 'y' * 300, show_alert=True)
        self.assertEqual(log[0], ('setMessageReaction', {'chat_id': 1, 'message_id': 2,
                                                         'reaction': [{'type': 'emoji', 'emoji': '👍'}]}, 4))
        self.assertEqual(log[1], ('sendChatAction', {'chat_id': 1, 'action': 'typing'}, 4))
        self.assertEqual(log[2], ('sendMessageDraft', {'chat_id': 1, 'draft_id': 77, 'text': '', 'can_stop': True}, 4))
        self.assertEqual(log[3][1], {'chat_id': 1, 'text': 'x', 'parse_mode': 'HTML',
                                     'reply_parameters': {'message_id': 5, 'allow_sending_without_reply': True}})
        self.assertEqual(log[4][1], {'chat_id': 1, 'message_id': 5, 'reply_markup': {'inline_keyboard': []}})
        self.assertEqual(len(log[5][1]['text']), 200)
        self.assertTrue(log[5][1]['show_alert'])


if __name__ == '__main__':
    unittest.main()
