"""Natural intent classification for the one personal conversation.

These tests cover WU2 of PA1-CONV-01: ordinary Korean and English utterances
reach the right capability without a magic command prefix, supported slash commands keep
working, an ambiguous utterance never triggers a consequential effect, and a
model's opinion cannot by itself authorise anything.

The whole pre-existing suite is the evidence that the prefix chain was
replaced without changing what any previously supported utterance does; these
tests are the evidence for what is new.
"""
import itertools
import tempfile
import unittest

from personal_agent.capabilities import CapabilityRegistry
from personal_agent.conversation_handoff import (AUTHORITY_DEFAULT, AUTHORITY_OWNER, AUTHORITY_RULE,
                                                 CONSEQUENTIAL_INTENTS, INTENT_AMBIGUOUS,
                                                 INTENT_CALENDAR_CREATE,
                                                 INTENT_CONVERSATION, INTENT_GREETING,
                                                 INTENT_KNOWLEDGE, INTENT_NOTE_CREATE,
                                                 INTENT_NOTE_LIST,
                                                 INTENT_RESEARCH, INTENT_SETTINGS,
                                                 INTENT_WORKSPACE_SEARCH,
                                                 ConversationFocus,
                                                 IntentClassifier)
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService, workspace_search_request
from personal_agent.quickstart_store import QuickStore


def classifier():
    """The classifier exactly as the service builds it."""
    return IntentClassifier(workspace_search=workspace_search_request)


#: Two Korean and two English paraphrases for every intent an ordinary
#: utterance is allowed to reach.  The criterion asks for *representative*
#: paraphrases, so no intent is carried by a single phrasing.
PARAPHRASES = {
    INTENT_KNOWLEDGE: (
        ('개인 공간에서 오로라 관련 자료 찾아줘', '오로라'),
        ('내 지식에서 예산 검토 알려줘', '예산 검토'),
        ('what do i know about aurora?', 'aurora'),
        ('search my knowledge base for the budget review', 'budget review'),
    ),
    INTENT_NOTE_CREATE: (
        ('금요일 3시 출시 검토 메모해줘', '금요일 3시 출시 검토'),
        ('오로라 예산 확정 적어둬', '오로라 예산 확정'),
        ('take a note: aurora budget approved', 'aurora budget approved'),
        ('make a note of the vendor call tomorrow', 'the vendor call tomorrow'),
    ),
    INTENT_WORKSPACE_SEARCH: (
        ('작업공간에 저장한 파일 열어줘', '__latest__'),
        ('내 워크스페이스에서 회의 브리프 보여줘', '회의 브리프'),
        ('open the saved file about aurora', 'aurora'),
        ('pull up the saved result about aurora', 'aurora'),
    ),
    INTENT_SETTINGS: (
        ('연결 상태 알려줘', '/settings'),
        ('드라이브 연결 해제해줘', '드라이브 연결 해제해줘'),
        ("what's connected?", '/settings'),
        ('pause the calendar connection', 'pause the calendar connection'),
    ),
    INTENT_RESEARCH: (
        ('웹에서 최신 환율 찾아줘', None),
        ('인터넷에서 조사해줘', None),
        ('look up the latest exchange rate', None),
        ('search the web for vendor reviews', None),
    ),
}

#: Recognised from ordinary prose.  What it reaches is a draft with an exact
#: preview; the effect waits for the owner's explicit approval of that preview.
CALENDAR_PARAPHRASES = ('내일 오후 3시에 팀 회의 일정 잡아줘', '금요일 약속 하나 등록해줘',
                        'schedule a meeting with the vendor tomorrow',
                        'add a calendar event for friday')

#: Natural memory phrasing is owned by `explicit_memory_request`, which issues
#: an approval and leaves the utterance on the conversation route.  It is a
#: flag, never a capability selection.
MEMORY_PARAPHRASES = ('이 선호를 기억해줘', '다음 내용을 저장해',
                      'remember this preference', 'save this for later')


class ParaphraseTests(unittest.TestCase):
    """Two Korean and two English paraphrases reach each intent."""

    def setUp(self):
        self.classifier = classifier()

    def test_every_intent_is_reachable_from_two_korean_and_two_english_paraphrases(self):
        for intent, rows in PARAPHRASES.items():
            korean = [text for text, _ in rows if not text.isascii()]
            english = [text for text, _ in rows if text.isascii()]
            self.assertGreaterEqual(len(korean), 2, intent)
            self.assertGreaterEqual(len(english), 2, intent)
            for text, argument in rows:
                with self.subTest(intent=intent, text=text):
                    decision = self.classifier.classify(text)
                    self.assertEqual(decision.intent, intent)
                    self.assertEqual(decision.authority, AUTHORITY_RULE)
                    self.assertTrue(decision.executes)
                    self.assertEqual(decision.argument, argument)
                    self.assertTrue(decision.cues, 'a rule decision must record the cues it used')

    def test_memory_phrasing_stays_on_the_conversation_route_as_an_approval_flag(self):
        for text in MEMORY_PARAPHRASES:
            with self.subTest(text=text):
                self.assertTrue(AgentService.explicit_memory_request(text))
                self.assertIn(self.classifier.classify(text).intent,
                              (INTENT_CONVERSATION, INTENT_RESEARCH))

    def test_a_negated_memory_request_is_still_not_an_approval(self):
        self.assertFalse(AgentService.explicit_memory_request('기억하지 마세요'))
        self.assertFalse(AgentService.explicit_memory_request('do not save this'))


class ExplicitFormTests(unittest.TestCase):
    """Supported slash commands remain authoritative; retired ones fall through."""

    def setUp(self):
        self.classifier = classifier()

    def test_every_slash_and_legacy_form_keeps_its_route_and_its_argument(self):
        cases = (
            ('/start', INTENT_GREETING, None),
            ('/help', INTENT_GREETING, None),
            ('/knowledge aurora', INTENT_KNOWLEDGE, 'aurora'),
            ('/settings Drive pause', INTENT_SETTINGS, 'Drive pause'),
            ('/settings', INTENT_SETTINGS, '/settings'),
            ('무엇이 연결되어 있어?', INTENT_SETTINGS, '무엇이 연결되어 있어?'),
            ('/note 회의: 금요일 출시 검토', INTENT_NOTE_CREATE, '회의: 금요일 출시 검토'),
            ('메모: 오로라 예산', INTENT_NOTE_CREATE, '오로라 예산'),
            ('기록: 오로라 예산', INTENT_NOTE_CREATE, '오로라 예산'),
            ('/notes', INTENT_NOTE_LIST, None),
            ('메모 목록', INTENT_NOTE_LIST, None),
        )
        for text, intent, argument in cases:
            with self.subTest(text=text):
                decision = self.classifier.classify(text)
                self.assertEqual(decision.intent, intent)
                self.assertEqual(decision.authority, AUTHORITY_OWNER)
                self.assertEqual(decision.argument, argument)

    def test_an_unrecognised_slash_command_falls_through_instead_of_guessing(self):
        for text in ('/summarize', '/workspace-summary Aurora :: Launch notes',
                     '/search AgentOS personal assistant verification', '/assistant Drive 검색: 예산',
                     '/recommend specialist-research'):
            with self.subTest(text=text):
                decision = self.classifier.classify(text)
                self.assertIn(decision.intent, (INTENT_CONVERSATION, INTENT_RESEARCH,
                                                INTENT_WORKSPACE_SEARCH))
                self.assertNotIn(decision.intent, CONSEQUENTIAL_INTENTS)


class SafeFallbackTests(unittest.TestCase):
    """An unrecognised utterance answers in conversation, it never guesses."""

    def setUp(self):
        self.classifier = classifier()

    def test_ordinary_prose_stays_on_the_conversation_route(self):
        for text in ('hello', '일반적인 다음 질문입니다.', 'show my notes', '성남시 날씨를 찾아줘',
                     '“Aurora” 자료를 요약해 “Launch notes”로 저장해줘'):
            with self.subTest(text=text):
                decision = self.classifier.classify(text)
                self.assertEqual(decision.intent, INTENT_CONVERSATION)
                self.assertEqual(decision.authority, AUTHORITY_DEFAULT)

    def test_external_peer_prose_stays_non_consequential(self):
        for text in ('이 작업을 외부 에이전트에게 맡겨줘', '다른 agent에게 위임해줘',
                     'delegate this task to the external agent',
                     'hand this off to the research peer'):
            with self.subTest(text=text):
                decision = self.classifier.classify(text)
                self.assertNotIn(decision.intent, CONSEQUENTIAL_INTENTS)

    def test_drive_prose_stays_on_a_safe_non_consequential_route(self):
        for text in ('구글 드라이브 파일을 요약해줘', '드라이브에서 자료 읽어줘'):
            with self.subTest(text=text):
                decision = self.classifier.classify(text)
                self.assertNotIn(decision.intent, CONSEQUENTIAL_INTENTS)


class ConsequentialEffectTests(unittest.TestCase):
    """Calendar creation is an effect; research and file reads are not."""

    def setUp(self):
        self.classifier = classifier()

    def test_a_recognised_calendar_request_is_consequential_and_carries_the_utterance(self):
        for text in CALENDAR_PARAPHRASES:
            with self.subTest(text=text):
                decision = self.classifier.classify(text)
                self.assertEqual(decision.intent, INTENT_CALENDAR_CREATE)
                self.assertTrue(decision.consequential)
                self.assertEqual(decision.authority, AUTHORITY_RULE)
                # It may proceed - as far as a draft.  The utterance is the
                # argument the draft rules read; nothing is extracted here.
                self.assertTrue(decision.executes)
                self.assertEqual(decision.argument, text)

    def test_a_pending_draft_claims_cue_free_follow_ups_only_while_it_is_pending(self):
        pending = {'intent': INTENT_CALENDAR_CREATE, 'calendar_pending': True}
        for text in ('치과', '오후 4시', '승인', 'approve', '취소', '아니 4시로'):
            with self.subTest(text=text):
                decision = self.classifier.classify(text, focus=pending)
                self.assertEqual(decision.intent, INTENT_CALENDAR_CREATE)
                self.assertTrue(decision.continuation)
                self.assertEqual(decision.argument, text)
        # Same focus intent, no pending draft: an ordinary utterance stays on
        # the conversation route exactly as before.
        stale = {'intent': INTENT_CALENDAR_CREATE}
        self.assertEqual(self.classifier.classify('치과', focus=stale).intent, INTENT_CONVERSATION)
        # A rule that fires still wins over the pending draft.
        self.assertEqual(self.classifier.classify('메모 목록', focus=pending).intent, INTENT_NOTE_LIST)
        self.assertEqual(self.classifier.classify('/notes', focus=pending).intent, INTENT_NOTE_LIST)

    def test_non_consequential_intents_execute_from_prose(self):
        for intent, rows in PARAPHRASES.items():
            self.assertNotIn(intent, CONSEQUENTIAL_INTENTS)
            for text, _argument in rows:
                with self.subTest(text=text):
                    self.assertTrue(self.classifier.classify(text).executes)

    def test_an_ambiguous_utterance_resolves_to_a_clarification_and_no_action(self):
        cases = (
            ('내일 회의 일정 잡고 작업공간에 저장한 자료도 찾아줘',
             (INTENT_WORKSPACE_SEARCH, INTENT_CALENDAR_CREATE)),
            ('개인 공간의 저장한 파일 찾아줘',
             (INTENT_KNOWLEDGE, INTENT_WORKSPACE_SEARCH)),
        )
        for text, options in cases:
            with self.subTest(text=text):
                decision = self.classifier.classify(text)
                self.assertEqual(decision.intent, INTENT_AMBIGUOUS)
                self.assertEqual(set(decision.alternatives), set(options))
                self.assertFalse(decision.executes)
                self.assertIn('아무 작업도 실행하지 않았습니다', decision.clarification)

    def test_a_recognised_intent_missing_its_subject_asks_instead_of_guessing(self):
        for text, intent in (('이거 메모해줘', INTENT_NOTE_CREATE),
                             ('개인 공간 보여줘', INTENT_KNOWLEDGE)):
            with self.subTest(text=text):
                decision = self.classifier.classify(text)
                self.assertEqual(decision.intent, intent)
                self.assertFalse(decision.executes)
                self.assertTrue(decision.clarification)


class ModelAuthorityTests(unittest.TestCase):
    """A model suggestion is input, never authority."""

    def setUp(self):
        self.classifier = classifier()
        self.ambiguous = '개인 공간의 저장한 파일 찾아줘'

    def test_a_suggestion_cannot_introduce_an_intent_the_rules_did_not_find(self):
        decision = self.classifier.classify('오늘 뭐 하면 좋을까?',
                                            model_suggestion={'intent': INTENT_KNOWLEDGE,
                                                              'confidence': 0.99})
        self.assertEqual(decision.intent, INTENT_CONVERSATION)
        self.assertEqual(decision.model_suggestion['state'], 'rejected')
        self.assertEqual(decision.model_suggestion['reason'], 'no-ambiguity-to-resolve')

    def test_a_suggestion_cannot_override_a_decision_the_rules_already_made(self):
        decision = self.classifier.classify('what do i know about aurora?',
                                            model_suggestion={'intent': INTENT_CALENDAR_CREATE})
        self.assertEqual(decision.intent, INTENT_KNOWLEDGE)
        self.assertEqual(decision.model_suggestion['state'], 'rejected')

    def test_a_suggestion_cannot_override_an_owner_explicit_form(self):
        decision = self.classifier.classify('/notes',
                                            model_suggestion={'intent': INTENT_KNOWLEDGE})
        self.assertEqual(decision.intent, INTENT_NOTE_LIST)
        self.assertEqual(decision.authority, AUTHORITY_OWNER)
        self.assertEqual(decision.model_suggestion['state'], 'rejected')

    def test_a_suggestion_cannot_select_a_consequential_intent(self):
        decision = self.classifier.classify('내일 회의 일정 잡고 작업공간에 저장한 자료도 찾아줘',
                                            model_suggestion={'intent': INTENT_CALENDAR_CREATE})
        self.assertEqual(decision.intent, INTENT_AMBIGUOUS)
        self.assertEqual(decision.model_suggestion['reason'], 'consequential-intent')

    def test_a_suggestion_naming_a_non_candidate_is_recorded_and_rejected(self):
        decision = self.classifier.classify(self.ambiguous,
                                            model_suggestion={'intent': INTENT_SETTINGS})
        self.assertEqual(decision.intent, INTENT_AMBIGUOUS)
        self.assertEqual(decision.model_suggestion['reason'], 'not-a-deterministic-candidate')

    def test_a_malformed_suggestion_is_rejected_rather_than_trusted(self):
        for suggestion in ({}, {'intent': None}, {'intent': 'rm -rf'}, 'personal-knowledge', 42):
            with self.subTest(suggestion=suggestion):
                decision = self.classifier.classify(self.ambiguous, model_suggestion=suggestion)
                self.assertEqual(decision.intent, INTENT_AMBIGUOUS)
                self.assertEqual(decision.model_suggestion['state'], 'rejected')

    def test_the_only_accepted_suggestion_narrows_an_agentos_candidate(self):
        decision = self.classifier.classify(self.ambiguous,
                                            model_suggestion={'intent': INTENT_WORKSPACE_SEARCH})
        self.assertEqual(decision.intent, INTENT_WORKSPACE_SEARCH)
        self.assertEqual(decision.model_suggestion['state'], 'accepted')
        # Even then the authority is AgentOS's: the rules produced the option
        # set and the argument, the suggestion only picked one of them.
        self.assertEqual(decision.authority, AUTHORITY_RULE)
        self.assertEqual(decision.argument, self.classifier.classify(
            '개인 공간의 저장한 파일 찾아줘', model_suggestion={'intent': INTENT_WORKSPACE_SEARCH}).argument)

    def test_no_decision_can_ever_carry_model_authority(self):
        texts = ['/notes', 'hello', self.ambiguous, *CALENDAR_PARAPHRASES]
        texts += [text for rows in PARAPHRASES.values() for text, _ in rows]
        for text in texts:
            for suggestion in (None, {'intent': INTENT_CALENDAR_CREATE}, {'intent': INTENT_KNOWLEDGE}):
                with self.subTest(text=text, suggestion=suggestion):
                    decision = self.classifier.classify(text, model_suggestion=suggestion)
                    self.assertIn(decision.authority,
                                  (AUTHORITY_OWNER, AUTHORITY_RULE, AUTHORITY_DEFAULT))


class CorrectionAndTopicChangeTests(unittest.TestCase):
    """A second utterance that changes the subject is not a continuation."""

    def setUp(self):
        self.classifier = classifier()

    def test_a_changed_subject_supersedes_the_previous_focus(self):
        first = self.classifier.classify('작업공간에 저장한 파일 열어줘')
        self.assertEqual(first.intent, INTENT_WORKSPACE_SEARCH)
        focus = {'intent': first.intent}
        second = self.classifier.classify('연결 상태 알려줘', focus=focus)
        self.assertEqual(second.intent, INTENT_SETTINGS)
        self.assertFalse(second.continuation)
        self.assertTrue(second.supersedes_previous)

    def test_a_correction_marker_supersedes_even_when_the_intent_repeats(self):
        focus = {'intent': INTENT_NOTE_CREATE}
        decision = self.classifier.classify('아니, 그거 말고 오로라 예산 확정 적어둬', focus=focus)
        self.assertEqual(decision.intent, INTENT_NOTE_CREATE)
        self.assertEqual(decision.argument, '오로라 예산 확정')
        self.assertTrue(decision.supersedes_previous)
        self.assertFalse(decision.continuation)

    def test_a_correction_marker_blocks_continuation_resolution(self):
        focus = {'intent': INTENT_RESEARCH}
        decision = self.classifier.classify('아니, 계속하지 말고 다른 얘기 하자', focus=focus)
        self.assertFalse(decision.continuation)
        self.assertTrue(decision.supersedes_previous)

    def test_a_genuine_continuation_stays_on_the_same_route(self):
        focus = {'intent': INTENT_CONVERSATION}
        for text in ('continue', 'keep going', '계속해줘', '이어서 말해줘'):
            with self.subTest(text=text):
                decision = self.classifier.classify(text, focus=focus)
                self.assertEqual(decision.intent, INTENT_CONVERSATION)
                self.assertFalse(decision.supersedes_previous)

    def test_continuation_never_replays_an_intent_that_needs_its_own_content(self):
        # "keep going" must not re-run a note write or a search with whatever
        # the previous turn happened to contain.
        for previous in (INTENT_NOTE_CREATE, INTENT_WORKSPACE_SEARCH, INTENT_KNOWLEDGE,
                         INTENT_CALENDAR_CREATE, INTENT_SETTINGS):
            with self.subTest(previous=previous):
                decision = self.classifier.classify('계속해줘', focus={'intent': previous})
                self.assertEqual(decision.intent, INTENT_CONVERSATION)
                self.assertTrue(decision.supersedes_previous)

    def test_the_focus_record_holds_no_utterance_content(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = QuickStore(temp.name)
        focus = ConversationFocus(store)
        decision = self.classifier.classify('개인 공간에서 오로라 관련 자료 찾아줘')
        focus.record(decision)
        saved = focus.current()
        self.assertEqual(set(saved), {'intent', 'at'})
        self.assertEqual(saved['intent'], INTENT_KNOWLEDGE)
        self.assertNotIn('오로라', repr(saved))

    def test_an_ambiguous_turn_does_not_overwrite_the_focus(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = QuickStore(temp.name)
        focus = ConversationFocus(store)
        focus.record(self.classifier.classify('what do i know about aurora?'))
        focus.record(self.classifier.classify('개인 공간의 저장한 파일 찾아줘'))
        self.assertEqual(focus.current()['intent'], INTENT_KNOWLEDGE)


class ServiceRoutingTests(unittest.TestCase):
    """The queued conversation worker honours the classifier's decision."""

    MODEL_ROUTE_ERROR = '설정에서 모델 또는 구독 엔진을 먼저 연결하세요.'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(self.temp.name)
        self.keys = itertools.count()

        def transport(url, body, headers=None, timeout=60):
            raise AssertionError('no model or Telegram call is expected here: ' + url)

        self.service = AgentService(self.store, ModelAdapter(transport), transport)
        self.registry = CapabilityRegistry(self.store)

    def run_one(self, message, channel='web', chat_id=None):
        job = self.store.enqueue(message, f'intent-{next(self.keys)}', channel=channel, chat_id=chat_id)
        self.assertTrue(self.service.run_one())
        return self.store.job(job)

    def assertConversationRoute(self, job):
        """No model is configured, so the conversation route fails distinctly."""
        self.assertEqual(job['status'], 'failed')
        self.assertIn(self.MODEL_ROUTE_ERROR, job['error'])

    # -- supported slash commands still work --------------------------------
    def test_slash_commands_still_route_after_the_prefix_chain_is_replaced(self):
        self.assertIn('개인 AgentOS에 연결되었습니다', self.run_one('/start')['response'])
        self.assertIn('메모를 저장했습니다', self.run_one('/note 금요일 출시 검토')['response'])
        self.assertIn('금요일 출시 검토', self.run_one('/notes')['response'])
        self.assertIn('금요일 출시 검토', self.run_one('메모 목록')['response'])
        self.assertIn('메모를 저장했습니다', self.run_one('기록: 오로라 예산')['response'])
        self.assertIn('오로라 예산', [row['content'] for row in self.store.notes()])

    def test_the_explicit_settings_command_reaches_settings_but_drafts_no_retired_change(self):
        self.registry.transition('google-drive-read', 'enabled', ('read',))
        before = self.store.config('capability_registry')
        self.assertIn('대화에서 제공하지 않습니다', self.run_one('/settings Drive pause')['response'])
        self.assertEqual(self.store.config('capability_registry'), before)
        self.assertEqual(self.store.config('settings_change_drafts', {}), {})

    # -- the same capabilities, reached naturally ---------------------------
    def test_knowledge_paraphrases_reach_the_personal_space_orchestrator(self):
        for text, _query in PARAPHRASES[INTENT_KNOWLEDGE]:
            with self.subTest(text=text):
                before = len(self.store.config('personal_knowledge_audit', []))
                job = self.run_one(text, channel='telegram:fixture', chat_id=7)
                self.assertEqual(job['status'], 'succeeded')
                self.assertEqual(len(self.store.config('personal_knowledge_audit', [])), before + 1)

    def test_note_paraphrases_store_the_extracted_content(self):
        for text, content in PARAPHRASES[INTENT_NOTE_CREATE]:
            with self.subTest(text=text):
                job = self.run_one(text)
                self.assertIn('메모를 저장했습니다', job['response'])
                self.assertIn(content, [row['content'] for row in self.store.notes()])

    def test_workspace_paraphrases_reach_the_file_workspace_not_the_model(self):
        for text, _query in PARAPHRASES[INTENT_WORKSPACE_SEARCH]:
            with self.subTest(text=text):
                job = self.run_one(text)
                self.assertEqual(job['status'], 'succeeded')
                self.assertEqual(job['response'], '현재 원본과 일치하는 저장 결과를 찾지 못했습니다.')

    def test_settings_paraphrases_reach_the_settings_orchestrator(self):
        self.registry.transition('google-drive-read', 'enabled', ('read',))
        self.registry.transition('google-calendar-create', 'enabled', ('calendar.events',))
        # #506: reads report authoritative connection state by owner name;
        # the retired registry lifecycle is refused rather than drafted.
        self.assertIn('Telegram · 연결 안 됨', self.run_one('연결 상태 알려줘')['response'])
        self.assertNotIn('google-drive-read', self.run_one("what's connected?")['response'])
        self.assertIn('대화에서 제공하지 않습니다', self.run_one('드라이브 연결 해제해줘')['response'])
        self.assertIn('대화에서 제공하지 않습니다', self.run_one('pause the calendar connection')['response'])
        self.assertEqual(self.store.config('settings_change_drafts', {}), {})

    def test_research_paraphrases_stay_on_the_conversation_route(self):
        for text, _ in PARAPHRASES[INTENT_RESEARCH]:
            with self.subTest(text=text):
                self.assertConversationRoute(self.run_one(text))

    # -- safety -------------------------------------------------------------
    def test_an_ambiguous_utterance_triggers_no_consequential_action(self):
        job = self.run_one('내일 회의 일정 잡고 작업공간에 저장한 자료도 찾아줘')
        self.assertEqual(job['status'], 'succeeded')
        self.assertIn('아무 작업도 실행하지 않았습니다', job['response'])
        self.assertEqual(self.store.config('personal_assistant_evidence', []), [])
        self.assertEqual(self.store.config('settings_change_drafts', {}), {})

    def test_a_natural_calendar_request_without_a_connector_refuses_and_creates_nothing(self):
        # This service has no Calendar connector at all.  The refusal names
        # the reason; it neither asks about the event nor drafts anything.
        for text in CALENDAR_PARAPHRASES:
            with self.subTest(text=text):
                job = self.run_one(text)
                self.assertEqual(job['status'], 'failed')
                self.assertIn('구성되어 있지 않습니다', job['error'])
        self.assertEqual(self.store.config('personal_assistant_evidence', []), [])
        self.assertEqual(self.store.config('calendar_create', {}), {})
        self.assertEqual(self.store.config('calendar_conversation', {}), {})

    def test_natural_delegation_never_reaches_the_orchestrator(self):
        for text in ('이 작업을 외부 에이전트에게 맡겨줘', 'delegate this task to the external agent'):
            with self.subTest(text=text):
                self.assertConversationRoute(self.run_one(text))
        self.assertEqual(self.store.config('personal_assistant_evidence', []), [])

    def test_drive_prose_keeps_reaching_the_shipped_picker_path(self):
        # The conversation route's own Drive preflight answers, exactly as it
        # did before this unit.  The orchestrator's unwired Drive seam - the
        # WU4 subject - is not reached.
        job = self.run_one('구글 드라이브 파일을 요약해줘')
        self.assertEqual(job['status'], 'failed')
        self.assertIn('Google Drive capability is not configured locally', job['error'])
        self.assertEqual(self.store.config('personal_assistant_evidence', []), [])

    def test_the_worker_never_supplies_a_model_suggestion_to_the_classifier(self):
        seen = []
        original = self.service.intent_classifier.classify

        def recording(text, model_suggestion=None, focus=None):
            seen.append(model_suggestion)
            return original(text, model_suggestion=model_suggestion, focus=focus)

        self.service.intent_classifier.classify = recording
        self.run_one('what do i know about aurora?', channel='telegram:fixture', chat_id=7)
        self.assertEqual(seen, [None])

    def test_topic_change_is_visible_to_the_worker_across_two_turns(self):
        self.run_one('작업공간에 저장한 파일 열어줘')
        self.assertEqual(self.service.conversation_focus.current()['intent'],
                         INTENT_WORKSPACE_SEARCH)
        decision = self.service.classify_intent('연결 상태 알려줘')
        self.assertEqual(decision.intent, INTENT_SETTINGS)
        self.assertTrue(decision.supersedes_previous)



class RecommendationRoutingTests(unittest.TestCase):
    """Retired mock capability recommendations never claim owner-usable availability."""

    TURN_35 = '10월에 제주 2박 3일 여행 가려는데 숙소랑 일정 추천해줘'
    INTERNAL_TAGS = ('private-document-research', 'specialist-research', 'local-specialist-processing')
    LEGACY_CAPABILITY_ASKS = (
        '전문가 조사에 연결할 만한 걸 알려줘',
        '내 문서 조사에 뭘 연결하면 좋을까',
        'which capability fits document research?',
        'what should i connect for specialist research?',
        '전문가 조사 추천해줘',
        'capability 하나 추천해줘',
        '/recommend specialist-research',
    )

    MODEL_ROUTE_ERROR = ServiceRoutingTests.MODEL_ROUTE_ERROR
    run_one = ServiceRoutingTests.run_one
    assertConversationRoute = ServiceRoutingTests.assertConversationRoute

    def setUp(self):
        ServiceRoutingTests.setUp(self)
        self.classifier = classifier()

    def assertNoInternalTag(self, text):
        for tag in self.INTERNAL_TAGS:
            self.assertNotIn(tag, text or '')

    def test_travel_and_product_recommendations_stay_on_the_conversation_route(self):
        for text in (self.TURN_35, '제주 맛집 추천해줘', '노이즈캔슬링 헤드폰 추천해줘',
                     '블루투스 연결 잘 되는 헤드폰 추천해줘', '세무 전문가 추천해줘',
                     'recommend a good hotel in jeju', 'any restaurant recommendation near gangnam?',
                     '공항 연결 추천해줘', '제주 공항에서 숙소까지 연결 추천해줘', '블루투스 연결 하나 추천해줘',
                     'hdmi 커넥터 추천해줘', '세무 전문가 연결 하나 추천해줘', '전문가 연결 추천해줘',
                     'recommend a usb-c connector cable', 'recommend a good integration test framework'):
            with self.subTest(text=text):
                decision = self.classifier.classify(text)
                self.assertEqual(decision.intent, INTENT_CONVERSATION)
                self.assertIsNone(decision.clarification)

    def test_retired_capability_catalogue_asks_use_only_the_ordinary_model_route(self):
        for text in self.LEGACY_CAPABILITY_ASKS:
            with self.subTest(text=text):
                decision = self.classifier.classify(text)
                self.assertIn(decision.intent, (INTENT_CONVERSATION, INTENT_RESEARCH))
                self.assertIsNone(decision.clarification)
                self.assertNotIn(decision.intent, CONSEQUENTIAL_INTENTS)
                job = self.run_one(text, channel='telegram:fixture', chat_id=7)
                self.assertConversationRoute(job)
                self.assertNoInternalTag(job.get('response'))
                self.assertNoInternalTag(job.get('error'))
        self.assertIsNone(self.store.config('capability_recommendation_audit'))

    def test_turn_35_reaches_the_same_route_as_the_itinerary_request(self):
        for text in (self.TURN_35, '제주 2박 3일 여행 일정 짜줘'):
            with self.subTest(text=text):
                job = self.run_one(text, channel='telegram:fixture', chat_id=7)
                self.assertConversationRoute(job)
                self.assertNoInternalTag(job.get('response'))
                self.assertNoInternalTag(job.get('error'))


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
