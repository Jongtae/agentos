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

from .providers import NOT_REPORTED, ProviderError, validate_model

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
    """How sure the provider said it was, and which route/provider that was.

    ``probability`` is the provider's own number; calibration is a property
    measured per provider, never assumed here.  ``model`` is the requested /
    configured identity and ``observed_model`` what the provider reported
    (empty when it reported nothing), kept apart so neither is presented as
    the other.  ``route``, ``engine`` and ``model_policy`` name the
    DecisionEngine route (#580) - never the Work-execution route.
    """

    __slots__ = ('probability', 'provider', 'model', 'observed_model', 'elapsed_seconds',
                 'route', 'engine', 'model_policy')

    def __init__(self, probability=None, *, provider='', model='', observed_model='', elapsed_seconds=None,
                 route='', engine='', model_policy=''):
        self.probability = probability
        self.provider, self.model, self.observed_model = provider, model, observed_model
        self.elapsed_seconds = elapsed_seconds
        self.route, self.engine, self.model_policy = route, engine, model_policy


# NOT_REPORTED (imported from ``providers``) is recorded when a provider/CLI
# did not report the model it used; the requested model is never copied into
# the observed field.


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


class SelectionSetDecision(_Decision):
    """Which of the declared candidates apply (zero or more)."""
    __slots__ = ('choices', 'candidates')

    def __init__(self, outcome, choices=None, candidates=(), confidence=None):
        super().__init__(outcome, confidence)
        self.candidates = tuple(candidates)
        self.choices = frozenset(choices or ()) if outcome == OUTCOME_DECIDED else None


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

    def choose_many(self, context, candidates, question):
        """Which of ``candidates`` (zero or more) answer ``question``?
        -> SelectionSetDecision.  An engine that cannot answer a multi-selection
        says so: the default is an explicit non-answer, never a guess."""
        return SelectionSetDecision(OUTCOME_UNAVAILABLE, candidates=candidates)


class UnavailableDecisionEngine(DecisionEngine):
    """No provider: every judgment is explicitly unavailable."""

    def judge(self, context, proposition):
        return BinaryDecision(OUTCOME_UNAVAILABLE)

    def choose(self, context, candidates, question):
        return SelectionDecision(OUTCOME_UNAVAILABLE, candidates=candidates)

    def score(self, context, question, scale=(0, 1)):
        return ScoreDecision(OUTCOME_UNAVAILABLE, scale=scale)


class RoutedDecisionEngine(DecisionEngine):
    """Delegates each judgment to the engine of the currently active route.

    ``resolve`` returns a ``DecisionEngine`` and is consulted per judgment,
    so an owner route change applies to the next judgment without a
    restart.  Callers keep depending on this one contract (#580); they never
    branch on the route.
    """

    def __init__(self, resolve):
        self.resolve = resolve

    def judge(self, context, proposition):
        return self.resolve().judge(context, proposition)

    def choose(self, context, candidates, question):
        return self.resolve().choose(context, candidates, question)

    def score(self, context, question, scale=(0, 1)):
        return self.resolve().score(context, question, scale)

    def choose_many(self, context, candidates, question):
        return self.resolve().choose_many(context, candidates, question)


class FixtureDecisionEngine(DecisionEngine):
    """Scripted answers for tests and fixture-backed acceptance.

    Each script is a callable receiving the same arguments as the contract
    method and returning a decision, or ``None`` for unavailable.  It is a
    test double for a provider, not a production fallback.
    """

    def __init__(self, judge=None, choose=None, score=None, choose_many=None):
        self._judge, self._choose, self._score, self._choose_many = judge, choose, score, choose_many
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

    def choose_many(self, context, candidates, question):
        self.asked.append(('choose_many', context, tuple(candidates), question))
        result = self._choose_many(context, candidates, question) if self._choose_many else None
        return result if result is not None else SelectionSetDecision(OUTCOME_UNAVAILABLE, candidates=candidates)


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

    def selection_set(self, decision):
        """The chosen subset (possibly empty) when decided with enough
        confidence and every choice is a declared candidate, else None."""
        if not decision.decided or decision.choices is None or not self._confident(decision, self.selection_threshold):
            return None
        if not decision.choices <= set(decision.candidates):
            return None
        return frozenset(decision.choices)

    def confident_binary(self, decision):
        """True when a decided answer met the binary threshold."""
        return decision.decided and self._confident(decision, self.binary_threshold)

    def selection(self, decision):
        """The chosen candidate, or None (including an explicit none-of-these)."""
        if not decision.decided or not self._confident(decision, self.selection_threshold):
            return None
        if decision.choice == NO_CANDIDATE or decision.choice not in decision.candidates:
            return None
        return decision.choice


# --- the model-backed adapters ----------------------------------------------
DEFAULT_DECISION_MODEL = 'gpt-4o-mini'
DEFAULT_DECISION_PROVIDER = {'provider': 'openai', 'endpoint': 'https://api.openai.com/v1',
                             'model': DEFAULT_DECISION_MODEL}

DECISION_SYSTEM = ('You make one bounded judgment for a personal assistant. Read the facts, answer '
                   'only with the requested structured judgment, and report how confident you are as a '
                   'probability between 0 and 1. Do not take any action, do not use any tool other than '
                   'the one that records the judgment, and do not add commentary.')
_SYSTEM = DECISION_SYSTEM

_DECIDE_TOOL = 'decide'

#: The route labels an adapter reports in provenance (#580).
ROUTE_DIRECT_API = 'direct_api'
ROUTE_JEV = 'jev'
ROUTE_SUBSCRIPTION_CLI = 'subscription_cli'


class SchemaDecisionEngine(DecisionEngine):
    """The contract mapped onto one JSON-schema-shaped answer per judgment.

    ``judge``/``choose``/``score`` declare the answer schema and a shape
    check; a subclass's ``_ask`` obtains one structured answer from its
    transport (a model tool call, a subscription CLI's structured output).
    Every adapter therefore returns the same AgentOS-owned typed envelopes,
    and provider vocabulary stays inside ``_ask``.
    """

    route_label = ''

    def __init__(self, *, audit=None, now=time.time):
        self.audit, self.now = audit, now

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

    def choose_many(self, context, candidates, question):
        options = [*dict.fromkeys(str(c) for c in candidates)]
        schema = {'type': 'object', 'additionalProperties': False,
                  # No `uniqueItems`: not every structured-output transport
                  # accepts it; uniqueness is checked after parsing below.
                  'properties': {'choices': {'type': 'array', 'items': {'type': 'string', 'enum': options},
                                             'maxItems': len(options)},
                                 'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1}},
                  'required': ['choices', 'confidence']}
        outcome, data, confidence = self._ask(
            context, 'choose_many',
            f'Question: {question}\nList every candidate that applies (possibly none) from: {", ".join(options)}',
            schema, lambda d: isinstance(d.get('choices'), list) and all(c in options for c in d['choices'])
            and len(set(d['choices'])) == len(d['choices']))
        return SelectionSetDecision(outcome, data.get('choices'), candidates, confidence)

    def _ask(self, context, kind, question, schema, valid):  # pragma: no cover - interface
        raise NotImplementedError

    # -- shared checks and the audit record -----------------------------------
    @staticmethod
    def _checked(data, confidence, valid):
        """``decided`` only when the answer fits the schema and carries a probability."""
        probability = confidence.probability
        if not isinstance(data, dict) or not isinstance(probability, (int, float)) \
                or isinstance(probability, bool) or not 0 <= probability <= 1 or not valid(data):
            return OUTCOME_MALFORMED
        return OUTCOME_DECIDED

    _ANSWER_FIELD = {'judge': 'answer', 'choose': 'choice', 'score': 'score', 'choose_many': 'choices'}

    def _done(self, context, kind, outcome, data, confidence, started, failure=''):
        confidence.elapsed_seconds = round(self.now() - started, 3)
        if self.audit:
            self.audit(audit_record(context, kind, outcome, data, confidence, self.now(), failure))
        return outcome, data if isinstance(data, dict) else {}, confidence


_ANSWER_FIELD = SchemaDecisionEngine._ANSWER_FIELD


def audit_record(context, kind, outcome, data, confidence, at, failure=''):
    """One small, content-free record of a judgment (shared by every adapter).

    The decided value is a bool, a declared candidate name or a number -
    never owner content.  #580: which DecisionEngine route answered, under
    which model policy; the requested and observed model stay separate and
    an unreported model is recorded as ``not reported``.
    """
    answer = data.get(_ANSWER_FIELD[kind]) if outcome == OUTCOME_DECIDED and isinstance(data, dict) else None
    record = {'at': at, 'kind': kind, 'purpose': context.purpose, 'outcome': outcome,
              'answer': answer,
              'confidence': confidence.probability, 'provider': confidence.provider,
              'model': confidence.model, 'observed_model': confidence.observed_model or NOT_REPORTED,
              'elapsed_seconds': confidence.elapsed_seconds,
              'route': confidence.route, 'engine': confidence.engine,
              'model_policy': confidence.model_policy, 'requested_model': confidence.model or ''}
    if failure:
        record['failure'] = failure
    return record


class ModelDecisionEngine(SchemaDecisionEngine):
    """The direct-API adapter: one model tool call per judgment.

    ``adapter`` is the repository's ``ModelAdapter``; ``route`` returns
    ``(config, key)`` for the configured decision provider, or ``None`` when
    no provider is configured - in which case no call is made and the
    decision is unavailable.  ``audit`` receives one small record per
    judgment (outcome, confidence, route/provider identity, timing); no
    reasoning text is ever recorded.
    """

    route_label = ROUTE_DIRECT_API

    def __init__(self, adapter, route, *, timeout=20.0, audit=None, now=time.time):
        super().__init__(audit=audit, now=now)
        self.adapter, self.route, self.timeout = adapter, route, timeout

    def _ask(self, context, kind, question, schema, valid):
        """Return (outcome, parsed arguments, confidence) for one judgment.

        ``valid`` checks the answer's shape; a provider answer that does not
        fit the declared schema is ``malformed`` and carries no answer.
        """
        started = self.now()
        resolved = self.route() if self.route else None
        if not resolved:
            return self._done(context, kind, OUTCOME_UNAVAILABLE, {}, DecisionConfidence(route=self.route_label),
                              started, 'not-configured')
        config, key = resolved
        try:
            config = validate_model(config)
        except ValueError:
            return self._done(context, kind, OUTCOME_UNAVAILABLE, {}, DecisionConfidence(route=self.route_label),
                              started, 'invalid-configuration')
        identity = dict(provider=config['provider'], model=config['model'], route=self.route_label,
                        engine=config['provider'])
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
                                                       timeout=self.timeout, report_observed=True)
        except ProviderError as exc:
            outcome = OUTCOME_TIMEOUT if exc.status == 'timeout' else OUTCOME_REJECTED if exc.status in (400, 413) else OUTCOME_UNAVAILABLE
            failure = 'auth' if exc.status in (401, 403) else 'usage-limit' if exc.status == 429 else ''
            return self._done(context, kind, outcome, {}, DecisionConfidence(**identity), started, failure)
        except ValueError:
            # The adapter refuses a configuration it cannot call (for example
            # a provider that requires a key).  Nothing was sent.
            return self._done(context, kind, OUTCOME_UNAVAILABLE, {}, DecisionConfidence(**identity), started,
                              'not-configured')
        data = self._arguments(message)
        confidence = DecisionConfidence(data.get('confidence') if isinstance(data, dict) else None,
                                        observed_model=observed if isinstance(observed, str) else '', **identity)
        outcome = self._checked(data, confidence, valid)
        return self._done(context, kind, outcome, data if outcome == OUTCOME_DECIDED else {}, confidence, started)

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
