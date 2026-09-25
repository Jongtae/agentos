"""PRESENCE-INTENT-01 / #597: capability-need and explicit-remember judgments.

Both are asked of the provider-neutral DecisionEngine instead of a cue table
or regex.  These tests pin the AgentOS side of that seam: what context is
sent, which turns are never sent, how policy reduces each answer, and that
an unavailable or unsure engine produces no handoff and no Memory write.

Evidence class: deterministic unit tests with ``FixtureDecisionEngine``.
No live provider judgment is claimed.
"""
import tempfile
import unittest
from pathlib import Path

from personal_agent.agent_runtime import Capabilities
from personal_agent.conversation_handoff import (CAPABILITY_JUDGMENT_MAX_CHARS, CAPABILITY_NEEDS,
                                                 INTENT_CALENDAR_CREATE, INTENT_CONVERSATION,
                                                 INTENT_MAIL_SEARCH, INTENT_NOTE_CREATE, INTENT_UNSUPPORTED,
                                                 JUDGMENT_NO, JUDGMENT_UNAVAILABLE, JUDGMENT_YES,
                                                 ConversationJudgments, IntentClassifier)
from personal_agent.decision import (OUTCOME_DECIDED, OUTCOME_TIMEOUT, BinaryDecision, FixtureDecisionEngine,
                                     SelectionDecision, UnavailableDecisionEngine, fixture_confidence)
from personal_agent.quickstart_service import workspace_search_request
from personal_agent.quickstart_store import QuickStore


def choosing(answers, probability=1.0):
    """A fixture engine answering the capability-need question from a table."""
    def choose(context, candidates, question):
        if context.purpose != 'capability-need':
            return None
        return SelectionDecision(OUTCOME_DECIDED, answers.get(context.facts['owner_message'], 'none-of-these'),
                                 candidates, fixture_confidence(probability))
    return FixtureDecisionEngine(choose=choose)


def classifier(engine):
    return IntentClassifier(workspace_search=workspace_search_request, judge=ConversationJudgments(engine))


def capability_asks(engine):
    return [item[1] for item in engine.asked if item[0] == 'choose' and item[1].purpose == 'capability-need']


class CapabilityNeedTests(unittest.TestCase):
    def test_a_cue_free_mail_read_is_routed_by_the_judgment_with_the_owners_own_words(self):
        engine = choosing({'집주인한테 답장 왔어?': INTENT_MAIL_SEARCH,
                           'did the landlord write back to me?': INTENT_MAIL_SEARCH})
        for text in ('집주인한테 답장 왔어?', 'did the landlord write back to me?'):
            with self.subTest(text=text):
                decision = classifier(engine).classify(text)
                self.assertEqual(decision.intent, INTENT_MAIL_SEARCH)
                self.assertTrue(decision.executes)
                self.assertEqual(decision.cues, ('judgment:capability-need',))
                # The argument comes from the owner's words, never from the engine.
                self.assertTrue(set(decision.argument.split()) <= set(text.rstrip('?').split()))
        [first, second] = capability_asks(engine)
        self.assertEqual(first.facts, {'owner_message': '집주인한테 답장 왔어?'})
        self.assertEqual(second.facts, {'owner_message': 'did the landlord write back to me?'})

    def test_the_engine_selects_only_declared_candidates(self):
        engine = choosing({})
        classifier(engine).classify('did the landlord write back to me?')
        [asked] = [item for item in engine.asked if item[0] == 'choose']
        self.assertEqual(asked[2], tuple(CAPABILITY_NEEDS))
        # An undeclared answer (e.g. an intent the engine invented) is not a selection.
        rogue = FixtureDecisionEngine(choose=lambda context, candidates, question: SelectionDecision(
            OUTCOME_DECIDED, INTENT_CALENDAR_CREATE, candidates, fixture_confidence()))
        self.assertEqual(classifier(rogue).classify('did the landlord write back to me?').intent,
                         INTENT_CONVERSATION)

    def test_a_judged_unsupported_capability_is_refused_truthfully(self):
        engine = choosing({'tell the landlord I agree': 'mail-send'})
        decision = classifier(engine).classify('tell the landlord I agree')
        self.assertEqual(decision.intent, INTENT_UNSUPPORTED)
        self.assertFalse(decision.executes)
        self.assertIn('보내지 않았습니다', decision.clarification)

    def test_unavailable_unsure_or_none_of_these_stays_ordinary_conversation(self):
        text = 'did the landlord write back to me?'
        timeout = FixtureDecisionEngine(choose=lambda context, candidates, question: SelectionDecision(
            OUTCOME_TIMEOUT, candidates=candidates))
        for engine in (UnavailableDecisionEngine(), timeout, choosing({text: INTENT_MAIL_SEARCH}, probability=0.3),
                       choosing({})):
            with self.subTest(engine=engine):
                self.assertEqual(classifier(engine).classify(text).intent, INTENT_CONVERSATION)

    def test_locally_claimed_turns_are_never_sent_to_the_engine(self):
        engine = choosing({})
        judged = classifier(engine)
        self.assertEqual(judged.classify('집주인 연락처 메모해줘').intent, INTENT_NOTE_CREATE)
        self.assertEqual(judged.classify('/notes').intent, 'note-list')
        # A pending calendar draft claims cue-free follow-ups without a judgment.
        self.assertEqual(judged.classify('오후 4시', focus={'calendar_pending': True}).intent,
                         INTENT_CALENDAR_CREATE)
        # A long pasted text is answered by conversation, not sent to the judgment too.
        self.assertEqual(judged.classify('가' * (CAPABILITY_JUDGMENT_MAX_CHARS + 1)).intent, INTENT_CONVERSATION)
        self.assertEqual(capability_asks(engine), [])


class ExplicitMemoryRequestTests(unittest.TestCase):
    def judge(self, answer, probability=1.0):
        engine = FixtureDecisionEngine(judge=lambda context, proposition: BinaryDecision(
            OUTCOME_DECIDED, answer, fixture_confidence(probability)))
        return engine, ConversationJudgments(engine)

    def test_policy_reduces_the_judgment_to_yes_no_or_unavailable(self):
        self.assertEqual(self.judge(True)[1].explicit_memory_request('잊지 마: 오후 회의').outcome, JUDGMENT_YES)
        self.assertEqual(self.judge(False)[1].explicit_memory_request('기억하지 마').outcome, JUDGMENT_NO)
        self.assertEqual(self.judge(True, 0.5)[1].explicit_memory_request('잊지 마').outcome, JUDGMENT_UNAVAILABLE)
        self.assertEqual(ConversationJudgments().explicit_memory_request('remember: tea').outcome,
                         JUDGMENT_UNAVAILABLE)
        engine, judgments = self.judge(True)
        judgments.explicit_memory_request('keep in mind I like tea')
        [(_kind, context, _proposition)] = engine.asked
        self.assertEqual((context.purpose, context.facts), ('explicit-memory-request',
                                                           {'owner_message': 'keep in mind I like tea'}))


class LazyMemoryApprovalTests(unittest.TestCase):
    """``Capabilities`` asks for the owner-request approval once, only on a proposed write."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = QuickStore(Path(temp.name) / 'data')
        self.job = self.store.enqueue('keep in mind that I like green tea', 'k1')
        self.asked = 0

    def capabilities(self, approve):
        def resolve():
            self.asked += 1
            return self.store.issue_memory_approval(self.job, 'keep in mind that I like green tea') if approve else None
        return Capabilities(self.store, None, {}, '', self.job, lambda *a, **k: None, memory_request=resolve)

    def test_a_judged_request_covers_only_the_owner_stated_value(self):
        tools = self.capabilities(True)
        self.assertEqual(self.asked, 0, 'nothing is judged before a write is proposed')
        self.assertIsNone(tools.memory_write_refusal('drink', 'green tea'))
        self.assertEqual(tools.memory_write_refusal('drink', 'coffee'), 'value-not-in-owner-request')
        self.assertEqual(self.asked, 1, 'judged once per Work')

    def test_no_judged_request_means_every_write_stays_a_candidate(self):
        tools = self.capabilities(False)
        self.assertEqual(tools.memory_write_refusal('drink', 'green tea'), 'no-owner-memory-request')
        self.assertEqual(tools.memory_write_refusal('drink', 'green tea'), 'no-owner-memory-request')
        self.assertEqual(self.asked, 1)


if __name__ == '__main__':
    unittest.main()
