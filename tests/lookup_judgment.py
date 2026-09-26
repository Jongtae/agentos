"""Shared test double for the #605 public-lookup sensitivity judgment.

Since #605 R1/R4 every public lookup that includes content of the owner's
current message is judged by the owner's DecisionEngine, and with no usable
judgment no current-message content is sent.  Tests that are about something
else (research outcomes, bridge mechanics, projection) run as if the owner's
DecisionEngine judged every term ordinary.  The judgment itself is tested in
tests/test_public_private_composition.py with a fixture engine.
"""
from unittest import mock

from personal_agent.conversation_handoff import JUDGMENT_NO, ConversationJudgments, Judgment


def _ordinary(self, utterance, terms):
    return Judgment(JUDGMENT_NO, value=frozenset(), source='fixture')


def ordinary_lookup_judgment(cls):
    """Class decorator: every lookup term is judged ordinary for this class's tests."""
    original = cls.setUp

    def setUp(self):
        patcher = mock.patch.object(ConversationJudgments, 'lookup_term_sensitivity', _ordinary)
        patcher.start()
        self.addCleanup(patcher.stop)
        original(self)

    cls.setUp = setUp
    return cls
