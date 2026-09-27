"""Owner-selectable DecisionEngine routes (DECISION-ROUTE-01 / #580).

The DecisionEngine route answers bounded semantic questions ("is this a
retry of the failed Work?").  It is a third role, distinct from the
Personal AgentOS assistant identity and from the Work-execution route
(#504, ``subscription_engine`` / ``model`` config).  This module owns only
the decision route:

* ``decision_route`` config row - the *active* route, written only by an
  explicit owner activation that passed its probe/qualification.  When the
  row is absent the #417 default applies (OpenAI ``gpt-4o-mini`` when an
  OpenAI key is already the owner's choice for that destination).
* ``decision_route_checks`` - the last explicit check per route option,
  content free.
* ``decision_cli_capabilities`` - what each installed CLI's own ``--help``
  declared, recorded on explicit owner action.

Invariants (tested in tests/test_decision_routes.py):

* reading the status (Settings) runs no subprocess and calls no model;
* saving a credential never activates a route;
* a failed activation leaves the previous route unchanged;
* activating a decision route never writes the Work-execution rows, and the
  legacy Work route selection never writes ``decision_route``; only the #619
  Main AI switch re-resolves a Judgment AI whose mode is ``follow_main``
  (its own probe; a failure leaves it needing attention, never a fallback);
* there is no cross-route fallback: an unavailable route answers
  ``provider_unavailable``;
* ``lowest_qualified`` selects only among declared candidates (the owner's,
  or the ranked cheapest-first list below, #679) that pass the versioned
  qualification suite in order; none passing is an explicit failure, never a
  jump to another model or route;
* listing models (#679) runs only on the owner's explicit 모델 목록 새로고침,
  never on opening Settings; a listed model is not a verified model.
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

from .decision import (DEFAULT_DECISION_MODEL, DEFAULT_DECISION_PROVIDER, OUTCOME_DECIDED,
                       ROUTE_DIRECT_API, ROUTE_JEV, ROUTE_SUBSCRIPTION_CLI, DecisionContext,
                       ModelDecisionEngine, UnavailableDecisionEngine)
import re
import threading

from .decision_adapters import (CLI_BINARIES, JEV_DEFAULT_MODEL, JEV_DESTINATION, JevDecisionEngine,
                                SubscriptionCliDecisionEngine, bounded_run, cli_fingerprint, codex_disable_plan,
                                codex_still_enabled, parse_codex_features, valid_effort, valid_model_id)
from .bounded_execution import parse_cli_version, strict_allowed_features
from .decision_qualification import SUITE_VERSION, qualify
from .main_ai import CHOOSER_ORDER, api_route_of, key_slot
from .providers import ProviderError, request_json

ROUTE_OFF = 'off'
TRANSPORTS = (ROUTE_DIRECT_API, ROUTE_JEV, ROUTE_SUBSCRIPTION_CLI, ROUTE_OFF)
POLICY_ENGINE_DEFAULT = 'engine_default'
POLICY_EXPLICIT = 'explicit'
POLICY_LOWEST_QUALIFIED = 'lowest_qualified'
MODEL_POLICIES = (POLICY_ENGINE_DEFAULT, POLICY_EXPLICIT, POLICY_LOWEST_QUALIFIED)
MAX_CANDIDATES = 3
#: #619: the Judgment AI follows the Main AI (default for a fresh install and
#: for owners on the #417 implicit default).  A follow row records the Main AI
#: it was resolved for; once the Main AI differs it answers unavailable until
#: it is re-resolved, so a judgment never goes to a destination the owner did
#: not see next to the current Main AI.
MODE_FOLLOW = 'follow_main'

# --- Judgment models (SEC-JUDGE-01 / #679) -------------------------------------
#: Ranked, cheapest-first Judgment model candidates per route.  Data, not a
#: component: ``lowest_qualified`` (the default in follow and separate mode)
#: activates the first candidate that passes ``qualify()``.  Being listed here
#: claims nothing about an account; only the qualification does.
RANKED_MODELS = {
    # Codex subscription.  Sources, checked 2026-09-27 (#679/#677):
    # https://developers.openai.com/codex/models and the installed codex-cli
    # 0.153.4 `codex debug models --bundled` (local, no network), which lists
    # gpt-5.6-luna and gpt-5.6-terra but not gpt-6-luna (`-m gpt-6-luna` warns
    # "Model metadata ... not found" on 0.153.4).  The list is filtered by the
    # installed binary's bundled listing at activation, so on 0.153.4 the
    # effective cheapest candidate is gpt-5.6-luna; a newer CLI that bundles
    # gpt-6-luna makes it first (after requalification).
    'codex': ('gpt-6-luna', 'gpt-5.6-luna', 'gpt-5.6-terra'),
    # Claude Code aliases.  Sources, checked 2026-09-27:
    # https://docs.anthropic.com/en/docs/claude-code/model-config and
    # `claude --help` 2.1.280 (`--model` accepts haiku/sonnet/opus or a full
    # name; there is no machine-readable model list).
    'claude-code': ('haiku', 'sonnet'),
    # OpenAI API.  Source, checked 2026-09-27: https://platform.openai.com/docs/pricing.
    # gpt-6-luna is cheaper, but its Chat Completions compatibility (the
    # transport ModelAdapter uses) is unverified, so gpt-4o-mini stays first.
    # To promote gpt-6-luna: after an owner live check in which an explicit
    # `gpt-6-luna` choice passed the full qualification on the owner's key
    # (Settings › 판단 AI › 고급 › OpenAI API › 모델), move it first here and
    # record that evidence in docs/decision-layer.en.md.
    'openai': ('gpt-4o-mini', 'gpt-6-luna'),
    # Anthropic API.  Source, checked 2026-09-27:
    # https://docs.anthropic.com/en/docs/about-claude/models (Claude Haiku 4.5,
    # $1/$5 per MTok, the cheapest current model).
    'anthropic': ('claude-haiku-4-5',),
}
#: The default reasoning effort for a judgment, sent only where the model
#: supports it (``supported_efforts``).
DEFAULT_EFFORT = 'low'
#: Claude Code ``--effort`` levels per alias (2.1.280 --help lists low, medium,
#: high, xhigh, max).  Claude Haiku 4.5 rejects the effort setting (Anthropic
#: model documentation), so no ``--effort`` is sent for ``haiku``.
CLAUDE_CODE_MODELS = {'haiku': (), 'sonnet': ('low', 'medium', 'high', 'xhigh', 'max'),
                      'opus': ('low', 'medium', 'high', 'xhigh', 'max')}
#: Owner-visible label of a listed model: a listing is not a qualification.
LISTED_LABEL = '목록에 있음(검증 전)'
#: Official model-list endpoints for the API routes (explicit refresh only).
ANTHROPIC_CONFIG = {'provider': 'anthropic', 'endpoint': 'https://api.anthropic.com', 'model': 'claude-haiku-4-5'}
API_MODEL_LISTS = {
    'openai': {'url': 'https://api.openai.com/v1/models', 'config': dict(DEFAULT_DECISION_PROVIDER)},
    'anthropic': {'url': 'https://api.anthropic.com/v1/models', 'config': dict(ANTHROPIC_CONFIG)},
}
MODEL_LIST_ROUTES = ('codex', 'claude-code', 'openai', 'anthropic')

#: Built-in Judgment candidates per Main AI route.  Direct API routes use the
#: Main AI's own saved provider key; the subscription CLIs use their own login.
#: Every entry runs ``lowest_qualified`` over its ranked list (#679).
FOLLOW_CANDIDATES = {
    'openai': {'transport': ROUTE_DIRECT_API, 'config': dict(DEFAULT_DECISION_PROVIDER),
               'model_policy': POLICY_LOWEST_QUALIFIED, 'candidates': list(RANKED_MODELS['openai'])},
    'anthropic': {'transport': ROUTE_DIRECT_API, 'config': dict(ANTHROPIC_CONFIG),
                  'model_policy': POLICY_LOWEST_QUALIFIED, 'candidates': list(RANKED_MODELS['anthropic'])},
    'openrouter': {'transport': ROUTE_DIRECT_API, 'config': {'provider': 'compatible', 'endpoint': 'https://openrouter.ai/api/v1',
                                                              'model': 'openai/gpt-4o-mini'},
                   'model_policy': POLICY_LOWEST_QUALIFIED, 'candidates': ['openai/gpt-4o-mini']},
    'claude-code': {'transport': ROUTE_SUBSCRIPTION_CLI, 'engine': 'claude-code', 'model_policy': POLICY_LOWEST_QUALIFIED,
                    'candidates': list(RANKED_MODELS['claude-code'])},
    'codex': {'transport': ROUTE_SUBSCRIPTION_CLI, 'engine': 'codex', 'model_policy': POLICY_LOWEST_QUALIFIED,
              'candidates': list(RANKED_MODELS['codex'])},
}

ENGINE_NAMES = {'codex': 'Codex', 'claude-code': 'Claude Code'}
#: Where each subscription engine sends the judgment.  Owner-visible so a
#: route switch never hides a destination change.
CLI_DESTINATIONS = {'codex': 'OpenAI (Codex 구독 계정)', 'claude-code': 'Anthropic (Claude Code 구독 계정)'}

#: Flags a CLI's own help must declare before AgentOS will run a judgment
#: through it: the isolation/no-tools flags are mandatory, the model flag
#: decides whether ``explicit`` / ``lowest_qualified`` can be offered.
REQUIRED_FLAGS = {
    # #679: no `--sandbox` - a judgment runs under the #616 strict permissions
    # profile, passed through `--config` (-c), with `--ignore-rules`.
    'codex': ('--json', '--ignore-user-config', '--ignore-rules', '--ephemeral', '--output-schema', '--disable',
              '--skip-git-repo-check', '--config'),
    'claude-code': ('--output-format', '--json-schema', '--tools', '--strict-mcp-config', '--no-session-persistence',
                    '--system-prompt', '--setting-sources', '--restricted'),
}
MODEL_FLAG = '--model'
#: Codex CLI versions whose CODEX_HOME instruction-file behaviour was re-checked
#: with the no-model harness (tests/test_strict_isolation.py::
#: CodexDecisionInstructionFiles) *and* whose limitation below is accepted for
#: a decision route (#624).  #679: 0.153.4 is listed under the owner's pilot
#: relaxation (#677 item 5).  The harness observed on exactly this version
#: which file reaches the prompt (`$CODEX_HOME/AGENTS.override.md`, else
#: `AGENTS.md`); the owner accepts it as owner-authored, untracked input to an
#: advisory judgment.  Activation checks only the *size* of those two files (a
#: stat, never their content) and shows a warning when one is non-empty.  Any
#: other version still fails closed until the harness is re-run for it.
CODEX_INSTRUCTION_FILES_QUALIFIED = frozenset({'0.153.4'})
#: The global instruction files Codex loads from CODEX_HOME (#624), in precedence order.
CODEX_INSTRUCTION_FILES = ('AGENTS.override.md', 'AGENTS.md')
#: Owner-visible limitation for the Codex route (#624, observed on 0.153.4).
CODEX_INSTRUCTION_FILES_LIMITATION = ('Codex는 로그인 프로필(CODEX_HOME)의 AGENTS.override.md 또는 AGENTS.md를 '
                                      '판단 요청에 함께 보냅니다. 끌 수 있는 공식 옵션이 없고, AgentOS는 그 내용을 '
                                      '읽거나 기록하지 않습니다.')


#: Main AI routes the Judgment AI cannot follow, with the owner-visible reason.
#: #679: Codex is followable (strict-isolated judgments, 0.153.4 qualified).
FOLLOW_UNAVAILABLE = {
    'other': '이 기본 AI 연결에는 판단 AI가 따라갈 가벼운 모델이 정해져 있지 않습니다.',
}
ROUTE_NAMES = {'codex': 'Codex', 'claude-code': 'Claude Code', 'openai': 'OpenAI API', 'anthropic': 'Anthropic API',
               'openrouter': 'OpenRouter', 'other': '기타 연결'}


def supported_efforts(engine_id, model, capability=None):
    """Effort levels one model supports, from the CLI's own metadata (#679).

    Codex: the model's ``supported_reasoning_levels`` in the installed
    binary's bundled listing (recorded at the capability check).  Claude Code:
    the documented per-alias levels.  ``()`` when unknown, so nothing is sent.
    """
    if engine_id == 'claude-code':
        return tuple(CLAUDE_CODE_MODELS.get(model or '', ()))
    if engine_id == 'codex':
        for row in (capability or {}).get('bundled_models') or ():
            if row.get('id') == model:
                return tuple(level for level in row.get('efforts') or () if valid_effort(level))
    return ()


def parse_bundled_models(text):
    """``[{id, efforts, visible}]`` from ``codex debug models --bundled``; ValueError otherwise."""
    data = json.loads(text or '')
    rows = data.get('models') if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError('unexpected bundled model listing')
    models = []
    for row in rows:
        slug = row.get('slug') if isinstance(row, dict) else None
        if not valid_model_id(slug):
            continue
        levels = [level.get('effort') for level in row.get('supported_reasoning_levels') or ()
                  if isinstance(level, dict)]
        models.append({'id': slug, 'efforts': [level for level in levels if valid_effort(level)],
                       'visible': row.get('visibility') == 'list'})
    if not models:
        raise ValueError('empty bundled model listing')
    return models


def has_flag(help_text, flag):
    """Whole-flag match in help text (``--model`` is not ``--model-provider``)."""
    return re.search(rf'(?<![\w-]){re.escape(flag)}(?![\w-])', help_text or '') is not None

#: A synthetic judgment used to verify a route on explicit owner action.
#: It carries no owner content.
PROBE_CONTEXT = {'owner_message': '다시 해봐', 'previous_intent': 'research', 'previous_status': 'failed'}


class DecisionRouteError(ValueError):
    """An owner-facing refusal; the previous route stays active."""


class DecisionRoutes:
    """The decision route read model, resolver and explicit owner actions.

    ``service`` supplies the store, the model adapter, the isolated CLI
    execution adapter, the #417 default resolver (``decision_route``), the
    CLI login check (#571) and the decision audit sink.  ``jev_transport``
    is the HTTP transport for Jev (tests inject a fixture).
    """

    def __init__(self, service, *, jev_transport=None, models_transport=None, clock=time.time):
        self.service, self.clock = service, clock
        self.jev_transport = jev_transport
        # The bounded HTTP transport for the explicit API model-list refresh.
        self.models_transport = models_transport or request_json
        self.store = service.store
        self._activating = threading.Lock()
        self.codex_instruction_qualified = CODEX_INSTRUCTION_FILES_QUALIFIED

    # -- configuration rows -------------------------------------------------
    def active(self):
        row = self.store.config('decision_route', None)
        return dict(row) if isinstance(row, dict) and row.get('transport') in TRANSPORTS else None

    def _checks(self):
        rows = self.store.config('decision_route_checks', {})
        return dict(rows) if isinstance(rows, dict) else {}

    def _record_check(self, option, record):
        with self.service.lock:
            rows = self._checks()
            rows[option] = {**record, 'checked_at': self.clock()}
            self.store.put('decision_route_checks', rows)
        return rows[option]

    def _capabilities(self):
        rows = self.store.config('decision_cli_capabilities', {})
        return dict(rows) if isinstance(rows, dict) else {}

    # -- engines ------------------------------------------------------------
    def _direct_engine(self, audit, route=None):
        return ModelDecisionEngine(self.service.adapter, lambda: self._direct_resolve(route), audit=audit)

    def _direct_resolve(self, route):
        """The #417/#580 direct destination and key, with an activated model (#679).

        The destination and key still come only from ``service.decision_route``;
        an owner-activated route adds only the qualified model for the same
        provider, so a model choice never changes where a judgment goes.
        """
        resolved = self.service.decision_route()
        if not resolved:
            return None
        config, key = resolved
        model = (route or {}).get('requested_model')
        if model and (route or {}).get('provider') == config.get('provider') and valid_model_id(model):
            config = {**config, 'model': model}
        return config, key

    def _jev_engine(self, model, audit):
        kwargs = {'transport': self.jev_transport} if self.jev_transport else {}
        return JevDecisionEngine(lambda: self.store.secret('decision_jev_key') or '', model=model,
                                 audit=audit, **kwargs)

    def _cli_engine(self, engine_id, model, policy, audit, guard=None, codex_disabled_features=None, effort=None):
        return SubscriptionCliDecisionEngine(self.service.execution_adapter, engine_id, model=model,
                                             model_policy=policy, audit=audit, guard=guard,
                                             codex_disabled_features=codex_disabled_features, effort=effort)

    def engine(self):
        """The engine for the next judgment, from the active route only."""
        audit = self.service.record_decision
        route = self.active()
        if route is not None and route.get('mode') == MODE_FOLLOW:
            if route.get('main') != self.service.main_ai.current():
                # Resolved for a previous Main AI: no stale destination.
                return UnavailableDecisionEngine()
            if route['transport'] == ROUTE_DIRECT_API:
                return ModelDecisionEngine(self.service.adapter, lambda: self._follow_resolve(route), audit=audit)
        if route is None or route['transport'] == ROUTE_DIRECT_API:
            return self._direct_engine(audit, route)
        if route['transport'] == ROUTE_OFF:
            return UnavailableDecisionEngine()
        if route['transport'] == ROUTE_JEV:
            return self._jev_engine(route.get('requested_model') or JEV_DEFAULT_MODEL, audit)
        engine_id, policy = route.get('engine'), route.get('model_policy')
        if engine_id not in CLI_BINARIES or policy not in MODEL_POLICIES:
            return UnavailableDecisionEngine()
        model = None if policy == POLICY_ENGINE_DEFAULT else route.get('requested_model')
        fingerprint = route.get('fingerprint') or ''

        def guard():
            # The isolation-flag check, the Codex tool-surface plan and any
            # verified model describe the CLI binary they were checked
            # against; a changed binary needs a new check, for every policy.
            if self.service.isolated_engine_adapter:
                return 'isolated-deployment'
            if fingerprint != cli_fingerprint(self.service.execution_adapter.finder(CLI_BINARIES[engine_id])):
                return 'requalification-needed'
            if engine_id == 'codex' and not self._codex_instructions_qualified(route):
                return 'instruction-files-unqualified'
            if engine_id == 'codex' and not self._codex_strict_recorded(route):
                # #679: a Codex judgment runs only under a passed strict
                # qualification on this platform (a route stored before #679,
                # or moved to another OS, has none).
                return 'strict-profile-unqualified'
            return ''

        effort = route.get('effort') if valid_effort(route.get('effort')) else None
        return self._cli_engine(engine_id, model, policy, audit, guard,
                                route.get('codex_disabled_features') if engine_id == 'codex' else None, effort)

    def _main_key(self, main_id):
        """The Main AI's own probed Work key (``model_key``), only while ``main_id`` is it.

        Not the provider slot: a newly saved, not yet probed key in the slot
        must not reach judgments before 확인하고 사용 (#643 review P2-1), and
        the Work and the Judgment AI always use the same account.
        """
        # One consistent snapshot: a Main AI switch writes `model` and
        # `model_key` under the same lock, so a key never pairs with another
        # provider's endpoint mid-switch (#643 review).
        with self.service.lock:
            if self.service.main_ai.current() != main_id or api_route_of(self.store.config('model', {})) != main_id:
                return ''
            return self.store.secret('model_key') or ''

    def _follow_resolve(self, route):
        """``(config, key)`` of a follow row: the Main AI's probed key, read live.

        A removed key makes the route unavailable; nothing falls back.
        """
        key = self._main_key(route.get('main', ''))
        config = {'provider': route.get('provider'), 'endpoint': route.get('endpoint'),
                  'model': route.get('requested_model')}
        return (config, key) if key else None

    def mode(self, route=None):
        route = self.active() if route is None else route
        if route is None or route.get('mode') == MODE_FOLLOW:
            return MODE_FOLLOW
        return ROUTE_OFF if route['transport'] == ROUTE_OFF else 'explicit'

    def follow_preview(self, main_id):
        """What following ``main_id`` would resolve to.  No call, no subprocess."""
        candidate = FOLLOW_CANDIDATES.get(main_id)
        if not candidate:
            return {'main': main_id, 'available': False,
                    'reason': FOLLOW_UNAVAILABLE.get(main_id, FOLLOW_UNAVAILABLE['other'])}
        if candidate['transport'] == ROUTE_DIRECT_API:
            candidates = list(candidate['candidates'])
            return {'main': main_id, 'available': True, 'transport': ROUTE_DIRECT_API,
                    'model': candidates[0], 'candidates': candidates, 'model_policy': candidate['model_policy'],
                    'destination': urlsplit(candidate['config']['endpoint']).hostname}
        if self.service.isolated_engine_adapter:
            return {'main': main_id, 'available': False,
                    'reason': '격리 런타임 배포에서는 구독 AI를 판단 AI로 쓸 수 없습니다.'}
        candidates = self._ranked(candidate['engine'])
        return {'main': main_id, 'available': True, 'transport': ROUTE_SUBSCRIPTION_CLI,
                'model': candidates[0] if candidates else '', 'candidates': candidates,
                'model_policy': candidate['model_policy'], 'destination': CLI_DESTINATIONS[candidate['engine']]}

    def _ranked(self, engine_id, capability=None):
        """The ranked candidates for one CLI, filtered by what the installed binary bundles.

        Codex: only models the recorded ``codex debug models --bundled``
        listing names (no listing recorded yet: the whole ranked list, and the
        qualification decides).  No subprocess here.
        """
        ranked = list(RANKED_MODELS.get(engine_id, ()))
        if engine_id != 'codex':
            return ranked
        capability = self._capabilities().get('codex') if capability is None else capability
        bundled = (capability or {}).get('bundled_models')
        if not bundled:
            return ranked
        listed = {row.get('id') for row in bundled}
        return [model for model in ranked if model in listed]

    def follow_main_switched(self, main_id):
        """Called after a successful Main AI switch.  Never raises.

        An explicit or ``off`` Judgment AI is left exactly as it was.  A
        following Judgment AI is re-resolved for the new Main AI; a failure
        leaves it needing attention (no fallback to the previous route).
        """
        if self.mode() != MODE_FOLLOW:
            return {'state': 'unchanged', 'mode': self.mode()}
        with self._activating:
            # Re-check under the lock: an explicit choice that finished while
            # this switch waited is the owner's latest decision (#643 review).
            if self.mode() != MODE_FOLLOW:
                return {'state': 'unchanged', 'mode': self.mode()}
            try:
                return self._follow(main_id, keep_previous=False)
            except Exception:  # never report a committed Main AI switch as failed
                with self.service.lock:
                    self.store.put('decision_route', {'mode': MODE_FOLLOW, 'main': main_id, 'transport': ROUTE_OFF,
                                                      'failure': 'probe-failed', 'activated_at': self.clock()})
                return {'state': 'attention', 'failure': 'probe-failed',
                        'message': '판단 AI를 확인하는 중 오류가 났습니다.'}

    def _follow(self, main_id, keep_previous):
        option = f'{MODE_FOLLOW}:{main_id}'

        def failed(failure, message, **extra):
            if keep_previous:
                self._fail(option, failure, message, **extra)
            self._record_check(option, {'state': 'failed', 'failure': failure, **extra})
            with self.service.lock:
                self.store.put('decision_route', {'mode': MODE_FOLLOW, 'main': main_id, 'transport': ROUTE_OFF,
                                                  'failure': failure, 'activated_at': self.clock()})
            return {'state': 'attention', 'failure': failure, 'message': message}

        candidate = FOLLOW_CANDIDATES.get(main_id)
        if not candidate:
            return failed('follow-unsupported', FOLLOW_UNAVAILABLE.get(main_id, FOLLOW_UNAVAILABLE['other']))
        follow = {'mode': MODE_FOLLOW, 'main': main_id}
        if candidate['transport'] == ROUTE_DIRECT_API:
            key = self._main_key(main_id)
            if not key:
                return failed('not-configured', '기본 AI의 API 키가 없어 판단 AI를 확인하지 못했습니다.')
            base = dict(candidate['config'])
            # #679: the ranked cheapest-first list, each through the full
            # qualification suite; the first that passes is used.
            model, result, tried = self._first_qualified(
                candidate['candidates'],
                lambda name, audit: ModelDecisionEngine(self.service.adapter,
                                                        lambda: ({**base, 'model': name}, key), audit=audit))
            if not model:
                return failed('no-qualified-candidate',
                              f'판단 AI 후보({", ".join(candidate["candidates"])}) 중 적격성 검사({SUITE_VERSION})를 '
                              '통과한 모델이 없습니다.', candidates=tried, suite_version=SUITE_VERSION)
            self._commit(option, {**follow, 'transport': ROUTE_DIRECT_API, 'provider': base['provider'],
                                  'endpoint': base['endpoint'], 'requested_model': model, 'key_source': 'main',
                                  'model_policy': POLICY_LOWEST_QUALIFIED,
                                  'qualification': self._qualification_record(model, result)},
                         {'model_policy': POLICY_LOWEST_QUALIFIED, 'requested_model': model, 'candidates': tried,
                          'suite_version': result['suite_version'], 'observed_model': tried[-1]['observed_model']})
            return {'state': 'active'}
        try:
            # No candidates: the ranked list, filtered by the capability check
            # that activation itself runs (#679).
            self._activate_cli({'engine': candidate['engine'], 'model_policy': candidate['model_policy']}, extra=follow)
        except DecisionRouteError as exc:
            if keep_previous:
                raise
            self._record_check(option, {'state': 'failed', 'failure': 'probe-failed'})
            with self.service.lock:
                self.store.put('decision_route', {**follow, 'transport': ROUTE_OFF, 'failure': 'probe-failed',
                                                  'activated_at': self.clock()})
            return {'state': 'attention', 'failure': 'probe-failed', 'message': str(exc)}
        self._record_check(option, {'state': 'active'})
        return {'state': 'active'}

    def _codex_instructions_qualified(self, route):
        # #624: a stored Codex route is usable only while its recorded CLI
        # version is instruction-file qualified (the same rule as activation).
        return parse_cli_version('codex', route.get('cli_version') or '') in self.codex_instruction_qualified

    @staticmethod
    def _codex_strict_recorded(route):
        strict = route.get('strict_profile')
        return isinstance(strict, dict) and strict.get('platform') == sys.platform

    def _first_qualified(self, candidates, make_engine):
        """Run ``qualify()`` on each candidate in order; ``(model, result, tried)``.

        ``tried`` is content free.  ``(None, None, tried)`` when none passed;
        no other model is tried.
        """
        tried = []
        for model in candidates:
            seen = []  # content-free records of the qualification calls, for observed identity only
            engine = make_engine(model, seen.append)
            result = qualify(engine)
            observed = sorted({row.get('observed_model') for row in seen
                               if row.get('observed_model') and row.get('observed_model') != 'not reported'})
            failures = [row.get('failure') for row in seen if row.get('failure')]
            tried.append({'model': model, 'qualified': result['qualified'], 'score': result['score'],
                          'ran': result['ran'], 'failure': getattr(engine, 'last_failure', '') or
                          (failures[-1] if failures else ''),
                          'observed_model': ', '.join(observed) or 'not reported'})
            if result['qualified']:
                return model, result, tried
        return None, None, tried

    def _qualification_record(self, model, result, capability=None):
        record = {'suite_version': result['suite_version'], 'model': model, 'score': result['score'],
                  'at': self.clock()}
        if capability:
            record.update(cli_version=capability['version'], fingerprint=capability['fingerprint'])
        return record

    def _cli_requalify(self, route):
        # Same check as the runtime guard (a local stat, no subprocess), for
        # every policy: the checked isolation/tool surface belongs to the
        # binary it was checked against.
        return (route.get('engine') in CLI_BINARIES
                and (route.get('fingerprint') or '') != cli_fingerprint(
                    self.service.execution_adapter.finder(CLI_BINARIES[route['engine']])))

    def _cli_active(self, route, engines, stale=False):
        engine = next((e for e in engines if e['id'] == route.get('engine')), None)
        requalify = self._cli_requalify(route)
        codex = route.get('engine') == 'codex'
        unqualified = codex and not self._codex_instructions_qualified(route)
        strict_missing = codex and not self._codex_strict_recorded(route)
        return dict(destination=CLI_DESTINATIONS.get(route.get('engine'), ''),
                    requalification_needed=requalify, instruction_files_unqualified=unqualified,
                    strict_profile_unqualified=strict_missing,
                    available=bool(engine and engine['installed'] and engine['login'] != 'signed-out'
                                   and not engine['isolated_deployment'] and not requalify and not unqualified
                                   and not strict_missing and not stale))

    # -- read model (no subprocess, no model call) ---------------------------
    def status(self):
        route = self.active()
        resolved = self.service.decision_route()
        checks = self._checks()
        capabilities = self._capabilities()
        direct_config = resolved[0] if resolved else None
        explicit = self.store.config('decision_model', {})
        key_source = ('decision' if isinstance(explicit, dict) and explicit.get('provider') and resolved
                      else 'work-api' if resolved else '')
        has_decision_key = bool(self.store.secret('decision_model_key'))
        direct_resolved = self._direct_resolve(route if route and route.get('transport') == ROUTE_DIRECT_API
                                               and route.get('mode') != MODE_FOLLOW else None)
        direct = {'transport': ROUTE_DIRECT_API, 'configured': bool(resolved) or has_decision_key,
                  'provider': direct_config['provider'] if direct_config else DEFAULT_DECISION_PROVIDER['provider'],
                  'model': direct_resolved[0]['model'] if direct_resolved else DEFAULT_DECISION_MODEL,
                  'destination': urlsplit((direct_config or DEFAULT_DECISION_PROVIDER)['endpoint']).hostname,
                  'key_source': key_source, 'has_decision_key': bool(self.store.secret('decision_model_key')),
                  # #679: the ranked cheapest-first candidates the activation qualifies in order.
                  'ranked_models': list(RANKED_MODELS['openai']),
                  'check': checks.get(ROUTE_DIRECT_API)}
        jev_config = self.store.config('decision_jev', {})
        jev = {'transport': ROUTE_JEV, 'configured': bool(self.store.secret('decision_jev_key')),
               'model': (jev_config.get('model') if isinstance(jev_config, dict) else None) or JEV_DEFAULT_MODEL,
               'destination': JEV_DESTINATION, 'check': checks.get(ROUTE_JEV)}
        engines = []
        for item in self.service.subscription_engine_status()['engines']:
            engine_id = item['id']
            if engine_id not in CLI_BINARIES:
                continue
            capability = capabilities.get(engine_id) or {}
            ranked = self._ranked(engine_id, capability)
            engines.append({'id': engine_id, 'name': ENGINE_NAMES[engine_id], 'installed': bool(item.get('installed')),
                            'login': (item.get('login') or {}).get('state', 'unchecked'),
                            'isolated_deployment': bool(self.service.isolated_engine_adapter),
                            'capabilities': capability or None,
                            'model_selection': ('supported' if capability.get('model_override') is True
                                                else 'unsupported' if capability.get('model_override') is False
                                                else 'unchecked'),
                            # A refused tool surface is shown with its reason.
                            'tool_surface': capability.get('tool_surface'),
                            'tool_surface_detail': capability.get('tool_surface_detail') or '',
                            'destination': CLI_DESTINATIONS[engine_id],
                            'instruction_files': CODEX_INSTRUCTION_FILES_LIMITATION if engine_id == 'codex' else '',
                            # #679: cheapest-first defaults and the efforts each supports.
                            'ranked_models': ranked,
                            'model_efforts': {model: list(supported_efforts(engine_id, model, capability))
                                              for model in ranked},
                            'check': checks.get(f'{ROUTE_SUBSCRIPTION_CLI}:{engine_id}')})
        main = self.service.main_ai.current()
        follow = self.follow_preview(main) if main else {'main': '', 'available': False,
                                                            'reason': '기본 AI가 아직 없습니다.'}
        if route is not None and route.get('mode') == MODE_FOLLOW:
            stale = route.get('main') != main
            active = {**{k: v for k, v in route.items() if k not in ('fingerprint',)}, 'source': 'follow', 'stale': stale}
            if route['transport'] == ROUTE_DIRECT_API:
                active.update(destination=urlsplit(route.get('endpoint') or '').hostname,
                              available=bool(self._follow_resolve(route)) and not stale)
            elif route['transport'] == ROUTE_SUBSCRIPTION_CLI:
                active.update(self._cli_active(route, engines, stale))
            else:
                active.update(available=False)
        elif route is None:
            active = ({'transport': ROUTE_DIRECT_API, 'source': 'default', 'provider': direct['provider'],
                       'requested_model': direct['model'], 'destination': direct['destination'], 'available': True}
                      if resolved else {'transport': 'none', 'source': 'default'})
        else:
            active = {**{k: v for k, v in route.items() if k not in ('fingerprint',)}, 'source': 'owner'}
            if route['transport'] == ROUTE_DIRECT_API:
                active.update(provider=direct['provider'], requested_model=direct['model'],
                              destination=direct['destination'], available=bool(resolved))
            elif route['transport'] == ROUTE_JEV:
                active.update(destination=JEV_DESTINATION, available=jev['configured'])
            elif route['transport'] == ROUTE_SUBSCRIPTION_CLI:
                active.update(self._cli_active(route, engines))
        follow_check = checks.get(f'{MODE_FOLLOW}:{main}') if main else None
        return {'active': active, 'direct_api': direct, 'jev': jev, 'subscription_cli': engines,
                'suite_version': SUITE_VERSION, 'mode': self.mode(route), 'main': main, 'follow': follow,
                'follow_candidates': {route_id: self.follow_preview(route_id) for route_id in CHOOSER_ORDER},
                'follow_check': follow_check,
                'effective': self.effective(active, route, main, follow, follow_check),
                'model_lists': self._model_lists()}

    def effective(self, active, route, main, follow, follow_check=None):
        """What answers the next judgment, in words the owner can check (#679).

        ``state`` is ``active`` (a route is in use), ``fallback`` (the #417
        default OpenAI API answers although the Judgment AI is meant to follow
        the Main AI - said out loud, never silent), ``attention`` (nothing
        answers until the owner acts) or ``off``.  ``template``/``params``
        (and ``reason_template``/``reason_params``) let Settings translate
        the sentence; ``text`` is the Korean rendering.  Read-only; no call.
        """
        main_name = ROUTE_NAMES.get(main, main or '-')
        model = active.get('requested_model') or ''

        def said(state, template, reason=('', {}), **params):
            reason_template, reason_params = reason
            reason_text = reason_template.format(**reason_params) if reason_template else ''
            return {'state': state, 'transport': active.get('transport') or 'none', 'model': model,
                    'destination': active.get('destination') or '', 'template': template, 'params': params,
                    'reason_template': reason_template, 'reason_params': reason_params, 'reason': reason_text,
                    'text': template.format(**params, reason=reason_text)}

        verified = '검증됨' if active.get('qualification') else '확인됨'
        if route is not None and route.get('transport') == ROUTE_OFF and route.get('mode') != MODE_FOLLOW:
            return said('off', '판단 AI를 쓰지 않습니다. 판단이 필요한 기능은 건너뜁니다.')
        if active.get('source') == 'default':
            if follow.get('available') and follow.get('transport') == ROUTE_SUBSCRIPTION_CLI:
                reason = ('기본 AI({main})를 따르는 구독 판단을 아직 확인하지 않았습니다. 확인을 누르면 가장 저렴한 모델부터 검증합니다.',
                          {'main': main_name})
            elif follow.get('available'):
                reason = ('기본 AI({main})를 따르는 판단 AI를 아직 확인하지 않았습니다.', {'main': main_name})
            else:
                reason = (follow.get('reason') or '기본 AI를 따라갈 수 없습니다.', {})
            if active.get('transport') != ROUTE_DIRECT_API:
                return said('attention', '판단 AI를 쓸 수 없어 판단이 필요한 기능은 건너뜁니다: {reason}', reason)
            template = ('구독 판단을 쓸 수 없어 OpenAI API({model})를 쓰는 중: {reason}' if main in CLI_BINARIES
                        else '판단 AI를 아직 확인하지 않아 OpenAI API({model})를 쓰는 중: {reason}')
            return said('fallback', template, reason, model=model)
        if active.get('source') == 'follow':
            if active.get('available'):
                return said('active', '기본 AI({main})를 따라가는 중 — {model}, {verified}',
                            main=main_name, model=model or '-', verified=verified)
            if active.get('stale'):
                reason = ('기본 AI가 {main}(으)로 바뀌어 판단 AI를 다시 확인해야 합니다.', {'main': main_name})
            elif active.get('transport') == ROUTE_OFF:
                reason = ('기본 AI({main})를 따르는 판단 AI 확인에 실패했습니다.', {'main': main_name})
            elif active.get('requalification_needed'):
                reason = ('CLI가 바뀌어 다시 확인해야 합니다.', {})
            else:
                reason = ('판단 AI를 지금 쓸 수 없습니다.', {})
            return said('attention', '판단 AI를 쓰지 못하는 중: {reason} 다른 경로로 자동 전환하지 않습니다.', reason)
        # Explicitly chosen (따로 지정).
        transport = active.get('transport')
        label = ({ROUTE_DIRECT_API: 'OpenAI API' if active.get('provider') == 'openai' else 'API', ROUTE_JEV: 'Jev (TypeSafe)',
                  ROUTE_SUBSCRIPTION_CLI: ENGINE_NAMES.get(active.get('engine'), active.get('engine') or '-')}
                 .get(transport, transport or '-'))
        if active.get('available') is False:
            reason = (('CLI가 바뀌어 다시 확인해야 합니다.' if active.get('requalification_needed')
                       else '엄격 격리 검증이 필요합니다.' if active.get('strict_profile_unqualified')
                       else '연결 정보가 없거나 확인이 필요합니다.'), {})
            return said('attention', '따로 지정한 판단 AI({label})를 쓰지 못하는 중: {reason} 다른 경로로 자동 전환하지 않습니다.',
                        reason, label=label)
        return said('active', '따로 지정한 판단 AI를 쓰는 중: {label} — {model}, {verified}', label=label,
                    model=model or '기본 모델', verified=verified)

    def _model_lists(self):
        rows = self.store.config('decision_model_lists', {})
        return dict(rows) if isinstance(rows, dict) else {}

    # -- explicit owner actions ---------------------------------------------
    def save_credential(self, body):
        """Store (or remove) a decision-route credential.  Never activates."""
        if not isinstance(body, dict):
            raise DecisionRouteError('저장할 연결 정보를 확인하세요.')
        transport, key = body.get('transport'), body.get('key')
        if not isinstance(key, str) or len(key) > 4096 or any(ch.isspace() for ch in key.strip()):
            raise DecisionRouteError('API 키 한 줄을 그대로 붙여 넣으세요.')
        key = key.strip()
        if transport == ROUTE_JEV:
            model = body.get('model') or JEV_DEFAULT_MODEL
            if not valid_model_id(model):
                raise DecisionRouteError('Jev 모델 이름 형식을 확인하세요.')
            with self.service.lock:
                self.store.secret('decision_jev_key', key)
                self.store.put('decision_jev', {'model': model})
        elif transport == ROUTE_DIRECT_API:
            # Only the key (#580 review F1).  `decision_model` - which the
            # #417 resolver treats as a configured provider - is written only
            # by a successful activation, so saving a key never starts egress.
            with self.service.lock:
                self.store.secret('decision_model_key', key)
        else:
            raise DecisionRouteError('키를 저장할 수 있는 대화 해석 경로가 아닙니다.')
        return self.status()

    def check_cli_capabilities(self, engine_id):
        """Read what the installed CLI's own help declares.  Local only: no
        login, no model request, no owner configuration read."""
        if engine_id not in CLI_BINARIES:
            raise DecisionRouteError('지원하는 구독 엔진을 선택하세요.')
        execution = self.service.execution_adapter
        binary = execution.finder(CLI_BINARIES[engine_id])
        if not binary:
            raise DecisionRouteError(f'{ENGINE_NAMES[engine_id]} CLI를 찾지 못했습니다.')
        help_argv = [binary, 'exec', '--help'] if engine_id == 'codex' else [binary, '--help']
        record = self._with_local_run(engine_id, binary,
                                      lambda run: self._capability_record(engine_id, binary, help_argv, run))
        with self.service.lock:
            rows = self._capabilities()
            rows[engine_id] = record
            self.store.put('decision_cli_capabilities', rows)
        return record

    def _with_local_run(self, engine_id, binary, action):
        """Call ``action(run)`` with a local, model-free CLI runner.

        An empty per-call HOME / CODEX_HOME: listings show the CLI's own
        defaults, which is what `--ignore-user-config` runs with, and nothing
        the CLI caches lands in the owner's profile.
        """
        execution = self.service.execution_adapter
        name = ENGINE_NAMES[engine_id]
        execution.runtime_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(dir=execution.runtime_root, prefix='capability-') as folder:
            env = {'HOME': folder, 'CODEX_HOME': folder, 'PATH': f'{Path(binary).parent}:/usr/bin:/bin',
                   'LANG': 'C.UTF-8'}

            def run(argv):
                try:
                    done = bounded_run(execution.runner, argv, cwd=folder, env=env, timeout=20)
                except (subprocess.TimeoutExpired, OSError) as exc:
                    raise DecisionRouteError(f'{name} CLI 기능을 확인하지 못했습니다 ({type(exc).__name__}).') from None
                return done.returncode, (done.stdout or ''), (getattr(done, 'stderr', '') or '')

            return action(run)

    def _capability_record(self, engine_id, binary, help_argv, run):
        _code, help_out, help_err = run(help_argv)
        _code, version_out, _err = run([binary, '--version'])
        help_text = help_out + '\n' + help_err
        missing = [flag for flag in REQUIRED_FLAGS[engine_id] if not has_flag(help_text, flag)]
        record = {'version': ' '.join(version_out.split())[:80], 'isolation_flags': not missing,
                  'missing_flags': missing, 'model_override': has_flag(help_text, MODEL_FLAG),
                  'fingerprint': cli_fingerprint(binary), 'checked_at': self.clock(), 'source': 'cli --help'}
        if engine_id == 'codex' and not missing:
            record.update(self._codex_tool_surface(run, binary))
        if engine_id == 'codex':
            record['bundled_models'] = self._codex_bundled_models(run, binary)
        return record

    @staticmethod
    def _codex_bundled_models(run, binary):
        """The installed binary's own model catalogue, or None (#679).

        Only ``codex debug models --bundled``: the catalogue compiled into the
        binary, no network.  The plain ``codex debug models`` would refresh
        the shared ``$CODEX_HOME/models_cache.json`` and is never run; ``run``
        also uses an empty CODEX_HOME.  Listed is not account-supported.
        """
        code, out, _err = run([binary, 'debug', 'models', '--bundled'])
        if code != 0:
            return None
        try:
            return parse_bundled_models(out)
        except ValueError:
            return None

    @staticmethod
    def _codex_tool_surface(run, binary):
        """Plan and verify the Codex feature set for decision calls (allowlist).

        Reads ``codex features list`` (local, no model call), disables every
        enabled feature outside the allowlist, reads the listing again with
        those disables and records whether only allowlisted features remain.
        Anything unparsable or still enabled fails closed.  #679: the
        allowlist is the #616 strict profile's (``strict_allowed_features``):
        ``unified_exec`` may stay listed as enabled because ``shell_tool`` is
        disabled (no command tool is offered) and the strict permissions
        profile would still confine a command.
        """
        allowed = strict_allowed_features()
        code, out, err = run([binary, 'features', 'list'])
        try:
            if code != 0:
                raise ValueError((err or out).strip()[:120] or f'exit {code}')
            plan = codex_disable_plan(parse_codex_features(out), allowed)
            argv = [binary, 'features', 'list']
            for feature in plan:
                argv += ['--disable', feature]
            code, out, err = run(argv)
            if code != 0:
                raise ValueError((err or out).strip()[:120] or f'exit {code}')
            remaining = codex_still_enabled(parse_codex_features(out), allowed)
        except ValueError as exc:
            return {'tool_surface': 'unverified', 'tool_surface_detail': str(exc)[:160], 'codex_disabled_features': None}
        if remaining:
            return {'tool_surface': 'tool-features-enabled', 'tool_surface_detail': ', '.join(remaining)[:160],
                    'codex_disabled_features': None}
        return {'tool_surface': 'allowlisted-features-only', 'codex_disabled_features': plan}

    def _probe(self, engine):
        """One synthetic judgment; ``(ok, decision)``."""
        decision = engine.choose(DecisionContext('decision-route-probe', PROBE_CONTEXT),
                                 ('retry', 'reference', 'cancel', 'correction'),
                                 'How does the owner message relate to the previous Work? This judgment authorizes nothing.')
        return decision.outcome == OUTCOME_DECIDED, decision

    def _fail(self, option, failure, message, **extra):
        self._record_check(option, {'state': 'failed', 'failure': failure, **extra})
        raise DecisionRouteError(message + ' 현재 대화 해석 경로는 그대로 유지됩니다.')

    def _commit(self, option, route, check):
        route = {**route, 'activated_at': self.clock()}
        self._record_check(option, {'state': 'active', **check})
        with self.service.lock:
            # Only the decision route row.  The Work-execution rows
            # (`subscription_engine`, `model`) are never written here.
            self.store.put('decision_route', route)
        return self.status()

    def activate(self, body):
        """Make one route the active DecisionEngine route after it proves it can answer.

        Explicit owner action only.  Any failure raises and leaves the
        previous route exactly as it was.  One activation runs at a time; a
        concurrent request is refused rather than racing the route row.
        """
        if not self._activating.acquire(blocking=False):
            raise DecisionRouteError('이미 대화 해석 경로를 확인하고 있습니다. 끝난 뒤 다시 시도하세요.')
        try:
            return self._activate(body)
        finally:
            self._activating.release()

    def _activate(self, body):
        if isinstance(body, dict) and body.get('transport') == MODE_FOLLOW:
            # Explicit owner choice of 기본 AI 따라가기: a failure keeps the
            # previous Judgment AI exactly as it was.
            main = self.service.main_ai.current()
            if not main:
                raise DecisionRouteError('기본 AI가 아직 없어 따라갈 수 없습니다.')
            self._follow(main, keep_previous=True)
            return self.status()
        if not isinstance(body, dict) or body.get('transport') not in TRANSPORTS:
            raise DecisionRouteError('대화 해석에 사용할 방식을 선택하세요.')
        transport = body['transport']
        if transport == ROUTE_OFF:
            return self._commit(ROUTE_OFF, {'transport': ROUTE_OFF}, {})
        if transport == ROUTE_DIRECT_API:
            return self._activate_direct(body)
        if transport == ROUTE_JEV:
            if not self.store.secret('decision_jev_key'):
                self._fail(ROUTE_JEV, 'not-configured', 'Jev(TypeSafe) API 키가 저장되어 있지 않습니다.')
            config = self.store.config('decision_jev', {})
            model = (config.get('model') if isinstance(config, dict) else None) or JEV_DEFAULT_MODEL
            engine = self._jev_engine(model, None)
            ok, decision = self._probe(engine)
            if not ok:
                self._fail(ROUTE_JEV, engine.last_failure or decision.outcome, 'Jev가 확인 판단에 답하지 않았습니다.')
            return self._commit(ROUTE_JEV, {'transport': ROUTE_JEV, 'provider': 'typesafe', 'requested_model': model},
                                {'observed_model': decision.confidence.observed_model or 'not reported'})
        return self._activate_cli(body)

    def _activate_direct(self, body):
        """The direct API route: the ranked list, or the owner's one model, through ``qualify()`` (#679).

        The destination and key are exactly the pre-#679 ones (a decision-only
        OpenAI key, or the #417 default); only the model is chosen here.
        """
        decision_key = self.store.secret('decision_model_key') or ''
        if decision_key:
            # A saved decision-only key: exactly that destination/key.
            base, key = dict(DEFAULT_DECISION_PROVIDER), decision_key
        elif self.service.decision_route():
            base, key = self.service.decision_route()
        else:
            self._fail(ROUTE_DIRECT_API, 'not-configured', 'OpenAI API 키가 없어 대화 해석에 사용할 수 없습니다.')
        model = body.get('model') or None
        if model is not None and not valid_model_id(model):
            raise DecisionRouteError('사용할 모델 이름 형식을 확인하세요.')
        if model:
            policy, candidates = POLICY_EXPLICIT, [model]
        elif base['provider'] == 'openai':
            policy, candidates = POLICY_LOWEST_QUALIFIED, list(RANKED_MODELS['openai'])
        else:
            policy, candidates = POLICY_EXPLICIT, [base['model']]
        chosen, result, tried = self._first_qualified(
            candidates, lambda name, audit: ModelDecisionEngine(self.service.adapter,
                                                                lambda: ({**base, 'model': name}, key), audit=audit))
        if not chosen:
            self._fail(ROUTE_DIRECT_API, 'model-not-verified' if model else 'no-qualified-candidate',
                       f'OpenAI API 모델({", ".join(candidates)}) 중 대화 해석 적격성 검사({SUITE_VERSION})를 통과한 모델이 '
                       '없습니다.', candidates=tried, suite_version=SUITE_VERSION,
                       **({'requested_model': model} if model else {}))
        if decision_key:
            # Written only here, after the qualification passed (#580 review F1).
            with self.service.lock:
                self.store.put('decision_model', {**DEFAULT_DECISION_PROVIDER, 'model': chosen})
        return self._commit(ROUTE_DIRECT_API, {'transport': ROUTE_DIRECT_API, 'provider': base['provider'],
                                               'requested_model': chosen, 'model_policy': policy,
                                               'qualification': self._qualification_record(chosen, result),
                                               'key_source': 'decision' if decision_key else 'existing'},
                            {'observed_model': tried[-1]['observed_model'], 'model_policy': policy,
                             'requested_model': chosen, 'candidates': tried, 'suite_version': result['suite_version']})

    def _codex_strict_profile(self, option, binary):
        """The #616 strict-isolated qualification, reused for Codex judgments (#679).

        ``BoundedExecutionAdapter.qualify_strict`` (no model): tested platform
        and CLI version, an engine runtime root outside the paths Codex's
        baseline keeps readable, Codex's own sandbox runner under the exact
        permissions profile refusing the owner store, the home folder, the
        login profile and a sibling turn directory while the turn directory
        stays readable, and the strict feature plan leaving only allowlisted
        features.  Any failure refuses activation; nothing falls back to the
        read-only sandbox.
        """
        qualify_strict = getattr(self.service.execution_adapter, 'qualify_strict', None)
        if not callable(qualify_strict):
            self._fail(option, 'strict-profile-unqualified',
                       '이 실행 환경에서는 Codex 판단의 엄격 격리를 검증할 수 없습니다.')
        result = qualify_strict('codex', binary=binary, store_root=self.store.root)
        if not result.get('qualified') or not result.get('disabled_features'):
            self._fail(option, 'strict-profile-unqualified',
                       f'Codex 판단용 엄격 격리 검증을 통과하지 못했습니다({result.get("reason") or "unknown"}).',
                       detail=str(result.get('reason') or '')[:160])
        return {'version': result.get('version'), 'platform': sys.platform, 'checked_at': self.clock(),
                'checks': [check.get('check') for check in result.get('checks') or ()],
                'disabled_features': list(result['disabled_features'])}

    def _codex_instruction_files(self):
        """Non-empty global instruction files in CODEX_HOME, by name and size only (#624/#679).

        A ``stat``; AgentOS never opens, reads or records their content.
        """
        profile = getattr(self.service.execution_adapter, '_login_profile', None)
        home = Path(profile()) if callable(profile) else None
        present = []
        for name in CODEX_INSTRUCTION_FILES:
            try:
                size = (home / name).stat().st_size if home else 0
            except OSError:
                continue
            if size > 0:
                present.append({'file': name, 'bytes': size})
        return present

    def _activate_cli(self, body, extra=None):
        engine_id, policy = body.get('engine'), body.get('model_policy') or POLICY_LOWEST_QUALIFIED
        if engine_id not in CLI_BINARIES:
            raise DecisionRouteError('지원하는 구독 엔진을 선택하세요.')
        if policy not in MODEL_POLICIES:
            raise DecisionRouteError('판단 모델 방식을 선택하세요.')
        requested_effort = body.get('effort') or None
        if requested_effort is not None and not valid_effort(requested_effort):
            raise DecisionRouteError('추론 강도를 확인하세요.')
        option = f'{ROUTE_SUBSCRIPTION_CLI}:{engine_id}'
        name = ENGINE_NAMES[engine_id]
        if self.service.isolated_engine_adapter:
            self._fail(option, 'isolated-deployment', '격리 런타임 배포에서는 구독 AI를 대화 해석에 아직 사용할 수 없습니다.')
        execution = self.service.execution_adapter
        binary = execution.finder(CLI_BINARIES[engine_id])
        if not binary:
            self._fail(option, 'cli-not-found', f'{name} CLI를 찾지 못했습니다.')
        login = self.service.check_engine_login(engine_id)
        if login.get('state') == 'signed-out':
            self._fail(option, 'auth', f'{name}에 로그인되어 있지 않습니다.')
        capability = self.check_cli_capabilities(engine_id)
        if not capability['isolation_flags']:
            self._fail(option, 'isolation-flags-missing',
                       f'설치된 {name} CLI가 격리 실행에 필요한 옵션을 지원하지 않습니다.',
                       missing_flags=capability['missing_flags'])
        disabled = capability.get('codex_disabled_features') if engine_id == 'codex' else None
        if engine_id == 'codex' and capability.get('tool_surface') != 'allowlisted-features-only':
            # Fail closed: the tool-bearing feature set could not be reduced to
            # the allowlist on this CLI version (#580 review F2).
            self._fail(option, 'tool-surface-unverified',
                       f'설치된 {name} CLI에서 도구 기능을 모두 끌 수 있는지 확인하지 못했습니다.',
                       detail=capability.get('tool_surface_detail') or capability.get('tool_surface') or '')
        if engine_id == 'codex' and parse_cli_version('codex', capability['version']) not in self.codex_instruction_qualified:
            # #624: CODEX_HOME instruction files reach the prompt and no
            # official option stops them; a version is allowed only after the
            # no-model harness was re-run and the limitation is shown.
            self._fail(option, 'instruction-files-unqualified',
                       f'설치된 {name} CLI가 로그인 프로필의 지침 파일을 판단 요청에 보내는지 아직 확인하지 않았습니다.',
                       detail=CODEX_INSTRUCTION_FILES_LIMITATION)
        codex_extra = {}
        if engine_id == 'codex':
            strict = self._codex_strict_profile(option, binary)
            # The strict qualification's own verified plan is what a judgment launches with.
            disabled = strict.pop('disabled_features')
            codex_extra = {'codex_disabled_features': disabled, 'strict_profile': strict,
                           'instruction_files_present': self._codex_instruction_files()}
        base = {'transport': ROUTE_SUBSCRIPTION_CLI, 'engine': engine_id, 'model_policy': policy,
                'fingerprint': capability['fingerprint'], 'cli_version': capability['version'],
                **codex_extra, **(extra or {})}
        warning = {'instruction_files_present': codex_extra['instruction_files_present']} if codex_extra else {}

        def effort_for(model):
            levels = supported_efforts(engine_id, model, capability)
            wanted = requested_effort or DEFAULT_EFFORT
            return wanted if wanted in levels else None

        if policy == POLICY_ENGINE_DEFAULT:
            engine = self._cli_engine(engine_id, None, policy, None, codex_disabled_features=disabled)
            ok, decision = self._probe(engine)
            if not ok:
                self._fail(option, engine.last_failure or decision.outcome, f'{name}이(가) 확인 판단에 답하지 않았습니다.')
            return self._commit(option, {**base, 'requested_model': None, 'effort': None},
                                {'observed_model': decision.confidence.observed_model or 'not reported',
                                 'model_policy': policy, **warning})
        if not capability['model_override']:
            self._fail(option, 'model-selection-unsupported',
                       f'설치된 {name} CLI는 모델 지정을 지원하지 않습니다. 구독 AI 기본 모델만 사용할 수 있습니다.')
        if policy == POLICY_EXPLICIT:
            model = body.get('model')
            if not valid_model_id(model):
                raise DecisionRouteError('사용할 모델 이름을 입력하세요.')
            if requested_effort and effort_for(model) != requested_effort:
                raise DecisionRouteError(f'모델 {model}은(는) 추론 강도 {requested_effort}를 지원한다고 확인되지 않았습니다.')
            candidates = [model]
        else:
            candidates = body.get('candidates')
            if candidates in (None, '', []):
                # #679: the ranked cheapest-first list, filtered by what this
                # binary bundles (checked just above).
                candidates = self._ranked(engine_id, capability)
                if not candidates:
                    self._fail(option, 'no-qualified-candidate',
                               f'설치된 {name} CLI의 모델 목록에 기본 후보가 없습니다. 모델을 직접 고르세요.')
            if isinstance(candidates, str):
                candidates = [part.strip() for part in candidates.split(',') if part.strip()]
            if not isinstance(candidates, list) or not 1 <= len(candidates) <= MAX_CANDIDATES \
                    or not all(valid_model_id(item) for item in candidates) or len(set(candidates)) != len(candidates):
                raise DecisionRouteError(f'후보 모델을 가벼운 순서로 1~{MAX_CANDIDATES}개 입력하세요.')
        chosen, result, tried = self._first_qualified(
            candidates, lambda model, audit: self._cli_engine(engine_id, model, policy, audit,
                                                              codex_disabled_features=disabled,
                                                              effort=effort_for(model)))
        if not chosen:
            if policy == POLICY_EXPLICIT:
                model = candidates[0]
                rejected = tried[0]['failure'] == 'request-rejected'
                self._fail(option, 'model-not-verified' if rejected else 'not-qualified',
                           f'{name}에서 모델 {model}을(를) 확인하지 못했습니다'
                           + ('(이 계정/CLI가 거부).' if rejected else f'(적격성 검사 {SUITE_VERSION} 미통과).'),
                           requested_model=model, candidates=tried, suite_version=SUITE_VERSION)
            self._fail(option, 'no-qualified-candidate',
                       f'후보 모델 중 대화 해석 적격성 검사({SUITE_VERSION})를 통과한 모델이 없습니다.',
                       candidates=tried, suite_version=SUITE_VERSION)
        return self._commit(option, {**base, 'requested_model': chosen, 'effort': effort_for(chosen),
                                     'qualification': self._qualification_record(chosen, result, capability)},
                            {'model_policy': policy, 'requested_model': chosen, 'candidates': tried,
                             'observed_model': tried[-1]['observed_model'], 'effort': effort_for(chosen),
                             'suite_version': result['suite_version'], **warning})

    # -- model lists (explicit owner action only, #679) ------------------------
    def _api_list_key(self, route_id):
        """The key that route would use; '' when none is saved.  Never returned."""
        if route_id == 'openai' and self.store.secret('decision_model_key'):
            return self.store.secret('decision_model_key')
        key = self.store.secret(key_slot(route_id)) or ''
        if not key and api_route_of(self.store.config('model', {})) == route_id:
            key = self.store.secret('model_key') or ''
        return key

    def list_models(self, route_id):
        """모델 목록 새로고침: what one route lists, labelled 목록에 있음(검증 전).

        Codex: ``codex debug models --bundled`` only (local, no network, empty
        CODEX_HOME; the plain form, which rewrites the shared
        ``models_cache.json``, is never run).  Claude Code: the documented
        aliases (no machine-readable list exists).  APIs: the provider's
        official ``GET /v1/models`` with the key that route would use,
        narrowed to the ranked candidates (other ids can still be typed).
        Choosing an entry is a separate activation that runs ``qualify()``.
        """
        if route_id not in MODEL_LIST_ROUTES:
            raise DecisionRouteError('모델 목록을 볼 경로를 선택하세요.')
        ranked = list(RANKED_MODELS[route_id])
        if route_id == 'claude-code':
            models, source = [{'id': alias, 'efforts': list(levels)} for alias, levels in CLAUDE_CODE_MODELS.items()], \
                'documented-aliases'
        elif route_id == 'codex':
            if self.service.isolated_engine_adapter:
                raise DecisionRouteError('격리 런타임 배포에서는 구독 AI 모델 목록을 읽지 않습니다.')
            binary = self.service.execution_adapter.finder(CLI_BINARIES['codex'])
            if not binary:
                raise DecisionRouteError('Codex CLI를 찾지 못했습니다.')
            rows = self._with_local_run('codex', binary, lambda run: self._codex_bundled_models(run, binary))
            if rows is None:
                raise DecisionRouteError('Codex CLI의 내장 모델 목록을 읽지 못했습니다.')
            models = [{'id': row['id'], 'efforts': row['efforts']} for row in rows
                      if row['visible'] or row['id'] in ranked]
            source = 'codex debug models --bundled'
        else:
            key = self._api_list_key(route_id)
            if not key:
                raise DecisionRouteError(f'{ROUTE_NAMES[route_id]} 키가 저장되어 있지 않아 모델 목록을 가져올 수 없습니다.')
            headers = ({'Authorization': 'Bearer ' + key} if route_id == 'openai'
                       else {'x-api-key': key, 'anthropic-version': '2023-06-01'})
            try:
                reply = self.models_transport(API_MODEL_LISTS[route_id]['url'], None, headers, 15)
            except ProviderError as exc:
                raise DecisionRouteError(f'{ROUTE_NAMES[route_id]} 모델 목록을 가져오지 못했습니다'
                                         f'({exc.status or "연결 오류"}). 현재 판단 AI는 그대로입니다.') from None
            rows = reply.get('data') if isinstance(reply, dict) else None
            ids = {row.get('id') for row in rows or () if isinstance(row, dict) and isinstance(row.get('id'), str)}
            # A dated id (e.g. `claude-haiku-4-5-20251001`) lists its alias.
            models = [{'id': model, 'efforts': []} for model in ranked
                      if model in ids or any(item.startswith(model + '-') for item in ids)]
            source = 'GET /v1/models'
        rank = {model: index for index, model in enumerate(ranked)}
        models.sort(key=lambda row: rank.get(row['id'], len(ranked)))
        record = {'route': route_id, 'source': source, 'checked_at': self.clock(), 'ranked': ranked,
                  'models': [{**row, 'rank': rank.get(row['id']), 'label': LISTED_LABEL} for row in models]}
        with self.service.lock:
            rows = self._model_lists()
            rows[route_id] = record
            self.store.put('decision_model_lists', rows)
        return record
