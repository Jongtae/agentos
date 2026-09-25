"""DecisionEngine route adapters beyond the direct API (DECISION-ROUTE-01 / #580).

Two adapters implement the AgentOS-owned ``DecisionEngine`` contract from
``decision.py``:

* ``SubscriptionCliDecisionEngine`` - one bounded, tool-less judgment through
  an authenticated official subscription CLI (Codex or Claude Code).  It
  reuses the #533/#571 isolation of ``BoundedExecutionAdapter`` (fresh empty
  per-call directory as HOME, minimal PATH, no inherited environment, the
  owner's Codex user config ignored, Claude Code's own token passed only as
  ``CLAUDE_CODE_OAUTH_TOKEN``) and adds the decision-specific restriction
  that the CLI gets **no** tools at all: no AgentOS MCP bridge, no shell, no
  plugins/apps.  Model selection uses only the CLI's own documented flag.
* ``JevDecisionEngine`` - TypeSafe AI's documented System One HTTP API
  (``POST https://api.typesafe.ai/v1/systemone``), reached through the
  repository's existing bounded ``request_json`` transport.  Jev's
  ``noul``/``choice``/``score`` vocabulary is translated here and never
  leaves this module.

Callers never see CLI or Jev types: every adapter answers with the same
``BinaryDecision``/``SelectionDecision``/``ScoreDecision`` envelopes and the
same explicit non-answer outcomes.  No adapter falls back to another route.

Verified capability sources (recorded, not assumed; see
docs/decision-layer.en.md "DecisionEngine routes"):

* Codex CLI 0.153.4 ``codex exec --help``: ``--json``, ``--ignore-user-config``,
  ``--ephemeral``, ``--sandbox read-only``, ``--output-schema FILE``,
  ``-m/--model``, ``--disable FEATURE``.
* Claude Code 2.1.280 ``claude --help``: ``-p``, ``--output-format json``,
  ``--json-schema``, ``--tools ""``, ``--strict-mcp-config``,
  ``--no-session-persistence``, ``--system-prompt``, ``--model``.
* TypeSafe HTTP API reference (docs.typesafe.ai/api): request
  ``{state, model, questions}``, answers keyed by question id, response
  ``model`` reports the versioned model that answered.

Whether a given *account* accepts a model is never inferred from these
flags; it is established only by an explicit owner-triggered probe.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from .bounded_execution import ExecutionError, cli_metadata, failure_details, is_not_signed_in
from .decision import (DECISION_SYSTEM, MAX_CONTEXT_CHARS, NO_CANDIDATE, OUTCOME_CANCELLED,
                       OUTCOME_DECIDED, OUTCOME_MALFORMED, OUTCOME_REJECTED, OUTCOME_TIMEOUT,
                       OUTCOME_UNAVAILABLE, ROUTE_JEV, ROUTE_SUBSCRIPTION_CLI, BinaryDecision,
                       DecisionConfidence, DecisionEngine, SchemaDecisionEngine, ScoreDecision,
                       SelectionDecision, audit_record)
from .providers import ProviderError, request_json

#: Upper bound for one CLI judgment.  A decision is a small question; a CLI
#: that needs longer is reported as a timeout, never retried elsewhere.
CLI_DECISION_TIMEOUT_SECONDS = 90
MAX_CLI_OUTPUT_BYTES = 400_000

CLI_BINARIES = {'codex': 'codex', 'claude-code': 'claude'}

#: A model identifier the owner may type.  It is passed as one argv element
#: (never a shell), so this only bounds its shape.
MODEL_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,99}$')

# Codex features that could let a judgment act rather than answer.  The
# names come from `codex features list` on the verified version; an unknown
# name makes the CLI fail, which surfaces as an explicit unavailable outcome.
CODEX_DISABLED_FEATURES = ('shell_tool', 'plugins', 'apps')


def valid_model_id(value):
    return isinstance(value, str) and bool(MODEL_ID.match(value))


class SubscriptionCliDecisionEngine(SchemaDecisionEngine):
    """One judgment per isolated, tool-less subscription-CLI invocation.

    ``execution`` is the service's ``BoundedExecutionAdapter`` (for its
    ``finder``, ``runner``, ``runtime_root`` and isolated ``environment``).
    ``model`` is ``None`` for ``engine_default``: then no model flag is sent
    and the CLI's own default for this isolated invocation answers - with
    the owner's user configuration ignored, so it is not a user-configured
    default.  ``guard`` is an optional callable returning a failure label
    (for example a changed CLI binary after qualification) or ``''``.
    """

    route_label = ROUTE_SUBSCRIPTION_CLI

    def __init__(self, execution, engine_id, *, model=None, model_policy='engine_default',
                 timeout=CLI_DECISION_TIMEOUT_SECONDS, audit=None, now=time.time, guard=None):
        super().__init__(audit=audit, now=now)
        if engine_id not in CLI_BINARIES:
            raise ValueError('지원하는 구독 엔진을 선택하세요.')
        if model is not None and not valid_model_id(model):
            raise ValueError('모델 이름 형식을 확인하세요.')
        self.execution, self.engine_id, self.model = execution, engine_id, model
        self.model_policy, self.timeout, self.guard = model_policy, timeout, guard
        self.last_failure = ''

    def argv(self, binary, prompt, schema_path, schema):
        if self.engine_id == 'codex':
            argv = [binary, 'exec', '--json', '--sandbox', 'read-only', '--skip-git-repo-check',
                    '--ignore-user-config', '--ephemeral', '--output-schema', str(schema_path)]
            for feature in CODEX_DISABLED_FEATURES:
                argv += ['--disable', feature]
            if self.model:
                argv += ['--model', self.model]
            return argv + [prompt]
        argv = [binary, '-p', prompt, '--output-format', 'json', '--json-schema', json.dumps(schema),
                '--tools', '', '--strict-mcp-config', '--no-session-persistence',
                '--system-prompt', DECISION_SYSTEM]
        if self.model:
            argv += ['--model', self.model]
        return argv

    def _identity(self):
        return dict(provider=self.engine_id, engine=self.engine_id, model=self.model or '',
                    route=self.route_label, model_policy=self.model_policy)

    def _ask(self, context, kind, question, schema, valid):
        started = self.now()
        identity = self._identity()
        self.last_failure = ''

        def done(outcome, data=None, confidence=None, failure=''):
            self.last_failure = failure
            return self._done(context, kind, outcome, data or {}, confidence or DecisionConfidence(**identity),
                              started, failure)

        if self.guard:
            blocked = self.guard()
            if blocked:
                return done(OUTCOME_UNAVAILABLE, failure=blocked)
        if context.is_cancelled():
            return done(OUTCOME_CANCELLED)
        rendered = context.render()
        if len(rendered) > MAX_CONTEXT_CHARS:
            return done(OUTCOME_REJECTED)
        binary = self.execution.finder(CLI_BINARIES[self.engine_id])
        if not binary:
            return done(OUTCOME_UNAVAILABLE, failure='cli-not-found')
        prompt = (('' if self.engine_id == 'claude-code' else DECISION_SYSTEM + '\n\n')
                  + f'Purpose: {context.purpose}\n{rendered}\n\n{question}\n\n'
                  'Reply with only one JSON object that matches the required schema.')
        root = self.execution.runtime_root
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(dir=root, prefix='decision-') as folder:
            run_dir = Path(folder)
            schema_path = run_dir / 'decision-schema.json'
            schema_path.write_text(json.dumps(schema), encoding='utf-8')
            try:
                env = self.execution.environment(self.engine_id, binary, run_dir)
            except ExecutionError:
                return done(OUTCOME_UNAVAILABLE, failure='auth')
            argv = self.argv(binary, prompt, schema_path, schema)
            try:
                completed = self.execution.runner(argv, cwd=run_dir, env=env, stdin=subprocess.DEVNULL,
                                                  capture_output=True, text=True, timeout=self.timeout,
                                                  shell=False)
            except subprocess.TimeoutExpired:
                return done(OUTCOME_TIMEOUT, failure='timeout')
            except OSError:
                return done(OUTCOME_UNAVAILABLE, failure='start-failed')
        stdout = (completed.stdout or '')[-MAX_CLI_OUTPUT_BYTES:]
        stderr = getattr(completed, 'stderr', '') or ''
        observed = cli_metadata(self.engine_id, stdout).get('reported_model') or ''
        identity_seen = DecisionConfidence(observed_model=observed, **identity)
        if completed.returncode != 0:
            status, reason = failure_details(self.engine_id, stdout, stderr)
            if (isinstance(status, int) and status in (401, 403)) or is_not_signed_in(' '.join((reason or '', stderr[-4000:]))):
                failure = 'auth'
            elif status == 429:
                failure = 'usage-limit'
            elif (isinstance(status, int) and 400 <= status < 500) or '[claude-code:unrecognized_model]' in stderr:
                # Codex reports the provider's structured 4xx; Claude Code 2.1.x
                # tags an unknown/inaccessible --model on stderr (observed locally).
                # Includes a model this account/CLI refused.  Reported as a
                # refusal, never retried with another model.
                failure = 'request-rejected'
            else:
                failure = 'engine-failed'
            return done(OUTCOME_UNAVAILABLE, confidence=identity_seen, failure=failure)
        data = self._structured(stdout)
        if data is None:
            return done(OUTCOME_MALFORMED, confidence=identity_seen, failure='invalid-output')
        confidence = DecisionConfidence(data.get('confidence') if isinstance(data, dict) else None,
                                        observed_model=observed, **identity)
        outcome = self._checked(data, confidence, valid)
        return done(outcome, data if outcome == OUTCOME_DECIDED else {}, confidence,
                    '' if outcome == OUTCOME_DECIDED else 'invalid-output')

    def _structured(self, stdout):
        """The CLI's structured answer as a dict, or None.

        Claude Code's ``json`` result record carries ``structured_output``
        when ``--json-schema`` is used (``result`` text as a fallback);
        Codex ``exec --json`` ends with the last ``agent_message`` whose text
        is the ``--output-schema`` answer.  Anything else is malformed.
        """
        lines = [line for line in stdout.splitlines() if line.strip()]
        records = []
        for line in lines:
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                records.append(value)
        if self.engine_id == 'claude-code':
            record = records[-1] if records else None
            if not isinstance(record, dict) or record.get('is_error') is True:
                return None
            if isinstance(record.get('structured_output'), dict):
                return record['structured_output']
            return _json_object(record.get('result'))
        for record in reversed(records):
            item = record.get('item')
            if isinstance(item, dict) and item.get('type') == 'agent_message':
                return _json_object(item.get('text'))
        return None


def _json_object(text):
    if not isinstance(text, str):
        return None
    text = text.strip()
    if text.startswith('```'):
        text = text.strip('`')
        text = text[text.find('{'):] if '{' in text else text
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


# --- Jev (TypeSafe System One) ------------------------------------------------
JEV_ENDPOINT = 'https://api.typesafe.ai/v1/systemone'
JEV_DESTINATION = 'api.typesafe.ai'
#: The documented alias.  It moves with new releases, so the response's
#: versioned ``model`` is what provenance records as observed.
JEV_DEFAULT_MODEL = 'jev-latest'
#: Levels used to express a numeric AgentOS scale as a Jev Score rubric
#: (the API accepts 2-10 ordered levels).
JEV_SCORE_LEVELS = 5
_QUESTION = 'q'


class JevDecisionEngine(DecisionEngine):
    """The contract over TypeSafe's documented System One HTTP API.

    ``credential`` returns the owner's TypeSafe API key or ``''``; with no
    key no request is made and every judgment is unavailable.  ``transport``
    defaults to the repository's bounded ``request_json`` (no redirects,
    size-limited, credential-free error text).

    Mapping at this boundary only:

    * ``judge`` -> one ``noul``; ``answer`` is ``noul >= 0.5`` and the
      reported probability is that of the chosen side.
    * ``choose`` -> one ``choice`` whose criteria are the declared candidates
      plus ``none-of-these``; Jev's own ``confidence`` is kept.
    * ``score`` -> one ``score`` over evenly spaced levels of the AgentOS
      scale; the probability-weighted level is mapped back onto the scale.
    """

    route_label = ROUTE_JEV

    def __init__(self, credential, *, model=JEV_DEFAULT_MODEL, transport=request_json, timeout=20.0,
                 audit=None, now=time.time):
        self.credential, self.model, self.transport = credential, model or JEV_DEFAULT_MODEL, transport
        self.timeout, self.audit, self.now = timeout, audit, now
        self.last_failure = ''

    # -- contract -----------------------------------------------------------
    def judge(self, context, proposition):
        outcome, answer, confidence = self._ask(context, 'judge', {'type': 'noul', 'instructions': proposition},
                                                self._noul)
        value = answer.get('answer') if outcome == OUTCOME_DECIDED else None
        return BinaryDecision(outcome, value, confidence)

    def choose(self, context, candidates, question):
        options = [*dict.fromkeys(str(c) for c in candidates)]
        criteria = {option: None for option in options}
        criteria[NO_CANDIDATE] = 'None of the other options fits, or the answer is unclear.'
        outcome, answer, confidence = self._ask(
            context, 'choose', {'type': 'choice', 'instructions': question, 'criteria': criteria},
            lambda a: self._choice(a, [*options, NO_CANDIDATE]))
        return SelectionDecision(outcome, answer.get('choice'), candidates, confidence)

    def score(self, context, question, scale=(0, 1)):
        low, high = float(scale[0]), float(scale[1])
        step = (high - low) / (JEV_SCORE_LEVELS - 1)
        levels = [f'{low + index * step:g}' + (' (lowest)' if index == 0 else ' (highest)'
                                               if index == JEV_SCORE_LEVELS - 1 else '')
                  for index in range(JEV_SCORE_LEVELS)]
        outcome, answer, confidence = self._ask(
            context, 'score', {'type': 'score', 'instructions': question, 'criteria': levels},
            lambda a: self._score(a, low, step))
        return ScoreDecision(outcome, answer.get('score'), (low, high), confidence)

    # -- Jev answer shapes --------------------------------------------------
    @staticmethod
    def _number(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def _noul(self, answer):
        value = answer.get('noul')
        if answer.get('type') != 'noul' or not self._number(value) or not 0 <= value <= 1:
            return None
        yes = value >= 0.5
        return {'answer': yes}, (value if yes else 1 - value)

    def _choice(self, answer, options):
        choice, confidence = answer.get('choice'), answer.get('confidence')
        if answer.get('type') != 'choice' or choice not in options or not self._number(confidence) \
                or not 0 <= confidence <= 1:
            return None
        return {'choice': choice}, confidence

    def _score(self, answer, low, step):
        value, confidence = answer.get('score'), answer.get('confidence')
        if answer.get('type') != 'score' or not self._number(value) or not 0 <= value <= JEV_SCORE_LEVELS - 1 \
                or not self._number(confidence) or not 0 <= confidence <= 1:
            return None
        return {'score': round(low + value * step, 6)}, confidence

    # -- one request ----------------------------------------------------------
    def _ask(self, context, kind, question, parse):
        started = self.now()
        identity = dict(provider='typesafe', engine='jev', model=self.model, route=self.route_label)
        self.last_failure = ''

        def done(outcome, data=None, confidence=None, failure=''):
            confidence = confidence or DecisionConfidence(**identity)
            confidence.elapsed_seconds = round(self.now() - started, 3)
            self.last_failure = failure
            if self.audit:
                self.audit(audit_record(context, kind, outcome, data or {}, confidence, self.now(), failure))
            return outcome, data or {}, confidence

        key = self.credential() if self.credential else ''
        if not isinstance(key, str) or not key:
            return done(OUTCOME_UNAVAILABLE, failure='not-configured')
        if context.is_cancelled():
            return done(OUTCOME_CANCELLED)
        if len(context.render()) > MAX_CONTEXT_CHARS:
            return done(OUTCOME_REJECTED)
        body = {'state': {'purpose': context.purpose, **context.facts}, 'model': self.model,
                'questions': {_QUESTION: question}}
        try:
            reply = self.transport(JEV_ENDPOINT, body, {'Authorization': 'Bearer ' + key}, self.timeout)
        except ProviderError as exc:
            if exc.status == 'timeout':
                return done(OUTCOME_TIMEOUT, failure='timeout')
            if exc.status in (401, 403):
                return done(OUTCOME_UNAVAILABLE, failure='auth')
            if exc.status in (413, 422):
                return done(OUTCOME_REJECTED, failure='request-rejected')
            if exc.status in (429, 529):
                return done(OUTCOME_UNAVAILABLE, failure='usage-limit')
            return done(OUTCOME_UNAVAILABLE, failure='provider-error')
        observed = reply.get('model') if isinstance(reply, dict) else None
        seen = DecisionConfidence(observed_model=observed[:120] if isinstance(observed, str) else '', **identity)
        answers = reply.get('answers') if isinstance(reply, dict) else None
        answer = answers.get(_QUESTION) if isinstance(answers, dict) else None
        parsed = parse(answer) if isinstance(answer, dict) else None
        if not parsed:
            return done(OUTCOME_MALFORMED, confidence=seen, failure='invalid-output')
        data, probability = parsed
        seen.probability = probability
        return done(OUTCOME_DECIDED, data, seen)


def cli_fingerprint(binary):
    """A local identity of the CLI binary AgentOS would run (no subprocess).

    Used to invalidate a qualification when the engine changes: resolved
    path, size and modification time.  ``''`` when the binary is absent.
    """
    if not binary:
        return ''
    try:
        path = os.path.realpath(binary)
        info = os.stat(path)
    except OSError:
        return ''
    return f'{path}|{info.st_size}|{int(info.st_mtime)}'
