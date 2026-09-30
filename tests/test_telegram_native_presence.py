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
import html
import html.parser
import io
import json
import re
import urllib.error
from unittest import mock
import tempfile
import threading
import time
import traceback
import unittest
from pathlib import Path

from personal_agent.conversation_handoff import (FOLLOWUP_CANCEL, FOLLOWUP_CORRECTION, FOLLOWUP_REFERENCE,
                                                 FOLLOWUP_RETRY, INTENT_AMBIGUOUS, INTENT_CALENDAR_CREATE,
                                                 INTENT_CONVERSATION, INTENT_NOTE_CREATE, INTENT_SETTINGS,
                                                 INTENT_UNSUPPORTED, TELEGRAM_POLL_UPDATE_KINDS, ConversationJudgments,
                                                 TelegramChannel,
                                                 TelegramRejected, telegram_request_json)
from personal_agent.conversation_projection import TERMINAL_FAILED_HEADER
from personal_agent.decision import OUTCOME_DECIDED, FixtureDecisionEngine, SelectionDecision, fixture_confidence
from personal_agent.agent_runtime import WORK_STOPPED
from personal_agent.providers import ModelAdapter, ProviderError, request_json
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.telegram_presence import (CLEAR_REACTION, CLOSING_CANDIDATES, DONE_REACTION, DOTS_FRAMES,
                                              PRESENCE_REACTIONS, RECEIVED_CANDIDATES, RECEIVED_REACTION,
                                              PROGRESS_CANDIDATES, TELEGRAM_REACTION_EMOJI, WROTE_REACTION, WAIT_CHAT_ACTION, WAIT_DRAFT,
                                              WAIT_NONE, PresenceTiming, draft_body_text, draft_frame, draft_id_for,
                                              outcome_reaction, render_telegram_html, rich_draft_blocks)

CHAT = 4242
GENERATION = 'g1'
PRESENCE_METHODS = ('setMessageReaction', 'sendChatAction', 'sendMessageDraft', 'sendRichMessageDraft')
DRAFT_METHODS = ('sendMessageDraft', 'sendRichMessageDraft')


class NativePresenceTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
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

    def emojis(self):
        """Each reaction call as its emoji, or '' for a removal (#835)."""
        return [(body['reaction'][0]['emoji'] if body['reaction'] else CLEAR_REACTION) for body in self.reactions()]

    def drafts(self):
        """Each draft edit as the text it shows: the rich thinking block (#858) or the plain fallback."""
        return [draft_body_text(body) for method, body in self.calls if method in DRAFT_METHODS]

    def draft_methods(self):
        return [method for method, _body in self.calls if method in DRAFT_METHODS]

    def after_answer(self):
        """Methods called after the last durable reply."""
        methods = self.methods()
        return methods[len(methods) - methods[::-1].index('sendMessage'):]

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
    def test_ordinary_question_is_looking_then_one_answer_then_done(self):
        self.connect_model()
        job, message_id = self.turn('오늘 저녁은 뭐해 먹을까?')
        self.assertEqual(job['status'], 'succeeded')
        # #835: 👀 on receipt; only after the answer, the outcome reaction replaces it.
        self.assertEqual(self.methods(), ['setMessageReaction', 'sendMessage', 'setMessageReaction'])
        self.assertEqual(self.reactions(), [{'chat_id': CHAT, 'message_id': message_id,
                                             'reaction': [{'type': 'emoji', 'emoji': '👀'}]},
                                            {'chat_id': CHAT, 'message_id': message_id,
                                             'reaction': [{'type': 'emoji', 'emoji': DONE_REACTION}]}])
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

    def test_command_turns_get_no_reaction(self):
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


class JudgmentReactionTests(NativePresenceTestCase):
    """#858: the existing Judgment AI chooses only the allowed presence emoji."""

    def install_reaction_judgment(self, choices):
        self.judgment_calls = []

        def choose(context, candidates, question):
            self.judgment_calls.append((context, tuple(candidates), question, self.service.current_work_id))
            return SelectionDecision(OUTCOME_DECIDED, choices.get(context.purpose, 'none-of-these'),
                                     tuple(candidates), fixture_confidence())

        self.service.decision_judge = ConversationJudgments(FixtureDecisionEngine(choose=choose),
                                                            redactor=self.service.redact_judgment_text)

    def test_judgment_ai_varies_start_and_success_reactions(self):
        self.connect_model()
        self.store.secret('decision_model_key', 'owner-private-sentinel')
        owner_message = '고마워, 이 계획은 owner-private-sentinel 괜찮을까?'
        self.install_reaction_judgment({'turn-reaction': '🤗', 'closing-reaction': '🎉'})

        job, message_id = self.turn(owner_message)

        self.assertEqual(job['status'], 'succeeded')
        self.assertEqual(self.emojis(), [RECEIVED_REACTION, '🤗', '🎉'])
        self.assertEqual([call[0].purpose for call in self.judgment_calls], ['turn-reaction', 'closing-reaction'])
        self.assertEqual(self.judgment_calls[0][0].facts,
                         {'owner_message': '고마워, 이 계획은 [redacted] 괜찮을까?'})
        self.assertEqual(self.judgment_calls[1][0].facts['owner_message'], '고마워, 이 계획은 [redacted] 괜찮을까?')
        self.assertEqual(self.judgment_calls[1][0].facts,
                         {'owner_message': '고마워, 이 계획은 [redacted] 괜찮을까?',
                          'answer_delivered': 'yes', 'saved_a_note_or_memory': 'no'})
        self.assertNotIn(job['response'], repr(self.judgment_calls[1][0].facts))
        self.assertEqual(self.judgment_calls[0][1], RECEIVED_CANDIDATES)
        self.assertEqual(self.judgment_calls[1][1], CLOSING_CANDIDATES)
        self.assertEqual([call[3] for call in self.judgment_calls], [job['id'], job['id']],
                         'both Judgment AI calls are linked to this Work for the #826 information-use audit')
        self.assertTrue(all(body['message_id'] == message_id for body in self.reactions()))

    def test_a_distinct_observed_progress_step_gets_one_redacted_judgment_reaction(self):
        self.connect_model()
        self.store.secret('decision_model_key', 'owner-private-sentinel')
        self.install_reaction_judgment({'turn-reaction': '🤗', 'progress-reaction': '🤓', 'closing-reaction': '🎉'})
        pending_judgments = []
        self.service.progress_reaction_spawn = pending_judgments.append

        def show_progress(job):
            with self.store.db() as db:
                db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                           (job['id'], 'web_search', 'running',
                            json.dumps({'call_id': 'step-1', 'step': {'action': 'web_search',
                                                                      'status': 'owner-private-sentinel 검색 중'}}),
                            job['created'] + 5))
            self.service.acknowledge_long_work(now=job['created'] + 6)
            self.assertTrue(any(method == 'sendRichMessageDraft' for method in self.methods()),
                            'the acknowledgement loop refreshes the wait surface before the judgment completes')
            self.assertNotIn('🤓', self.emojis(), 'the optional judgment is still pending')
            self.assertEqual(len(pending_judgments), 1)
            pending_judgments.pop()()
            # A wait refresh with no new event must not ask or react again.
            self.service.acknowledge_long_work(now=job['created'] + 7)

        self.during_model = show_progress
        job, message_id = self.turn('자료를 조사해줘')

        self.assertEqual(job['status'], 'succeeded')
        self.assertEqual(self.emojis(), [RECEIVED_REACTION, '🤗', '🤓', '🎉'])
        progress_calls = [call for call in self.judgment_calls if call[0].purpose == 'progress-reaction']
        self.assertEqual(len(progress_calls), 1)
        self.assertEqual(progress_calls[0][0].facts, {'current_step': '[redacted] 검색 중'})
        self.assertEqual(progress_calls[0][1], PROGRESS_CANDIDATES)
        self.assertEqual(progress_calls[0][3], job['id'])
        self.assertTrue(all(body['message_id'] == message_id for body in self.reactions()))

    def test_approval_step_does_not_get_a_progress_judgment(self):
        self.connect_model()
        self.install_reaction_judgment({'turn-reaction': '🤗', 'progress-reaction': '🤓', 'closing-reaction': '🎉'})

        def show_approval(job):
            with self.store.db() as db:
                db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                           (job['id'], 'browser_click', 'running',
                            json.dumps({'call_id': 'payment-1', 'step': {'action': 'browser_click', 'approval': True}}),
                            job['created'] + 5))
            self.service.acknowledge_long_work(now=job['created'] + 6)

        self.during_model = show_approval
        self.turn('결제를 진행해줘')
        self.assertNotIn('progress-reaction', [call[0].purpose for call in self.judgment_calls])

    def test_a_step_reaction_is_discarded_if_a_newer_step_arrives_during_judgment(self):
        self.connect_model()
        self.store.secret('decision_model_key', 'owner-private-sentinel')
        self.judgment_calls = []
        work_id = {'value': None}

        def choose(context, candidates, question):
            self.judgment_calls.append((context, tuple(candidates), question, self.service.current_work_id))
            if context.purpose == 'progress-reaction':
                with self.store.db() as db:
                    db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                               (work_id['value'], 'web_search', 'running',
                                json.dumps({'call_id': 'step-2', 'step': {'action': 'web_search',
                                                                          'status': 'next step'}}),
                                time.time()))
                return SelectionDecision(OUTCOME_DECIDED, '🤓', candidates, fixture_confidence())
            return SelectionDecision(OUTCOME_DECIDED,
                                     '🤗' if context.purpose == 'turn-reaction' else '🎉',
                                     candidates, fixture_confidence())

        self.service.decision_judge = ConversationJudgments(FixtureDecisionEngine(choose=choose),
                                                            redactor=self.service.redact_judgment_text)
        self.service.progress_reaction_spawn = lambda target: target()

        def show_progress(job):
            work_id['value'] = job['id']
            with self.store.db() as db:
                db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                           (job['id'], 'web_search', 'running',
                            json.dumps({'call_id': 'step-1', 'step': {'action': 'web_search',
                                                                      'status': 'first step'}}),
                            job['created'] + 5))
            self.service.acknowledge_long_work(now=job['created'] + 6)

        self.during_model = show_progress
        self.turn('자료를 조사해줘')
        self.assertNotIn('🤓', self.emojis(), 'the judgment for a superseded step is stale')

    def test_none_of_these_keeps_deterministic_reactions_without_repeating_them(self):
        self.connect_model()
        self.install_reaction_judgment({})

        self.turn('질문')

        self.assertEqual(self.emojis(), [RECEIVED_REACTION, DONE_REACTION])
        self.assertEqual([call[0].purpose for call in self.judgment_calls], ['turn-reaction', 'closing-reaction'])

    def test_a_matching_turn_choice_is_not_sent_again(self):
        self.connect_model()
        self.install_reaction_judgment({'turn-reaction': RECEIVED_REACTION, 'closing-reaction': '🎉'})

        self.turn('질문')

        self.assertEqual(self.emojis(), [RECEIVED_REACTION, '🎉'])

    def test_a_matching_closing_choice_keeps_the_existing_reaction_without_a_call(self):
        self.connect_model()
        self.install_reaction_judgment({'turn-reaction': '🤗', 'closing-reaction': '🤗'})

        self.turn('질문')

        self.assertEqual(self.emojis(), [RECEIVED_REACTION, '🤗'])

    def test_failed_work_clears_reaction_without_a_closing_judgment(self):
        self.connect_model()
        self.install_reaction_judgment({'turn-reaction': '🤗', 'closing-reaction': '🎉'})
        self.model_error = ProviderError('fixture failure')

        job, _ = self.turn('이 자료를 찾아줘')

        self.assertEqual(job['status'], 'failed')
        self.assertEqual(self.emojis(), [RECEIVED_REACTION, '🤗', CLEAR_REACTION])
        self.assertEqual([call[0].purpose for call in self.judgment_calls], ['turn-reaction'])

    def test_closing_judgment_failure_keeps_deterministic_completion_reaction(self):
        self.connect_model()
        self.install_reaction_judgment({'turn-reaction': '🤗'})

        def fail_closing(*args, **kwargs):
            raise RuntimeError('fixture judgment failure')

        self.service.decision_judge.closing_reaction = fail_closing
        job, _ = self.turn('질문')

        self.assertEqual(job['status'], 'succeeded')
        self.assertEqual(self.emojis(), [RECEIVED_REACTION, '🤗', DONE_REACTION])

    def test_closing_judgment_runs_without_the_service_lock(self):
        self.connect_model()
        lock_was_available = []
        self.judgment_calls = []

        def choose(context, candidates, question):
            if context.purpose == 'closing-reaction':
                acquired = threading.Event()

                def acquire_service_lock():
                    with self.service.lock:
                        acquired.set()

                thread = threading.Thread(target=acquire_service_lock)
                thread.start()
                thread.join(timeout=1)
                lock_was_available.append(acquired.is_set())
            return SelectionDecision(OUTCOME_DECIDED, 'none-of-these', tuple(candidates), fixture_confidence())

        self.service.decision_judge = ConversationJudgments(FixtureDecisionEngine(choose=choose),
                                                            redactor=self.service.redact_judgment_text)
        self.turn('질문')

        self.assertEqual(lock_was_available, [True])


class DraftCompositionTests(unittest.TestCase):
    """#858: the animated thinking block carries the wait, attention stays a paragraph."""

    def test_rich_draft_blocks_keep_attention_outside_the_thinking_block(self):
        self.assertEqual(rich_draft_blocks('저장한 메모를 확인 중 · ·', '참, 준비한 답이 있어요'),
                         [{'type': 'thinking', 'text': '저장한 메모를 확인 중 · ·'},
                          {'type': 'paragraph', 'text': '참, 준비한 답이 있어요'}])
        self.assertEqual(rich_draft_blocks('·'), [{'type': 'thinking', 'text': '·'}])


class WaitSurfaceTests(NativePresenceTestCase):
    def test_noticeable_wait_is_typing_not_a_status_bubble(self):
        self.connect_model()
        self.during_model = lambda job: self.service.acknowledge_long_work(now=job['created'] + 2)
        job, _ = self.turn('오늘 저녁은 뭐해 먹을까?')
        self.assertEqual(self.methods(), ['setMessageReaction', 'sendChatAction', 'sendMessage', 'setMessageReaction'])
        self.assertEqual(self.calls[1][1], {'chat_id': CHAT, 'action': 'typing'})
        self.assertEqual(len(self.sends()), 1)
        self.assertEqual(job['status'], 'succeeded')

    def test_long_generation_uses_one_stop_able_dots_draft_then_one_durable_answer(self):
        self.connect_model()

        def think(job):
            for offset in (6, 7, 12, 27):
                self.service.acknowledge_long_work(now=job['created'] + offset)
        self.during_model = think
        job, message_id = self.turn('제주 여행 준비 자료 조사해줘')
        drafts = [body for method, body in self.calls if method == 'sendRichMessageDraft']
        # #835: a draft edit at 6s, 12s and 27s, each the next dots frame.  #858:
        # each is Telegram's animated thinking block holding the dots and no
        # "생각" label; the plain draft is only the fallback.
        self.assertEqual(drafts, [{'chat_id': CHAT, 'draft_id': draft_id_for(job['id']), 'can_stop': True,
                                   'rich_message': {'blocks': [{'type': 'thinking', 'text': frame}]}}
                                  for frame in DOTS_FRAMES])
        self.assertNotIn('sendMessageDraft', self.methods())
        self.assertFalse(any('생각' in draft_body_text(body) for body in drafts))
        # 7s: no draft edit due yet, so typing… (never sent before) is refreshed.
        self.assertEqual(self.methods().count('sendChatAction'), 1)
        self.assertEqual(self.after_answer(), ['setMessageReaction'])
        [reply] = self.sends()
        self.assertEqual(reply['reply_parameters'], {'message_id': message_id, 'allow_sending_without_reply': True})
        self.assertIsNone(self.store.task_card(job['id']), 'the draft replaces the old running-Work card')

    def test_nothing_is_presented_after_the_final_answer(self):
        self.connect_model()
        job, _ = self.turn('질문')
        before = len(self.calls)
        self.service.acknowledge_long_work(now=job['created'] + 30)
        self.assertEqual(len(self.calls), before)

    def test_queued_acknowledgement_is_removed_when_work_starts(self):
        self.connect_model()
        job_id, _ = self.receive('줄 서 있는 요청')
        self.service.acknowledge_long_work(now=time.time() + 10)
        with self.store.db() as db:
            db.execute('UPDATE telegram_task_cards SET created=? WHERE job_id=?', (time.time() - 10, job_id))
        self.service.run_one()
        self.service.deliver_one()
        texts = [body['text'] for method, body in self.calls if method in ('sendMessage', 'editMessageText')]
        self.assertEqual(texts[0], '요청을 받았습니다. 곧 시작할게요.')
        self.assertEqual(texts[-1], self.text)
        self.assertEqual(texts, ['요청을 받았습니다. 곧 시작할게요.', self.text])
        self.assertTrue(any(method == 'deleteMessage' for method, _body in self.calls))
        self.assertIsNone(self.store.task_card(job_id))


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
                # The failed outcome reaction is attempted once and changes nothing.
                self.assertEqual(self.after_answer(), ['setMessageReaction'])

    def test_a_refused_presence_call_is_logged_without_telegram_detail(self):
        self.connect_model()
        self.store.secret('telegram_token', '123:SECRET-TOKEN')
        self.failing = {'setMessageReaction': TelegramRejected(400, 'Bad Request: REACTION_INVALID owner-text')}
        with self.assertLogs('personal_agent.service', 'INFO') as logs:
            job, _ = self.turn('오늘 저녁은 뭐해 먹을까?')
        self.assertEqual(job['delivery'], 'sent')
        lines = [line for line in logs.output if 'telegram presence' in line]
        self.assertEqual(len(lines), 2, 'the 👀 and the outcome reaction')
        for line in lines:
            self.assertIn('set_message_reaction failed: TelegramRejected status=400', line)
            for secret in ('REACTION_INVALID', 'owner-text', 'SECRET-TOKEN', '저녁'):
                self.assertNotIn(secret, line)

    def test_unsupported_draft_falls_back_to_typing(self):
        self.connect_model()
        self.failing = {'sendRichMessageDraft': ProviderError('method not found'),
                        'sendMessageDraft': ProviderError('method not found')}
        self.during_model = lambda job: [self.service.acknowledge_long_work(now=job['created'] + t) for t in (6, 7, 9)]
        self.turn('긴 요청')
        self.assertEqual(self.methods().count('sendRichMessageDraft'), 1, 'a refused rich draft is not retried')
        self.assertEqual(self.methods().count('sendMessageDraft'), 1, 'a failed plain draft is not retried')
        self.assertIn('sendChatAction', self.methods())
        self.assertEqual(len(self.sends()), 1)

    def test_a_refused_thinking_block_falls_back_to_the_plain_dots_draft(self):
        # #858: a client/API without the rich draft still gets the dots, as text.
        self.connect_model()
        self.failing = {'sendRichMessageDraft': ProviderError('Bad Request: method not found')}
        self.during_model = lambda job: [self.service.acknowledge_long_work(now=job['created'] + t) for t in (6, 8, 10)]
        job, _ = self.turn('긴 요청')
        self.assertEqual(self.draft_methods(), ['sendRichMessageDraft', 'sendMessageDraft', 'sendMessageDraft',
                                                'sendMessageDraft'])
        plain = [body for method, body in self.calls if method == 'sendMessageDraft']
        self.assertEqual(plain, [{'chat_id': CHAT, 'draft_id': draft_id_for(job['id']), 'text': frame, 'can_stop': True}
                                 for frame in DOTS_FRAMES[:3]])
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
        self.assertEqual(labels, ['다시 시도'], 'no 상세 button (owner direction 2026-09-30)')
        # 👀 came first; a failed outcome removes it and never shows a done emoji (#835).
        self.assertEqual(self.methods()[0], 'setMessageReaction')
        self.assertEqual(self.emojis(), [RECEIVED_REACTION, CLEAR_REACTION])

    def usage_limit_reply(self, *, alternate_signed_in=True):
        job_id, _source = self.receive('이전 요청')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='failed',response='',error=?,delivery='pending' WHERE id=?",
                       ('Claude Code 구독의 사용량 한도에 도달했습니다.',job_id))
        self.service.record_turn_provenance(job_id,route='subscription',engine='claude-code',
                                            failure_class='usage-limit')
        self.store.put('subscription_engine',{'id':'claude-code','authentication':'owner-confirmed-official-login'})
        self.store.put('engine_login',{'claude-code':{'state':'signed-in'},
                                       'codex':{'state':'signed-in' if alternate_signed_in else 'unchecked'}})
        self.service.subscription_engines.finder=lambda _command:'/fake/cli'
        self.service.deliver_one()
        return self.store.job(job_id)

    def test_usage_limit_reply_offers_only_an_existing_signed_in_alternate(self):
        job=self.usage_limit_reply()
        [reply]=self.sends()
        self.assertIn('사용량 한도',reply['text'])
        rows=reply['reply_markup']['inline_keyboard']
        self.assertEqual(rows[1],[{'text':'Codex로 전환','callback_data':f"p7e:{job['id']}:codex"}])

    def test_usage_limit_route_choice_changes_route_without_replaying_work_and_consumes_stale_choice(self):
        job=self.usage_limit_reply()
        reply_id=self.service.telegram_turns.get(job['id'])['reply_message_id']
        self.tap(f"p7e:{job['id']}:codex",reply_id,sender=999,callback_id='foreign')
        self.tap(f"p7e:{job['id']}:codex",reply_id+1,callback_id='wrong-message')
        self.assertEqual(self.store.config('subscription_engine')['id'],'claude-code')
        def login_without_service_lock(*args,**kwargs):
            self.assertFalse(self.service.lock._is_owned(),'CLI login checks run outside the service lock')
            return {'state':'signed-in'}
        with mock.patch.object(self.service,'check_engine_login',side_effect=login_without_service_lock):
            self.tap(f"p7e:{job['id']}:codex",reply_id,callback_id='choose')
        self.assertEqual(self.store.config('subscription_engine')['id'],'codex')
        self.assertEqual(len(self.store.jobs()),1,'route selection does not retry the failed Work')
        self.assertEqual(self.store.job(job['id'])['status'],'failed')
        self.assertEqual(self.store.turn_provenance(job['id'])['usage_limit_recovery_selected'],'codex')
        answer=[body for method,body in self.calls if method=='answerCallbackQuery'][-1]
        self.assertIn('자동으로 다시 실행하지 않았어요',answer['text'])
        self.assertIn('다시 보내 주세요',answer['text'])
        # Even if the owner later returns to Claude Code, the old reply's button is spent.
        self.store.put('subscription_engine',{'id':'claude-code'})
        with mock.patch.object(self.service,'check_engine_login',return_value={'state':'signed-in'}):
            self.tap(f"p7e:{job['id']}:codex",reply_id,callback_id='stale')
        self.assertEqual(self.store.config('subscription_engine')['id'],'claude-code')
        self.assertEqual(len(self.store.jobs()),1)

    def test_web_usage_limit_route_choice_is_bound_and_revalidated_by_the_server(self):
        job=self.usage_limit_reply()
        body={'engine':'codex','officially_authenticated':True,'recovery_work_id':job['id'],
              'expected_current':'claude-code'}
        with mock.patch.object(self.service,'check_engine_login',return_value={'state':'signed-in'}):
            self.service.connect_subscription_engine(body)
        self.assertEqual(self.store.config('subscription_engine')['id'],'codex')
        self.assertEqual(self.store.turn_provenance(job['id'])['usage_limit_recovery_selected'],'codex')
        self.assertEqual(len(self.store.jobs()),1,'route selection does not replay the failed Work')
        with mock.patch.object(self.service,'check_engine_login',return_value={'state':'signed-in'}):
            with self.assertRaisesRegex(ValueError,'이미 처리되었거나 더 이상 유효하지 않습니다'):
                self.service.connect_subscription_engine(body)
        self.store.put('subscription_engine',{'id':'claude-code'})
        self.store.put_turn_provenance(job['id'],{**self.store.turn_provenance(job['id']),
                                                   'usage_limit_recovery_selected':None})
        stale={**body,'engine':'claude-code'}
        with self.assertRaisesRegex(ValueError,'선택할 수 있는 로그인된 AI 연결이 아니거나 현재 선택이 바뀌었습니다'):
            self.service.connect_subscription_engine(stale)

    def test_usage_limit_without_an_alternate_points_to_ai_settings(self):
        self.usage_limit_reply(alternate_signed_in=False)
        [reply]=self.sends()
        self.assertIn('AI 설정에서 선택할 수 있어요',reply['text'])
        self.assertNotIn('p7e:',json.dumps(reply.get('reply_markup',{})))

    def test_usage_limit_choice_is_refused_if_the_alternate_login_is_no_longer_verified(self):
        job=self.usage_limit_reply()
        reply_id=self.service.telegram_turns.get(job['id'])['reply_message_id']
        with mock.patch.object(self.service,'check_engine_login',return_value={'state':'unknown'}):
            self.tap(f"p7e:{job['id']}:codex",reply_id)
        self.assertEqual(self.store.config('subscription_engine')['id'],'claude-code')
        self.assertNotIn('usage_limit_recovery_selected',self.store.turn_provenance(job['id']))
        answer=[body for method,body in self.calls if method=='answerCallbackQuery'][-1]
        self.assertTrue(answer['show_alert'])
        self.assertIn('로그인 상태를 확인하지 못해 전환하지 않았습니다',answer['text'])

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

    def test_one_retry_per_failed_work_across_control_and_conversation(self):
        """Review P3: the tap and a conversational "다시 해줘" cannot both replay the same failure."""
        job, _ = self.failed_turn()
        reply_id = self.service.telegram_turns.get(job['id'])['reply_message_id']
        self.tap(f"p7r:{job['id']}", reply_id)
        self.assertEqual(len(self.store.jobs()), 2)
        # Before the tapped retry runs, the owner also types a retry of the same failure.
        self.service.use_decision_engine(self.relation_engine({'다시 해줘': FOLLOWUP_RETRY}))
        typed, _ = self.receive('다시 해줘')
        with self.store.db() as db:   # run the typed turn first
            db.execute('UPDATE jobs SET created=0 WHERE id=?', (typed,))
        self.service.run_one()
        self.service.deliver_one()
        # #730: the typed turn does not replay the failure a second time; it runs as its own Work.
        [continuity] = [e for e in self.store.task_events(typed) if e['tool'] == 'conversation_continuity']
        self.assertEqual(continuity['trace']['relation'], 'retry-refused-ran-current')
        self.assertFalse(continuity['trace']['executed'])
        self.assertIn('이미 한 번 다시 시도했습니다', continuity['trace']['reason'])
        # The tapped retry itself still runs once.
        self.model_error = None
        self.service.run_one()
        tapped = [j for j in self.store.jobs() if str(j.get('request_key') or '').startswith('tgr:')][0]
        self.assertEqual(self.store.job(tapped['id'])['status'], 'succeeded')

    def test_a_tap_after_a_conversational_retry_is_refused(self):
        job, _ = self.failed_turn()
        reply_id = self.service.telegram_turns.get(job['id'])['reply_message_id']
        self.service.use_decision_engine(self.relation_engine({'다시 해줘': FOLLOWUP_RETRY}))
        self.model_error = None
        self.turn('다시 해줘')
        self.assertEqual(self.store.jobs()[0]['relation_kind'], FOLLOWUP_RETRY)
        count = len(self.store.jobs())
        self.tap(f"p7r:{job['id']}", reply_id, callback_id='late')
        self.assertEqual(len(self.store.jobs()), count)
        answer = [body for method, body in self.calls if method == 'answerCallbackQuery'][-1]
        self.assertIn('이미 한 번 다시 시도했습니다', answer['text'])

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
        self.assertFalse(edits[-1]['reply_markup'].get('inline_keyboard'), 'the used control is removed and nothing else remains')
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
        self.assertFalse((reply.get('reply_markup') or {}).get('inline_keyboard'), 'no retry and no 상세 button')
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
        self.assertEqual(len(self.draft_methods()), 1, 'no draft after Stop')
        self.assertNotIn('sendChatAction', self.methods())
        # #606 T1: Stop is checked before the next model turn or tool call, so
        # the running Work ends there and its one real result says why.
        self.assertEqual(job['status'], 'failed', 'Stop ended the Work before its next step')
        notice, answer = self.sends()
        self.assertEqual(notice['text'], AgentService.STOP_RUNNING_TEXT)
        self.assertIn('다음 단계는 실행하지 않아요', notice['text'])
        self.assertNotIn('취소했', notice['text'])
        self.assertEqual(notice['reply_parameters']['message_id'], message_id)
        self.assertIn(WORK_STOPPED, answer['text'], 'the real result is still delivered once')
        self.assertNotIn(self.text, answer['text'])

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
        # #606 T1: the next step does not run; the recorded effect is not undone
        # and nothing claims the request was never executed.
        self.assertEqual(self.store.job(job['id'])['status'], 'failed')
        self.assertFalse(any('멈췄어요. 이 요청은 실행하지' in body['text'] for body in self.sends()))

    def test_a_repeated_stop_update_sends_one_notice(self):
        self.connect_model()
        outcomes = []

        def think(job):
            self.service.acknowledge_long_work(now=job['created'] + 6)
            outcomes.extend([self.stop(job['id']), self.stop(job['id'])])
        self.during_model = think
        self.turn('긴 조사 부탁해')
        self.assertEqual(outcomes, ['running', 'duplicate'])
        self.assertEqual([body['text'] for body in self.sends()].count(AgentService.STOP_RUNNING_TEXT), 1)

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


class RestartRecoveryTests(NativePresenceTestCase):
    def test_running_work_without_a_card_gets_one_truthful_interrupted_reply_after_restart(self):
        running, source = self.receive('긴 요청')
        deleting, deleting_source = self.receive('카드를 지우던 요청')
        carded, _ = self.receive('카드가 있던 요청')
        web = self.store.enqueue('웹 요청', 'web-1', channel='web')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id IN (?,?,?,?)", (running, deleting, carded, web))
            db.execute('INSERT INTO telegram_task_cards VALUES (?,?,?,?,?)', (deleting, CHAT, 78, 'deleting', time.time()))
            db.execute('INSERT INTO telegram_task_cards VALUES (?,?,?,?,?)', (carded, CHAT, 77, 'running', time.time()))
        restarted = AgentService(self.store, self.service.adapter, self.service.telegram_transport)
        self.assertCountEqual(restarted.recover_interrupted_work(), [running, deleting])
        self.assertEqual(self.store.job(running)['status'], 'interrupted')
        self.assertEqual(self.store.job(deleting)['status'], 'interrupted')
        self.assertEqual(self.store.job(carded)['delivery'], 'none', 'the card remains its recovery surface')
        self.assertEqual(self.store.job(web)['delivery'], 'none')
        self.assertIsNone(self.store.task_card(deleting), 'restart settles the deletion marker')
        restarted.deliver_one()
        restarted.deliver_one()
        replies = self.sends()
        self.assertEqual(len(replies), 2)
        expected='이 요청은 중단되었습니다. 자동으로 다시 실행하지 않았습니다.\n\n'
        expected+='실행 중 재시작되었습니다. 자동으로 재호출하지 않습니다.\n\n'
        expected+='AgentOS 웹에서 실행 기록과 다음 단계를 확인하세요.'
        self.assertEqual({reply['reply_parameters']['message_id'] for reply in replies}, {source,deleting_source})
        self.assertTrue(all(reply['text']==expected for reply in replies))
        for reply in replies:
            labels = [button['text'] for button in reply['reply_markup']['inline_keyboard'][0]]
            self.assertEqual(labels, ['다시 시도'])
        self.assertFalse(restarted.run_one(), 'nothing is re-run automatically')

    def test_uncertain_delivery_is_not_resent_by_restart_recovery(self):
        job_id, _ = self.receive('보내는 중이던 요청')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='succeeded',delivery='sending' WHERE id=?", (job_id,))
        self.assertEqual(self.service.recover_interrupted_work(), [])
        self.service.deliver_one()
        self.assertEqual(self.store.job(job_id)['delivery'], 'unknown')
        self.assertEqual(self.sends(), [])


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


def write_event(tool, saved=True, status='succeeded'):
    return {'tool': tool, 'status': status, 'trace': {'evidence': {'saved': saved}}}


class OutcomeReactionTests(unittest.TestCase):
    """#835: the outcome reaction is a pure function of the decided outcome and observed events."""

    def test_every_presence_reaction_is_a_documented_telegram_reaction(self):
        self.assertEqual(PRESENCE_REACTIONS, (RECEIVED_REACTION, DONE_REACTION, WROTE_REACTION))
        for emoji in PRESENCE_REACTIONS:
            self.assertIn(emoji, TELEGRAM_REACTION_EMOJI)
        for emoji in (*RECEIVED_CANDIDATES, *CLOSING_CANDIDATES, *PROGRESS_CANDIDATES):
            self.assertIn(emoji, TELEGRAM_REACTION_EMOJI)
        self.assertFalse({'👎', '🤬', '💩', '🤡', '🖕', '😈', '🤮'} &
                         set(RECEIVED_CANDIDATES + CLOSING_CANDIDATES + PROGRESS_CANDIDATES))
        self.assertEqual((RECEIVED_REACTION, DONE_REACTION, WROTE_REACTION), ('👀', '👌', '✍'))

    def test_succeeded_is_done_and_an_observed_note_or_memory_write_is_writing(self):
        self.assertEqual(outcome_reaction('succeeded'), DONE_REACTION)
        self.assertEqual(outcome_reaction('succeeded', [write_event('save_note')]), WROTE_REACTION)
        self.assertEqual(outcome_reaction('succeeded', [write_event('save_memory')]), WROTE_REACTION)
        aliased = {'tool': 'package.save_fact', 'status': 'succeeded',
                   'trace': {'host_action': 'save_memory', 'evidence': {'saved': True}}}
        self.assertEqual(outcome_reaction('succeeded', [aliased]), WROTE_REACTION)
        # A pending MemoryCandidate, a failed write or another tool is not a write.
        for events in ([write_event('save_memory', saved=False)], [write_event('save_note', status='failed')],
                       [write_event('save_note', status='running')], [write_event('web_search')],
                       [{'tool': 'save_note', 'status': 'succeeded', 'trace': {}}]):
            self.assertEqual(outcome_reaction('succeeded', events), DONE_REACTION, events)

    def test_no_done_reaction_unless_succeeded_and_delivered(self):
        done = (DONE_REACTION, WROTE_REACTION)
        for outcome in ('partial', 'failed', 'unknown', 'cancelled', 'interrupted'):
            with self.subTest(outcome=outcome):
                reaction = outcome_reaction(outcome, [write_event('save_note')])
                self.assertEqual(reaction, CLEAR_REACTION)
                self.assertNotIn(reaction, done)
        self.assertEqual(outcome_reaction('succeeded', delivered=False), CLEAR_REACTION)
        self.assertEqual(outcome_reaction('succeeded', [write_event('save_note')], blocked=True), CLEAR_REACTION)

    def test_a_succeeded_work_awaiting_the_owners_approval_is_not_done(self):
        # Typed flags only: a calendar draft awaiting approval, an unapplied
        # draft needing confirmation, or the caller's pending-approval signal.
        for events in ([{'tool': 'calendar_draft', 'status': 'succeeded', 'trace': {'state': 'awaiting-approval'}}],
                       [{'tool': 'x', 'status': 'succeeded',
                         'trace': {'evidence': {'requires_owner_approval': True, 'applied': False}}}],
                       [{'tool': 'y', 'status': 'succeeded', 'trace': {'evidence': {'requires_owner_confirmation': True}}}]):
            self.assertEqual(outcome_reaction('succeeded', events), CLEAR_REACTION, events)
        self.assertEqual(outcome_reaction('succeeded', awaiting_owner=True), CLEAR_REACTION)
        applied = [{'tool': 'y', 'status': 'succeeded',
                    'trace': {'evidence': {'requires_owner_confirmation': True, 'applied': True}}}]
        self.assertEqual(outcome_reaction('succeeded', applied), DONE_REACTION)

    def test_an_undecided_outcome_keeps_the_looking_reaction(self):
        for outcome in ('queued', 'running', 'awaiting_connection', 'awaiting_drive', 'awaiting_context', None, 'x'):
            self.assertIsNone(outcome_reaction(outcome), outcome)

    def test_poll_includes_the_stop_update_kind(self):
        self.assertIn('stopped_message_generation', TELEGRAM_POLL_UPDATE_KINDS)


class OutcomeReactionServiceTests(NativePresenceTestCase):
    """#835 through the real delivery path: 👀 on receipt, the outcome reaction only after the answer."""

    def test_looking_appears_as_soon_as_the_work_runs(self):
        job_id, message_id = self.receive('오래 걸리는 질문')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job_id,))
        self.service.acknowledge_long_work(now=self.store.job(job_id)['created'] + 0.1)
        self.assertEqual(self.reactions(), [{'chat_id': CHAT, 'message_id': message_id,
                                             'reaction': [{'type': 'emoji', 'emoji': RECEIVED_REACTION}]}])
        # present_turn later in the same run does not react twice.
        self.service.present_turn(self.store.job(job_id))
        self.assertEqual(len(self.reactions()), 1)

    def test_superseded_parked_work_clears_looking_reaction(self):
        job_id, message_id = self.receive('연결 후 이어서 해줘')
        self.service.present_turn(self.store.job(job_id))
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='awaiting_connection',delivery='pending' WHERE id=?", (job_id,))
        self.service.cancel_superseded_work([job_id], notify=False)
        self.assertEqual(self.reactions()[-1], {'chat_id': CHAT, 'message_id': message_id, 'reaction': []})

    def settle(self, status, response='결과', delivery='pending'):
        job_id, _ = self.receive('요청')
        self.service.present_turn(self.store.job(job_id))
        with self.store.db() as db:
            db.execute('UPDATE jobs SET status=?,response=?,delivery=? WHERE id=?', (status, response, delivery, job_id))
        self.service.deliver_one()
        return job_id

    def test_no_done_reaction_on_failed_partial_unknown_or_interrupted(self):
        for status in ('failed', 'partial', 'unknown', 'interrupted'):
            with self.subTest(status=status):
                self.calls.clear()
                self.settle(status)
                self.assertEqual(self.emojis(), [RECEIVED_REACTION, CLEAR_REACTION])
                self.assertEqual(self.after_answer(), ['setMessageReaction'])
                self.assertEqual(self.reactions()[-1]['reaction'], [])

    def test_done_reaction_only_after_the_answer_on_succeeded(self):
        self.settle('succeeded')
        self.assertEqual(self.methods(), ['setMessageReaction', 'sendMessage', 'setMessageReaction'])
        self.assertEqual(self.emojis(), [RECEIVED_REACTION, DONE_REACTION])

    def test_uncertain_delivery_never_shows_done(self):
        self.failing = {'sendMessage': ProviderError('response lost')}
        job_id = self.settle('succeeded')
        self.assertEqual(self.store.job(job_id)['delivery'], 'unknown')
        self.assertEqual(self.emojis(), [RECEIVED_REACTION, CLEAR_REACTION])

    def test_a_parked_work_keeps_looking_until_it_ends(self):
        self.settle('awaiting_connection', response='연결이 필요해요.')
        self.assertEqual(self.emojis(), [RECEIVED_REACTION])

    def test_a_note_write_that_succeeded_gets_the_writing_reaction(self):
        self.connect_model()

        def wrote(job):
            with self.store.db() as db:
                db.execute('INSERT INTO tool_events(job_id,tool,status,detail,created) VALUES (?,?,?,?,?)',
                           (job['id'], 'save_note', 'succeeded', json.dumps({'evidence': {'saved': True, 'id': 'n1'}}),
                            time.time()))
        self.during_model = wrote
        # The words say nothing about notes: only the observed event chooses ✍.
        job, _ = self.turn('오늘 저녁은 뭐해 먹을까?')
        self.assertEqual(job['status'], 'succeeded')
        self.assertEqual(self.emojis(), [RECEIVED_REACTION, WROTE_REACTION])

    def test_a_correction_turn_gets_the_same_looking_reaction(self):
        self.connect_model()
        self.turn('오늘 저녁 메뉴 추천해줘')
        self.calls.clear()
        self.service.use_decision_engine(self.relation_engine({'아니 국물 말고': FOLLOWUP_CORRECTION}))
        _job, message_id = self.turn('아니 국물 말고')
        self.assertEqual(self.emojis(), [RECEIVED_REACTION, DONE_REACTION])
        self.assertEqual({body['message_id'] for body in self.reactions()}, {message_id})


class LiveWaitTests(NativePresenceTestCase):
    """#835: typing… stays alive under the dots draft, and nothing follows the answer."""

    def tick_every(self, job, start, end, step=0.25):
        """Tick like the acknowledge thread; returns [(offset, methods sent in that tick)]."""
        seen = []
        for index in range(int(round((end - start) / step)) + 1):
            offset = start + index * step
            before = len(self.calls)
            self.service.acknowledge_long_work(now=job['created'] + offset)
            seen.append((offset, [method for method, _body in self.calls[before:]]))
        return seen

    def test_typing_is_refreshed_while_the_dots_draft_is_shown(self):
        self.connect_model()
        ticks = []
        self.during_model = lambda job: ticks.extend(self.tick_every(job, 0, 20))
        job, _ = self.turn('긴 조사 부탁해')
        typing = [offset for offset, methods in ticks if 'sendChatAction' in methods]
        drafted = [offset for offset, methods in ticks if 'sendRichMessageDraft' in methods]
        self.assertEqual(drafted[0], 5, drafted)
        self.assertTrue([offset for offset in typing if offset > drafted[0]], 'typing continues under the draft')
        # From the first typing… to the end, never a gap the 5 s typing lifetime could expire in.
        gaps = [later - earlier for earlier, later in zip(typing, typing[1:])] + [20 - typing[-1]]
        self.assertLessEqual(max(gaps), 4.25, typing)
        # One draft edit per dots_refresh at most, each the next frame, never empty.
        self.assertTrue(all(later - earlier >= 1.5 for earlier, later in zip(drafted, drafted[1:])), drafted)
        self.assertEqual(self.drafts()[:4], [DOTS_FRAMES[0], DOTS_FRAMES[1], DOTS_FRAMES[2], DOTS_FRAMES[0]])
        self.assertTrue(all(self.drafts()))
        # At most one presence call per Work per tick.
        self.assertTrue(all(len(methods) <= 1 for _offset, methods in ticks))
        self.assertEqual(job['status'], 'succeeded')

    def test_nothing_is_sent_after_the_final_answer(self):
        self.connect_model()
        self.during_model = lambda job: self.tick_every(job, 0, 8)
        job_id, _ = self.receive('긴 조사 부탁해')
        self.service.run_one()
        self.assertIn('sendRichMessageDraft', self.methods())
        # Decided but not yet delivered: no more typing… or draft either.
        before = len(self.calls)
        self.tick_every(self.store.job(job_id), 8, 12)
        self.assertEqual(len(self.calls), before)
        self.service.deliver_one()
        self.tick_every(self.store.job(job_id), 12, 40, step=1)
        self.assertEqual(self.after_answer(), ['setMessageReaction'], 'only the outcome reaction, on the owner message')
        self.assertEqual(self.emojis(), [RECEIVED_REACTION, DONE_REACTION])


class DotsFrameTests(unittest.TestCase):
    def test_dots_cycle_follow_a_step_line_and_are_never_empty(self):
        self.assertEqual([draft_frame('', frame) for frame in range(4)], ['·', '· ·', '· · ·', '·'])
        self.assertEqual(draft_frame('웹 검색 중: 환율', 1), '웹 검색 중: 환율 · ·')
        self.assertEqual(draft_frame('다시 해보는 중…', 2), '다시 해보는 중 · · ·', 'the dots replace an ellipsis')
        self.assertEqual(draft_frame('찾는 중...', 0), '찾는 중 ·')
        self.assertEqual(draft_frame(None, 0), '·')


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
        self.assertEqual(render_telegram_html('# 제목\n- 하나\n* 둘\n*기울임* 과 **굵게**'),
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

    def test_a_markdown_table_becomes_one_line_per_row(self):
        """#848: Telegram has no tables; a raw ``| a | b |`` block reached the owner."""
        table = '| 출발 코스 | 티타임 | 표시 가격 |\n|---|---|---:|\n| A | 06:30 | 218,500원 |\n| B | 07:12 | 219,000원 |\n| C | 07:54 | 221,000원 |'
        self.assertEqual(render_telegram_html(table),
                         '<b>출발 코스 · 티타임 · 표시 가격</b>\nA · 06:30 · 218,500원\nB · 07:12 · 219,000원\nC · 07:54 · 221,000원')
        self.assertNotIn('|', visible(render_telegram_html(table)))
        self.assertNotIn('---', visible(render_telegram_html(table)))

    def test_table_alignment_separators_cells_and_surrounding_text(self):
        # Alignment colons are separator syntax; bold and links inside cells are kept; text around the table is untouched.
        text = ('정리했어요.\n\n| 항목 | 값 |\n| :--- | ---: |\n| **가격** | [보기](https://x.test/a) |\n| 재고 | 3개 |\n\n'
                '더 필요하면 말씀해 주세요.')
        self.assertEqual(render_telegram_html(text),
                         '정리했어요.\n\n<b>항목 · 값</b>\n<b>가격</b> · <a href="https://x.test/a">보기</a>\n재고 · 3개\n\n'
                         '더 필요하면 말씀해 주세요.')
        # A pipe in prose or a lone row without a separator line is not a table.
        for plain in ('a | b', '| x |', '| a | b |\n| c | d |', '|---|'):
            with self.subTest(plain=plain):
                self.assertEqual(visible(render_telegram_html(plain)), plain)
        # An escaped pipe is cell content; an empty cell is dropped from the line.
        self.assertEqual(render_telegram_html('| a \\| b | c |\n|--|--|\n| 1 |  |'), '<b>a | b · c</b>\n1')
        self.valid(text)

    def test_a_cell_ending_in_a_backslash_still_ends_at_the_pipe(self):
        # #852 (#851 review P2): only an odd run of backslashes escapes a pipe.  A
        # cell that ends in one backslash (an even run of two before the
        # delimiter) keeps its backslash and the pipe stays a delimiter.
        self.assertEqual(render_telegram_html('| C:\\\\| yes |\n|--|--|\n| x | y |'), '<b>C:\\\\ · yes</b>\nx · y')
        self.assertEqual(render_telegram_html('| a \\\\\\| b | c |\n|--|--|\n| 1 | 2 |'), '<b>a \\\\| b · c</b>\n1 · 2')
        # Unchanged: a lone escaped pipe, and a backslash elsewhere in a cell.
        self.assertEqual(render_telegram_html('| a \\| b | c |\n|--|--|\n| 1 | 2 |'), '<b>a | b · c</b>\n1 · 2')
        self.assertEqual(render_telegram_html('| C:\\\\tmp | y |\n|--|--|\n| 1 | 2 |'), '<b>C:\\\\tmp · y</b>\n1 · 2')
        # #872 review P2: a long run of backslashes not followed by a pipe is scanned once, not quadratically.
        run = '\\' * 200_000
        started = time.monotonic()
        rendered = render_telegram_html(f'| {run}x | y |\n|--|--|\n| 1 | 2 |')
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(rendered, f'<b>{run}x · y</b>\n1 · 2')


def visible(rendered):
    """What the owner reads: tags removed, entities decoded."""
    return html.unescape(re.sub(r'<[^>]+>', '', rendered))


class RenderContentPreservationTests(unittest.TestCase):
    """Independent review P2: rendering may only consume delimiters, never change content."""

    def test_arithmetic_identifiers_and_unmatched_markers_are_unchanged(self):
        for text in ('2**10 = 1024 이고 x**2 + y**2', 'a**b**c', 'x**2', '__init__ 호출', 'obj.__dict__',
                     'snake_case_name 과 _private', '**unclosed', 'closed** only', '** **', 'a*b*c', '2 * 3 * 4',
                     'x*y + z*w', 'foo__bar__baz'):
            with self.subTest(text=text):
                self.assertEqual(visible(render_telegram_html(text)), text)

    def test_only_consumed_delimiters_disappear(self):
        for text, expected in (('**갈비탕**을 추천', '갈비탕을 추천'), ('이건 **중요**해', '이건 중요해'),
                               ('*기울임*을', '기울임을'), ('`2**10`', '2**10'), ('__a *b__ c*', '__a b__ c'),
                               ('[링크](https://x.test/a_b__c)', '링크')):
            with self.subTest(text=text):
                self.assertEqual(visible(render_telegram_html(text)), expected)
        self.assertEqual(render_telegram_html('**갈비탕**을'), '<b>갈비탕</b>을')

    def test_same_type_entities_are_never_nested(self):
        self.assertEqual(render_telegram_html('# **제목**'), '<b>제목</b>')
        self.assertEqual(render_telegram_html('## 오늘 **꼭** 할 일'), '<b>오늘 꼭 할 일</b>')
        for text in ('# **a** *b* `c`', '### **[x](https://x.test)**', '**a *b* c**'):
            rendered = render_telegram_html(text)
            self.assertNotRegex(rendered, r'<b>[^/]*<b>', text)
            self.assertNotRegex(rendered, r'<i>[^/]*<i>', text)


class EntityRejectionTests(NativePresenceTestCase):
    """A definite Telegram refusal of the formatting gets one plain resend; nothing else does."""

    def setUp(self):
        super().setUp()
        self._base_transport = self.service.telegram_transport

    def reject(self, response):
        original = self._base_transport

        def transport(url, body=None, headers=None, timeout=60):
            if url.endswith('/sendMessage') and body.get('parse_mode') == 'HTML':
                self.calls.append(('sendMessage', body))
                if isinstance(response, Exception):
                    raise response
                return response
            return original(url, body, headers, timeout)
        self.service.telegram_transport = transport

    def test_cant_parse_entities_resends_once_as_plain_text(self):
        self.connect_model()
        self.text = '**굵게** 답변'
        self.reject({'ok': False, 'error_code': 400,
                     'description': "Bad Request: can't parse entities: unexpected end tag at byte offset 3"})
        job, _ = self.turn('질문')
        first, second = self.sends()
        self.assertEqual(first['parse_mode'], 'HTML')
        self.assertNotIn('parse_mode', second)
        self.assertEqual(second['text'], self.text, 'the plain resend is the unchanged answer')
        self.assertEqual(self.store.job(job['id'])['delivery'], 'sent')

    def test_any_other_failure_keeps_unknown_and_is_not_resent(self):
        for response in ({'ok': False, 'error_code': 400, 'description': 'Bad Request: chat not found'},
                         {'ok': False, 'error_code': 403, 'description': "Forbidden: can't parse entities"},
                         {'ok': False, 'error_code': 429, 'description': 'Too Many Requests'},
                         ProviderError('response lost')):
            with self.subTest(response=response):
                self.calls.clear()
                self.connect_model()
                self.reject(response)
                job, _ = self.turn('질문')
                self.assertEqual(len(self.sends()), 1)
                self.assertEqual(self.store.job(job['id'])['delivery'], 'unknown')


class TelegramErrorEnvelopeTests(unittest.TestCase):
    """`telegram_request_json` keeps Telegram's 4xx envelope and makes exactly one request."""

    def opener(self, error=None, body=b'{"ok": true, "result": 1}'):
        opened = []

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class Opener:
            def open(self, req, timeout=None):
                opened.append(req.full_url)
                if error is not None:
                    raise error
                return Response(body)
        return Opener(), opened

    def http_error(self, code, payload):
        return urllib.error.HTTPError('https://api.telegram.org/botX/sendMessage', code, 'err', {},
                                      io.BytesIO(payload))

    def test_4xx_envelope_is_returned_as_data(self):
        opener, opened = self.opener(self.http_error(
            400, b'{"ok":false,"error_code":400,"description":"Bad Request: can\'t parse entities"}'))
        with mock.patch('personal_agent.conversation_handoff._build_opener', return_value=opener):
            result = telegram_request_json('https://api.telegram.org/botX/sendMessage', {'a': 1})
        self.assertEqual(result, {'ok': False, 'error_code': 400, 'description': "Bad Request: can't parse entities"})
        self.assertEqual(len(opened), 1)
        channel = TelegramChannel(lambda: lambda *a, **k: result, lambda: 'X')
        with self.assertRaises(TelegramRejected) as caught:
            channel.send_message(1, 'x')
        self.assertTrue(caught.exception.entity_parse_error)
        self.assertNotIn('parse', str(caught.exception), 'the owner-facing text never carries Telegram detail')

    def test_other_errors_raise_owner_safe_provider_errors_once(self):
        for error in (self.http_error(500, b'{"ok":false}'), self.http_error(400, b'not json'),
                      urllib.error.URLError(TimeoutError()), TimeoutError()):
            with self.subTest(error=type(error).__name__):
                opener, opened = self.opener(error)
                with mock.patch('personal_agent.conversation_handoff._build_opener', return_value=opener):
                    with self.assertRaises(ProviderError) as caught:
                        telegram_request_json('https://api.telegram.org/botX/sendMessage', {'a': 1})
                self.assertNotIsInstance(caught.exception, TelegramRejected)
                self.assertEqual(len(opened), 1, 'never a second request')

    def test_the_http_status_not_the_body_error_code_classifies_a_refusal(self):
        """#594 item 3: a body claiming 400 on another 4xx status is not an entity-parse refusal."""
        opener, _ = self.opener(self.http_error(
            403, b'{"ok":false,"error_code":400,"description":"Bad Request: can\'t parse entities"}'))
        with mock.patch('personal_agent.conversation_handoff._build_opener', return_value=opener):
            result = telegram_request_json('https://api.telegram.org/botX/sendMessage', {'a': 1})
        self.assertEqual(result['error_code'], 403)
        channel = TelegramChannel(lambda: lambda *a, **k: result, lambda: 'X')
        with self.assertRaises(TelegramRejected) as caught:
            channel.send_message(1, 'x')
        self.assertFalse(caught.exception.entity_parse_error)

    def test_a_bot_token_in_the_failed_url_never_reaches_a_formatted_traceback(self):
        """#594 item 4: the HTTPError (whose URL carries the token) is not a shown cause or context."""
        token = '123456:SECRET-bot-token'
        url = f'https://api.telegram.org/bot{token}/sendMessage'
        errors = (urllib.error.HTTPError(url, 500, 'err', {}, io.BytesIO(b'{"ok":false}')),
                  urllib.error.HTTPError(url, 401, 'err', {}, io.BytesIO(b'not json')),
                  urllib.error.URLError(f'failed {url}'))
        for call, seam in ((telegram_request_json, 'personal_agent.conversation_handoff._build_opener'),
                           (request_json, 'personal_agent.providers.build_opener')):
            for error in errors:
                with self.subTest(call=call.__name__, error=type(error).__name__):
                    opener, _ = self.opener(error)
                    with mock.patch(seam, return_value=opener), self.assertRaises(ProviderError) as caught:
                        call(url, {'a': 1})
                    raised = caught.exception
                    self.assertIsNone(raised.__cause__)
                    self.assertTrue(raised.__suppress_context__)
                    shown = ''.join(traceback.format_exception(type(raised), raised, raised.__traceback__))
                    self.assertNotIn(token, shown)
                    self.assertNotIn(token, str(raised))

    def test_success_body_is_parsed(self):
        opener, _ = self.opener()
        with mock.patch('personal_agent.conversation_handoff._build_opener', return_value=opener):
            self.assertEqual(telegram_request_json('https://api.telegram.org/botX/getMe', {}), {'ok': True, 'result': 1})


class _TelegramNestingChecker(_TagChecker):
    """Also enforce Telegram's nesting rule: bold/italic never contain or sit inside code/pre."""

    def handle_starttag(self, tag, attrs):
        if tag in ('code', 'pre'):
            assert not set(self.stack) & {'b', 'i'}, f'<{tag}> inside {self.stack}'
        if tag in ('b', 'i'):
            assert not set(self.stack) & {'code', 'pre'}, f'<{tag}> inside {self.stack}'
        super().handle_starttag(tag, attrs)


class EmphasisAroundSpansWireTests(unittest.TestCase):
    """#581 live discrepancy: emphasis wrapping a link or inline code leaked literal ``**``.

    Driven through the real ingest -> worker -> delivery path and the real
    ``telegram_request_json`` transport; only the HTTP opener (the network
    seam) is fake, so the asserted text is the exact wire body Telegram gets.
    """

    CASES = (
        ('**[기사 제목](https://news.test/a)** — 요약',
         '<b><a href="https://news.test/a">기사 제목</a></b> — 요약'),
        ('**출처: [A](https://a.test)**', '<b>출처: <a href="https://a.test">A</a></b>'),
        ('*[링크](https://a.test)*', '<i><a href="https://a.test">링크</a></i>'),
        ('**`npm test`** 로 확인', '<code>npm test</code> 로 확인'),
        ('**실행: `make` 후 확인**', '<b>실행: </b><code>make</code><b> 후 확인</b>'),
        ('# 설치 `pip`', '<b>설치 </b><code>pip</code>'),
    )

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(Path(self.temp.name) / 'data')
        self.answer = 'ok'  # the connection check needs a text reply
        self.wire = []

        def model(url, body, headers=None, timeout=60):
            tools = [t.get('function', {}).get('name') or t.get('name') for t in body.get('tools', [])]
            if 'agentos_connection_probe' in tools:
                return {'message': {'content': '', 'tool_calls': [
                    {'id': 'probe', 'function': {'name': 'agentos_connection_probe', 'arguments': {}}}]}}
            return {'message': {'content': self.answer}}

        wire = self.wire

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class Opener:
            def open(self, req, timeout=None):
                method = req.full_url.rsplit('/', 1)[-1]
                wire.append((method, json.loads(req.data.decode())))
                result = {'message_id': 9000 + len(wire)} if method == 'sendMessage' else True
                return Response(json.dumps({'ok': True, 'result': result}).encode())

        patcher = mock.patch('personal_agent.conversation_handoff._build_opener', return_value=Opener())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.service = AgentService(self.store, ModelAdapter(model))  # default telegram_request_json transport
        self.service.save_model({'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434',
                                 'model': 'test-model', 'api_key': ''})
        self.assertTrue(self.service.test_model()['ok'])
        self.store.secret('telegram_token', '123:fixture')
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': GENERATION, 'cursor': 0})

    def test_emphasis_around_links_and_code_reaches_telegram_formatted(self):
        for update_id, (answer, expected) in enumerate(self.CASES, start=1):
            with self.subTest(answer=answer):
                self.answer = answer
                self.wire.clear()
                self.service.ingest_update({'update_id': update_id, 'message': {
                    'message_id': 700 + update_id, 'from': {'id': CHAT},
                    'chat': {'id': CHAT, 'type': 'private'}, 'text': f'질문 {update_id}'}}, GENERATION)
                self.service.run_one()
                self.service.deliver_one()
                [reply] = [body for method, body in self.wire if method == 'sendMessage']
                self.assertEqual(reply['parse_mode'], 'HTML')
                self.assertEqual(reply['text'], expected)
                self.assertNotIn('**', reply['text'])
                checker = _TelegramNestingChecker()
                checker.feed(reply['text'])
                checker.close()
                self.assertEqual(checker.stack, [])

    def test_rendering_around_spans_still_only_consumes_delimiters(self):
        for text in ('**a [b** c](https://x.test)', '`a **b` c**', '**[x](https://x.test)', 'x**`y`**z',
                     '2**`n`** 이고', '**`a`** **`b`**', '# **`c`**', '*`i`* 와 **[l](https://l.test)**'):
            with self.subTest(text=text):
                rendered = render_telegram_html(text)
                checker = _TelegramNestingChecker()
                checker.feed(rendered)
                checker.close()
                self.assertEqual(checker.stack, [])
                self.assertNotRegex(rendered, r'<(b|i)></\1>')
        # Unmatched or arithmetic-adjacent markers stay literal; matched ones are consumed.
        self.assertEqual(visible(render_telegram_html('**a [b** c](https://x.test)')), '**a b** c')
        self.assertEqual(visible(render_telegram_html('x**`y`**z')), 'x**y**z')
        self.assertEqual(visible(render_telegram_html('**`a`** **`b`**')), 'a b')
        self.assertEqual(visible(render_telegram_html('*`i`* 와 **[l](https://l.test)**')), 'i 와 l')

    def test_code_inside_a_link_is_restored_never_a_placeholder(self):
        # Review P2: a code span inside a link label or URL must not leak U+E000/U+E001.
        self.assertEqual(render_telegram_html('[run `foo` now](https://example.com)'),
                         '<a href="https://example.com">run foo now</a>')
        self.assertEqual(render_telegram_html('**[run `foo`](https://example.com)**'),
                         '<b><a href="https://example.com">run foo</a></b>')
        self.assertEqual(render_telegram_html('[x](https://a.test/`y`)'), '[x](https://a.test/<code>y</code>)')
        for text in ('[run `foo` now](https://example.com)', '[x](https://a.test/`y`)', '[`a`](https://a.test) `b`'):
            with self.subTest(text=text):
                rendered = render_telegram_html(text)
                self.assertNotRegex(rendered, '[\ue000\ue001]')


class ChannelWireTests(unittest.TestCase):
    def test_presence_method_bodies_follow_bot_api_10_3(self):
        log = []

        def transport(url, body, headers, timeout=15):
            log.append((url.rsplit('/', 1)[-1], body, timeout))
            return {'ok': True, 'result': True}
        channel = TelegramChannel(lambda: transport, lambda: 'BOT:TOKEN')
        channel.set_message_reaction(1, 2, '👀')
        channel.send_chat_action(1)
        channel.send_message_draft(1, 77, '·')
        channel.set_message_reaction(1, 2, CLEAR_REACTION)
        channel.send_message(1, 'x', parse_mode='HTML', reply_to=5)
        channel.edit_message_reply_markup(1, 5, {'inline_keyboard': []})
        channel.answer_callback_query('c', 'y' * 300, show_alert=True)
        self.assertEqual(log[0], ('setMessageReaction', {'chat_id': 1, 'message_id': 2,
                                                         'reaction': [{'type': 'emoji', 'emoji': '👀'}]}, 4))
        self.assertEqual(log[1], ('sendChatAction', {'chat_id': 1, 'action': 'typing'}, 4))
        self.assertEqual(log[2], ('sendMessageDraft', {'chat_id': 1, 'draft_id': 77, 'text': '·', 'can_stop': True}, 4))
        # Bot API: an empty reaction list removes the bot's reaction (#835).
        self.assertEqual(log.pop(3), ('setMessageReaction', {'chat_id': 1, 'message_id': 2, 'reaction': []}, 4))
        self.assertEqual(log[3][1], {'chat_id': 1, 'text': 'x', 'parse_mode': 'HTML',
                                     'reply_parameters': {'message_id': 5, 'allow_sending_without_reply': True}})
        self.assertEqual(log[4][1], {'chat_id': 1, 'message_id': 5, 'reply_markup': {'inline_keyboard': []}})
        self.assertEqual(len(log[5][1]['text']), 200)
        self.assertTrue(log[5][1]['show_alert'])


if __name__ == '__main__':
    unittest.main()
