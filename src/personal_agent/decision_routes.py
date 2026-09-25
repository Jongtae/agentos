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
  Work route selection never writes ``decision_route``;
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
from .decision_adapters import (CLI_BINARIES, JEV_DEFAULT_MODEL, JEV_DESTINATION, JevDecisionEngine,
                                SubscriptionCliDecisionEngine, cli_fingerprint, valid_model_id)
from .decision_qualification import SUITE_VERSION, qualify

ROUTE_OFF = 'off'
TRANSPORTS = (ROUTE_DIRECT_API, ROUTE_JEV, ROUTE_SUBSCRIPTION_CLI, ROUTE_OFF)
POLICY_ENGINE_DEFAULT = 'engine_default'
POLICY_EXPLICIT = 'explicit'
POLICY_LOWEST_QUALIFIED = 'lowest_qualified'
MODEL_POLICIES = (POLICY_ENGINE_DEFAULT, POLICY_EXPLICIT, POLICY_LOWEST_QUALIFIED)
MAX_CANDIDATES = 3

ENGINE_NAMES = {'codex': 'Codex', 'claude-code': 'Claude Code'}
#: Where each subscription engine sends the judgment.  Owner-visible so a
#: route switch never hides a destination change.
CLI_DESTINATIONS = {'codex': 'OpenAI (Codex 구독 계정)', 'claude-code': 'Anthropic (Claude Code 구독 계정)'}

#: Flags a CLI's own help must declare before AgentOS will run a judgment
#: through it: the isolation/no-tools flags are mandatory, the model flag
#: decides whether ``explicit`` / ``lowest_qualified`` can be offered.
REQUIRED_FLAGS = {
    'codex': ('--json', '--ignore-user-config', '--ephemeral', '--output-schema', '--disable'),
    'claude-code': ('--output-format', '--json-schema', '--tools', '--strict-mcp-config', '--no-session-persistence',
                    '--system-prompt'),
}
MODEL_FLAG = '--model'

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

    def _cli_engine(self, engine_id, model, policy, audit, guard=None):
        return SubscriptionCliDecisionEngine(self.service.execution_adapter, engine_id, model=model,
                                             model_policy=policy, audit=audit, guard=guard)

    def engine(self):
        """The engine for the next judgment, from the active route only."""
        audit = self.service.record_decision
        route = self.active()
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
            # A verified model / qualification describes the CLI binary it
            # was checked against; a changed binary needs a new check.
            if self.service.isolated_engine_adapter:
                return 'isolated-deployment'
            if policy != POLICY_ENGINE_DEFAULT and fingerprint != cli_fingerprint(
                    self.service.execution_adapter.finder(CLI_BINARIES[engine_id])):
                return 'requalification-needed'
            return ''

        return self._cli_engine(engine_id, model, policy, audit, guard)

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
        direct = {'transport': ROUTE_DIRECT_API, 'configured': bool(resolved),
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
                            'destination': CLI_DESTINATIONS[engine_id],
                            'check': checks.get(f'{ROUTE_SUBSCRIPTION_CLI}:{engine_id}')})
        if route is None:
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
                # Same check as the runtime guard (a local stat, no subprocess):
                # a verified model describes the binary it was checked against.
                requalify = (route.get('model_policy') != POLICY_ENGINE_DEFAULT and route.get('engine') in CLI_BINARIES
                             and (route.get('fingerprint') or '') != cli_fingerprint(
                                 self.service.execution_adapter.finder(CLI_BINARIES[route['engine']])))
                active.update(destination=CLI_DESTINATIONS.get(route.get('engine'), ''),
                              requalification_needed=requalify,
                              available=bool(engine and engine['installed'] and engine['login'] != 'signed-out'
                                             and not engine['isolated_deployment'] and not requalify))
        return {'active': active, 'direct_api': direct, 'jev': jev, 'subscription_cli': engines,
                'suite_version': SUITE_VERSION}

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
            with self.service.lock:
                self.store.secret('decision_model_key', key)
                self.store.put('decision_model', dict(DEFAULT_DECISION_PROVIDER) if key else {})
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
        texts = []
        execution.runtime_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(dir=execution.runtime_root, prefix='capability-') as folder:
            env = {'HOME': folder, 'PATH': f'{Path(binary).parent}:/usr/bin:/bin', 'LANG': 'C.UTF-8'}
            for argv in (help_argv, [binary, '--version']):
                try:
                    done = execution.runner(argv, cwd=folder, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                                            text=True, timeout=20, shell=False)
                except (subprocess.TimeoutExpired, OSError) as exc:
                    raise DecisionRouteError(f'{ENGINE_NAMES[engine_id]} CLI 기능을 확인하지 못했습니다 ({type(exc).__name__}).') from None
                texts.append((done.stdout or '') + '\n' + (getattr(done, 'stderr', '') or ''))
        help_text, version = texts[0], ' '.join(texts[1].split())[:80]
        missing = [flag for flag in REQUIRED_FLAGS[engine_id] if flag not in help_text]
        record = {'version': version, 'isolation_flags': not missing, 'missing_flags': missing,
                  'model_override': MODEL_FLAG in help_text, 'fingerprint': cli_fingerprint(binary),
                  'checked_at': self.clock(), 'source': 'cli --help'}
        with self.service.lock:
            rows = self._capabilities()
            rows[engine_id] = record
            self.store.put('decision_cli_capabilities', rows)
        return record

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
        previous route exactly as it was.
        """
        if not isinstance(body, dict) or body.get('transport') not in TRANSPORTS:
            raise DecisionRouteError('대화 해석에 사용할 방식을 선택하세요.')
        transport = body['transport']
        if transport == ROUTE_OFF:
            return self._commit(ROUTE_OFF, {'transport': ROUTE_OFF}, {})
        if transport == ROUTE_DIRECT_API:
            if not self.service.decision_route():
                self._fail(ROUTE_DIRECT_API, 'not-configured', 'OpenAI API 키가 없어 대화 해석에 사용할 수 없습니다.')
            ok, decision = self._probe(self._direct_engine(None))
            if not ok:
                self._fail(ROUTE_DIRECT_API, decision.outcome, 'OpenAI API가 확인 판단에 답하지 않았습니다.',
                           observed_model=decision.confidence.observed_model or 'not reported')
            config = self.service.decision_route()[0]
            return self._commit(ROUTE_DIRECT_API, {'transport': ROUTE_DIRECT_API, 'provider': config['provider'],
                                                   'requested_model': config['model']},
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

    def _activate_cli(self, body):
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
        base = {'transport': ROUTE_SUBSCRIPTION_CLI, 'engine': engine_id, 'model_policy': policy,
                'fingerprint': capability['fingerprint'], 'cli_version': capability['version']}
        if policy == POLICY_ENGINE_DEFAULT:
            engine = self._cli_engine(engine_id, None, policy, None)
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
            engine = self._cli_engine(engine_id, model, policy, None)
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
            engine = self._cli_engine(engine_id, model, policy, seen.append)
            result = qualify(engine)
            observed = sorted({row.get('observed_model') for row in seen if row.get('observed_model')})
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
