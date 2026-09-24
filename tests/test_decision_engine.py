"""PRESENCE-DEC-01 / #417: the provider-neutral decision layer.

Evidence class: deterministic unit tests and recorded provider response
shapes through a fake transport.  No live provider is called; nothing here
claims that any provider is calibrated or available.
"""
import json
import tempfile
import unittest

from personal_agent.conversation_handoff import (JUDGMENT_NO, JUDGMENT_UNAVAILABLE, JUDGMENT_YES,
                                                 ConversationJudgments)
from personal_agent.decision import (DEFAULT_DECISION_MODEL, MAX_CONTEXT_CHARS, NO_CANDIDATE,
                                     OUTCOME_CANCELLED, OUTCOME_DECIDED, OUTCOME_MALFORMED, OUTCOME_REJECTED, OUTCOME_TIMEOUT,
                                     OUTCOME_UNAVAILABLE, BinaryDecision, DecisionContext,
                                     DecisionPolicy, FixtureDecisionEngine, ModelDecisionEngine,
                                     ScoreDecision, SelectionDecision, UnavailableDecisionEngine,
                                     fixture_confidence)
from personal_agent.providers import ModelAdapter, ProviderError
from personal_agent.quickstart_service import AgentService
from personal_agent.quickstart_store import QuickStore

OPENAI = {'provider': 'openai', 'endpoint': 'https://api.openai.com/v1', 'model': DEFAULT_DECISION_MODEL}
ANTHROPIC = {'provider': 'anthropic', 'endpoint': 'https://api.anthropic.com', 'model': 'claude-x'}


def openai_tool_reply(arguments, model='gpt-4o-mini-2024-07-18'):
    """The recorded shape of an OpenAI-compatible tool call."""
    return {'model': model, 'choices': [{'message': {
        'role': 'assistant', 'content': None,
        'tool_calls': [{'id': 'call_1', 'type': 'function',
                        'function': {'name': 'decide', 'arguments': json.dumps(arguments)}}]}}]}


class ScriptedTransport:
    """A fake provider transport: replies in order, or raises."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, url, body, headers=None, timeout=60):
        self.calls.append({'url': url, 'body': body, 'headers': headers or {}, 'timeout': timeout})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def engine_for(transport, route=lambda: (dict(OPENAI), 'sk-test'), **kwargs):
    audit = []
    engine = ModelDecisionEngine(ModelAdapter(transport), route, audit=audit.append, **kwargs)
    return engine, audit


class ContractTests(unittest.TestCase):
    """Types and the two non-provider engines."""

    def test_only_a_decided_outcome_carries_an_answer(self):
        self.assertIsNone(BinaryDecision(OUTCOME_UNAVAILABLE, True).answer)
        self.assertIsNone(SelectionDecision(OUTCOME_TIMEOUT, 'a', ('a',)).choice)
        self.assertIsNone(ScoreDecision(OUTCOME_MALFORMED, 0.5).score)
        self.assertTrue(BinaryDecision(OUTCOME_DECIDED, False, fixture_confidence()).decided)

    def test_the_unavailable_engine_never_answers(self):
        engine = UnavailableDecisionEngine()
        context = DecisionContext('test', {'a': 'b'})
        self.assertEqual(engine.judge(context, 'p').outcome, OUTCOME_UNAVAILABLE)
        self.assertEqual(engine.choose(context, ('x',), 'q').outcome, OUTCOME_UNAVAILABLE)
        self.assertEqual(engine.score(context, 'q').outcome, OUTCOME_UNAVAILABLE)

    def test_the_fixture_engine_records_questions_and_defaults_to_unavailable(self):
        engine = FixtureDecisionEngine(judge=lambda c, p: BinaryDecision(OUTCOME_DECIDED, True, fixture_confidence()))
        context = DecisionContext('test')
        self.assertTrue(engine.judge(context, 'p').answer)
        self.assertEqual(engine.choose(context, ('x',), 'q').outcome, OUTCOME_UNAVAILABLE)
        self.assertEqual([item[0] for item in engine.asked], ['judge', 'choose'])

    def test_context_holds_only_short_attributable_strings(self):
        context = DecisionContext('why', {'owner_message': '안녕', 'n': 3})
        self.assertEqual(context.render(), 'owner_message: 안녕\nn: 3')


class PolicyTests(unittest.TestCase):
    """Thresholds are AgentOS policy; the provider's confidence is only input."""

    def test_binary_needs_a_decided_answer_and_enough_confidence(self):
        policy = DecisionPolicy(binary_threshold=0.75)
        self.assertEqual(policy.binary(BinaryDecision(OUTCOME_DECIDED, True, fixture_confidence(0.9))), 'yes')
        self.assertEqual(policy.binary(BinaryDecision(OUTCOME_DECIDED, False, fixture_confidence(0.75))), 'no')
        self.assertEqual(policy.binary(BinaryDecision(OUTCOME_DECIDED, True, fixture_confidence(0.6))), 'unknown')
        self.assertEqual(policy.binary(BinaryDecision(OUTCOME_DECIDED, True)), 'unknown', 'no probability is not confident')
        for outcome in (OUTCOME_UNAVAILABLE, OUTCOME_TIMEOUT, OUTCOME_MALFORMED, OUTCOME_REJECTED,
                        OUTCOME_CANCELLED):
            self.assertEqual(policy.binary(BinaryDecision(outcome, True, fixture_confidence())), 'unknown', outcome)
        self.assertEqual(policy.binary(BinaryDecision(OUTCOME_DECIDED, True, fixture_confidence(True))), 'unknown',
                         'a boolean is not a probability')

    def test_selection_admits_only_a_declared_candidate(self):
        policy = DecisionPolicy(selection_threshold=0.6)
        candidates = ('a', 'b')
        self.assertEqual(policy.selection(SelectionDecision(OUTCOME_DECIDED, 'a', candidates, fixture_confidence(0.8))), 'a')
        self.assertIsNone(policy.selection(SelectionDecision(OUTCOME_DECIDED, NO_CANDIDATE, candidates, fixture_confidence())))
        self.assertIsNone(policy.selection(SelectionDecision(OUTCOME_DECIDED, 'zzz', candidates, fixture_confidence())))
        self.assertIsNone(policy.selection(SelectionDecision(OUTCOME_DECIDED, 'a', candidates, fixture_confidence(0.2))))


class ModelEngineTests(unittest.TestCase):
    """The production adapter over the repository's ModelAdapter tool-call shape."""

    def context(self):
        return DecisionContext('parked-work-withdrawal', {'waiting_connection': 'Gmail', 'owner_message': '취소해줘'})

    def test_a_valid_tool_call_becomes_a_decided_judgment_with_provider_identity(self):
        transport = ScriptedTransport(openai_tool_reply({'answer': True, 'confidence': 0.93}))
        engine, audit = engine_for(transport, timeout=7)
        decision = engine.judge(self.context(), 'withdraws?')
        self.assertEqual(decision.outcome, OUTCOME_DECIDED)
        self.assertTrue(decision.answer)
        self.assertEqual(decision.confidence.probability, 0.93)
        self.assertEqual((decision.confidence.provider, decision.confidence.model), ('openai', DEFAULT_DECISION_MODEL))
        self.assertEqual(decision.confidence.observed_model, 'gpt-4o-mini-2024-07-18')
        # One call, to the pinned endpoint, forced onto the decide tool, with the decision timeout.
        call = transport.calls[0]
        self.assertEqual(call['url'], 'https://api.openai.com/v1/chat/completions')
        self.assertEqual(call['body']['tool_choice'], 'required')
        self.assertEqual(call['body']['tools'][0]['function']['name'], 'decide')
        self.assertEqual(call['timeout'], 7)
        self.assertEqual(call['headers'], {'Authorization': 'Bearer sk-test'})
        # Only the rendered context and the question travel.
        prompt = call['body']['messages'][-1]['content']
        self.assertIn('owner_message: 취소해줘', prompt)
        self.assertIn('waiting_connection: Gmail', prompt)
        # The audit names outcome and identity, never reasoning text.
        self.assertEqual(audit[0]['outcome'], OUTCOME_DECIDED)
        self.assertIs(audit[0]['answer'], True)
        self.assertEqual(audit[0]['observed_model'], 'gpt-4o-mini-2024-07-18')
        self.assertEqual(set(audit[0]), {'at', 'kind', 'purpose', 'outcome', 'answer', 'confidence', 'provider',
                                         'model', 'observed_model', 'elapsed_seconds'})

    def test_choose_and_score_validate_the_provider_answer_against_the_declared_range(self):
        transport = ScriptedTransport(openai_tool_reply({'choice': 'b', 'confidence': 0.7}),
                                      openai_tool_reply({'choice': 'not-offered', 'confidence': 0.7}),
                                      openai_tool_reply({'score': 4, 'confidence': 0.8}),
                                      openai_tool_reply({'score': 11, 'confidence': 0.8}))
        engine, _audit = engine_for(transport)
        chosen = engine.choose(self.context(), ('a', 'b'), 'which?')
        self.assertEqual((chosen.outcome, chosen.choice), (OUTCOME_DECIDED, 'b'))
        self.assertEqual(transport.calls[0]['body']['tools'][0]['function']['parameters']['properties']['choice']['enum'],
                         ['a', 'b', NO_CANDIDATE])
        self.assertEqual(engine.choose(self.context(), ('a', 'b'), 'which?').outcome, OUTCOME_MALFORMED)
        scored = engine.score(self.context(), 'how?', (0, 10))
        self.assertEqual((scored.outcome, scored.score), (OUTCOME_DECIDED, 4))
        self.assertEqual(engine.score(self.context(), 'how?', (0, 10)).outcome, OUTCOME_MALFORMED)

    def test_every_failure_is_an_explicit_outcome_and_none_becomes_an_answer(self):
        cases = (
            ('no tool call', {'choices': [{'message': {'role': 'assistant', 'content': 'yes'}}]}, OUTCOME_MALFORMED),
            ('bad json', {'choices': [{'message': {'role': 'assistant', 'tool_calls': [
                {'id': '1', 'type': 'function', 'function': {'name': 'decide', 'arguments': '{not json'}}]}}]}, OUTCOME_MALFORMED),
            ('other tool', {'choices': [{'message': {'role': 'assistant', 'tool_calls': [
                {'id': '1', 'type': 'function', 'function': {'name': 'other', 'arguments': '{}'}}]}}]}, OUTCOME_MALFORMED),
            ('non-boolean answer', openai_tool_reply({'answer': 'yes', 'confidence': 0.9}), OUTCOME_MALFORMED),
            ('confidence out of range', openai_tool_reply({'answer': True, 'confidence': 1.7}), OUTCOME_MALFORMED),
            ('timeout', ProviderError('timed out', status='timeout'), OUTCOME_TIMEOUT),
            ('rate limited', ProviderError('429', status=429), OUTCOME_UNAVAILABLE),
            ('server error', ProviderError('500', status=500), OUTCOME_UNAVAILABLE),
            ('request rejected', ProviderError('400', status=400), OUTCOME_REJECTED),
            ('unreachable', ProviderError('down'), OUTCOME_UNAVAILABLE),
        )
        policy = DecisionPolicy()
        for label, reply, expected in cases:
            with self.subTest(case=label):
                engine, audit = engine_for(ScriptedTransport(reply))
                decision = engine.judge(self.context(), 'withdraws?')
                self.assertEqual(decision.outcome, expected)
                self.assertIsNone(decision.answer)
                self.assertEqual(policy.binary(decision), 'unknown')
                self.assertEqual(audit[0]['outcome'], expected)
                self.assertIsNone(audit[0]['answer'])

    def test_low_confidence_is_decided_by_the_provider_but_unknown_to_policy(self):
        engine, _audit = engine_for(ScriptedTransport(openai_tool_reply({'answer': True, 'confidence': 0.4})))
        decision = engine.judge(self.context(), 'withdraws?')
        self.assertEqual(decision.outcome, OUTCOME_DECIDED)
        self.assertEqual(DecisionPolicy().binary(decision), 'unknown')

    def test_no_route_or_cancelled_or_oversized_context_makes_no_call(self):
        transport = ScriptedTransport()
        engine, audit = engine_for(transport, route=lambda: None)
        self.assertEqual(engine.judge(self.context(), 'p').outcome, OUTCOME_UNAVAILABLE)
        engine, audit = engine_for(transport)
        cancelled = DecisionContext('x', {'owner_message': 'a'}, cancelled=lambda: True)
        self.assertEqual(engine.judge(cancelled, 'p').outcome, OUTCOME_CANCELLED)
        huge = DecisionContext('x', {'owner_message': 'a' * (MAX_CONTEXT_CHARS + 1)})
        self.assertEqual(engine.judge(huge, 'p').outcome, OUTCOME_REJECTED)
        self.assertEqual(transport.calls, [])
        self.assertEqual([row['outcome'] for row in audit], [OUTCOME_CANCELLED, OUTCOME_REJECTED])

    def test_a_key_requiring_provider_without_a_key_is_unavailable_without_a_call(self):
        transport = ScriptedTransport()
        engine, _audit = engine_for(transport, route=lambda: (dict(ANTHROPIC), ''))
        self.assertEqual(engine.judge(self.context(), 'p').outcome, OUTCOME_UNAVAILABLE)
        self.assertEqual(transport.calls, [])

    def test_the_same_judgment_runs_on_another_provider_without_engine_changes(self):
        # Provider replacement: the Anthropic tool-use shape through the same engine.
        reply = {'model': 'claude-x', 'content': [{'type': 'tool_use', 'id': 't1', 'name': 'decide',
                                                   'input': {'answer': False, 'confidence': 0.88}}]}
        transport = ScriptedTransport(reply)
        engine, _audit = engine_for(transport, route=lambda: (dict(ANTHROPIC), 'ak-test'))
        decision = engine.judge(self.context(), 'withdraws?')
        self.assertEqual((decision.outcome, decision.answer, decision.confidence.provider), (OUTCOME_DECIDED, False, 'anthropic'))
        self.assertEqual(transport.calls[0]['url'], 'https://api.anthropic.com/v1/messages')
        self.assertEqual(transport.calls[0]['body']['tool_choice'], {'type': 'any'})


class ConversationJudgmentTests(unittest.TestCase):
    """The two conversation questions reduce engine decisions through policy."""

    def test_withdrawal_reduces_to_yes_no_unavailable(self):
        yes = FixtureDecisionEngine(judge=lambda c, p: BinaryDecision(OUTCOME_DECIDED, True, fixture_confidence(0.9)))
        no = FixtureDecisionEngine(judge=lambda c, p: BinaryDecision(OUTCOME_DECIDED, False, fixture_confidence(0.9)))
        unsure = FixtureDecisionEngine(judge=lambda c, p: BinaryDecision(OUTCOME_DECIDED, True, fixture_confidence(0.3)))
        self.assertEqual(ConversationJudgments(yes).parked_work_withdrawn('취소', ('google-gmail',)).outcome, JUDGMENT_YES)
        self.assertEqual(ConversationJudgments(no).parked_work_withdrawn('안녕', ('google-gmail',)).outcome, JUDGMENT_NO)
        self.assertEqual(ConversationJudgments(unsure).parked_work_withdrawn('음', ('google-gmail',)).outcome, JUDGMENT_UNAVAILABLE)
        self.assertEqual(ConversationJudgments().parked_work_withdrawn('취소', ('google-gmail',)).outcome, JUDGMENT_UNAVAILABLE)
        # The context carries the utterance and a connector label, nothing else.
        context = yes.asked[0][1]
        self.assertEqual(set(context.facts), {'waiting_connection', 'owner_message'})
        self.assertEqual(context.facts['owner_message'], '취소')

    def test_recommendation_yields_a_reviewed_outcome_or_no(self):
        pick = FixtureDecisionEngine(choose=lambda c, cands, q: SelectionDecision(OUTCOME_DECIDED, 'specialist-research', cands, fixture_confidence()))
        none = FixtureDecisionEngine(choose=lambda c, cands, q: SelectionDecision(OUTCOME_DECIDED, NO_CANDIDATE, cands, fixture_confidence()))
        judged = ConversationJudgments(pick).capability_recommendation('전문가 조사 추천해줘')
        self.assertEqual((judged.outcome, judged.value), (JUDGMENT_YES, 'specialist-research'))
        self.assertEqual(ConversationJudgments(none).capability_recommendation('맛집 추천해줘').outcome, JUDGMENT_NO)
        unsure = FixtureDecisionEngine(choose=lambda c, cands, q: SelectionDecision(OUTCOME_DECIDED, 'specialist-research', cands, fixture_confidence(0.2)))
        self.assertEqual(ConversationJudgments(unsure).capability_recommendation('전문가 조사 추천해줘').outcome,
                         JUDGMENT_UNAVAILABLE, 'not confident enough is unknown, not a confident no')
        self.assertEqual(ConversationJudgments().capability_recommendation('맛집 추천해줘').outcome, JUDGMENT_UNAVAILABLE)
        self.assertEqual(pick.asked[0][2], ('private-document-research', 'specialist-research', 'local-specialist-processing'))


class ServiceRouteTests(unittest.TestCase):
    """Provider selection is deterministic configuration owned by the service."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = QuickStore(self.temp.name)

        def transport(url, body, headers=None, timeout=60):
            raise AssertionError('no call expected: ' + url)

        self.service = AgentService(self.store, ModelAdapter(transport), transport)

    def test_nothing_configured_means_unavailable_and_no_call(self):
        self.assertIsNone(self.service.decision_route())
        self.assertEqual(self.service.decision_route_status()['source'], 'unavailable')
        self.assertEqual(self.service.decision_engine.judge(DecisionContext('x', {'m': 'a'}), 'p').outcome, OUTCOME_UNAVAILABLE)

    def test_the_default_is_gpt_4o_mini_only_when_the_owner_route_is_openai_with_a_key(self):
        self.store.put('model', {'provider': 'anthropic', 'endpoint': 'https://api.anthropic.com', 'model': 'claude-x'})
        self.store.secret('model_key', 'ak-owner')
        self.assertIsNone(self.service.decision_route(), 'another owner route is not silently reused')
        self.store.put('model', {'provider': 'openai', 'endpoint': 'https://api.openai.com/v1', 'model': 'gpt-5'})
        self.store.secret('model_key', 'sk-owner')
        config, key = self.service.decision_route()
        self.assertEqual((config['provider'], config['model'], key), ('openai', DEFAULT_DECISION_MODEL, 'sk-owner'))
        status = self.service.decision_route_status()
        self.assertEqual(status, {'provider': 'openai', 'model': DEFAULT_DECISION_MODEL, 'source': 'default-openai'})
        self.assertEqual(self.service.settings()['decision_model'], status)

    def test_an_explicit_decision_model_wins_and_needs_its_own_key(self):
        self.store.put('decision_model', {'provider': 'compatible', 'endpoint': 'https://router.example.test/v1', 'model': 'small'})
        self.assertIsNone(self.service.decision_route(), 'a key-requiring provider without a key is unavailable')
        self.store.secret('decision_model_key', 'rk-1')
        config, key = self.service.decision_route()
        self.assertEqual((config['model'], key), ('small', 'rk-1'))
        self.assertEqual(self.service.decision_route_status()['source'], 'explicit')
        self.store.put('decision_model', {'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434', 'model': 'local'})
        self.assertEqual(self.service.decision_route(), ({'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434', 'model': 'local'}, ''),
                         'a local provider needs no key, and the earlier explicit key must not travel to it')
        self.store.put('decision_model', {'provider': 'openai', 'endpoint': 'https://elsewhere.test', 'model': 'x'})
        self.assertIsNone(self.service.decision_route(), 'an invalid configuration is unavailable, not guessed')

    def test_the_service_engine_is_replaceable_without_touching_policy_code(self):
        fixture = FixtureDecisionEngine()
        self.service.use_decision_engine(fixture)
        self.assertIs(self.service.decision_judge.engine, fixture)
        self.service.classify_intent('전문가 조사 추천해줘')
        self.assertEqual(fixture.asked[0][0], 'choose')


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
