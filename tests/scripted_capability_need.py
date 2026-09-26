"""A scripted ``capability-need`` DecisionEngine for service tests (#672).

Calendar-create and Drive-read requests are selected by the DecisionEngine's
``capability-need`` judgment, never by request words.  A test that drives such
a request through the worker therefore scripts the judgment: it names the
exact owner utterances the fixture engine answers with a capability.  Every
other ``capability-need`` question is answered ``none-of-these``; any other
judgment is delegated to ``base`` (itself a ``DecisionEngine``) or is
unavailable.  This is a test double for a provider, not a routing rule.
"""
from personal_agent.decision import (OUTCOME_DECIDED, FixtureDecisionEngine, SelectionDecision,
                                     fixture_confidence)


def capability_need_engine(needs, base=None):
    """``needs`` maps an exact owner utterance to the capability key the engine selects.

    The mapping is read on every question, so a test may add an utterance later.
    """

    def choose(context, candidates, question):
        if context.purpose == 'capability-need':
            choice = needs.get(context.facts.get('owner_message'), 'none-of-these')
            return SelectionDecision(OUTCOME_DECIDED, choice, candidates, fixture_confidence())
        return base.choose(context, candidates, question) if base is not None else None

    def judge(context, proposition):
        return base.judge(context, proposition) if base is not None else None

    return FixtureDecisionEngine(judge=judge, choose=choose)
