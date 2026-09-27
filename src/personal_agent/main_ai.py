"""The owner's Main AI (기본 AI) route and per-provider API keys (#619).

Settings › AI 연결 shows one card: the **Main AI** that runs Work and, as a
subordinate line, the **Judgment AI** (DecisionEngine, #580) that follows it
by default.  This module owns only the Main AI side:

* a fixed-order chooser model (subscription CLIs, then API providers);
* per-provider API keys in the existing local secret store
  (``api_key:<provider>``), with a one-time migration of the former single
  ``model_key`` slot into the slot of the provider it belonged to;
* one explicit **확인하고 사용** action that probes the candidate route and
  switches only when the probe passes (the #580 probe-and-commit pattern),
  and a separate **확인** that re-probes the current route without switching.

``model_key`` stays the *active* Work key read by the runtime; it is written
only by a successful switch (or cleared when the owner removes the active
provider's key), so saving a key never changes where Work goes.

Invariants (tests/test_main_ai_routes.py):

* reading the status runs no subprocess and calls no model;
* saving or removing a key never switches the Main AI;
* a failed probe leaves the Main AI *and* the Judgment AI unchanged;
* key values are never returned, only ``saved_at``;
* the Judgment AI follows the new Main AI only when its mode is
  ``follow_main``; a failed judgment probe leaves it needing attention and
  never falls back to another route or key (``decision_routes.follow``).
"""
import threading
import time

from .providers import validate_model

SUBSCRIPTION_ROUTES = ('codex', 'claude-code')
#: API routes offered in the chooser.  Ollama/local is deliberately absent
#: (owner decision 2026-09-26); an existing Ollama config still renders.
API_ROUTES = {
    'openai': {'name': 'OpenAI', 'provider': 'openai', 'endpoint': 'https://api.openai.com/v1',
               'model': 'gpt-4o-mini', 'destination': 'api.openai.com'},
    'anthropic': {'name': 'Anthropic', 'provider': 'anthropic', 'endpoint': 'https://api.anthropic.com',
                  'model': 'claude-sonnet-4-5', 'destination': 'api.anthropic.com'},
    'openrouter': {'name': 'OpenRouter', 'provider': 'compatible', 'endpoint': 'https://openrouter.ai/api/v1',
                   'model': 'openrouter/free', 'destination': 'openrouter.ai'},
}
#: The chooser order.  Fixed: switching never re-sorts it (AC2).
CHOOSER_ORDER = (*SUBSCRIPTION_ROUTES, *API_ROUTES)
ENGINE_NAMES = {'codex': 'Codex', 'claude-code': 'Claude Code'}
ENGINE_DESTINATIONS = {'codex': 'OpenAI (Codex 구독 계정)', 'claude-code': 'Anthropic (Claude Code 구독 계정)'}
KEY_META = 'api_keys'
MIGRATED = 'api_keys_migrated'
CHECKS = 'main_ai_checks'
#: #679: the owner's Main AI model per subscription CLI (absent: the CLI's own
#: default).  The Work route runs each CLI with its user configuration ignored
#: (Codex `--ignore-user-config`, Claude Code `--setting-sources`/isolated
#: HOME), so a model set in `~/.codex/config.toml` never reaches Work; this is
#: the owner's explicit choice instead, passed as the CLI's `--model`.
SUBSCRIPTION_MODELS = 'subscription_engine_models'
#: Owner-visible note for the Codex model row.
CODEX_CONFIG_NOTE = ('AgentOS는 Codex 개인 설정을 격리하므로 ~/.codex/config.toml의 모델은 쓰지 않습니다. '
                     '비워 두면 CLI 기본 모델을 씁니다.')
#: The isolated sidecar deployment has a closed request contract (prompt,
#: engine, bearer, task id; `isolated_engine_sidecar._validate`) and a pinned
#: CLI image, so it takes no model: the setting is hidden and refused there
#: instead of being silently ignored (#679 review).
ISOLATED_MODEL_NOTE = '격리 런타임 배포는 작업 모델 지정을 지원하지 않아 CLI 기본 모델을 씁니다.'
#: #701: owner-facing reasons of the per-route agency line (Settings › AI 연결).
ISOLATED_AGENCY_TEXT = '격리 런타임 배포에서는 CLI 자체 웹 검색과 브라우저 도구를 제공하지 않습니다'
STRICT_BROWSER_TEXT = '엄격 격리 실행 프로필에서는 브라우저 도구를 제공하지 않습니다'
CLI_SEARCH_NOTE = '개인 자료가 포함된 작업에서는 그 작업에 한해 꺼집니다'
CLI_NOT_INSTALLED_TEXT = '이 컴퓨터에서 CLI를 찾지 못해 실행할 수 없습니다'
CLI_SIGNED_OUT_TEXT = 'CLI가 로그인되어 있지 않아 실행할 수 없습니다'


#: #710: the probe fields ``model_ready`` reads; no response text is kept.
VERIFIED_TEST_FIELDS = ('ok', 'tools_ok', 'fingerprint', 'time', 'provider', 'model', 'runtime_model')


def verified_test(record):
    """The content-free part of a successful Work-route probe (#710)."""
    return {key: record.get(key) for key in VERIFIED_TEST_FIELDS if isinstance(record, dict) and key in record}


def key_slot(provider_id):
    return f'api_key:{provider_id}'


def api_route_of(config):
    """The chooser API route a stored ``model`` config belongs to, or ''."""
    if not isinstance(config, dict):
        return ''
    endpoint = str(config.get('endpoint', '')).rstrip('/')
    for route_id, preset in API_ROUTES.items():
        if config.get('provider') == preset['provider'] and endpoint == preset['endpoint']:
            return route_id
    return ''


class MainAiError(ValueError):
    """An owner-facing refusal; the current Main AI and Judgment AI stay."""


class MainAiRoutes:
    def __init__(self, service, clock=time.time):
        self.service, self.store, self.clock = service, service.store, clock
        self._switching = threading.Lock()

    # -- per-provider keys ------------------------------------------------------
    def _meta(self):
        rows = self.store.config(KEY_META, {})
        return dict(rows) if isinstance(rows, dict) else {}

    def migrate(self):
        """Move the single ``model_key`` into its provider's slot, once.

        The flag is written even when there is nothing to move, so a later
        key typed into the legacy form is never re-attributed.  An existing
        slot is never overwritten.
        """
        if self.store.config(MIGRATED, False):
            return False
        with self.service.lock:
            if self.store.config(MIGRATED, False):
                return False
            route_id = api_route_of(self.store.config('model', {}))
            key = self.store.secret('model_key') or ''
            moved = False
            if route_id and key and not self.store.secret(key_slot(route_id)):
                self.store.secret(key_slot(route_id), key)
                meta = self._meta()
                meta[route_id] = {'saved_at': self.clock(), 'source': 'migrated'}
                self.store.put(KEY_META, meta)
                moved = True
            self.store.put(MIGRATED, True)
            return moved

    def save_key(self, body):
        """Store or remove one provider key.  Never switches the Main AI."""
        if not isinstance(body, dict) or body.get('provider') not in API_ROUTES:
            raise MainAiError('키를 저장할 API를 선택하세요.')
        route_id, key = body['provider'], body.get('key')
        if not isinstance(key, str) or len(key) > 4096 or any(ch.isspace() for ch in key.strip()):
            raise MainAiError('API 키 한 줄을 그대로 붙여 넣으세요.')
        self.migrate()
        key = key.strip()
        with self.service.lock:
            self.store.secret(key_slot(route_id), key)
            meta = self._meta()
            if key:
                meta[route_id] = {'saved_at': self.clock(), 'source': 'owner'}
            else:
                meta.pop(route_id, None)
                if self.current() == route_id:
                    # The active route loses its key: it now needs attention.
                    # Nothing else is selected in its place (no fallback).
                    self.store.secret('model_key', '')
                    self.store.put('model_test', None)
            self.store.put(KEY_META, meta)
        return self.status()

    def store_openrouter_key(self, key):
        """OpenRouter PKCE result: saved into its slot, never activated."""
        return self.save_key({'provider': 'openrouter', 'key': key})

    # -- read model (no subprocess, no model call) ------------------------------
    def current(self):
        selected = (self.store.config('subscription_engine', {}) or {}).get('id', '')
        if selected:
            return selected
        model = self.store.config('model', {}) or {}
        if not model.get('model'):
            return ''
        return api_route_of(model) or 'other'

    def _checks(self):
        rows = self.store.config(CHECKS, {})
        return dict(rows) if isinstance(rows, dict) else {}

    def subscription_model(self, route_id):
        """The owner's Work model for one CLI, or '' for the CLI's own default (#679)."""
        from .decision_adapters import valid_model_id
        rows = self.store.config(SUBSCRIPTION_MODELS, {})
        model = rows.get(route_id) if isinstance(rows, dict) else None
        return model if valid_model_id(model) else ''

    def _record_check(self, route_id, record):
        with self.service.lock:
            rows = self._checks()
            rows[route_id] = {**record, 'checked_at': self.clock()}
            self.store.put(CHECKS, rows)

    def agency(self, route_id, isolated, saved_key=False, engine=None):
        """#701: whether this route's own web search and the browser tools are available, and why not.

        Read-only: stored configuration and remembered observations only, no
        subprocess and no model call.  A CLI's own search that is available can
        still be off for a single Work whose prompt carries private material
        (the per-turn gate); ``note`` says so.  ``engine`` is the CLI's row
        from ``subscription_engine_status`` (installed, login): a CLI that is
        not installed or is signed out cannot run, so neither is available.
        """
        from .bounded_execution import BOUNDED_PROFILE
        from .search_providers import NATIVE_REASONS, ProviderRegistry
        profile = getattr(self.service, 'browser_profile', None)
        browser_reason = None
        try:
            browser_reason = profile.unavailable_reason() if profile is not None else 'platform'
        except Exception:
            browser_reason = 'platform'
        browser_text = profile.unavailable_message() if browser_reason and profile is not None else ''

        def row(available, reason='', text='', note=''):
            return {'available': bool(available), 'reason': '' if available else reason,
                    'reason_text': '' if available else text, 'note': note if available else ''}
        registry = ProviderRegistry.from_store(self.store)
        if route_id in SUBSCRIPTION_ROUTES:
            host_profile = self.service.subscription_isolation()['profile'] if hasattr(self.service, 'subscription_isolation') \
                else BOUNDED_PROFILE
            if isolated:
                return {'search': row(False, 'isolated', ISOLATED_AGENCY_TEXT), 'browser': row(False, 'isolated', ISOLATED_AGENCY_TEXT)}
            engine = engine if isinstance(engine, dict) else {}
            if not engine.get('installed'):
                return {'search': row(False, 'not_installed', CLI_NOT_INSTALLED_TEXT),
                        'browser': row(False, 'not_installed', CLI_NOT_INSTALLED_TEXT)}
            if (engine.get('login') or {}).get('state') == 'signed-out':
                return {'search': row(False, 'signed_out', CLI_SIGNED_OUT_TEXT),
                        'browser': row(False, 'signed_out', CLI_SIGNED_OUT_TEXT)}
            if host_profile != BOUNDED_PROFILE:
                return {'search': row(False, 'strict_profile', NATIVE_REASONS['strict_profile']),
                        'browser': row(False, 'strict_profile', STRICT_BROWSER_TEXT)}
            recorded = registry.recorded_native(route_id, route_id) or {}
            refused = recorded.get('state') == 'unavailable'
            search = row(not refused, recorded.get('reason') or 'refused',
                         NATIVE_REASONS.get(recorded.get('reason') or 'refused', ''), CLI_SEARCH_NOTE)
            return {'search': search, 'browser': row(browser_reason is None, browser_reason or '', browser_text)}
        preset = API_ROUTES.get(route_id) or {}
        if not saved_key:
            search = row(False, 'no_api_key', NATIVE_REASONS['no_api_key'])
        else:
            fingerprint = registry.fingerprint(route_id, {'endpoint': preset.get('endpoint', ''),
                                                          'model': preset.get('model', '')})
            status = registry.native_status()
            recorded = status if status.get('route') == route_id else (registry.recorded_native(route_id, fingerprint) or {})
            refused = recorded.get('state') == 'unavailable'
            search = row(not refused, recorded.get('reason') or 'rejected', NATIVE_REASONS.get(recorded.get('reason') or 'rejected', ''))
        return {'search': search, 'browser': row(browser_reason is None, browser_reason or '', browser_text)}

    def status(self):
        self.migrate()
        current = self.current()
        model = self.store.config('model', {}) or {}
        meta, checks = self._meta(), self._checks()
        engines = {item['id']: item for item in self.service.subscription_engine_status()['engines']}
        isolated = bool(getattr(self.service, 'isolated_engine_adapter', None))
        model_test = self.store.config('model_test')
        routes = []
        for route_id in CHOOSER_ORDER:
            check = checks.get(route_id)
            if route_id in SUBSCRIPTION_ROUTES:
                engine = engines.get(route_id) or {}
                login = engine.get('login') or {'state': 'unchecked'}
                routes.append({'id': route_id, 'kind': 'subscription', 'name': ENGINE_NAMES[route_id],
                               'destination': ENGINE_DESTINATIONS[route_id], 'installed': bool(engine.get('installed')),
                               'login': login, 'credential': bool(engine.get('credential')), 'check': check,
                               # #679: '' means the CLI's own default.
                               # Shown even when isolated, so a refused Work names it;
                               # 확인하고 사용 there clears it.
                               'model': self.subscription_model(route_id),
                               'model_selectable': not isolated,
                               'model_note': ISOLATED_MODEL_NOTE if isolated
                               else CODEX_CONFIG_NOTE if route_id == 'codex' else '',
                               'agency': self.agency(route_id, isolated, engine=engine)})
                continue
            preset = API_ROUTES[route_id]
            saved = bool(self.store.secret(key_slot(route_id)))
            active_key = current == route_id and saved and \
                self.store.secret(key_slot(route_id)) == (self.store.secret('model_key') or '')
            routes.append({'id': route_id, 'kind': 'api', 'name': preset['name'], 'destination': preset['destination'],
                           'model': model.get('model') if current == route_id else preset['model'],
                           'key': {'saved': saved, 'saved_at': (meta.get(route_id) or {}).get('saved_at') if saved else None,
                                   # A replaced key of the current route is used only after 확인하고 사용.
                                   'pending': bool(current == route_id and saved and not active_key)},
                           'check': check, 'agency': self.agency(route_id, isolated, saved)})
        last = None
        if current in SUBSCRIPTION_ROUTES:
            login = (engines.get(current) or {}).get('login') or {}
            last = {'state': login.get('state', 'unchecked'), 'checked_at': login.get('checked_at')}
        elif current:
            ready = self.service.model_ready(model, model_test)
            tested = model_test if isinstance(model_test, dict) else {}
            last = {'state': 'ok' if ready else 'failed' if tested.get('time') else 'unchecked',
                    'checked_at': tested.get('time'), 'error': tested.get('error', '') if not ready else ''}
        other = None
        if current == 'other':
            other = {'provider': model.get('provider', ''), 'model': model.get('model', ''),
                     'destination': str(model.get('endpoint', ''))}
        return {'current': current, 'routes': routes, 'last_check': last, 'other': other,
                'order': list(CHOOSER_ORDER)}

    # -- explicit owner actions --------------------------------------------------
    def activate(self, body):
        """확인하고 사용: probe the chosen route, switch only if it passes.

        Then, when the Judgment AI follows the Main AI, re-resolve it for the
        new Main AI (its own probe; failure leaves it needing attention).
        """
        if not self._switching.acquire(blocking=False):
            raise MainAiError('이미 기본 AI를 확인하고 있습니다. 끝난 뒤 다시 시도하세요.')
        try:
            route_id = body.get('route') if isinstance(body, dict) else None
            if route_id not in CHOOSER_ORDER:
                raise MainAiError('사용할 기본 AI를 선택하세요.')
            self.migrate()
            if route_id in SUBSCRIPTION_ROUTES:
                self._activate_subscription(route_id, body.get('model'))
            else:
                self._activate_api(route_id, body.get('model'))
            judgment = self.service.decision_routes.follow_main_switched(route_id)
            return {'main_ai': self.status(), 'decision_route': self.service.decision_routes.status(),
                    'judgment': judgment}
        finally:
            self._switching.release()

    def _activate_subscription(self, route_id, model_name=None):
        # #679: an explicit Work model for this CLI ('' clears it to the CLI
        # default); checked for shape before anything else changes.
        from .decision_adapters import valid_model_id
        if model_name is not None:
            model_name = model_name.strip() if isinstance(model_name, str) else model_name
            if model_name and not valid_model_id(model_name):
                raise MainAiError('모델 이름 형식을 확인하세요. 현재 기본 AI와 판단 AI는 그대로입니다.')
            if model_name and getattr(self.service, 'isolated_engine_adapter', None):
                raise MainAiError(ISOLATED_MODEL_NOTE + ' 현재 기본 AI와 판단 AI는 그대로입니다.')
        try:
            # The owner's 확인하고 사용 is the login attestation; the CLI's own
            # login check runs first and a known sign-out refuses the switch.
            self.service.connect_subscription_engine({'engine': route_id, 'officially_authenticated': True})
        except ValueError as exc:
            self._record_check(route_id, {'state': 'failed', 'failure': str(exc)[:300]})
            raise MainAiError(f'{exc} 현재 기본 AI와 판단 AI는 그대로입니다.') from None
        if model_name is not None:
            with self.service.lock:
                rows = self.store.config(SUBSCRIPTION_MODELS, {})
                rows = dict(rows) if isinstance(rows, dict) else {}
                if model_name:
                    rows[route_id] = model_name
                else:
                    rows.pop(route_id, None)
                self.store.put(SUBSCRIPTION_MODELS, rows)
        self._record_check(route_id, {'state': 'ok'})

    def _activate_api(self, route_id, model_name):
        preset = API_ROUTES[route_id]
        key = self.store.secret(key_slot(route_id)) or ''
        if not key:
            self._record_check(route_id, {'state': 'failed', 'failure': 'not-configured'})
            raise MainAiError(f'{preset["name"]} API 키가 저장되어 있지 않습니다. 키를 먼저 저장하세요. '
                              '현재 기본 AI와 판단 AI는 그대로입니다.')
        current = self.store.config('model', {}) or {}
        if not isinstance(model_name, str) or not model_name.strip():
            model_name = current.get('model') if api_route_of(current) == route_id else preset['model']
        try:
            config = validate_model({'provider': preset['provider'], 'endpoint': preset['endpoint'],
                                     'model': model_name.strip()})
        except ValueError as exc:
            raise MainAiError(str(exc)) from None
        record = self.service.probe_model(config, key)
        if not record['ok']:
            self._record_check(route_id, {'state': 'failed', 'failure': record.get('error', '')[:300]})
            raise MainAiError(f'{preset["name"]} 확인에 실패했습니다: {record.get("error") or "응답 없음"} '
                              '현재 기본 AI와 판단 AI는 그대로입니다.')
        with self.service.lock:
            self.store.put('model', config)
            self.store.secret('model_key', key)
            self.store.put('model_test', record)
            self.store.put('model_draft_test', None)
            self.store.put('subscription_engine', {})
            # A new destination: earlier document/public-page approvals were
            # given for the previous one (same rule as save_model).
            self.store.put('document_sharing', {})
            self.store.put('public_page_sharing', {})
        # #710: the verified config and its tool-call probe stay with this
        # route's check, so the orchestrator may offer the route as a worker
        # after the owner switches the Main AI elsewhere (key unchanged since).
        self._record_check(route_id, {'state': 'ok', 'config': config, 'test': verified_test(record)})

    def check(self):
        """확인: re-probe the current Main AI.  Never switches."""
        current = self.current()
        if not current:
            raise MainAiError('확인할 기본 AI가 없습니다. 변경에서 하나를 고르세요.')
        if current in SUBSCRIPTION_ROUTES:
            login = self.service.check_engine_login(current)
            self._record_check(current, {'state': 'failed' if login.get('state') == 'signed-out' else 'ok',
                                         'login': login.get('state')})
        else:
            result = self.service.test_model()
            if current in API_ROUTES:
                self._record_check(current, {'state': 'ok' if result['ok'] else 'failed',
                                             'failure': (result.get('error') or '')[:300]})
        return {'main_ai': self.status()}
