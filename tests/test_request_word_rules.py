"""#672: no word in the owner's request selects calendar, research or Drive.

Three pre-model request-word rules were removed: the calendar-create verb
table (which contained "book"), the research cue table ("google it") and
``AgentService.requests_drive_access`` ("google drive").  Calendar create and
Drive read are now selected only by the DecisionEngine's ``capability-need``
judgment; public research is the ordinary conversation route, where the Work
model loop chooses ``web_search`` itself.  An unavailable engine keeps the
turn on that ordinary route; it never falls back to a word list.

Evidence class: model-free.  A scripted DecisionEngine
(``FixtureDecisionEngine``) and a scripted model transport replace only the
providers; ``IntentClassifier``, ``AgentService.run_one`` and the Work loop run
unchanged.
"""
import json
import tempfile
import unittest
from pathlib import Path

from personal_agent import conversation_handoff
from personal_agent.conversation_handoff import (AUTHORITY_DEFAULT, AUTHORITY_RULE, CAPABILITY_NEEDS,
                                                 INTENT_CALENDAR_CREATE, INTENT_CONVERSATION,
                                                 INTENT_DRIVE_READ, ConversationJudgments, IntentClassifier)
from personal_agent.decision import UnavailableDecisionEngine
from personal_agent.providers import ModelAdapter
from personal_agent.quickstart_service import AgentService, workspace_search_request
from personal_agent.quickstart_store import QuickStore
from scripted_capability_need import capability_need_engine

#: Requests that carry a removed word but ask for none of the three capabilities.
REMOVED_WORDS_ONLY = ('책 book 추천해줘', 'book 한 권 추천해줘', 'what book should I read next?',
                      'google it', '그거 google it 해봐', '구글 드라이브가 뭐야?',
                      'google drive vs dropbox 비교해줘')
#: Former research cues: the loop, not a routing rule, chooses to search.
FORMER_RESEARCH_CUES = ('웹에서 최신 환율 찾아줘', 'look up the latest exchange rate', 'search the web for vendor reviews')
CALENDAR_REQUEST = '내일 오후 3시에 치과 일정 잡아줘'
DRIVE_REQUEST = '구글 드라이브에서 회의 자료 요약해줘'


def classifier(engine):
    return IntentClassifier(workspace_search=workspace_search_request, judge=ConversationJudgments(engine))


def capability_asks(engine):
    return [item[1].facts['owner_message'] for item in engine.asked
            if item[0] == 'choose' and item[1].purpose == 'capability-need']


class RemovedRulesTests(unittest.TestCase):
    def test_the_three_rules_are_gone(self):
        for name in ('_CALENDAR_VERBS', '_CALENDAR_OBJECTS', '_RESEARCH_CUES'):
            self.assertFalse(hasattr(conversation_handoff, name), name)
        for name in ('_rule_calendar', '_rule_research'):
            self.assertFalse(hasattr(IntentClassifier, name), name)
        self.assertFalse(hasattr(AgentService, 'requests_drive_access'))

    def test_a_removed_word_no_longer_routes_a_turn_on_its_own(self):
        for engine in (UnavailableDecisionEngine(), capability_need_engine({})):
            for text in (*REMOVED_WORDS_ONLY, *FORMER_RESEARCH_CUES):
                with self.subTest(engine=type(engine).__name__, text=text):
                    decision = classifier(engine).classify(text)
                    self.assertEqual(decision.intent, INTENT_CONVERSATION)
                    self.assertEqual(decision.authority, AUTHORITY_DEFAULT)
                    self.assertEqual(decision.cues, ())

    def test_the_judgment_declares_calendar_create_and_drive_read(self):
        self.assertIn(INTENT_CALENDAR_CREATE, CAPABILITY_NEEDS)
        self.assertIn(INTENT_DRIVE_READ, CAPABILITY_NEEDS)


class JudgedCapabilityTests(unittest.TestCase):
    def test_a_judged_calendar_request_carries_the_utterance_to_the_draft_path(self):
        engine = capability_need_engine({CALENDAR_REQUEST: INTENT_CALENDAR_CREATE})
        decision = classifier(engine).classify(CALENDAR_REQUEST)
        self.assertEqual(decision.intent, INTENT_CALENDAR_CREATE)
        self.assertEqual(decision.authority, AUTHORITY_RULE)
        self.assertEqual(decision.cues, ('judgment:capability-need',))
        self.assertEqual(decision.argument, CALENDAR_REQUEST)
        self.assertTrue(decision.consequential)
        self.assertTrue(decision.executes)
        self.assertEqual(capability_asks(engine), [CALENDAR_REQUEST])

    def test_a_judged_drive_request_reaches_drive_read(self):
        engine = capability_need_engine({DRIVE_REQUEST: INTENT_DRIVE_READ})
        decision = classifier(engine).classify(DRIVE_REQUEST)
        self.assertEqual(decision.intent, INTENT_DRIVE_READ)
        self.assertEqual(decision.cues, ('judgment:capability-need',))
        self.assertTrue(decision.executes)

    def test_an_unavailable_engine_keeps_the_ordinary_route_instead_of_matching_words(self):
        for text in (CALENDAR_REQUEST, DRIVE_REQUEST, 'book a dentist appointment tomorrow at 3pm'):
            with self.subTest(text=text):
                decision = classifier(UnavailableDecisionEngine()).classify(text)
                self.assertEqual(decision.intent, INTENT_CONVERSATION)
                self.assertEqual(decision.authority, AUTHORITY_DEFAULT)


class _DriveOffer:
    """The Drive handoff seam: disconnected, and it records the offer it makes."""

    def __init__(self):
        self.begun = []

    def status(self):
        return {'state': 'disconnected'}

    effective_status = status

    def begin(self, owner, job_id):
        self.begun.append((owner, job_id))
        return {'message': 'Google Drive 연결이 필요합니다.',
                'button': {'text': 'Google Drive 연결하기', 'url': 'https://connect.example.test/drive'}}


class ServiceRouteTests(unittest.TestCase):
    """Through the worker: the loop searches, a judged Drive request parks, "book" drafts nothing."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = QuickStore(Path(tmp.name) / 'data')
        self.script = []
        self.bodies = []
        self.telegram = []
        self.plans = []
        ready = [False]

        def transport(url, body, headers=None, timeout=60):
            if not isinstance(body, dict) or 'messages' not in body:
                self.telegram.append(body)
                return {'ok': True, 'result': {'message_id': 1}}
            names = [tool.get('function', {}).get('name') for tool in body.get('tools', [])]
            if 'agentos_connection_probe' in names:
                return {'message': {'content': '', 'tool_calls': [
                    {'function': {'name': 'agentos_connection_probe', 'arguments': {}}}]}}
            if not ready[0]:
                return {'message': {'content': 'ok'}}
            self.bodies.append(json.loads(json.dumps(body)))
            return {'message': self.script.pop(0) if self.script else {'content': '끝났습니다.'}}

        test = self

        class Network:
            def execute(self, plan):
                test.plans.append(plan)
                return {'tool': 'web_search', 'query': plan['query'], 'retrieved_at': 1,
                        'results': [{'title': 'USD/KRW', 'url': 'https://rates.example/usd-krw', 'snippet': '1,380'}],
                        'sources': ['https://rates.example/usd-krw']}

        self.drive = _DriveOffer()
        self.store.secret('telegram_token', 'test-token')
        self.service = AgentService(self.store, ModelAdapter(transport), transport, drive_web_oauth=self.drive)
        self.service.local_tools = Network()
        self.service.save_model({'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434',
                                 'model': 'test-model', 'api_key': ''})
        self.assertTrue(self.service.test_model()['ok'])
        ready[0] = True

    def run_turn(self, text, needs=None):
        self.service.use_decision_engine(capability_need_engine(needs or {}))
        job = self.store.enqueue(text, f'k-{len(self.store.jobs())}', channel='telegram:g', chat_id=42)
        self.assertTrue(self.service.run_one())
        return self.store.job(job)

    def test_book_in_a_book_request_creates_no_calendar_draft(self):
        # The loop asks once more before ending a turn with no finish claim (#657).
        self.script += [{'content': '이번 달 추천 도서는 다음과 같습니다.'}] * 2
        row = self.run_turn('책 book 추천해줘')
        self.assertEqual(row['status'], 'succeeded')
        self.assertEqual(row['response'], '이번 달 추천 도서는 다음과 같습니다.')
        self.assertEqual(self.service.conversation_focus.current()['intent'], INTENT_CONVERSATION)
        self.assertEqual(self.store.config('calendar_create', {}), {})
        self.assertEqual(self.store.config('calendar_conversation', {}), {})

    def test_a_research_request_reaches_web_search_through_the_loop(self):
        self.script += [{'tool_calls': [{'id': '1', 'function': {
                            'name': 'web_search', 'arguments': {'query': 'USD KRW exchange rate today'}}}]},
                        {'content': '오늘 USD/KRW는 1,380원입니다 (rates.example).'},
                        {'content': '오늘 USD/KRW는 1,380원입니다 (rates.example).'}]
        row = self.run_turn('google it: 오늘 환율')
        self.assertEqual([plan['tool'] for plan in self.plans], ['web_search'])
        self.assertEqual(self.plans[0]['query'], 'USD KRW exchange rate today')
        self.assertIn('web_search', [tool['function']['name'] for tool in self.bodies[0]['tools']])
        self.assertIn('1,380', row['response'])
        self.assertEqual(self.drive.begun, [])

    def test_a_judged_drive_request_parks_for_the_drive_connection(self):
        row = self.run_turn(DRIVE_REQUEST, {DRIVE_REQUEST: INTENT_DRIVE_READ})
        self.assertEqual(row['status'], 'awaiting_drive')
        self.assertEqual(self.drive.begun, [(42, row['id'])])
        offer = next(body for body in self.telegram if 'reply_markup' in body)
        self.assertEqual(offer['reply_markup']['inline_keyboard'][0][0]['text'], 'Google Drive 연결하기')
        self.assertEqual(self.bodies, [], 'no model turn runs before the connection')

    def test_the_words_google_drive_alone_do_not_park_anything(self):
        self.script += [{'content': 'Google Drive는 클라우드 저장 서비스입니다.'}] * 2
        row = self.run_turn('구글 드라이브가 뭐야?')
        self.assertEqual(row['status'], 'succeeded')
        self.assertEqual(self.drive.begun, [])
        self.assertFalse(any('reply_markup' in body for body in self.telegram))


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
