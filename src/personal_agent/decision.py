"""Provider-neutral decision layer (PRESENCE-DEC-01 / #417).

AgentOS owns this contract; providers only implement it.  A decision is a
bounded *judgment* - "does this turn withdraw the parked request?", "which
of these declared candidates fits?" - together with an explicit account of
how sure the provider was.  It is never authority: what may happen next is
decided by deterministic AgentOS policy (`DecisionPolicy` here, Grants,
approvals and effect rules elsewhere), which a provider cannot bypass no
matter how confident it is.

Every engine answers with an *outcome*.  Only ``decided`` carries an
answer; every other outcome is an explicit non-answer that callers must
handle.  Nothing in this module falls back to phrase or regex rules when a
provider cannot answer; the declared fallback is to say so.

See docs/decision-layer.en.md.  Vendor SDK types and vocabulary stay out of
this module: the model adapter is reached only through the repository's
existing ``ModelAdapter`` tool-call shape.
"""
import json
import time

from .providers import ProviderError, validate_model

# --- outcomes ----------------------------------------------------------------
OUTCOME_DECIDED = 'decided'
OUTCOME_UNAVAILABLE = 'provider_unavailable'
OUTCOME_TIMEOUT = 'timeout'
OUTCOME_MALFORMED = 'malformed'
OUTCOME_REJECTED = 'context_rejected'
OUTCOME_CANCELLED = 'cancelled'

#: Low confidence is not an engine outcome: a provider answers and reports
#: its probability, and `DecisionPolicy` decides that the answer is unknown.
NON_ANSWERS = frozenset({OUTCOME_UNAVAILABLE, OUTCOME_TIMEOUT, OUTCOME_MALFORMED,
                         OUTCOME_REJECTED, OUTCOME_CANCELLED})

#: A DecisionContext larger than this is rejected before any provider call.
#: Decisions are bounded questions over a few attributable facts, not a
#: channel for history, Memory or documents.
MAX_CONTEXT_CHARS = 6000

#: The selection candidate a provider may pick to say "none of these".
NO_CANDIDATE = 'none-of-these'


class DecisionContext:
    """The minimal, attributable facts one bounded question is asked over.

    ``facts`` maps short labels to short strings supplied by the caller.  The
    caller decides what is covered for the decision provider; this class
    only bounds the size and renders it.  ``cancelled`` is an optional
    callable consulted before a provider is contacted.
    """

    __slots__ = ('purpose', 'facts', 'work_id', 'cancelled')

    def __init__(self, purpose, facts=None, *, work_id=None, cancelled=None):
        self.purpose = str(purpose)
        self.facts = {str(k): str(v) for k, v in (facts or {}).items()}
        self.work_id = work_id
        self.cancelled = cancelled

    def render(self):
        return '\n'.join(f'{label}: {value}' for label, value in self.facts.items())

    def is_cancelled(self):
        return bool(self.cancelled and self.cancelled())


class DecisionConfidence:
    """How sure the provider said it was, and which provider that was.

    ``probability`` is the provider's own number; calibration is a property
    measured per provider, never assumed here.  ``model`` is the configured
    identity and ``observed_model`` what the provider reported, kept apart
    so neither is presented as the other.
    """

    __slots__ = ('probability', 'provider', 'model', 'observed_model', 'elapsed_seconds')

    def __init__(self, probability=None, *, provider='', model='', observed_model='', elapsed_seconds=None):
        self.probability = probability
        self.provider, self.model, self.observed_model = provider, model, observed_model
        self.elapsed_seconds = elapsed_seconds


class _Decision:
    __slots__ = ('outcome', 'confidence')

    def __init__(self, outcome, confidence=None):
        self.outcome = outcome
        self.confidence = confidence or DecisionConfidence()

    @property
    def decided(self):
        return self.outcome == OUTCOME_DECIDED


class BinaryDecision(_Decision):
    __slots__ = ('answer',)

    def __init__(self, outcome, answer=None, confidence=None):
        super().__init__(outcome, confidence)
        self.answer = answer if outcome == OUTCOME_DECIDED else None


class SelectionDecision(_Decision):
    __slots__ = ('choice', 'candidates')

    def __init__(self, outcome, choice=None, candidates=(), confidence=None):
        super().__init__(outcome, confidence)
        self.candidates = tuple(candidates)
        self.choice = choice if outcome == OUTCOME_DECIDED else None


class ScoreDecision(_Decision):
    __slots__ = ('score', 'scale')

    def __init__(self, outcome, score=None, scale=(0, 1), confidence=None):
        super().__init__(outcome, confidence)
        self.scale = tuple(scale)
        self.score = score if outcome == OUTCOME_DECIDED else None


# --- the contract ------------------------------------------------------------
class DecisionEngine:
    """Provider-independent judgment interface.  Implementations answer;
    they never act."""

    def judge(self, context, proposition):
        """Is ``proposition`` true of ``context``?  -> BinaryDecision"""
        raise NotImplementedError

    def choose(self, context, candidates, question):
        """Which of ``candidates`` answers ``question``?  -> SelectionDecision.
        ``NO_CANDIDATE`` is always an admissible choice."""
        raise NotImplementedError

    def score(self, context, question, scale=(0, 1)):
        """Rate ``context`` against ``question`` on ``scale``.  -> ScoreDecision"""
        raise NotImplementedError


class UnavailableDecisionEngine(DecisionEngine):
    """No provider: every judgment is explicitly unavailable."""

    def judge(self, context, proposition):
        return BinaryDecision(OUTCOME_UNAVAILABLE)

    def choose(self, context, candidates, question):
        return SelectionDecision(OUTCOME_UNAVAILABLE, candidates=candidates)

    def score(self, context, question, scale=(0, 1)):
        return ScoreDecision(OUTCOME_UNAVAILABLE, scale=scale)


class FixtureDecisionEngine(DecisionEngine):
    """Scripted answers for tests and fixture-backed acceptance.

    Each script is a callable receiving the same arguments as the contract
    method and returning a decision, or ``None`` for unavailable.  It is a
    test double for a provider, not a production fallback.
    """

    def __init__(self, judge=None, choose=None, score=None):
        self._judge, self._choose, self._score = judge, choose, score
        self.asked = []

    def judge(self, context, proposition):
        self.asked.append(('judge', context, proposition))
        result = self._judge(context, proposition) if self._judge else None
        return result if result is not None else BinaryDecision(OUTCOME_UNAVAILABLE)

    def choose(self, context, candidates, question):
        self.asked.append(('choose', context, tuple(candidates), question))
        result = self._choose(context, candidates, question) if self._choose else None
        return result if result is not None else SelectionDecision(OUTCOME_UNAVAILABLE, candidates=candidates)

    def score(self, context, question, scale=(0, 1)):
        self.asked.append(('score', context, question, scale))
        result = self._score(context, question, scale) if self._score else None
        return result if result is not None else ScoreDecision(OUTCOME_UNAVAILABLE, scale=scale)


def fixture_confidence(probability=1.0):
    return DecisionConfidence(probability, provider='fixture', model='fixture', observed_model='fixture')


# --- deterministic policy ----------------------------------------------------
class DecisionPolicy:
    """AgentOS-owned thresholds.  Turns a decision into what policy may act on.

    Thresholds live here, in configuration AgentOS controls, never in a
    provider adapter.  A missing probability counts as not confident.
    """

    def __init__(self, binary_threshold=0.75, selection_threshold=0.6):
        self.binary_threshold = float(binary_threshold)
        self.selection_threshold = float(selection_threshold)

    @staticmethod
    def _confident(decision, threshold):
        probability = decision.confidence.probability
        return (isinstance(probability, (int, float)) and not isinstance(probability, bool)
                and probability >= threshold)

    def confident_selection(self, decision):
        """True when a decided selection met the threshold (whatever was chosen)."""
        return decision.decided and self._confident(decision, self.selection_threshold)

    def binary(self, decision):
        """'yes' / 'no' when decided with enough confidence, else 'unknown'."""
        if not decision.decided or decision.answer is None or not self._confident(decision, self.binary_threshold):
            return 'unknown'
        return 'yes' if decision.answer else 'no'

    def selection(self, decision):
        """The chosen candidate, or None (including an explicit none-of-these)."""
        if not decision.decided or not self._confident(decision, self.selection_threshold):
            return None
        if decision.choice == NO_CANDIDATE or decision.choice not in decision.candidates:
            return None
        return decision.choice


# --- the model-backed adapter ------------------------------------------------
DEFAULT_DECISION_MODEL = 'gpt-4o-mini'
DEFAULT_DECISION_PROVIDER = {'provider': 'openai', 'endpoint': 'https://api.openai.com/v1',
                             'model': DEFAULT_DECISION_MODEL}

_SYSTEM = ('You make one bounded judgment for a personal assistant. Read the facts, answer '
           'only by calling the `decide` tool, and report how confident you are as a '
           'probability between 0 and 1. Do not take any action and do not add commentary.')

_DECIDE_TOOL = 'decide'


class ModelDecisionEngine(DecisionEngine):
    """The production adapter: one model tool call per judgment.

    ``adapter`` is the repository's ``ModelAdapter``; ``route`` returns
    ``(config, key)`` for the configured decision provider, or ``None`` when
    no provider is configured - in which case no call is made and the
    decision is unavailable.  ``audit`` receives one small record per
    judgment (outcome, confidence, provider identity, timing); no reasoning
    text is ever recorded.
    """

    def __init__(self, adapter, route, *, timeout=20.0, audit=None, now=time.time):
        self.adapter, self.route, self.timeout, self.audit, self.now = adapter, route, timeout, audit, now

    # -- contract -----------------------------------------------------------
    def judge(self, context, proposition):
        schema = {'type': 'object', 'additionalProperties': False,
                  'properties': {'answer': {'type': 'boolean'},
                                 'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1}},
                  'required': ['answer', 'confidence']}
        outcome, data, confidence = self._ask(context, 'judge', f'Proposition: {proposition}', schema,
                                              lambda d: isinstance(d.get('answer'), bool))
        return BinaryDecision(outcome, data.get('answer'), confidence)

    def choose(self, context, candidates, question):
        options = [*dict.fromkeys(str(c) for c in candidates), NO_CANDIDATE]
        schema = {'type': 'object', 'additionalProperties': False,
                  'properties': {'choice': {'type': 'string', 'enum': options},
                                 'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1}},
                  'required': ['choice', 'confidence']}
        outcome, data, confidence = self._ask(
            context, 'choose', f'Question: {question}\nChoose exactly one of: {", ".join(options)}', schema,
            lambda d: d.get('choice') in options)
        return SelectionDecision(outcome, data.get('choice'), candidates, confidence)

    def score(self, context, question, scale=(0, 1)):
        low, high = float(scale[0]), float(scale[1])
        schema = {'type': 'object', 'additionalProperties': False,
                  'properties': {'score': {'type': 'number', 'minimum': low, 'maximum': high},
                                 'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1}},
                  'required': ['score', 'confidence']}
        outcome, data, confidence = self._ask(
            context, 'score', f'Question: {question}\nScore from {low:g} to {high:g}.', schema,
            lambda d: isinstance(d.get('score'), (int, float)) and not isinstance(d.get('score'), bool)
            and low <= d.get('score') <= high)
        return ScoreDecision(outcome, data.get('score'), (low, high), confidence)

    # -- one call -------------------------------------------------------------
    def _ask(self, context, kind, question, schema, valid):
        """Return (outcome, parsed arguments, confidence) for one judgment.

        ``valid`` checks the answer's shape; a provider answer that does not
        fit the declared schema is ``malformed`` and carries no answer.
        """
        started = self.now()
        resolved = self.route() if self.route else None
        if not resolved:
            return self._done(context, kind, OUTCOME_UNAVAILABLE, {}, DecisionConfidence(), started)
        config, key = resolved
        try:
            config = validate_model(config)
        except ValueError:
            return self._done(context, kind, OUTCOME_UNAVAILABLE, {}, DecisionConfidence(), started)
        identity = dict(provider=config['provider'], model=config['model'])
        if context.is_cancelled():
            return self._done(context, kind, OUTCOME_CANCELLED, {}, DecisionConfidence(**identity), started)
        rendered = context.render()
        if len(rendered) > MAX_CONTEXT_CHARS:
            return self._done(context, kind, OUTCOME_REJECTED, {}, DecisionConfidence(**identity), started)
        messages = [{'role': 'system', 'content': _SYSTEM},
                    {'role': 'user', 'content': f'Purpose: {context.purpose}\n{rendered}\n\n{question}'}]
        tools = [{'type': 'function', 'function': {'name': _DECIDE_TOOL, 'description': 'Record the judgment.',
                                                   'parameters': schema}}]
        try:
            message, observed = self.adapter.tool_turn(config, key, messages, tools, tool_choice='required',
                                                       timeout=self.timeout)
        except ProviderError as exc:
            outcome = OUTCOME_TIMEOUT if exc.status == 'timeout' else OUTCOME_REJECTED if exc.status in (400, 413) else OUTCOME_UNAVAILABLE
            return self._done(context, kind, outcome, {}, DecisionConfidence(**identity), started)
        except ValueError:
            # The adapter refuses a configuration it cannot call (for example
            # a provider that requires a key).  Nothing was sent.
            return self._done(context, kind, OUTCOME_UNAVAILABLE, {}, DecisionConfidence(**identity), started)
        data = self._arguments(message)
        confidence = DecisionConfidence(data.get('confidence') if isinstance(data, dict) else None,
                                        observed_model=observed if isinstance(observed, str) else '', **identity)
        if not isinstance(data, dict) or not isinstance(confidence.probability, (int, float)) \
                or isinstance(confidence.probability, bool) or not 0 <= confidence.probability <= 1 \
                or not valid(data):
            return self._done(context, kind, OUTCOME_MALFORMED, {}, confidence, started)
        return self._done(context, kind, OUTCOME_DECIDED, data, confidence, started)

    @staticmethod
    def _arguments(message):
        """The `decide` call's arguments, or None when the provider did not make one."""
        calls = message.get('tool_calls') if isinstance(message, dict) else None
        if not isinstance(calls, list) or not calls:
            return None
        call = calls[0]
        try:
            if call['function']['name'] != _DECIDE_TOOL:
                return None
            return json.loads(call['function']['arguments'])
        except (KeyError, TypeError, ValueError):
            return None

    _ANSWER_FIELD = {'judge': 'answer', 'choose': 'choice', 'score': 'score'}

    def _done(self, context, kind, outcome, data, confidence, started):
        confidence.elapsed_seconds = round(self.now() - started, 3)
        if self.audit:
            # The decided value is a bool, a declared candidate name or a
            # number - never owner content.
            answer = data.get(self._ANSWER_FIELD[kind]) if outcome == OUTCOME_DECIDED and isinstance(data, dict) else None
            self.audit({'at': self.now(), 'kind': kind, 'purpose': context.purpose, 'outcome': outcome,
                        'answer': answer,
                        'confidence': confidence.probability, 'provider': confidence.provider,
                        'model': confidence.model, 'observed_model': confidence.observed_model,
                        'elapsed_seconds': confidence.elapsed_seconds})
        return outcome, data if isinstance(data, dict) else {}, confidence
