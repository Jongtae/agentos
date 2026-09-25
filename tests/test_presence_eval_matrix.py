"""PRESENCE-EVAL-01 / #512: the Presence A-J acceptance matrix, end to end.

Every scenario is driven through the shipped boundaries a paired owner
actually uses - Telegram ingest (``ingest_update`` / ``ingest_callback`` /
``ingest_stop``) -> the one conversation worker (``run_one``) -> durable
delivery (``deliver_one``) - and, where the contract puts the authority step
on the owner's Mac, through the real local HTTP handler (``make_handler``).

What is scripted, and only that:

* the Telegram Bot API is a fake transport that records every outbound
  method and body in wire order (``self.wire``), so assertions are about the
  exact method sequence, durable bubble count, reactions, chat actions,
  drafts, reply anchors and callback answers the owner's client receives;
* the model is a scripted ``ModelAdapter`` transport (tool calls, text or a
  provider error per call);
* semantic judgments use ``FixtureDecisionEngine`` - the provider-neutral
  DecisionEngine seam - never a cue list added by this suite;
* Gmail, Google Calendar, the public web and the macOS folder dialog are
  fixture transports/providers.  No live Telegram, Google, provider or
  macOS dialog is contacted.

Evidence class: automated synthetic fixture only.  Nothing here is live
owner, live provider or live Telegram evidence; see
docs/presence-eval-01.en.md for the separate owner-live checklist.

Owner phrasing deliberately varies across cases (Korean/English, direct and
indirect) so a pass does not depend on one magic phrase.  Where the product
itself only recognises literal cue words, the gap is recorded as a finding
(``expectedFailure`` tests named ``test_finding_*``) instead of being fixed
here: evaluation never activates missing implementation.
"""
import http.client
import json
import tempfile
import threading
import unittest
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet

from personal_agent.agent_runtime import CORE_INSTRUCTIONS
from personal_agent.bounded_execution import ExecutionError, ExecutionResult
from personal_agent.calendar import CALENDAR_SPEC, CALENDAR_WRITE_SPEC, CalendarConnector
from personal_agent.calendar_conversation import CREATED, OUTCOME_UNKNOWN, PREVIEW_HEADER
from personal_agent.connector_contract import ConnectorRegistry, ConnectorState
from personal_agent.conversation_handoff import FOLLOWUP_RETRY, LOCAL_AUTHORITY_PREVIEWS, LOCAL_FOLDER_READ
from personal_agent.conversation_projection import (TERMINAL_FAILED_HEADER, TERMINAL_PARTIAL_HEADER,
                                                    TERMINAL_UNVERIFIED_MARKER)
from personal_agent.decision import (OUTCOME_DECIDED, BinaryDecision, FixtureDecisionEngine, SelectionDecision,
                                     fixture_confidence)
from personal_agent.gmail import (GMAIL_CONNECTOR, GMAIL_CONNECTOR_ID, GMAIL_READONLY_SCOPE,
                                  EncryptedGmailSecretStore, GmailConnector)
from personal_agent.google_calendar import CALENDAR_WRITE_SCOPE, GoogleCalendar, GoogleCalendarHTTPError
from personal_agent.providers import ModelAdapter, ProviderError
from personal_agent.quickstart import make_handler
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore
from personal_agent.subscription_engines import SubscriptionEngines
from personal_agent.telegram_presence import draft_id_for

CHAT = 5120
GENERATION = 'eval-g1'
OWNER = f'telegram:{CHAT}'
ZONE = 'Asia/Seoul'
#: Tuesday 2026-09-22 10:00 KST: a fixed clock for Calendar previews.
CAL_NOW = datetime(2026, 9, 22, 10, 0, tzinfo=ZoneInfo(ZONE)).timestamp()
PRESENCE_METHODS = ('setMessageReaction', 'sendChatAction', 'sendMessageDraft')
#: Administrative lifecycle phrasing that must never be a routine bubble.
LIFECYCLE_CHATTER = ('처리 중입니다', '처리가 끝났습니다', '요청을 받았습니다', '작업을 시작', '작업이 완료',
                     '결과 상태 보기', 'queued', 'running', 'completed')
#: Raw internal identifiers that must not be the owner's default language.
RAW_IDS = ('google-gmail-read', 'google-drive-read', 'google-calendar', 'folder:read', 'handoff_id',
           'resume_token', 'capability_id', 'grant_id')


class EvalNet:
    """Fixture public web: a search with two results; ``unreadable`` pages fail."""

    def __init__(self, unreadable=()):
        self.unreadable = set(unreadable)
        self.calls = []

    def execute(self, plan):
        self.calls.append(plan['tool'])
        if plan['tool'] == 'web_search':
            return {'tool': 'web_search', 'retrieved_at': 1, 'results': [
                {'url': 'https://example.com/a', 'title': 'A', 'snippet': ''},
                {'url': 'https://example.com/b', 'title': 'B', 'snippet': ''}]}
        if plan['url'].rsplit('/', 1)[-1] in self.unreadable:
            raise ValueError('공개 페이지가 정상 응답하지 않았습니다.')
        return {'tool': 'public_page_read', 'url': plan['url'], 'retrieved_at': 2,
                'content': f"Page {plan['url'][-1]}: Model {plan['url'][-1].upper()} ships for 3,000 KRW."}


class CalendarProvider:
    """Fixture Calendar create; records every create reaching the provider."""

    def __init__(self):
        self.calls = []

    def create(self, payload, key):
        self.calls.append((payload, key))
        return {'id': f'ev{len(self.calls)}', 'version': '"etag"'}


class CliEngine:
    """Fixture subscription CLI worker (e.g. Codex); records the prompt it got."""

    def __init__(self):
        self.prompts = []
        self.fail = None

    def execute(self, engine, prompt, tools, **_kwargs):
        self.prompts.append(prompt)
        if self.fail:
            raise self.fail
        return ExecutionResult('CLI 워커가 쓴 답: 내일은 우산을 챙기세요.', engine, 0)


class PresenceEval(unittest.TestCase):
    """One paired Telegram owner, recorded Telegram wire, scripted model/decisions."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parent))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = QuickStore(self.root / 'data')
        self.wire = []              # (method, body) in wire order
        self.failing = {}           # Telegram method -> exception (presentation failure injection)
        self.script = []            # per model call: ('tool', name, args) | ('text', s) | ('error', exc)
        self.text = '좋아요. 오늘은 따뜻한 국물 요리가 어울려요.'
        self.model_bodies = []      # every conversation model request body
        self.during_model = None    # hook(job) while the model "thinks"
        self.update_id = 1000
        self.message_id = 7000
        self.relations = {}         # owner utterance -> follow-up relation the fixture engine judges
        self.withdrawals = set()    # owner utterances the fixture engine judges as withdrawing parked work
        self.picked = None          # what the fixture macOS folder dialog returns
        self.service = self.make_service()
        self.store.put('telegram', {'enabled': True, 'user_id': CHAT, 'generation': GENERATION, 'cursor': 0})

    # --- construction --------------------------------------------------------
    def telegram_transport(self, url, body=None, headers=None, timeout=60):
        method = url.rsplit('/', 1)[-1]
        self.wire.append((method, body))
        if method in self.failing:
            raise self.failing[method]
        if method == 'sendMessage':
            return {'ok': True, 'result': {'message_id': 90000 + len(self.wire)}}
        if method == 'getMe':
            return {'ok': True, 'result': {'username': 'eval_owner_bot'}}
        return {'ok': True, 'result': True}

    def model_transport(self, url, body, headers=None, timeout=60):
        tools = [t.get('function', {}).get('name') or t.get('name') for t in body.get('tools', [])]
        if 'agentos_connection_probe' in tools:
            return {'message': {'content': '', 'tool_calls': [
                {'id': 'probe', 'function': {'name': 'agentos_connection_probe', 'arguments': {}}}]}}
        if tools:
            self.model_bodies.append(json.loads(json.dumps(body)))
        running = [job for job in self.store.jobs() if job['status'] == 'running']
        if self.during_model and running:
            hook, self.during_model = self.during_model, None
            hook(running[0])
        if self.script and tools:
            step = self.script.pop(0)
            if step[0] == 'error':
                raise step[1]
            if step[0] == 'tool':
                return {'message': {'content': '', 'tool_calls': [
                    {'id': f'call-{len(self.model_bodies)}', 'function': {'name': step[1], 'arguments': step[2]}}]}}
            return {'message': {'content': step[1]}}
        return {'message': {'content': self.text}}

    def make_service(self, **kwargs):
        service = AgentService(self.store, ModelAdapter(self.model_transport), self.telegram_transport, **kwargs)
        service.use_decision_engine(self.decision_engine())
        service.folder_picker = lambda prompt: self.picked
        return service

    def decision_engine(self):
        """The scripted DecisionEngine: it answers only what the fixture tables say."""
        def choose(context, candidates, question):
            if context.purpose == 'conversation-followup':
                answer = self.relations.get(context.facts.get('owner_message'), 'none-of-these')
                return SelectionDecision(OUTCOME_DECIDED, answer, candidates, fixture_confidence())
            return SelectionDecision(OUTCOME_DECIDED, 'none-of-these', candidates, fixture_confidence())

        def judge(context, proposition):
            return BinaryDecision(OUTCOME_DECIDED, context.facts.get('owner_message') in self.withdrawals,
                                  fixture_confidence())
        return FixtureDecisionEngine(judge=judge, choose=choose)

    def connect_model(self, model='eval-model', clear=True):
        self.service.save_model({'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434',
                                 'model': model, 'api_key': ''})
        self.assertTrue(self.service.test_model()['ok'])
        if clear:
            self.wire.clear()

    # --- the owner's Telegram client -----------------------------------------
    def receive(self, text, sender=CHAT):
        self.update_id += 1
        self.message_id += 1
        before = {job['id'] for job in self.store.jobs()}
        self.service.ingest_update({'update_id': self.update_id, 'message': {
            'message_id': self.message_id, 'from': {'id': sender},
            'chat': {'id': sender, 'type': 'private'}, 'text': text}}, GENERATION)
        created = [job['id'] for job in self.store.jobs() if job['id'] not in before]
        return (created[0] if created else None), self.message_id

    def turn(self, text):
        job_id, message_id = self.receive(text)
        self.service.run_one()
        self.service.deliver_one()
        return self.store.job(job_id), message_id

    def tap(self, data, message_id, sender=CHAT, callback_id='cb'):
        self.service.ingest_callback({'id': callback_id, 'from': {'id': sender}, 'data': data,
                                      'message': {'message_id': message_id,
                                                  'chat': {'id': sender, 'type': 'private'}}}, GENERATION)

    def stop(self, job_id):
        return self.service.ingest_stop({'chat': {'id': CHAT, 'type': 'private'}, 'draft_id': draft_id_for(job_id)},
                                        GENERATION)

    def methods(self, since=0):
        return [method for method, _ in self.wire[since:]]

    def bubbles(self, since=0):
        """Durable owner-visible bubbles (sendMessage), in order."""
        return [body for method, body in self.wire[since:] if method == 'sendMessage']

    def texts(self, since=0):
        return [body['text'] for body in self.bubbles(since)]

    def reactions(self, since=0):
        return [body['reaction'][0]['emoji'] for method, body in self.wire[since:] if method == 'setMessageReaction']

    def callback_answers(self, since=0):
        return [body for method, body in self.wire[since:] if method == 'answerCallbackQuery']

    # --- the kernel underneath ------------------------------------------------
    def events(self, job_id):
        return self.store.task_events(job_id)

    def task(self, job_id):
        return self.service.task_progress(job_id)['selected']

    def assistant_rows(self, job_id):
        return [row for row in self.store.history() if row['job_id'] == job_id and row['role'] == 'assistant']

    def assert_no_lifecycle_chatter(self, texts):
        for text in texts:
            for phrase in LIFECYCLE_CHATTER:
                self.assertNotIn(phrase, text, f'lifecycle chatter {phrase!r} in {text!r}')

    def assert_no_raw_ids(self, text):
        for raw in RAW_IDS:
            self.assertNotIn(raw, text)
        self.assertNotIn(str(self.root), text)


# =============================================================================
# A. trivial request -> useful answer without routine lifecycle bubbles
# =============================================================================
class A_TrivialRequest(PresenceEval):
    PHRASES = ('오늘 저녁 뭐 먹지?', '비 오는 날 듣기 좋은 노래 하나만 추천해줘', 'What should I cook tonight?',
               '점심 뭐 먹을까 고민이야')

    def test_every_phrasing_is_one_reaction_then_one_answer_and_nothing_else(self):
        self.connect_model()
        for phrase in self.PHRASES:
            with self.subTest(phrase=phrase):
                start = len(self.wire)
                job, message_id = self.turn(phrase)
                # Owner-visible: exactly a received-reaction then one durable answer.
                self.assertEqual(self.methods(start), ['setMessageReaction', 'sendMessage'])
                [reply] = self.bubbles(start)
                self.assertEqual(reply['text'], self.text)
                self.assertNotIn('reply_markup', reply)
                self.assertNotIn('reply_parameters', reply)
                self.assert_no_lifecycle_chatter([reply['text']])
                # Claim <-> Work: the answer is a succeeded Work, sent once, no card.
                self.assertEqual((job['status'], job['delivery']), ('succeeded', 'sent'))
                self.assertIsNone(self.store.task_card(job['id']))
                self.assertEqual([row['content'] for row in self.assistant_rows(job['id'])], [self.text])
                self.assertIsNone(self.task(job['id'])['qualifier'])

    def test_a_brief_wait_adds_only_native_typing_never_a_status_bubble(self):
        self.connect_model()
        self.during_model = lambda job: self.service.acknowledge_long_work(now=job['created'] + 2)
        job, _ = self.turn('내일 아침 뭐 입을까?')
        self.assertEqual(self.methods(), ['setMessageReaction', 'sendChatAction', 'sendMessage'])
        self.assertEqual(len(self.bubbles()), 1)
        self.assertEqual(job['status'], 'succeeded')

    def test_presentation_api_failures_degrade_without_changing_truth_or_duplicating(self):
        self.connect_model()
        for failure in (ProviderError('reaction rejected'), RuntimeError('client bug'), TimeoutError('slow')):
            with self.subTest(failure=type(failure).__name__):
                start = len(self.wire)
                self.failing = {name: failure for name in PRESENCE_METHODS}
                self.during_model = lambda job: [self.service.acknowledge_long_work(now=job['created'] + t)
                                                 for t in (2, 6, 7)]
                job, _ = self.turn('주말에 뭐 하고 놀까?')
                self.assertEqual((job['status'], job['delivery']), ('succeeded', 'sent'))
                self.assertEqual(len(self.bubbles(start)), 1)
                self.assertEqual(self.methods(start)[-1], 'sendMessage')
        self.failing = {}

    def test_model_markdown_renders_as_telegram_html_not_raw_markers(self):
        self.connect_model()
        self.text = '**김치찌개** 어때요? `두부`는 *꼭* 넣어요.'
        _job, _ = self.turn('저녁 메뉴 골라줘')
        [reply] = self.bubbles()
        self.assertEqual(reply['parse_mode'], 'HTML')
        self.assertNotIn('**', reply['text'])
        self.assertIn('<b>김치찌개</b>', reply['text'])


# =============================================================================
# B. failed runtime -> truthful conversational failure + safe next action
# =============================================================================
class B_FailedRuntime(PresenceEval):
    def fail_turn(self, text='회의록 요약해줘'):
        self.connect_model()
        self.script = [('error', ProviderError('모델 서버에 연결할 수 없습니다.'))]
        return self.turn(text)

    def test_direct_api_failure_is_one_anchored_truthful_bubble_with_bounded_recovery(self):
        self.text = '요약을 완료했습니다.'   # a success sentence that must never reach the owner
        job, message_id = self.fail_turn()
        self.assertEqual(self.methods(), ['setMessageReaction', 'sendMessage'])
        self.assertEqual(self.reactions(), ['👍'], 'the reaction only acknowledges receipt')
        [reply] = self.bubbles()
        self.assertTrue(reply['text'].startswith(TERMINAL_FAILED_HEADER))
        self.assertIn('모델 서버에 연결할 수 없습니다.', reply['text'])
        self.assertNotIn('완료했습니다', reply['text'])
        self.assertEqual(reply['reply_parameters']['message_id'], message_id)
        self.assertEqual([b['text'] for b in reply['reply_markup']['inline_keyboard'][0]], ['다시 시도', '상세'])
        # Claim <-> Work/Evidence.
        self.assertEqual(job['status'], 'failed')
        self.assertEqual(self.store.turn_provenance(job['id'])['status'], 'failed')
        task = self.task(job['id'])
        self.assertEqual(task['qualifier']['outcome'], 'failed')
        self.assertEqual(task['route']['status'], 'failed')

    def test_details_are_on_demand_and_do_not_add_a_bubble(self):
        job, _ = self.fail_turn()
        reply_id = self.service.telegram_turns.get(job['id'])['reply_message_id']
        start = len(self.wire)
        self.tap(f"p7d:{job['id']}", reply_id, callback_id='details')
        self.assertEqual(self.bubbles(start), [])
        [answer] = self.callback_answers(start)
        self.assertTrue(answer['show_alert'])
        self.assertTrue(answer['text'].startswith('작업 상태: 완료하지 못함'))

    def test_subscription_cli_failure_is_the_same_truthful_projection(self):
        engine = CliEngine()
        engine.fail = ExecutionError('engine failed', failure_class='auth', exit_code=1)
        self.service = self.make_service(subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/cli',
                                                                                  clock=lambda: 1),
                                         execution_adapter=engine)
        self.service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        job, _ = self.turn('내일 날씨 알려줘')
        self.assertEqual(job['status'], 'failed')
        [reply] = self.bubbles()
        self.assertTrue(reply['text'].startswith(TERMINAL_FAILED_HEADER))
        self.assertNotIn('Codex', reply['text'].split('\n')[0], 'the assistant, not the worker, speaks')
        task = self.task(job['id'])
        self.assertEqual(task['route'], {'kind': 'subscription', 'engine': 'codex', 'status': 'failed'})
        self.assertEqual(task['failure_class'], 'auth')

    def test_opposing_no_ai_route_is_a_blocked_turn_without_a_retry_control(self):
        job, _ = self.turn('안녕, 오늘 할 일 정리 도와줄래?')   # nothing connected
        self.assertEqual(job['status'], 'failed')
        [reply] = self.bubbles()
        self.assertNotIn('reply_markup', reply)
        self.assertIn('AI가 연결되지 않아', reply['text'])
        self.assertIn('지금 바로 되는 일', reply['text'], 'a safe next action in conversation')
        # A repeat of the same blocker is a one-line reminder, not the same explanation again.
        self.turn('다른 거 물어봐도 돼?')
        self.assertNotIn('지금 바로 되는 일', self.texts()[-1])


# =============================================================================
# C. "try again / does it work now?" -> resolves to the prior failed Work
# =============================================================================
class C_RetryContinuity(PresenceEval):
    ORIGINAL = '다음 주 출장 준비물 목록 만들어줘'

    def failed(self):
        self.connect_model()
        self.script = [('error', ProviderError('모델 서버에 연결할 수 없습니다.'))]
        job, source = self.turn(self.ORIGINAL)
        self.assertEqual(job['status'], 'failed')
        return job, source

    def test_varied_follow_ups_resolve_to_the_failed_work_and_replay_it_once(self):
        for phrase in ('이제 돼?', '다시 해봐', 'try again please', '한 번 더 부탁해'):
            with self.subTest(phrase=phrase):
                self.setUp()
                failed, source = self.failed()
                self.relations = {phrase: FOLLOWUP_RETRY}
                self.text = '출장 준비물: 충전기, 여권, 우산.'
                start, calls = len(self.wire), len(self.model_bodies)
                retry, message_id = self.turn(phrase)
                self.assertEqual(retry['status'], 'succeeded')
                self.assertEqual((retry['relation_kind'], retry['related_job_id']), (FOLLOWUP_RETRY, failed['id']))
                self.assertEqual(self.store.job(failed['id'])['status'], 'failed', 'history is not rewritten')
                # The model received the ORIGINAL request, not the follow-up phrase.
                self.assertEqual(self.model_bodies[calls]['messages'][-1]['content'], self.ORIGINAL)
                self.assertEqual(self.methods(start), ['setMessageReaction', 'sendMessage'])
                self.assertEqual(self.texts(start), [self.text])
                continuity = [e for e in self.events(retry['id']) if e['tool'] == 'conversation_continuity']
                self.assertEqual([(e['trace']['relation'], e['trace']['executed']) for e in continuity],
                                 [('retry', True)])
                self.assertEqual(self.task(retry['id'])['relation'], {'kind': 'retry', 'work_id': failed['id']})
                self.assertFalse(self.service.run_one(), 'nothing else was queued')

    def test_a_second_retry_of_the_same_failure_is_refused_not_duplicated(self):
        failed, _ = self.failed()
        self.relations = {'다시 해봐': FOLLOWUP_RETRY}
        self.script = [('error', ProviderError('모델 서버에 연결할 수 없습니다.'))]
        first, _ = self.turn('다시 해봐')
        self.assertEqual(first['status'], 'failed')
        calls = len(self.model_bodies)
        # The original failure was already replayed once; its retry control now refuses.
        reply_id = self.service.telegram_turns.get(failed['id'])['reply_message_id']
        start = len(self.wire)
        self.tap(f"p7r:{failed['id']}", reply_id, callback_id='late')
        self.assertIn('이미 한 번 다시 시도했습니다', self.callback_answers(start)[-1]['text'])
        self.assertEqual(len(self.model_bodies), calls)

    def test_retry_control_and_conversation_share_one_owner_bound_idempotent_gate(self):
        failed, source = self.failed()
        reply_id = self.service.telegram_turns.get(failed['id'])['reply_message_id']
        self.tap(f"p7r:{failed['id']}", reply_id, sender=4444, callback_id='foreign')
        self.tap(f"p7r:{failed['id']}", reply_id, callback_id='first')
        self.tap(f"p7r:{failed['id']}", reply_id, callback_id='second')
        jobs = self.store.jobs()
        self.assertEqual(len(jobs), 2, 'foreign tap ignored; two owner taps create one retry')
        answers = self.callback_answers()
        self.assertEqual([a['callback_query_id'] for a in answers], ['first', 'second'])
        self.text = '출장 준비물: 충전기.'
        self.service.run_one()
        self.service.deliver_one()
        self.assertEqual(self.bubbles()[-1]['reply_parameters']['message_id'], source,
                         'the retried answer is anchored to the original owner turn')

    def test_callback_presentation_failures_never_duplicate_the_retry(self):
        failed, _ = self.failed()
        reply_id = self.service.telegram_turns.get(failed['id'])['reply_message_id']
        self.failing = {'answerCallbackQuery': ProviderError('callback answer lost'),
                        'editMessageReplyMarkup': ProviderError('edit rejected')}
        for callback_id in ('tap-1', 'tap-2', 'tap-3'):
            try:
                self.tap(f"p7r:{failed['id']}", reply_id, callback_id=callback_id)
            except ProviderError:
                self.fail('a presentation failure must not escape the callback path')
        self.failing = {}
        retries = [job for job in self.store.jobs() if job.get('relation_kind') == FOLLOWUP_RETRY]
        self.assertEqual(len(retries), 1)
        self.text = '출장 준비물: 여권.'
        self.service.run_one()
        self.service.deliver_one()
        self.assertEqual(self.store.job(retries[0]['id'])['status'], 'succeeded')
        self.assertEqual(self.store.job(failed['id'])['status'], 'failed')
        self.assertEqual(self.texts().count('출장 준비물: 여권.'), 1)

    def test_opposing_a_new_topic_or_unavailable_judgment_never_replays(self):
        failed, _ = self.failed()
        # Judged none-of-these: an ordinary new request.
        calls = len(self.model_bodies)
        job, _ = self.turn('그건 됐고 오늘 저녁 추천해줘')
        self.assertIsNone(job['relation_kind'])
        self.assertEqual(self.model_bodies[calls]['messages'][-1]['content'], '그건 됐고 오늘 저녁 추천해줘')
        # Unavailable engine: nothing is resolved or replayed.
        self.service.use_decision_engine(FixtureDecisionEngine())
        job, _ = self.turn('이제 돼?')
        self.assertIsNone(job['relation_kind'])
        self.assertEqual(self.store.job(failed['id'])['status'], 'failed')

    def test_opposing_failed_work_that_attempted_an_effect_is_never_replayed(self):
        self.connect_model()
        self.script = [('tool', 'save_note', {'content': '출장 준비'}),
                       ('error', ProviderError('모델 서버에 연결할 수 없습니다.'))]
        failed, _ = self.turn('출장 준비 메모하고 목록도 만들어줘')
        self.assertEqual(failed['status'], 'failed')
        [reply] = self.bubbles()
        self.assertEqual([b['text'] for b in reply['reply_markup']['inline_keyboard'][0]], ['상세'])
        notes = len(self.store.notes())
        self.relations = {'다시 해줘': FOLLOWUP_RETRY}
        job, _ = self.turn('다시 해줘')
        self.assertIn('상태를 바꾸는 작업을 시도해', job['response'])
        continuity = [e for e in self.events(job['id']) if e['tool'] == 'conversation_continuity']
        self.assertEqual(continuity[-1]['trace']['executed'], False)
        self.assertEqual(len(self.store.notes()), notes, 'the note is never saved twice')


# =============================================================================
# G. long research -> selective semantic progress, not scheduler narration
# =============================================================================
class G_LongResearch(PresenceEval):
    def research_turn(self, text, net, reply, think=None):
        self.connect_model()
        self.service.local_tools = net
        self.script = [('tool', 'bounded_public_research', {'mode': 'product_comparison', 'query': 'headphones'})]
        self.text = reply
        self.during_model = think
        return self.turn(text)

    def test_long_generation_is_one_stop_able_draft_then_one_durable_answer(self):
        def think(job):
            for offset in (1.5, 6, 9, 14, 27):
                self.service.acknowledge_long_work(now=job['created'] + offset)
        job, message_id = self.research_turn('노이즈캔슬링 헤드폰 두 개 비교 조사해줘', EvalNet(),
                                             '두 모델 모두 배송비는 3,000원입니다. (출처: example.com/a, /b)', think)
        self.assertEqual(job['status'], 'succeeded', job.get('error'))
        methods = self.methods()
        self.assertEqual(methods[0], 'setMessageReaction')
        self.assertEqual(methods[-1], 'sendMessage')
        self.assertEqual(len(self.bubbles()), 1, 'progress never becomes a durable bubble')
        drafts = [body for method, body in self.wire if method == 'sendMessageDraft']
        self.assertEqual(len(drafts), 2, 'first draft at 6s, one refresh at 27s; 9s/14s are no-ops')
        for body in drafts:
            self.assertEqual(body, {'chat_id': CHAT, 'draft_id': draft_id_for(job['id']), 'text': '', 'can_stop': True})
        self.assertEqual(self.bubbles()[0]['reply_parameters']['message_id'], message_id)
        self.assertIsNone(self.store.task_card(job['id']))
        self.assert_no_lifecycle_chatter(self.texts())
        # Claim <-> Evidence: both pages were actually read.
        research = [e for e in self.events(job['id']) if e['tool'] == 'bounded_public_research'][-1]
        self.assertEqual(research['status'], 'succeeded')
        self.assertNotIn('partial', research['trace']['evidence'].get('qualifiers') or [])

    def test_stop_during_running_research_is_reconciled_with_real_cancellation_state(self):
        outcomes = []

        def think(job):
            self.service.acknowledge_long_work(now=job['created'] + 6)
            outcomes.append(self.stop(job['id']))
            outcomes.append(self.stop(job['id']))
            self.service.acknowledge_long_work(now=job['created'] + 30)
        job, message_id = self.research_turn('캠핑 의자 조사 좀 해줄래', EvalNet(), '의자 A가 가볍습니다.', think)
        self.assertEqual(outcomes, ['running', 'duplicate'])
        self.assertEqual(self.methods().count('sendMessageDraft'), 1, 'no draft after Stop')
        self.assertEqual(job['status'], 'succeeded', 'running Work was not cancellable and was not cancelled')
        notice, answer = self.bubbles()
        self.assertEqual(notice['text'], AgentService.STOP_RUNNING_TEXT)
        self.assertNotIn('취소했', notice['text'])
        self.assertTrue(answer['text'].startswith('의자 A가 가볍습니다.'), 'the real result is still delivered once')
        self.assertIn('https://example.com/a', answer['text'], 'observed sources travel with the answer')

    def test_stop_on_queued_work_cancels_it_through_the_state_machine(self):
        self.connect_model()
        job_id, _ = self.receive('여행지 후보 조사해줘')
        self.assertEqual(self.stop(job_id), 'cancelled')
        self.assertEqual(self.store.job(job_id)['status'], 'cancelled')
        self.assertFalse(self.service.run_one(), 'cancelled Work never runs')
        self.assertEqual(self.texts(), [AgentService.STOP_CANCELLED_TEXT])


# =============================================================================
# Owner-local HTTP surface (the Mac), used by D and E
# =============================================================================
class LocalHttp:
    """The real ``make_handler`` on loopback, with an owner session cookie."""

    def serve(self, service):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(service, ('mobile.example.test',), 'pairing'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def shutdown():
            server.shutdown()
            thread.join()
            server.server_close()
        self.addCleanup(shutdown)
        if not self.store.claimed():
            self.store.claim(self.store.bootstrap.read_text(), 'long-password-eval')
        self.port = server.server_port
        self.session = {'Cookie': 'agentos_session=' + self.store.local_session()}
        service.local_server_port = self.port
        return self.port

    def http(self, method, path, body=None, headers=None, session=True):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        sent = {**(self.session if session else {}), **(headers or {})}
        payload = None
        if body is not None:
            payload = json.dumps(body).encode()
            sent['Content-Type'] = 'application/json'
        connection.request(method, path, body=payload, headers=sent)
        response = connection.getresponse()
        raw = response.read()
        location = response.getheader('Location')
        connection.close()
        try:
            data = json.loads(raw)
        except ValueError:
            data = raw.decode('utf-8', 'replace')
        return response.status, data, location


# =============================================================================
# D. missing Gmail -> contextual connect handoff + exactly-once resume
# =============================================================================
class D_MissingGmail(LocalHttp, PresenceEval):
    PHRASES = ('메일에서 숙소 예약 확인 찾아줘', 'check my inbox for the flight receipt', '받은편지함에서 예산 승인 메일 찾아봐')

    def setUp(self):
        super().setUp()
        self.gmail_calls = []
        self.encrypted = EncryptedGmailSecretStore(self.store, Fernet.generate_key())
        # Same wiring as the owner-local deployment (quickstart.py).
        self.registry = ConnectorRegistry(self.store, (GMAIL_CONNECTOR, CALENDAR_SPEC, CALENDAR_WRITE_SPEC))

        def gmail_transport(method, endpoint, params, headers):
            self.gmail_calls.append((method, endpoint))
            if endpoint.endswith('/messages'):
                return {'messages': [{'id': 'm_1', 'threadId': 't_1'}]}
            return {'id': 'm_1', 'threadId': 't_1', 'payload': {'headers': [
                {'name': 'Subject', 'value': '예약 확인 안내'}, {'name': 'From', 'value': 'Stay <stay@example.test>'},
                {'name': 'Date', 'value': 'Mon, 1 Sep 2026 10:00:00 +0000'}]}}
        self.exchanges = []
        self.service = self.make_service(connector_registry=self.registry)
        self.connect_model()
        # The redirect URI carries the port the listener really bound, exactly
        # as the owner-local deployment derives it (quickstart.py).
        port = self.serve(self.service)
        self.gmail = GmailConnector(self.encrypted, 'gmail-client', f'http://localhost:{port}/oauth/gmail/callback',
                                    registry=self.registry, allow_localhost=True, transport=gmail_transport)
        self.service.gmail = self.gmail

        def exchange(request):
            self.exchanges.append(request['code'])
            return {'access_token': 'fixture-access', 'refresh_token': 'fixture-refresh',
                    'expires_in': 7200, 'scope': GMAIL_READONLY_SCOPE}
        self.service.gmail_token_exchange = exchange

    def searches(self):
        return len([call for call in self.gmail_calls if call[1].endswith('/messages')])

    def start_connection(self):
        status, _body, location = self.http('GET', '/google-gmail')
        self.assertIn(status, (302, 303), 'the owner-authenticated start route redirects to Google')
        self.assertTrue(location.startswith('https://accounts.google.com/'), location)
        return parse_qs(urlsplit(location).query)['state'][0]

    def connect_through_the_browser(self, code='fixture-code'):
        state = self.start_connection()
        return self.http('GET', f'/oauth/gmail/callback?state={state}&code={code}', session=False)

    def test_each_phrasing_parks_with_one_contextual_next_action_and_resumes_exactly_once(self):
        for phrase in self.PHRASES:
            with self.subTest(phrase=phrase):
                self.registry.transition(OWNER, GMAIL_CONNECTOR_ID, ConnectorState.DISCONNECTED)
                start, searches = len(self.wire), self.searches()
                job, _ = self.turn(phrase)
                # Owner-visible: one guidance bubble; nothing ran, nothing is claimed.
                self.assertEqual(job['status'], 'awaiting_connection')
                self.assertEqual(self.methods(start), ['setMessageReaction', 'sendMessage'],
                                 'a received-reaction, then exactly one guidance bubble')
                [guidance] = self.texts(start)
                self.assertIn('Gmail', guidance)
                self.assertIn('실행하지 않았습니다', guidance)
                self.assertIn(f'http://127.0.0.1:{self.port}/google-gmail', guidance)
                for lie in ('연결되었습니다', '찾았습니다', '검색했습니다'):
                    self.assertNotIn(lie, guidance)
                self.assert_no_raw_ids(guidance)
                self.assertEqual(self.searches(), searches, 'no mailbox call before the connection')
                # The owner connects on this Mac (fixture OAuth token exchange).
                status, page, _ = self.connect_through_the_browser()
                self.assertEqual((status, page), (200, 'Gmail connected. Return to Telegram.'))
                self.assertEqual(self.store.job(job['id'])['status'], 'queued')
                # The ORIGINAL Work resumes once and answers once in the same conversation.
                resumed_at = len(self.wire)
                self.assertTrue(self.service.run_one())
                self.service.deliver_one()
                self.assertFalse(self.service.run_one(), 'exactly once')
                resumed = self.store.job(job['id'])
                self.assertEqual((resumed['status'], resumed['message']), ('succeeded', phrase))
                self.assertEqual(self.searches(), searches + 1)
                self.assertEqual(self.methods(resumed_at), ['sendMessage'], 'a resumed Work is not re-acknowledged')
                [answer] = self.texts(resumed_at)
                self.assertIn('예약 확인 안내', answer)

    def test_a_replayed_callback_never_resumes_twice(self):
        self.turn(self.PHRASES[0])
        state = self.start_connection()
        self.assertEqual(self.http('GET', f'/oauth/gmail/callback?state={state}&code=a', session=False)[0], 200)
        replay = self.http('GET', f'/oauth/gmail/callback?state={state}&code=a', session=False)
        self.assertEqual(replay[0], 400)
        self.assertEqual(len(self.exchanges), 1, 'the single-use state is consumed before the code')
        self.assertTrue(self.service.run_one())
        self.assertFalse(self.service.run_one())
        self.assertEqual(self.searches(), 1)

    def test_a_denied_connection_fails_the_work_truthfully_and_grants_nothing(self):
        job, _ = self.turn(self.PHRASES[1])
        state = self.start_connection()
        self.http('GET', f'/oauth/gmail/callback?state={state}&error=access_denied', session=False)
        failed = self.store.job(job['id'])
        self.assertEqual(failed['status'], 'failed')
        self.assertIn('연결이 승인되지 않아', failed['error'])
        self.assertNotEqual(self.registry.status(OWNER, GMAIL_CONNECTOR_ID).state, ConnectorState.CONNECTED)
        self.assertFalse(self.service.run_one())
        self.assertEqual(self.searches(), 0)

    def test_ordinary_conversation_meanwhile_keeps_the_parked_request_and_only_a_judged_withdrawal_cancels(self):
        job, _ = self.turn(self.PHRASES[2])
        for phrase in ('알겠어, 지금 연결할게', 'ok one sec'):
            self.turn(phrase)
        self.assertEqual(self.store.job(job['id'])['status'], 'awaiting_connection')
        self.withdrawals = {'아까 메일 찾는 건 그만둘게'}
        self.turn('아까 메일 찾는 건 그만둘게')
        self.assertEqual(self.store.job(job['id'])['status'], 'cancelled')
        self.connect_through_the_browser()
        self.assertFalse(self.service.run_one(), 'a withdrawn request never runs after connecting')
        self.assertEqual(self.searches(), 0)

    @unittest.expectedFailure
    def test_finding_d1_a_mail_request_without_a_mail_cue_word_gets_no_gmail_handoff(self):
        """FINDING D1: intent routing is a literal cue table (IntentClassifier).

        "집주인한테 답장 왔어?" / "did the landlord write back to me?" is a
        mailbox read by meaning but contains no mail cue word, so it goes to
        the ordinary model route and no contextual Gmail handoff is offered.
        The assertion states the contract's expected behaviour (model-first
        semantics); the product does not meet it today.
        """
        observed = {}
        for phrase in ('집주인한테 답장 왔어?', 'did the landlord write back to me?'):
            self.registry.transition(OWNER, GMAIL_CONNECTOR_ID, ConnectorState.DISCONNECTED)
            observed[phrase] = self.turn(phrase)[0]['status']
        # Both phrasings are ingested before asserting, so each gap is observed.
        self.assertEqual(observed, {phrase: 'awaiting_connection' for phrase in observed})


# =============================================================================
# E. missing local folder -> owner-local picker + scoped grant + exactly-once resume
# =============================================================================
class E_MissingFolder(LocalHttp, PresenceEval):
    PHRASES = ('내 계약서 폴더에서 갱신 날짜 찾아줘', 'find the renewal date in my contract files')

    def setUp(self):
        super().setUp()
        self.connect_model()
        self.serve(self.service)
        self.folder = self.root / 'contracts'
        self.folder.mkdir()
        (self.folder / 'renewal.txt').write_text('계약서 갱신일: 10월 1일', encoding='utf-8')

    def roots(self):
        return [root['path'] for root in self.store.config('file_roots', [])]

    def park(self, phrase):
        self.script = [('tool', 'find_files', {'query': '계약서'})]
        self.text = '갱신일은 10월 1일입니다. (renewal.txt)'
        return self.turn(phrase)

    def test_each_phrasing_hands_off_to_the_mac_grants_only_the_picked_folder_and_resumes_once(self):
        for phrase in self.PHRASES:
            with self.subTest(phrase=phrase):
                self.service.save_roots({'paths': []})
                start = len(self.wire)
                job, _ = self.park(phrase)
                self.assertEqual(job['status'], 'awaiting_connection')
                self.assertEqual(self.methods(start), ['setMessageReaction', 'sendMessage'])
                [guidance] = self.texts(start)
                self.assertIn('Mac에서 계속', guidance)
                self.assertIn('읽기만', guidance)
                self.assert_no_raw_ids(guidance)
                self.assertEqual(self.roots(), [], 'asking grants nothing')
                self.assertEqual(self.store.turn_provenance(job['id'])['status'], 'setup-required')
                # A phone/tunnel cannot choose or approve.
                status, listing, _ = self.http('GET', '/api/folder-requests', headers={'Host': 'mobile.example.test'})
                self.assertFalse(listing['local_surface'])
                handoff = listing['requests'][0]['handoff_id']
                self.assertEqual(self.http('POST', '/api/folder-requests/approve', {'handoff_id': handoff},
                                           headers={'Host': 'mobile.example.test'})[0], 403)
                # The Mac: the preview shows read-only authority; the (fixture) folder dialog picks.
                status, listing, _ = self.http('GET', '/api/folder-requests')
                [request] = listing['requests']
                self.assertEqual((request['authority'], request['preview']),
                                 ('read', LOCAL_AUTHORITY_PREVIEWS[LOCAL_FOLDER_READ]))
                self.picked = str(self.folder)
                status, selected, _ = self.http('POST', '/api/folder-requests/select', {'handoff_id': handoff})
                self.assertEqual((status, selected['state']), (200, 'selected'))
                self.assertEqual(self.roots(), [], 'selecting is not granting')
                notice_at = len(self.wire)
                status, approved, _ = self.http('POST', '/api/folder-requests/approve', {'handoff_id': handoff})
                self.assertEqual((status, approved['state'], approved['authority']), (200, 'approved', 'read'))
                self.assertEqual(self.roots(), [str(self.folder.resolve())])
                self.assertIsNone(self.store.config('file_workspace', {}).get('workspace'), 'read is not write')
                self.assertEqual(self.methods(notice_at), ['sendMessage'])
                self.assertEqual(self.texts(notice_at), ['선택한 폴더를 읽기로 허용했습니다. 방금 요청을 이어서 처리합니다.'])
                # Exactly-once resume of the ORIGINAL Work.
                self.script = [('tool', 'find_files', {'query': '계약서'})]
                answer_at = len(self.wire)
                self.assertTrue(self.service.run_one())
                self.service.deliver_one()
                self.assertFalse(self.service.run_one())
                self.assertEqual(self.store.job(job['id'])['status'], 'succeeded')
                self.assertEqual(self.methods(answer_at), ['sendMessage'])
                self.assertEqual(self.texts(answer_at), [self.text])
                replay = self.http('POST', '/api/folder-requests/approve', {'handoff_id': handoff})
                self.assertEqual((replay[0], replay[1]['reason']), (409, 'no_pending_work'))
                self.assertEqual((self.folder / 'renewal.txt').read_text(encoding='utf-8'), '계약서 갱신일: 10월 1일')

    def test_a_cancelled_picker_changes_nothing_and_deny_grants_nothing(self):
        job, _ = self.park(self.PHRASES[0])
        _status, listing, _ = self.http('GET', '/api/folder-requests')
        handoff = listing['requests'][0]['handoff_id']
        self.picked = None   # the owner closed the dialog
        self.assertEqual(self.http('POST', '/api/folder-requests/select', {'handoff_id': handoff})[1],
                         {'state': 'cancelled'})
        self.assertEqual(self.store.job(job['id'])['status'], 'awaiting_connection')
        self.assertEqual(self.http('POST', '/api/folder-requests/deny', {'handoff_id': handoff})[1], {'state': 'denied'})
        self.assertEqual(self.store.job(job['id'])['status'], 'failed')
        self.assertEqual(self.roots(), [])
        self.assertFalse(self.service.run_one())

    def test_read_and_result_write_are_two_distinct_mac_approvals_for_one_request(self):
        minutes = self.root / 'minutes'
        minutes.mkdir()
        (minutes / 'meeting.md').write_text('회의 결정: 출시일 확정', encoding='utf-8')
        results = self.root / 'results'
        results.mkdir()
        self.text = '결정: 출시일 확정. 다음 단계: 공지.'
        job, _ = self.turn('/workspace-summary 회의 :: 회의 결과 브리프')
        self.assertEqual(job['status'], 'awaiting_connection')
        for picked, authority in ((minutes, 'read'), (results, 'write')):
            _status, listing, _ = self.http('GET', '/api/folder-requests')
            [request] = listing['requests']
            self.assertEqual(request['authority'], authority)
            self.picked = str(picked)
            self.http('POST', '/api/folder-requests/select', {'handoff_id': request['handoff_id']})
            self.http('POST', '/api/folder-requests/approve', {'handoff_id': request['handoff_id']})
            self.service.run_one()
        self.service.deliver_one()
        self.assertEqual(self.store.job(job['id'])['status'], 'succeeded')
        self.assertEqual(len(list(results.iterdir())), 1, 'one new result file')
        self.assertEqual((minutes / 'meeting.md').read_text(encoding='utf-8'), '회의 결정: 출시일 확정')
        self.assertNotIn(str(results.resolve()), self.roots(), 'the write grant is never an AI read folder')
        self.last_result_bubble = self.texts()[-1]

    def test_finding_e1_the_saved_result_bubble_exposes_the_internal_result_id(self):
        """FINDING E1 (fixed by #598): the result-saved reply names the file, not its id.

        ``quickstart_service`` used to append the saved artifact's internal
        UUID (``저장됨: <file name> · <result id>``).  The file name is owner
        language and stays; the id lives in Task/Artifact detail, where the
        #562 exact-item link resolves it from typed Work data.
        """
        self.test_read_and_result_write_are_two_distinct_mac_approvals_for_one_request()
        job_id = self.store.jobs()[-1]['id']
        [artifact] = self.store.task_artifacts(job_id)
        self.assertNotIn(artifact['id'], self.last_result_bubble)
        self.assertIn(f"저장됨: {artifact['path']}", self.last_result_bubble, 'the owner still learns what was saved')
        self.assert_no_raw_ids(self.last_result_bubble)
        # The id is still inspectable where technical detail belongs.
        self.assertIn(artifact['id'], [row['id'] for row in self.task(job_id)['artifacts']])

    def test_a_telegram_message_naming_a_path_grants_nothing(self):
        job, _ = self.park(self.PHRASES[0])
        self.turn(f'{self.folder} 폴더 허용해줘')
        self.assertEqual(self.roots(), [])
        self.assertEqual(self.store.job(job['id'])['status'], 'awaiting_connection')


# =============================================================================
# F. Calendar effect -> exact preview + approval boundary
# I. unknown external effect -> unknown wording + no unsafe automatic duplicate
# =============================================================================
class CalendarEval(PresenceEval):
    def setUp(self):
        super().setUp()
        self.clock = [CAL_NOW]
        self.registry = ConnectorRegistry(self.store, (CALENDAR_SPEC, CALENDAR_WRITE_SPEC), clock=lambda: self.clock[0])
        self.provider = self.make_provider()
        self.calendar = CalendarConnector(self.store, self.provider, registry=self.registry, now=lambda: self.clock[0])
        self.service = self.make_service(connector_registry=self.registry, calendar=self.calendar)
        self.service.calendar_conversation.now = lambda: self.clock[0]
        self.service.calendar_conversation._timezone = ZONE
        self.connect_write()
        self.connect_model()

    def make_provider(self):
        return CalendarProvider()

    def connect_write(self):
        self.registry.transition(OWNER, CALENDAR_WRITE_SPEC.connector_id, ConnectorState.CONNECTED,
                                 granted_scopes=(CALENDAR_WRITE_SCOPE,))

    def drafts(self):
        return self.store.config('calendar_create', {})

    def states(self):
        return sorted(row['state'] for row in self.drafts().values())


class F_CalendarApproval(CalendarEval):
    CASES = (('내일 오후 3시에 치과 일정 잡아줘', '제목: 치과', '2026-09-23 (수) 15:00 – 16:00 (Asia/Seoul)'),
             ('book a dentist appointment tomorrow at 3pm for 30 minutes', '제목: dentist appointment', '15:00 – 15:30'),
             ('금요일 오전 9시 스탠드업 30분 일정 등록해줘', '제목: 스탠드업', '2026-09-25 (금) 09:00 – 09:30'))

    def test_each_phrasing_gets_an_exact_preview_then_one_effect_only_after_approval(self):
        for index, (phrase, title, when) in enumerate(self.CASES):
            with self.subTest(phrase=phrase):
                start, calls = len(self.wire), len(self.provider.calls)
                job, _ = self.turn(phrase)
                self.assertEqual(self.methods(start), ['sendMessage'], 'a consequential request gets no reaction')
                [preview] = self.texts(start)
                self.assertTrue(preview.startswith(PREVIEW_HEADER))
                self.assertIn(title, preview)
                self.assertIn(when, preview)
                self.assertIn('"승인"', preview)
                self.assertEqual(len(self.provider.calls), calls, 'nothing reaches the provider before approval')
                self.assertIn('awaiting-approval', self.states())
                approval = ('승인', 'approve', 'yes')[index]
                approved_at = len(self.wire)
                done, _ = self.turn(approval)
                [created] = self.texts(approved_at)
                self.assertTrue(created.startswith(CREATED))
                self.assertIn(title, created)
                self.assertEqual(len(self.provider.calls), calls + 1)
                # Replayed approval: nothing is created twice.
                self.turn(approval)
                self.assertEqual(len(self.provider.calls), calls + 1)
                calendar_events = [e for e in self.events(done['id']) if e['tool'].startswith('calendar')]
                self.assertTrue(calendar_events, 'the effect is attributable in Evidence')
                for event in calendar_events:
                    self.assertNotIn(title.split(': ')[1], json.dumps(event['trace'], ensure_ascii=False),
                                     'evidence is content-free')

    def test_an_expired_preview_cannot_be_approved(self):
        self.turn(self.CASES[0][0])
        self.clock[0] += 901
        self.turn('승인')
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.states(), ['awaiting-approval'])

    def test_a_correction_redrafts_and_only_the_corrected_preview_executes(self):
        self.turn(self.CASES[0][0])
        start = len(self.wire)
        self.turn('아니 4시로')
        [redraft] = self.texts(start)
        self.assertIn('16:00 – 17:00', redraft)
        self.turn('승인')
        [(payload, _key)] = self.provider.calls
        self.assertEqual(payload['start'], '2026-09-23T16:00:00+09:00')

    def test_another_identity_cannot_approve_and_cancel_creates_nothing(self):
        self.turn(self.CASES[0][0])
        web = self.store.enqueue('승인', 'web-approve', channel='web')
        self.service.run_one()
        self.assertEqual(self.provider.calls, [], 'a web turn cannot spend the Telegram preview')
        self.turn('취소')
        self.turn('승인')
        self.assertEqual(self.provider.calls, [])
        self.assertNotEqual(self.store.job(web)['response'], CREATED)

    def test_missing_write_grant_is_a_contextual_handoff_and_the_resumed_work_only_previews(self):
        self.registry.transition(OWNER, CALENDAR_WRITE_SPEC.connector_id, ConnectorState.DISCONNECTED)
        start = len(self.wire)
        job, _ = self.turn('다음 주 화요일 10시 반 병원 예약 일정 추가해줘')
        self.assertEqual(job['status'], 'awaiting_connection')
        [guidance] = self.texts(start)
        self.assertIn('Google Calendar', guidance)
        self.assertIn('실행하지 않았습니다', guidance)
        self.assert_no_raw_ids(guidance)
        self.connect_write()
        self.service.resume_connector_work(CALENDAR_WRITE_SPEC.connector_id, OWNER, (CALENDAR_WRITE_SCOPE,))
        resumed_at = len(self.wire)
        self.assertTrue(self.service.run_one())
        self.service.deliver_one()
        self.assertFalse(self.service.run_one(), 'resumes exactly once')
        [preview] = self.texts(resumed_at)
        self.assertTrue(preview.startswith(PREVIEW_HEADER))
        self.assertEqual(self.provider.calls, [], 'resuming reaches a preview, never the effect')


class _Conflict409:
    """A Google Calendar transport whose create answers HTTP 409 (#447)."""

    def __init__(self):
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        raise GoogleCalendarHTTPError(409)


class I_UnknownExternalEffect(CalendarEval):
    def make_provider(self):
        self.transport = _Conflict409()
        return GoogleCalendar(self.transport)

    def approve_into_unknown(self):
        self.turn('내일 오후 3시에 치과 일정 잡아줘')
        start = len(self.wire)
        job, message_id = self.turn('승인')
        return job, message_id, start

    def test_a_409_create_is_reported_unknown_and_never_retried(self):
        job, _message_id, start = self.approve_into_unknown()
        [bubble] = self.texts(start)
        self.assertEqual(bubble, OUTCOME_UNKNOWN)
        self.assertIn('확인할 수 없습니다', bubble)
        self.assertIn('자동으로 다시 시도하지 않았습니다', bubble)
        self.assertNotIn(CREATED, bubble)
        self.assertEqual(self.transport.calls, 1)
        self.assertEqual(self.states(), ['outcome-unknown'])
        # A repeated approval, and a judged "try again", never replay the create.
        self.turn('승인')
        self.relations = {'다시 해줘': FOLLOWUP_RETRY, 'is it there now?': FOLLOWUP_RETRY}
        for phrase in ('다시 해줘', 'is it there now?'):
            retry, _ = self.turn(phrase)
            continuity = [e for e in self.events(retry['id']) if e['tool'] == 'conversation_continuity']
            self.assertEqual(continuity[-1]['trace']['executed'], False)
        self.assertEqual(self.transport.calls, 1, 'no unsafe automatic duplicate')

    @unittest.expectedFailure
    def test_finding_i1_the_unknown_effect_work_is_recorded_as_succeeded(self):
        """FINDING I1: the Work that applied the approval ends ``succeeded``.

        The owner-visible bubble is truthful (OUTCOME_UNKNOWN), but the Work
        record, its web status and its transcript qualifier say the turn
        simply succeeded, so a later reader (web card, next model turn's
        context) sees no unknown-effect outcome.  Expected by the contract:
        failed/partial/unknown stay distinct in Work/Evidence, not only prose.
        """
        job, _message_id, _start = self.approve_into_unknown()
        qualifier = self.task(job['id'])['qualifier'] or {}
        self.assertEqual(qualifier.get('outcome'), 'unknown', 'an explicit unknown outcome, not failed/partial')
        self.relations = {'다시 해줘': FOLLOWUP_RETRY}
        retry, _ = self.turn('다시 해줘')
        self.assertIn('외부 결과가 불확실', retry['response'], 'the refusal names the unknown effect')


# =============================================================================
# H. partial result -> verified and failed portions separated
# =============================================================================
class H_PartialResult(PresenceEval):
    def partial_research(self):
        self.connect_model()
        self.service.local_tools = EvalNet(unreadable=('b',))
        self.script = [('tool', 'bounded_public_research', {'mode': 'product_comparison', 'query': 'headphones'})]
        self.text = '두 제품을 모두 비교했습니다.'
        return self.turn('헤드폰 두 개 비교해줘')

    def test_partial_research_is_never_collapsed_into_success(self):
        job, message_id = self.partial_research()
        self.assertEqual(job['status'], 'partial')
        self.assertEqual(self.methods(), ['setMessageReaction', 'sendMessage'])
        [bubble] = self.bubbles()
        self.assertTrue(bubble['text'].startswith(TERMINAL_PARTIAL_HEADER))
        self.assertIn('일부 자료는 읽지 못했습니다', bubble['text'], 'the failed portion is named')
        self.assertIn(TERMINAL_UNVERIFIED_MARKER, bubble['text'])
        self.assertNotIn('모두 비교했습니다', bubble['text'], 'the unverified claim is not asserted')
        self.assertEqual([b['text'] for b in bubble['reply_markup']['inline_keyboard'][0]], ['상세'])
        self.assertEqual(bubble['reply_parameters']['message_id'], message_id)
        # Claim <-> Evidence: the call ran; its evidence is qualified partial.
        research = [e for e in self.events(job['id']) if e['tool'] == 'bounded_public_research'][-1]
        self.assertEqual(research['status'], 'succeeded')
        self.assertEqual(research['trace']['evidence']['qualifiers'], ['partial'])
        # The preserved text is inspectable but qualified everywhere it is read.
        [row] = self.assistant_rows(job['id'])
        self.assertEqual(row['qualifier']['outcome'], 'partial')
        self.assertEqual(self.task(job['id'])['qualifier']['outcome'], 'partial')

    def test_opposing_outcomes_read_differently_and_carry_matching_controls(self):
        self.connect_model()
        outcomes = {}
        self.text = '확인된 답입니다.'
        outcomes['succeeded'] = self.turn('차 한 잔 추천해줘')[0]
        self.script = [('error', ProviderError('모델 서버에 연결할 수 없습니다.'))]
        outcomes['failed'] = self.turn('회의 요약해줘')[0]
        self.service.local_tools = EvalNet(unreadable=('b',))
        self.script = [('tool', 'bounded_public_research', {'mode': 'product_comparison', 'query': 'kettle'})]
        outcomes['partial'] = self.turn('전기포트 비교해줘')[0]
        bubbles = self.bubbles()
        self.assertEqual(self.methods(), ['setMessageReaction', 'sendMessage'] * 3)
        self.assertEqual([job['status'] for job in outcomes.values()], ['succeeded', 'failed', 'partial'])
        heads = [body['text'].split('\n')[0] for body in bubbles]
        self.assertEqual(heads[1:], [TERMINAL_FAILED_HEADER, TERMINAL_PARTIAL_HEADER])
        self.assertEqual(bubbles[0]['text'], '확인된 답입니다.')
        controls = [[b['text'] for b in body.get('reply_markup', {}).get('inline_keyboard', [[]])[0]] for body in bubbles]
        self.assertEqual(controls, [[], ['다시 시도', '상세'], ['상세']])

    @unittest.expectedFailure
    def test_finding_h1_the_verified_portion_is_not_stated_in_conversation(self):
        """FINDING H1: the partial bubble names what failed, not what was verified.

        Page A was read and supports "ships for 3,000 KRW"; page B failed.
        The contract asks the conversation to state the verified completed
        portion and the failed portion separately.  The bubble says only that
        some material was unreadable and points to the AgentOS web record, so
        the verified portion is available only on demand.
        """
        self.partial_research()
        [bubble] = self.bubbles()
        self.assertIn('일부 자료는 읽지 못했습니다', bubble['text'], 'the failed portion')
        self.assertIn('3,000', bubble['text'], 'the verified fact from the page that was read')
        self.assertIn('example.com/a', bubble['text'], 'and its source')


class Inspectability(LocalHttp, PresenceEval):
    """Presence recedes the machinery; it never hides it (Task/Evidence detail on the Mac)."""

    def setUp(self):
        super().setUp()
        self.connect_model()
        self.serve(self.service)

    def test_failed_and_partial_work_stay_inspectable_behind_the_conversation(self):
        self.script = [('error', ProviderError('모델 서버에 연결할 수 없습니다.'))]
        failed, _ = self.turn('회의 요약해줘')
        self.service.local_tools = EvalNet(unreadable=('b',))
        self.script = [('tool', 'bounded_public_research', {'mode': 'product_comparison', 'query': 'kettle'})]
        self.text = '두 제품을 모두 비교했습니다.'
        partial, _ = self.turn('전기포트 비교해줘')
        for job, outcome in ((failed, 'failed'), (partial, 'partial')):
            status, detail, _ = self.http('GET', f"/api/tasks/{job['id']}")
            self.assertEqual(status, 200)
            task = detail['selected']
            self.assertEqual((task['status'], task['qualifier']['outcome']), (outcome, outcome))
            self.assertTrue(task['error'], 'the cause is inspectable')
            self.assertEqual(task['route']['kind'], 'direct-api')
            self.assertEqual(task['provenance']['requested_model'], 'eval-model')
        _status, detail, _ = self.http('GET', f"/api/tasks/{partial['id']}")
        tools = [event['tool'] for event in detail['selected']['events']]
        self.assertIn('bounded_public_research', tools, 'the tool id lives in technical detail')
        # The preserved (unverified) model text is still reachable, qualified.
        rows = [row for row in self.store.history() if row['job_id'] == partial['id'] and row['role'] == 'assistant']
        self.assertIn('두 제품을 모두 비교했습니다.', rows[0]['content'])


class OwnerLanguageFindings(PresenceEval):
    @unittest.expectedFailure
    def test_finding_x1_failed_and_partial_bubbles_name_raw_tool_ids(self):
        """FINDING X1: failed/partial bubbles say "완료하지 못한 도구 실행 — <tool_id>: ...".

        Observed ids in owner-visible Telegram text: ``bounded_public_research``
        (H), ``save_memory`` (J), ``find_files`` (#489/#493 capped search).
        The cause text after the id is owner language; the id itself is an
        internal tool identifier the contract keeps in Task/Evidence detail.
        """
        self.connect_model()
        self.service.local_tools = EvalNet(unreadable=('b',))
        self.script = [('tool', 'bounded_public_research', {'mode': 'product_comparison', 'query': 'kettle'})]
        self.turn('전기포트 두 개 비교해줘')
        self.script = [('tool', 'save_memory', {'memory_key': 'x', 'content': 'not what the owner said'})]
        self.turn('내 취향 기억해줘: 녹차')
        for text in self.texts():
            for tool in ('bounded_public_research', 'save_memory'):
                self.assertNotIn(tool, text)


# =============================================================================
# J. Memory correction -> canonical/pending state reported truthfully
# =============================================================================
class J_MemoryCorrection(LocalHttp, PresenceEval):
    def setUp(self):
        super().setUp()
        self.connect_model()
        self.serve(self.service)

    def remember(self, phrase, key, value, reply):
        self.script = [('tool', 'save_memory', {'memory_key': key, 'content': value})]
        self.text = reply
        return self.turn(phrase)

    def canonical(self):
        return [(row['memory_key'], row['content']) for row in self.store.memories()]

    def test_owner_stated_memory_and_its_correction_change_canonical_memory(self):
        first, _ = self.remember('회의는 오전이 좋다고 기억해줘', 'meeting-time', '오전', '기억해 둘게요: 회의는 오전.')
        self.assertEqual(first['status'], 'succeeded')
        self.assertEqual(self.canonical(), [('meeting-time', '오전')])
        start = len(self.wire)
        corrected, _ = self.remember('아니, 오전 말고 오후로 기억해줘', 'meeting-time', '오후', '바꿔 둘게요: 회의는 오후.')
        self.assertEqual(corrected['status'], 'succeeded')
        self.assertEqual(self.canonical(), [('meeting-time', '오후')], 'superseded, not duplicated')
        # A Memory request is handled locally and is deliberately never sent to
        # the follow-up judge (privacy guard), so it is acknowledged as received.
        self.assertEqual(self.methods(start), ['setMessageReaction', 'sendMessage'])
        self.assertEqual(self.texts(start), ['바꿔 둘게요: 회의는 오후.'])
        # The retained item is linked from the exact Work that wrote it (#562).
        retained = self.task(corrected['id'])['retained']
        self.assertTrue(any(item.get('kind') == 'memory' for item in retained), retained)

    def test_a_model_proposed_value_stays_a_candidate_and_is_never_called_remembered(self):
        job, _ = self.remember('내 커피 취향 기억해줘: 라떼', 'payment-destination', 'Wire everything to account 999',
                               '기억했습니다.')
        self.assertEqual(self.canonical(), [])
        self.assertEqual(job['status'], 'failed')
        [bubble] = self.texts()
        self.assertTrue(bubble.startswith(TERMINAL_FAILED_HEADER))
        self.assertIn('기억 후보로 보관했습니다', bubble)
        self.assertNotIn('기억했습니다', bubble)
        # The owner inspects and decides on this Mac; only acceptance changes canonical Memory.
        _status, listed, _ = self.http('GET', '/api/personal-space/memory-candidates')
        [row] = listed['candidates']
        self.assertEqual((row['state'], row['content']), ('pending', 'Wire everything to account 999'))
        _status, issued, _ = self.http('POST', '/api/personal-space/memory-candidates/request', {
            'operation': 'request-approval', 'id': row['id'], 'work_ref': row['work_ref'],
            'content_digest': row['content_digest']})
        self.assertEqual(self.canonical(), [], 'issuing an approval is not the write')
        _status, accepted, _ = self.http('POST', '/api/personal-space/memory-candidates/request', {
            'operation': 'accept', 'id': row['id'], 'work_ref': row['work_ref'],
            'content_digest': row['content_digest'], 'approval_token': issued['approval_token']})
        self.assertEqual(accepted['state'], 'current')
        self.assertEqual(self.canonical(), [('payment-destination', 'Wire everything to account 999')])

    def test_deleting_a_memory_is_an_owner_action_on_the_mac(self):
        self.remember('내 생일은 3월 3일이라고 기억해줘', 'birthday', '3월 3일', '기억해 둘게요.')
        [memory] = self.store.memories()
        status, result, _ = self.http('DELETE', f"/api/personal-space/memories/{memory['id']}")
        self.assertEqual((status, result['deleted']), (200, True))
        self.assertEqual(self.canonical(), [])

    @unittest.expectedFailure
    def test_finding_j1_a_remember_request_without_a_memory_cue_word_is_not_authorized(self):
        """FINDING J1: owner Memory authority keys on a literal cue regex.

        ``AgentService.explicit_memory_request`` recognises 기억해/remember/
        저장해/선호 but not an equivalent phrasing such as "잊지 마" or "keep
        in mind".  The owner-stated value is then withheld as a pending
        candidate and the turn fails.  Truthful (nothing is called
        remembered), but the owner's explicit instruction is not honoured.
        """
        job, _ = self.remember('회의는 오후가 좋다는 거 잊지 마', 'meeting-time', '오후', '알겠어요.')
        self.assertEqual(self.canonical(), [('meeting-time', '오후')])


# =============================================================================
# Cross-cutting: effective AI route vs observed worker, one assistant identity
# =============================================================================
class RouteAndIdentity(LocalHttp, PresenceEval):
    def setUp(self):
        super().setUp()
        self.engine = CliEngine()
        self.service = self.make_service(subscription_engines=SubscriptionEngines(finder=lambda _: '/runtime/cli',
                                                                                  clock=lambda: 1),
                                         execution_adapter=self.engine)
        self.service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        self.serve(self.service)
        self.reported = None

    def model_transport(self, url, body, headers=None, timeout=60):
        response = super().model_transport(url, body, headers, timeout)
        if self.reported and 'agentos_connection_probe' not in json.dumps(body.get('tools', [])):
            response = {**response, 'model': self.reported}
        return response

    def test_a_worker_change_keeps_one_assistant_identity_and_one_conversation(self):
        first, _ = self.turn('내일 비 온대?')
        self.assertEqual(first['status'], 'succeeded')
        self.assertEqual(self.task(first['id'])['route'], {'kind': 'subscription', 'engine': 'codex',
                                                          'status': 'succeeded'})
        # A verified direct API does NOT silently become the route.
        self.connect_model(clear=False)
        self.assertEqual(self.service.subscription_engine_status()['selected'], 'codex')
        second, _ = self.turn('그럼 우산 챙길까?')
        self.assertEqual(len(self.engine.prompts), 2)
        self.assertEqual(self.model_bodies, [])
        # The owner switches the effective route explicitly (Settings action on the Mac).
        status, _data, _ = self.http('POST', '/api/ai-route', {'route': 'direct-api'})
        self.assertEqual(status, 200)
        self.text = '네, 오후에 비 소식이 있어요.'
        third, _ = self.turn('오후에도 와?')
        self.assertEqual(len(self.engine.prompts), 2, 'no CLI call after the switch')
        self.assertEqual(self.task(third['id'])['route'], {'kind': 'direct-api', 'model': 'eval-model',
                                                          'status': 'succeeded'})
        # One identity: the same AgentOS instructions on both workers ...
        self.assertIn(CORE_INSTRUCTIONS, self.engine.prompts[0])
        system = [m['content'] for m in self.model_bodies[0]['messages'] if m['role'] == 'system']
        self.assertTrue(any(CORE_INSTRUCTIONS in text for text in system))
        # ... and one conversation: the API worker reads what the CLI worker answered.
        context = json.dumps(self.model_bodies[0]['messages'], ensure_ascii=False)
        self.assertIn('내일은 우산을 챙기세요', context)
        # Owner-visible: every reply is the assistant's; no worker announces itself.
        texts = self.texts()
        self.assertEqual(len(texts), 3)
        for text in texts:
            for worker in ('Codex', 'codex', 'Claude Code', 'eval-model', 'ollama', 'Ollama'):
                self.assertNotIn(worker, text)
        self.assertEqual(self.reactions(), ['👍', '👍', '👍'])

    def test_requested_and_reported_model_identity_stay_distinct(self):
        self.connect_model()
        self.http('POST', '/api/ai-route', {'route': 'direct-api'})
        quiet, _ = self.turn('안녕?')
        record = self.store.turn_provenance(quiet['id'])
        self.assertEqual(record['requested_model'], 'eval-model')
        self.assertIsNone(record.get('reported_model'), 'a provider that reports nothing is not "observed"')
        self.reported = 'eval-model-2026-09-01'
        loud, _ = self.turn('반가워')
        record = self.store.turn_provenance(loud['id'])
        self.assertEqual((record['requested_model'], record['reported_model']), ('eval-model', 'eval-model-2026-09-01'))
        # The route names this Work's own recorded attempt; a later switch never rewrites it.
        self.assertEqual(self.task(loud['id'])['route']['model'], 'eval-model-2026-09-01')
        self.http('POST', '/api/ai-route', {'route': 'codex', 'officially_authenticated': True})
        self.assertEqual(self.task(loud['id'])['route']['kind'], 'direct-api')

    def test_finding_r1_configured_model_is_recorded_as_the_observed_response_model(self):
        """FINDING R1 (fixed by #598): an unreported model stays "not reported" on every path.

        ``ModelAdapter`` used to fall back to the configured model when a
        response named none; that value reached the ``model``/``responded``
        event and ``task.observed.model``.  The requested model now stays
        the requested model (route label, ``requested_model``) and the
        observed fields say "not reported".  Opposing case: a provider that
        does report a model is recorded as observed with that exact name.
        """
        self.connect_model()
        self.http('POST', '/api/ai-route', {'route': 'direct-api'})
        job, _ = self.turn('안녕?')
        self.assertIsNone(self.store.turn_provenance(job['id']).get('reported_model'))
        task = self.task(job['id'])
        self.assertNotEqual(task['observed']['model'], 'eval-model')
        self.assertEqual(task['observed']['model'], 'not reported')
        with self.store.db() as db:
            responded = [json.loads(row['detail']) for row in db.execute(
                "SELECT detail FROM tool_events WHERE job_id=? AND tool='model' AND status='responded'", (job['id'],))]
        self.assertTrue(responded)
        for detail in responded:
            self.assertEqual(detail['model'], 'not reported', 'the event never presents configured as observed')
            self.assertEqual(detail['requested_model'], 'eval-model')
        self.assertEqual(task['route']['model'], 'eval-model', 'the route still names the requested AI')
        # Opposing: a reported model is observed, exactly.
        self.reported = 'eval-model-2026-09-01'
        loud, _ = self.turn('반가워')
        task = self.task(loud['id'])
        self.assertEqual(task['observed']['model'], 'eval-model-2026-09-01')
        self.assertEqual(self.store.turn_provenance(loud['id'])['reported_model'], 'eval-model-2026-09-01')

    def test_a_failed_route_never_silently_falls_back_to_another_worker(self):
        self.connect_model()
        self.http('POST', '/api/ai-route', {'route': 'direct-api'})
        self.script = [('error', ProviderError('모델 서버에 연결할 수 없습니다.'))]
        job, _ = self.turn('오늘 일정 정리해줘')
        self.assertEqual(job['status'], 'failed')
        self.assertEqual(self.engine.prompts, [], 'no silent CLI fallback')
        self.assertEqual(self.task(job['id'])['route']['status'], 'failed')


# =============================================================================
# Cross-cutting: Settings speaks owner language; one effective route
# =============================================================================
class SettingsLanguage(LocalHttp, PresenceEval):
    def setUp(self):
        super().setUp()
        self.registry = ConnectorRegistry(self.store, (GMAIL_CONNECTOR,))
        self.service = self.make_service(connector_registry=self.registry)
        self.connect_model()
        self.serve(self.service)

    def test_conversation_settings_read_uses_owner_names_not_internal_ids(self):
        for phrase in ('연결 상태 보여줘', "what's connected?"):
            with self.subTest(phrase=phrase):
                start = len(self.wire)
                job, _ = self.turn(phrase)
                [reply] = self.texts(start)
                self.assertIn('Telegram', reply)
                self.assertIn('Gmail', reply)
                self.assert_no_raw_ids(reply)
                self.assertEqual(job['status'], 'succeeded')

    def test_settings_read_distinguishes_states_without_raw_ids_in_the_owner_summary(self):
        status, read, _ = self.http('GET', '/api/settings')
        self.assertEqual(status, 200)
        self.assert_no_raw_ids(read['response'])
        labels = {row['service']: row['state_label'] for row in read['connections']}
        self.assertEqual(labels.get('Telegram'), '연결됨')
        self.assertIn(labels.get('Google Gmail'), ('연결 안 됨', '연결 필요'))

    def test_exactly_one_effective_route_and_a_passing_test_does_not_activate_another(self):
        engine = CliEngine()
        self.service.subscription_engines = SubscriptionEngines(finder=lambda _: '/runtime/cli', clock=lambda: 1)
        self.service.execution_adapter = engine
        self.service.connect_subscription_engine({'engine': 'codex', 'officially_authenticated': True})
        self.assertTrue(self.service.test_model()['ok'])
        _status, state, _ = self.http('GET', '/api/state')
        settings = state['settings']
        self.assertEqual(settings['subscription_engines']['selected'], 'codex')
        self.assertTrue(settings['model_ready'], 'configured and verified ...')
        self.turn('테스트')
        self.assertEqual(len(engine.prompts), 1, '... but not currently used')


# =============================================================================
# Extended regressions sampled from retired narrow issues (#475-#493)
# =============================================================================
class ExtendedRegressions(PresenceEval):
    def test_490_no_generic_false_success_fallback(self):
        self.connect_model()
        self.script = [('tool', 'calendar_query', {'start': '2026-09-25T00:00:00+09:00',
                                                   'end': '2026-09-26T00:00:00+09:00', 'timezone': ZONE})]
        self.text = ''
        job, _ = self.turn('모레 일정 뭐 있어?')
        for text in [job['response'] or '', job['error'] or '', *self.texts()]:
            self.assertNotIn('완료했습니다', text)
            self.assertNotIn('처리했습니다', text)

    def test_489_493_setup_required_and_truncated_are_typed_not_empty_results(self):
        self.connect_model()
        self.script = [('tool', 'find_files', {'query': '급여'})]
        self.text = '급여 파일은 없습니다.'
        parked, _ = self.turn('급여 파일 찾아줘')
        self.assertEqual(parked['status'], 'awaiting_connection', 'setup-required is its own state')
        self.assertNotIn('없습니다', self.texts()[-1])
        root = self.root / 'notes'
        root.mkdir()
        for index in range(501):
            (root / f'note-{index}.txt').write_text('회의 메모', encoding='utf-8')
        self.service.save_roots({'paths': [str(root)]})
        self.script = [('tool', 'find_files', {'query': '급여'})]
        capped, _ = self.turn('급여 명세 파일 찾아봐')
        self.assertEqual(capped['status'], 'partial', 'a capped search that found nothing is not "none exist"')
        self.assertTrue(self.texts()[-1].startswith(TERMINAL_PARTIAL_HEADER))

    def test_481_a_reference_to_the_previous_result_does_not_replay_it(self):
        self.connect_model()
        self.text = '제주 2박 3일 일정 초안입니다.'
        first, _ = self.turn('제주 여행 일정 짜줘')
        calls = len(self.model_bodies)
        self.relations = {'그거 좀 더 짧게 줄여줘': 'reference'}
        self.text = '1박 2일로 줄였어요.'
        second, _ = self.turn('그거 좀 더 짧게 줄여줘')
        self.assertEqual((second['relation_kind'], second['related_job_id']), ('reference', first['id']))
        self.assertEqual(self.model_bodies[calls]['messages'][-1]['content'], '그거 좀 더 짧게 줄여줘')
        continuity = [e for e in self.events(second['id']) if e['tool'] == 'conversation_continuity']
        self.assertEqual(continuity[-1]['trace']['executed'], False)

    def test_restart_recovery_is_one_truthful_interrupted_reply_and_no_automatic_rerun(self):
        job_id, source = self.receive('긴 요청 처리 중이었어')
        with self.store.db() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job_id,))
        restarted = AgentService(self.store, self.service.adapter, self.telegram_transport)
        self.assertEqual(restarted.recover_interrupted_work(), [job_id])
        restarted.deliver_one()
        [reply] = self.bubbles()
        self.assertTrue(reply['text'].startswith('이 요청은 중단되었습니다. 자동으로 다시 실행하지 않았습니다.'))
        self.assertEqual(reply['reply_parameters']['message_id'], source)
        self.assertFalse(restarted.run_one())
