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
* ``lowest_qualified`` selects only among owner-declared candidates that
  pass the versioned qualification suite in order; none passing is an
  explicit failure, never a jump to another model or route.
"""
import subprocess
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
                                codex_still_enabled, parse_codex_features, valid_model_id)
from .bounded_execution import parse_cli_version
from .decision_qualification import SUITE_VERSION, qualify
from .main_ai import CHOOSER_ORDER, key_slot

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
#: Built-in light Judgment candidates per Main AI route.  Direct API routes use
#: the Main AI's own saved provider key; Claude Code uses its own login and the
#: existing ``lowest_qualified`` qualification with one declared candidate.
FOLLOW_CANDIDATES = {
    'openai': {'transport': ROUTE_DIRECT_API, 'config': dict(DEFAULT_DECISION_PROVIDER)},
    'anthropic': {'transport': ROUTE_DIRECT_API, 'config': {'provider': 'anthropic', 'endpoint': 'https://api.anthropic.com',
                                                             'model': 'claude-haiku-4-5'}},
    'openrouter': {'transport': ROUTE_DIRECT_API, 'config': {'provider': 'compatible', 'endpoint': 'https://openrouter.ai/api/v1',
                                                              'model': 'openai/gpt-4o-mini'}},
    'claude-code': {'transport': ROUTE_SUBSCRIPTION_CLI, 'engine': 'claude-code', 'model_policy': POLICY_LOWEST_QUALIFIED,
                    'candidates': ['haiku']},
}

ENGINE_NAMES = {'codex': 'Codex', 'claude-code': 'Claude Code'}
#: Where each subscription engine sends the judgment.  Owner-visible so a
#: route switch never hides a destination change.
CLI_DESTINATIONS = {'codex': 'OpenAI (Codex 구독 계정)', 'claude-code': 'Anthropic (Claude Code 구독 계정)'}

#: Flags a CLI's own help must declare before AgentOS will run a judgment
#: through it: the isolation/no-tools flags are mandatory, the model flag
#: decides whether ``explicit`` / ``lowest_qualified`` can be offered.
REQUIRED_FLAGS = {
    'codex': ('--json', '--ignore-user-config', '--ignore-rules', '--ephemeral', '--output-schema', '--disable', '--sandbox',
              '--skip-git-repo-check', '--config'),
    'claude-code': ('--output-format', '--json-schema', '--tools', '--strict-mcp-config', '--no-session-persistence',
                    '--system-prompt', '--setting-sources', '--restricted'),
}
MODEL_FLAG = '--model'
#: Codex CLI versions whose CODEX_HOME instruction-file behaviour was re-checked
#: with the no-model harness (tests/test_strict_isolation.py::
#: CodexDecisionInstructionFiles) *and* whose limitation below is accepted for
#: a decision route (#624).  Empty: no Codex version is qualified, so Codex
#: activation fails closed even if a future version passes the tool check.
CODEX_INSTRUCTION_FILES_QUALIFIED = frozenset()
#: Owner-visible limitation for the Codex route (#624, observed on 0.153.4).
CODEX_INSTRUCTION_FILES_LIMITATION = ('Codex는 로그인 프로필(CODEX_HOME)의 AGENTS.override.md 또는 AGENTS.md를 '
                                      '판단 요청에 함께 보냅니다. 끌 수 있는 공식 옵션이 없고, AgentOS는 그 내용을 '
                                      '읽거나 기록하지 않습니다.')


#: Main AI routes the Judgment AI cannot follow, with the owner-visible reason.
FOLLOW_UNAVAILABLE = {
    'codex': ('설치된 Codex CLI에서는 판단 요청의 도구 기능을 모두 끌 수 있는지 확인되지 않았고, 로그인 프로필의 지침 '
              '파일이 함께 전송됩니다. 그래서 판단 AI가 Codex를 따라가지 않습니다.'),
    'other': '이 기본 AI 연결에는 판단 AI가 따라갈 가벼운 모델이 정해져 있지 않습니다.',
}


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

    def __init__(self, service, *, jev_transport=None, clock=time.time):
        self.service, self.clock = service, clock
        self.jev_transport = jev_transport
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
    def _direct_engine(self, audit):
        return ModelDecisionEngine(self.service.adapter, self.service.decision_route, audit=audit)

    def _jev_engine(self, model, audit):
        kwargs = {'transport': self.jev_transport} if self.jev_transport else {}
        return JevDecisionEngine(lambda: self.store.secret('decision_jev_key') or '', model=model,
                                 audit=audit, **kwargs)

    def _cli_engine(self, engine_id, model, policy, audit, guard=None, codex_disabled_features=None):
        return SubscriptionCliDecisionEngine(self.service.execution_adapter, engine_id, model=model,
                                             model_policy=policy, audit=audit, guard=guard,
                                             codex_disabled_features=codex_disabled_features)

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
            return self._direct_engine(audit)
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
            return ''

        return self._cli_engine(engine_id, model, policy, audit, guard,
                                route.get('codex_disabled_features') if engine_id == 'codex' else None)

    def _follow_resolve(self, route):
        """``(config, key)`` of a follow row: the Main AI provider's own key, read live.

        A removed key makes the route unavailable; nothing falls back.
        """
        key = self.store.secret(key_slot(route.get('main', ''))) or ''
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
            return {'main': main_id, 'available': True, 'transport': ROUTE_DIRECT_API,
                    'model': candidate['config']['model'],
                    'destination': urlsplit(candidate['config']['endpoint']).hostname}
        if self.service.isolated_engine_adapter:
            return {'main': main_id, 'available': False,
                    'reason': '격리 런타임 배포에서는 구독 AI를 판단 AI로 쓸 수 없습니다.'}
        return {'main': main_id, 'available': True, 'transport': ROUTE_SUBSCRIPTION_CLI,
                'model': candidate['candidates'][0], 'destination': CLI_DESTINATIONS[candidate['engine']]}

    def follow_main_switched(self, main_id):
        """Called after a successful Main AI switch.  Never raises.

        An explicit or ``off`` Judgment AI is left exactly as it was.  A
        following Judgment AI is re-resolved for the new Main AI; a failure
        leaves it needing attention (no fallback to the previous route).
        """
        if self.mode() != MODE_FOLLOW:
            return {'state': 'unchanged', 'mode': self.mode()}
        with self._activating:
            return self._follow(main_id, keep_previous=False)

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
            key = self.store.secret(key_slot(main_id)) or ''
            if not key:
                return failed('not-configured', '기본 AI의 API 키가 없어 판단 AI를 확인하지 못했습니다.')
            config = dict(candidate['config'])
            ok, decision = self._probe(ModelDecisionEngine(self.service.adapter, lambda: (config, key)))
            if not ok:
                return failed(decision.outcome, f'판단 AI({config["model"]})가 확인 판단에 답하지 않았습니다.',
                              observed_model=decision.confidence.observed_model or 'not reported')
            self._commit(option, {**follow, 'transport': ROUTE_DIRECT_API, 'provider': config['provider'],
                                  'endpoint': config['endpoint'], 'requested_model': config['model'],
                                  'key_source': 'main'},
                         {'observed_model': decision.confidence.observed_model or 'not reported'})
            return {'state': 'active'}
        try:
            self._activate_cli({'engine': candidate['engine'], 'model_policy': candidate['model_policy'],
                                'candidates': list(candidate['candidates'])}, extra=follow)
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
        direct = {'transport': ROUTE_DIRECT_API, 'configured': bool(resolved) or has_decision_key,
                  'provider': direct_config['provider'] if direct_config else DEFAULT_DECISION_PROVIDER['provider'],
                  'model': direct_config['model'] if direct_config else DEFAULT_DECISION_MODEL,
                  'destination': urlsplit((direct_config or DEFAULT_DECISION_PROVIDER)['endpoint']).hostname,
                  'key_source': key_source, 'has_decision_key': bool(self.store.secret('decision_model_key')),
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
            engines.append({'id': engine_id, 'name': ENGINE_NAMES[engine_id], 'installed': bool(item.get('installed')),
                            'login': (item.get('login') or {}).get('state', 'unchecked'),
                            'isolated_deployment': bool(self.service.isolated_engine_adapter),
                            'capabilities': capability or None,
                            'model_selection': ('supported' if capability.get('model_override') is True
                                                else 'unsupported' if capability.get('model_override') is False
                                                else 'unchecked'),
                            # A refused tool surface is shown with its reason
                            # (for example `unified_exec` on Codex 0.153.4).
                            'tool_surface': capability.get('tool_surface'),
                            'tool_surface_detail': capability.get('tool_surface_detail') or '',
                            'destination': CLI_DESTINATIONS[engine_id],
                            'instruction_files': CODEX_INSTRUCTION_FILES_LIMITATION if engine_id == 'codex' else '',
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
                engine = next((e for e in engines if e['id'] == route.get('engine')), None)
                requalify = (route.get('engine') in CLI_BINARIES
                             and (route.get('fingerprint') or '') != cli_fingerprint(
                                 self.service.execution_adapter.finder(CLI_BINARIES[route['engine']])))
                active.update(destination=CLI_DESTINATIONS.get(route.get('engine'), ''),
                              requalification_needed=requalify,
                              available=bool(engine and engine['installed'] and engine['login'] != 'signed-out'
                                             and not engine['isolated_deployment'] and not requalify and not stale))
            else:
                active.update(available=False)
        elif route is None:
            active = ({'transport': ROUTE_DIRECT_API, 'source': 'default', 'provider': direct['provider'],
                       'requested_model': direct['model'], 'destination': direct['destination']}
                      if resolved else {'transport': 'none', 'source': 'default'})
        else:
            active = {**{k: v for k, v in route.items() if k not in ('fingerprint',)}, 'source': 'owner'}
            if route['transport'] == ROUTE_DIRECT_API:
                active.update(provider=direct['provider'], requested_model=direct['model'],
                              destination=direct['destination'], available=bool(resolved))
            elif route['transport'] == ROUTE_JEV:
                active.update(destination=JEV_DESTINATION, available=jev['configured'])
            elif route['transport'] == ROUTE_SUBSCRIPTION_CLI:
                engine = next((e for e in engines if e['id'] == route.get('engine')), None)
                # Same check as the runtime guard (a local stat, no subprocess),
                # for every policy: the checked isolation/tool surface belongs
                # to the binary it was checked against.
                requalify = (route.get('engine') in CLI_BINARIES
                             and (route.get('fingerprint') or '') != cli_fingerprint(
                                 self.service.execution_adapter.finder(CLI_BINARIES[route['engine']])))
                unqualified = route.get('engine') == 'codex' and not self._codex_instructions_qualified(route)
                active.update(destination=CLI_DESTINATIONS.get(route.get('engine'), ''),
                              requalification_needed=requalify, instruction_files_unqualified=unqualified,
                              available=bool(engine and engine['installed'] and engine['login'] != 'signed-out'
                                             and not engine['isolated_deployment'] and not requalify
                                             and not unqualified))
        return {'active': active, 'direct_api': direct, 'jev': jev, 'subscription_cli': engines,
                'suite_version': SUITE_VERSION, 'mode': self.mode(route), 'main': main, 'follow': follow,
                'follow_candidates': {route_id: self.follow_preview(route_id) for route_id in CHOOSER_ORDER},
                'follow_check': checks.get(f'{MODE_FOLLOW}:{main}') if main else None}

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
        name = ENGINE_NAMES[engine_id]
        execution.runtime_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(dir=execution.runtime_root, prefix='capability-') as folder:
            # An empty HOME / CODEX_HOME: the listing shows the CLI's own
            # defaults, which is what `--ignore-user-config` runs with.
            env = {'HOME': folder, 'CODEX_HOME': folder, 'PATH': f'{Path(binary).parent}:/usr/bin:/bin',
                   'LANG': 'C.UTF-8'}

            def run(argv):
                try:
                    done = bounded_run(execution.runner, argv, cwd=folder, env=env, timeout=20)
                except (subprocess.TimeoutExpired, OSError) as exc:
                    raise DecisionRouteError(f'{name} CLI 기능을 확인하지 못했습니다 ({type(exc).__name__}).') from None
                return done.returncode, (done.stdout or ''), (getattr(done, 'stderr', '') or '')

            _code, help_out, help_err = run(help_argv)
            _code, version_out, _err = run([binary, '--version'])
            help_text = help_out + '\n' + help_err
            missing = [flag for flag in REQUIRED_FLAGS[engine_id] if not has_flag(help_text, flag)]
            record = {'version': ' '.join(version_out.split())[:80], 'isolation_flags': not missing,
                      'missing_flags': missing, 'model_override': has_flag(help_text, MODEL_FLAG),
                      'fingerprint': cli_fingerprint(binary), 'checked_at': self.clock(), 'source': 'cli --help'}
            if engine_id == 'codex' and not missing:
                record.update(self._codex_tool_surface(run, binary))
        with self.service.lock:
            rows = self._capabilities()
            rows[engine_id] = record
            self.store.put('decision_cli_capabilities', rows)
        return record

    @staticmethod
    def _codex_tool_surface(run, binary):
        """Plan and verify the Codex feature set for decision calls (allowlist).

        Reads ``codex features list`` (local, no model call), disables every
        enabled feature outside the allowlist, reads the listing again with
        those disables and records whether only allowlisted features remain.
        Anything unparsable or still enabled fails closed.
        """
        code, out, err = run([binary, 'features', 'list'])
        try:
            if code != 0:
                raise ValueError((err or out).strip()[:120] or f'exit {code}')
            plan = codex_disable_plan(parse_codex_features(out))
            argv = [binary, 'features', 'list']
            for feature in plan:
                argv += ['--disable', feature]
            code, out, err = run(argv)
            if code != 0:
                raise ValueError((err or out).strip()[:120] or f'exit {code}')
            remaining = codex_still_enabled(parse_codex_features(out))
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
            decision_key = self.store.secret('decision_model_key') or ''
            if decision_key:
                # A saved decision-only key: probe exactly that destination/key.
                resolve = lambda: (dict(DEFAULT_DECISION_PROVIDER), decision_key)  # noqa: E731
            elif self.service.decision_route():
                resolve = self.service.decision_route
            else:
                self._fail(ROUTE_DIRECT_API, 'not-configured', 'OpenAI API 키가 없어 대화 해석에 사용할 수 없습니다.')
            ok, decision = self._probe(ModelDecisionEngine(self.service.adapter, resolve))
            if not ok:
                self._fail(ROUTE_DIRECT_API, decision.outcome, 'OpenAI API가 확인 판단에 답하지 않았습니다.',
                           observed_model=decision.confidence.observed_model or 'not reported')
            config = resolve()[0]
            if decision_key:
                # Written only here, after the probe passed (#580 review F1).
                with self.service.lock:
                    self.store.put('decision_model', dict(DEFAULT_DECISION_PROVIDER))
            return self._commit(ROUTE_DIRECT_API, {'transport': ROUTE_DIRECT_API, 'provider': config['provider'],
                                                   'requested_model': config['model'],
                                                   'key_source': 'decision' if decision_key else 'existing'},
                                {'observed_model': decision.confidence.observed_model or 'not reported'})
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

    def _activate_cli(self, body, extra=None):
        engine_id, policy = body.get('engine'), body.get('model_policy') or POLICY_ENGINE_DEFAULT
        if engine_id not in CLI_BINARIES:
            raise DecisionRouteError('지원하는 구독 엔진을 선택하세요.')
        if policy not in MODEL_POLICIES:
            raise DecisionRouteError('판단 모델 방식을 선택하세요.')
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
        base = {'transport': ROUTE_SUBSCRIPTION_CLI, 'engine': engine_id, 'model_policy': policy,
                'fingerprint': capability['fingerprint'], 'cli_version': capability['version'],
                **({'codex_disabled_features': disabled} if engine_id == 'codex' else {}), **(extra or {})}
        if policy == POLICY_ENGINE_DEFAULT:
            engine = self._cli_engine(engine_id, None, policy, None, codex_disabled_features=disabled)
            ok, decision = self._probe(engine)
            if not ok:
                self._fail(option, engine.last_failure or decision.outcome, f'{name}이(가) 확인 판단에 답하지 않았습니다.')
            return self._commit(option, {**base, 'requested_model': None},
                                {'observed_model': decision.confidence.observed_model or 'not reported',
                                 'model_policy': policy})
        if not capability['model_override']:
            self._fail(option, 'model-selection-unsupported',
                       f'설치된 {name} CLI는 모델 지정을 지원하지 않습니다. 구독 AI 기본 모델만 사용할 수 있습니다.')
        if policy == POLICY_EXPLICIT:
            model = body.get('model')
            if not valid_model_id(model):
                raise DecisionRouteError('사용할 모델 이름을 입력하세요.')
            engine = self._cli_engine(engine_id, model, policy, None, codex_disabled_features=disabled)
            ok, decision = self._probe(engine)
            if not ok:
                unsupported = engine.last_failure == 'request-rejected'
                self._fail(option, 'model-not-verified' if unsupported else (engine.last_failure or decision.outcome),
                           f'{name}에서 모델 {model}을(를) 확인하지 못했습니다'
                           + ('(이 계정/CLI가 거부).' if unsupported else '.'), requested_model=model)
            return self._commit(option, {**base, 'requested_model': model},
                                {'observed_model': decision.confidence.observed_model or 'not reported',
                                 'model_policy': policy, 'requested_model': model})
        candidates = body.get('candidates')
        if isinstance(candidates, str):
            candidates = [part.strip() for part in candidates.split(',') if part.strip()]
        if not isinstance(candidates, list) or not 1 <= len(candidates) <= MAX_CANDIDATES \
                or not all(valid_model_id(item) for item in candidates) or len(set(candidates)) != len(candidates):
            raise DecisionRouteError(f'후보 모델을 가벼운 순서로 1~{MAX_CANDIDATES}개 입력하세요.')
        tried = []
        for model in candidates:
            seen = []  # content-free records of the qualification calls, for observed identity only
            engine = self._cli_engine(engine_id, model, policy, seen.append, codex_disabled_features=disabled)
            result = qualify(engine)
            observed = sorted({row.get('observed_model') for row in seen
                               if row.get('observed_model') and row.get('observed_model') != 'not reported'})
            tried.append({'model': model, 'qualified': result['qualified'], 'score': result['score'],
                          'ran': result['ran'], 'failure': engine.last_failure or '',
                          'observed_model': ', '.join(observed) or 'not reported'})
            if result['qualified']:
                qualification = {'suite_version': result['suite_version'], 'model': model,
                                 'score': result['score'], 'cli_version': capability['version'],
                                 'fingerprint': capability['fingerprint'], 'at': self.clock()}
                return self._commit(option, {**base, 'requested_model': model, 'qualification': qualification},
                                    {'model_policy': policy, 'requested_model': model, 'candidates': tried,
                                     'suite_version': result['suite_version']})
        self._fail(option, 'no-qualified-candidate',
                   f'후보 모델 중 대화 해석 적격성 검사({SUITE_VERSION})를 통과한 모델이 없습니다.',
                   candidates=tried, suite_version=SUITE_VERSION)
