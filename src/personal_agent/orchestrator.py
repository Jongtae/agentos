"""The decision model orchestrates each Work (ORCH-01 / #710).

Constitution C16: an AI does the work; AgentOS orchestrates.  For each Work
the owner's Judgment AI (the DecisionEngine route, #580/#679) returns one
typed plan through ``DecisionEngine.structured``:

* ``worker`` - which configured AI route runs the request, and ``model``;
* ``brief`` - the goal written for that worker, the AgentOS context sections
  it needs (profile, current context, prepared answers, history) and the
  observable completion criteria;
* ``tools`` - optionally, the subset of that worker's AgentOS tools offered in
  this attempt;
* ``reason`` - one line.

Deterministic code here only **validates** the plan: the worker is in the
catalogue and available, the model is one the catalogue lists for it, the
tools are a subset of that worker's tools, and the Work budget still allows
an attempt.  It never decides what a request needs.  No request, site,
provider or category is named in this module (tests/test_no_scenario_code.py)
and the question text is generic.

After the worker finishes, the existing ``goal_reached`` judgment (#657)
evaluates the attempt; when the goal is not shown, the orchestrator is asked
for an adjusted brief and/or another worker, at most ``MAX_REDELEGATIONS``
times, within the Work's shared ``WorkBudget``, and never after an attempt
that ran an action with an effect (C8: a re-delegation must not repeat one).

When the Judgment AI cannot answer, or answers with a plan that fails
validation, the owner's default Main AI runs the raw request exactly as it
did before #710, and why is recorded once in the Work's Evidence
(``orchestrator`` events).  A change from working orchestration to that
fallback is also said once in the conversation (``notice``).

The worker catalogue is data: the configured Main AI routes (``main_ai``),
their qualified or listed models (#679, ``decision_routes.known_models``),
the agency observed at run time (#701: own web search, browser tools,
availability) and cost/latency tiers.  See docs/decision-layer.en.md
"Orchestration (#710)".
"""
import hashlib
import json

from .decision import MAX_CONTEXT_CHARS, OUTCOME_DECIDED, OUTCOME_MALFORMED, DecisionContext, DecisionPolicy

#: AgentOS context sections a brief may select (``agent_runtime.turn_context``).
SECTIONS = ('profile', 'current_context', 'prepared', 'history')
#: Re-delegations after the first attempt (so at most three attempts per Work).
MAX_REDELEGATIONS = 2
#: An attempt is started only while the Work's deadline leaves at least this.
MIN_ATTEMPT_SECONDS = 60
#: Bounds of the plan text AgentOS keeps and forwards.
MAX_GOAL_CHARS = 1200
MAX_CRITERIA = 5
MAX_CRITERION_CHARS = 300
MAX_REASON_CHARS = 200
#: Bounds of the facts the orchestrator is asked over, besides the owner's
#: request and the catalogue, which are never cut.
CONVERSATION_CHARS = 1500
ATTEMPTS_CHARS = 1800
ANSWER_EXCERPT_CHARS = 600
OBSERVATION_CHARS = 3800
FAILURE_CHARS = 600

KIND_SUBSCRIPTION = 'subscription'
KIND_API = 'api'
#: Cost and latency per route kind: data the orchestrator weighs, never a branch.
KIND_TIERS = {
    KIND_SUBSCRIPTION: {'cost': 'included in the owner\'s subscription usage',
                        'latency': 'agent CLI process: slower start, can work through many steps'},
    KIND_API: {'cost': 'metered per token on the owner\'s API key',
               'latency': 'direct API call: faster start'},
}
#: Model cost tier from its rank in the route's cheapest-first list (#679).
TIER_LOWEST, TIER_HIGHER, TIER_UNRANKED = 'lowest-cost', 'higher-cost', 'unranked'

TOOLS_DEFAULT, TOOLS_SUBSET = 'worker_default', 'subset'

# --- Evidence vocabulary (``orchestrator`` tool events) ----------------------
EVENT_TOOL = 'orchestrator'
PLANNED, FALLBACK, EVALUATED = 'planned', 'fallback', 'evaluated'
#: Why the default Main AI ran the raw request.
FALLBACK_UNAVAILABLE = 'judgment_unavailable'
FALLBACK_MALFORMED = 'plan_malformed'
FALLBACK_UNCONFIDENT = 'plan_unconfident'
FALLBACK_INVALID = 'plan_invalid'
FALLBACK_BUDGET = 'budget_short'
#: What an evaluation found.
REACHED, NOT_REACHED, UNJUDGED, OWNER_NEEDED, WORKER_FAILED, NOT_JUDGED = (
    'reached', 'not_reached', 'unjudged', 'owner_needed', 'worker_failed', 'not_judged')
#: Why no further attempt was made.
STOP_REACHED, STOP_LIMIT, STOP_BUDGET, STOP_EFFECT, STOP_UNJUDGED, STOP_OWNER, STOP_REPLAN = (
    'reached', 'limit', 'budget', 'effect', 'unjudged', 'owner', 'replan_failed')

#: Owner-visible text (Korean) recorded with each event, for 작업 현황 (#707:
#: presentation belongs to the UX child; the text is kept with the Evidence).
FALLBACK_TEXT = {
    FALLBACK_UNAVAILABLE: '판단 AI를 사용할 수 없어 요청별 AI 선택 없이 기본 AI가 요청을 그대로 처리했습니다.',
    FALLBACK_MALFORMED: '판단 AI의 작업 계획을 읽을 수 없어 기본 AI가 요청을 그대로 처리했습니다.',
    FALLBACK_UNCONFIDENT: '판단 AI가 작업 계획을 확신하지 못해 기본 AI가 요청을 그대로 처리했습니다.',
    FALLBACK_BUDGET: '남은 작업 시간이 부족해 판단 AI에 묻지 않고 기본 AI가 요청을 그대로 처리했습니다.',
    FALLBACK_INVALID: ('판단 AI의 작업 계획이 사용 가능한 AI·모델·도구 또는 남은 작업 예산과 맞지 않아 '
                       '기본 AI가 요청을 그대로 처리했습니다.'),
}
#: Said once in the conversation when working orchestration falls back.
NOTICE_ONCE = ('참고: 판단 AI를 지금 사용할 수 없어 요청마다 알맞은 AI를 고르지 않고 기본 AI가 요청을 그대로 '
               '처리합니다. 판단 AI가 다시 응답하면 자동으로 돌아갑니다.')
EVALUATED_TEXT = {
    REACHED: '목표 달성이 확인되었습니다.',
    NOT_REACHED: '관찰된 결과로 목표 달성이 확인되지 않았습니다.',
    UNJUDGED: '목표 달성 여부를 판단할 수 없었습니다.',
    OWNER_NEEDED: '소유자의 확인이나 정보가 필요합니다.',
    WORKER_FAILED: '작업 AI가 이 시도를 끝내지 못했습니다.',
    NOT_JUDGED: '더 맡길 수 없는 시도라 목표 달성 여부를 따로 판단하지 않았습니다.',
}
NEXT_TEXT = {
    'redelegate': '계획을 조정해 다시 맡깁니다.',
    STOP_REACHED: '',
    STOP_LIMIT: f'다시 맡기는 횟수 한도({MAX_REDELEGATIONS}회)에 도달해 더 맡기지 않았습니다.',
    STOP_BUDGET: '남은 작업 시간이나 턴이 부족해 더 맡기지 않았습니다.',
    STOP_EFFECT: '이 시도에서 되돌릴 수 없는 작업이 실행되어 같은 요청을 다시 맡기지 않았습니다.',
    STOP_UNJUDGED: '목표 달성 여부를 판단할 수 없어 더 맡기지 않았습니다.',
    STOP_OWNER: '소유자의 확인이나 정보가 필요해 더 맡기지 않았습니다.',
    STOP_REPLAN: '판단 AI가 새 계획을 내지 못해 더 맡기지 않았습니다.',
}
DEFAULT_MODEL_LABEL = '기본 모델'
#: The evaluator's reason as the next plan call reads it (#729).
EVALUATION_REASON = {
    REACHED: 'the recorded observations showed the goal met',
    NOT_REACHED: 'the recorded observations did not show the goal met',
    UNJUDGED: 'the goal could not be judged',
    OWNER_NEEDED: 'the owner\'s confirmation or information is needed',
    WORKER_FAILED: 'the worker did not finish the attempt',
    NOT_JUDGED: 'not judged: nothing more could follow',
}

#: The orchestration question.  Generic by construction: it names no request,
#: site, provider or category (C16).
QUESTION = (
    'Plan how the owner\'s request is handled by one of the AI workers listed. You orchestrate: you choose the '
    'worker and model and write the brief the worker receives; you do not do the work yourself. Choose an '
    'available worker whose capabilities and tools fit what the request needs; when several fit, prefer lower '
    'cost and latency. model is "" for the worker\'s default or one of the models listed for it. brief.goal says '
    'what the worker must achieve, specific and self-contained, in the owner\'s language. The owner\'s request '
    'may continue recent_conversation: resolve what it refers to or leaves unsaid from that conversation and write '
    'it into brief.goal, and select history when the request continues it; do not brief the worker to ask the '
    'owner for something the conversation already says. brief.context lists only '
    'the AgentOS context sections the worker needs; brief.completion_criteria lists observable results that show '
    'the goal is met. tools_mode is "worker_default": the worker keeps its full offered toolset and chooses among '
    'the tools itself; tools is then [] and tools_reason "". The only subset AgentOS keeps is one that keeps '
    'private-read tools and web search apart: it removes either the private-read tools or the web-search tools '
    '(web_search, bounded_public_research) and nothing else, with tools_reason saying so; any other subset is '
    'replaced by the full toolset. The '
    'tool_descriptions fact says what each tool does. On a worker with its own web search, web_search means that '
    'search; a private-read tool and the worker\'s own web search are never on in the same attempt, so selecting a '
    'private-read tool turns that search off for the attempt. When earlier attempts are listed, they did not meet '
    'the goal: read what each one called, what failed or never completed and why it was judged short, then change '
    'the worker, the model, the tools or the brief. A combination of worker, model and tools that already fell '
    'short is refused. reason is one short line saying why this worker and brief fit.')
PURPOSE = 'work-orchestration'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def one_line(text, limit):
    return ' '.join(str(text or '').split())[:limit]


# --- the worker catalogue (data) ---------------------------------------------
def model_tier(route_id, model, ranked):
    order = list(ranked.get(route_id, ()))
    if model not in order:
        return TIER_UNRANKED
    return TIER_LOWEST if order.index(model) == 0 else TIER_HIGHER


# --- models an account can run (#735) ------------------------------------------
MODEL_REFUSALS_KEY = 'route_model_refusals'
#: A refused model is offered again after this long (the account or plan may change).
MODEL_REFUSAL_TTL_SECONDS = 7 * 24 * 3600
MAX_REFUSALS_PER_ROUTE = 20


def refused_models(store, now=None):
    """``{route: {model, ...}}`` the CLI refused for the owner's account, still within the TTL."""
    import time as _time
    now = _time.time() if now is None else now
    rows = store.config(MODEL_REFUSALS_KEY, {})
    rows = rows if isinstance(rows, dict) else {}
    return {route: {model for model, row in (models or {}).items()
                    if isinstance(row, dict) and isinstance(row.get('at'), (int, float))
                    and now - row['at'] < MODEL_REFUSAL_TTL_SECONDS}
            for route, models in rows.items() if isinstance(models, dict)}


def remember_model_refusal(store, route, model, now=None):
    """Record that ``route`` refused ``model`` for this account (no refusal text is kept)."""
    import time as _time
    rows = store.config(MODEL_REFUSALS_KEY, {})
    rows = dict(rows) if isinstance(rows, dict) else {}
    models = dict(rows.get(route) or {}) if isinstance(rows.get(route), dict) else {}
    models[model] = {'at': _time.time() if now is None else now}
    rows[route] = dict(sorted(models.items(), key=lambda item: item[1]['at'])[-MAX_REFUSALS_PER_ROUTE:])
    store.put(MODEL_REFUSALS_KEY, rows)


def model_refused(model, meta):
    """Whether one CLI failure refused ``model`` itself (#735 review).

    Only the CLI's own unsupported-model signal, classified at the execution
    boundary (``bounded_execution.unsupported_model``) into the failure's
    ``meta``; a generic rejection that mentions the model does not count.
    """
    return bool(model) and isinstance(meta, dict) and meta.get('unsupported_model') == model


def runnable_models(service, route_id, configured, known, refused):
    """The models a subscription worker offers (#735).

    Codex: only what the installed binary bundles and lists
    (``DecisionRoutes.bundled_models``: ``codex debug models --bundled`` with
    an empty ``CODEX_HOME``, cached per binary); with no listing, only the
    configured model.  Every route: minus the models its CLI refused for the
    owner's account.
    """
    candidates = [configured, *known]
    if route_id == 'codex':
        bundled = None
        lookup = getattr(getattr(service, 'decision_routes', None), 'bundled_models', None)
        if callable(lookup):
            try:
                bundled = lookup(route_id)
            except Exception:
                bundled = None
        listed = list(bundled or ())
        candidates = [configured, *[model for model in known if model in listed],
                      *[model for model in listed if model not in known]]
    gone = refused.get(route_id) or set()
    return [model for model in dict.fromkeys(candidates) if model and model not in gone]


def worker_catalogue(service):
    """``Catalogue`` of every configured Main AI route as a worker (#710).

    Read-only: stored configuration and remembered observations only (the
    #619/#701 status), no subprocess and no model call.  A route other than
    the current Main AI is available only when the owner already connected it
    with 확인하고 사용 (its check passed) and nothing observed since says it
    cannot run: a subscription CLI must be installed and not signed out (the
    isolated deployment serves only its own engine; a strict-isolated CLI
    needs its own qualification); an API route must still hold the key that
    passed the tool-call probe.
    """
    from .agent_runtime import BROWSER_ACTIONS
    from .bounded_execution import (BOUNDED_PROFILE, HOST_CLI_PROFILES, ISOLATED_PROFILE, STRICT_PROFILE,
                                    private_read_actions, profile_actions)
    from .decision_routes import RANKED_MODELS, known_models
    from .main_ai import CHECKS, KEY_META, SUBSCRIPTION_ROUTES, api_route_of, key_slot
    store = service.store
    status = service.main_ai.status()
    current = status.get('current') or ''
    checks = store.config(CHECKS, {})
    checks = checks if isinstance(checks, dict) else {}
    meta = store.config(KEY_META, {})
    meta = meta if isinstance(meta, dict) else {}
    listed = store.config('decision_model_lists', {})
    refused = refused_models(store)
    isolated = bool(getattr(service, 'isolated_engine_adapter', None))
    profile = service.subscription_isolation()['profile']
    host_profile = profile if profile in HOST_CLI_PROFILES else STRICT_PROFILE
    private = private_read_actions()
    package_tools = sorted({tool['id'] for package in service.runtime_packages() for tool in package['tools']})
    workers, routes = [], {}
    for row in status.get('routes') or ():
        route_id = row['id']
        agency = row.get('agency') or {}
        search = bool((agency.get('search') or {}).get('available'))
        browser = bool((agency.get('browser') or {}).get('available'))
        checked = (checks.get(route_id) or {}).get('state') == 'ok'
        worker = {'id': route_id, 'kind': row['kind'], 'name': row.get('name') or route_id,
                  'destination': row.get('destination') or '', 'default': route_id == current,
                  'native_search': search, 'browser': browser, **KIND_TIERS[row['kind']]}
        if route_id in SUBSCRIPTION_ROUTES:
            login = (row.get('login') or {}).get('state')
            configured = service.main_ai.subscription_model(route_id)
            if isolated:
                reason = '' if route_id == current else 'isolated'
                tools = list(profile_actions(ISOLATED_PROFILE))
                models = []
            else:
                reason = ('not_installed' if not row.get('installed') else 'signed_out' if login == 'signed-out'
                          else 'not_connected' if route_id != current and not checked else '')
                if not reason and host_profile != BOUNDED_PROFILE:
                    _facade, options = service.subscription_facade(route_id)
                    reason = '' if options.get('qualification') else 'strict_unqualified'
                tools = [*profile_actions(host_profile), 'web_search']
                models = runnable_models(service, route_id, configured, known_models(route_id, listed), refused)
                if configured and configured in (refused.get(route_id) or set()):
                    # #735 review: the owner's configured model was refused for this
                    # account; "" resolves to the next runnable model instead.
                    reason = reason or ('' if models else 'default_model_refused')
            if not browser:
                tools = [tool for tool in tools if tool not in BROWSER_ACTIONS]
            substitute = configured and configured in (refused.get(route_id) or set())
            worker.update(available=not reason, reason=reason, models=models,
                          default_model=(models[0] if models else '') if substitute else configured,
                          default_refused=configured if substitute else '')
            routes[route_id] = {'kind': KIND_SUBSCRIPTION, 'subscription': {'id': route_id}}
        else:
            if route_id == current:
                config = store.config('model', {}) or {}
                key = store.secret('model_key') or ''
                test = store.config('model_test')
            else:
                check = checks.get(route_id) or {}
                config, test = check.get('config'), check.get('test')
                key = store.secret(key_slot(route_id)) or ''
                saved_at = (meta.get(route_id) or {}).get('saved_at') or 0
                if not isinstance(check.get('checked_at'), (int, float)) or check['checked_at'] < saved_at:
                    config = None
            config = dict(config) if isinstance(config, dict) else {}
            ready = bool(config and key and api_route_of(config) == route_id and service.model_ready(config, test))
            reason = '' if ready else ('no_api_key' if not key else 'not_verified')
            tools = [tool for tool in package_tools if browser or tool not in BROWSER_ACTIONS]
            model = str(config.get('model') or '')
            worker.update(available=ready, reason=reason, default_model=model, models=[model] if model else [])
            routes[route_id] = {'kind': KIND_API, 'config': config, 'key': key, 'test': test}
        worker['tools'] = sorted(dict.fromkeys(tools))
        worker['private_tools'] = sorted(set(worker['tools']) & private)
        worker['model_tiers'] = {model: model_tier(route_id, model, RANKED_MODELS) for model in worker['models']}
        workers.append(worker)
    if current == 'other':
        # A Main AI outside the chooser (an existing local or compatible
        # connection) is the default worker and the only one of its kind.
        config = store.config('model', {}) or {}
        key = store.secret('model_key') or ''
        ready = service.model_ready(config)
        workers.append({'id': 'other', 'kind': KIND_API, 'name': str(config.get('provider') or 'other'),
                        'destination': str(config.get('endpoint') or ''), 'default': True, 'native_search': False,
                        'browser': False, **KIND_TIERS[KIND_API], 'available': ready, 'reason': '' if ready else 'not_verified',
                        'default_model': str(config.get('model') or ''), 'models': [str(config.get('model') or '')],
                        'model_tiers': {}, 'tools': [tool for tool in package_tools if tool not in BROWSER_ACTIONS],
                        'private_tools': []})
        workers[-1]['private_tools'] = sorted(set(workers[-1]['tools']) & private)
        routes['other'] = {'kind': KIND_API, 'config': dict(config), 'key': key, 'test': None}
    tools_by_id = {tool['id']: tool for package in service.runtime_packages() for tool in package['tools']}
    return Catalogue(workers, routes, current, descriptions=tool_descriptions(tools_by_id))


class Catalogue:
    """The workers one Work may be given, and how each is reached.

    ``workers`` is what the orchestrator is shown (no credentials); ``routes``
    is what the service needs to run one (never shown to a model).
    """

    def __init__(self, workers, routes, default, descriptions=None):
        self.workers = [dict(worker) for worker in workers]
        #: One declared line per tool id (#729), shown to the orchestrator once.
        self.descriptions = dict(descriptions or {})
        self.routes = dict(routes)
        self.default = default if any(worker['id'] == default for worker in self.workers) else ''

    def worker(self, worker_id):
        return next((worker for worker in self.workers if worker['id'] == worker_id), None)

    def available(self, pinned=False):
        """Workers a plan may choose: every available one, or only the default when pinned."""
        rows = [worker for worker in self.workers if worker['available']]
        return [worker for worker in rows if worker['id'] == self.default] if pinned else rows


def one_line_description(text, limit=180):
    """The first sentence of a tool description, on one line (#729)."""
    text = ' '.join(str(text or '').split())
    end = text.find('. ')
    return (text[:end + 1] if 0 < end < limit else text[:limit]).strip()


def tool_descriptions(package_tools):
    """``{tool id: one line}`` from the tools' own declared descriptions (#729).

    ``package_tools`` maps tool ids to their manifest entries (``host_action``);
    the text is the host action's model-facing description (``DEFINITIONS``),
    never a line written here.
    """
    from .agent_runtime import DEFINITIONS
    declared = {row['function']['name']: row['function'].get('description', '') for row in DEFINITIONS}
    return {tool_id: one_line_description(declared.get((tool or {}).get('host_action'), ''))
            for tool_id, tool in sorted(package_tools.items())}


def render_tool_descriptions(workers, descriptions):
    """One line per tool any offered worker has: what it does (data only)."""
    names = sorted({tool for worker in workers for tool in worker['tools']})
    return '\n'.join(f'- {name}: {descriptions.get(name) or "no description declared"}' for name in names) or 'none'


def render_catalogue(workers):
    """The catalogue as the orchestrator reads it: one line per worker, data only."""
    lines = []
    for worker in workers:
        default = worker['default_model'] or 'its own default'
        models = ', '.join([f'"" (worker default: {default})',
                            *[f'{model} ({worker["model_tiers"].get(model, TIER_UNRANKED)})'
                              for model in worker['models'] if model != worker['default_model']]])
        tools = ', '.join(f'{tool} (private read)' if tool in worker['private_tools'] else tool for tool in worker['tools'])
        lines.append(f'- worker={worker["id"]} ({worker["name"]}, {worker["kind"]}; default Main AI: '
                     f'{"yes" if worker["default"] else "no"}; cost: {worker["cost"]}; latency: {worker["latency"]}; '
                     f'own web search: {"available" if worker["native_search"] else "not available"}; browser tools: '
                     f'{"available" if worker["browser"] else "not available"}; models: {models}; tools: {tools or "none"})')
    return '\n'.join(lines)


def plan_schema(workers):
    tools = sorted({tool for worker in workers for tool in worker['tools']})
    item = {'type': 'string', 'enum': tools} if tools else {'type': 'string'}
    return {'type': 'object', 'additionalProperties': False,
            'properties': {
                'worker': {'type': 'string', 'enum': [worker['id'] for worker in workers]},
                'model': {'type': 'string'},
                'brief': {'type': 'object', 'additionalProperties': False,
                          'properties': {'goal': {'type': 'string'},
                                         'context': {'type': 'array', 'items': {'type': 'string', 'enum': list(SECTIONS)}},
                                         'completion_criteria': {'type': 'array', 'items': {'type': 'string'}}},
                          'required': ['goal', 'context', 'completion_criteria']},
                'tools_mode': {'type': 'string', 'enum': [TOOLS_DEFAULT, TOOLS_SUBSET]},
                'tools': {'type': 'array', 'items': item},
                'tools_reason': {'type': 'string'},
                'reason': {'type': 'string'}},
            'required': ['worker', 'model', 'brief', 'tools_mode', 'tools', 'tools_reason', 'reason']}


def plan_shape(data):
    """Types only; meaning is ``Orchestration.validate``'s."""
    brief = data.get('brief')
    strings = lambda value: isinstance(value, list) and all(isinstance(item, str) for item in value)  # noqa: E731
    return (isinstance(data.get('worker'), str) and isinstance(data.get('model'), str)
            and isinstance(brief, dict) and isinstance(brief.get('goal'), str)
            and strings(brief.get('context')) and strings(brief.get('completion_criteria'))
            and data.get('tools_mode') in (TOOLS_DEFAULT, TOOLS_SUBSET) and strings(data.get('tools'))
            and isinstance(data.get('tools_reason'), str) and isinstance(data.get('reason'), str))


# --- the tool subset rule (#735) ----------------------------------------------
#: Why a planned subset was replaced by the worker's full toolset.
SUBSET_SHAPE, SUBSET_NO_REASON, SUBSET_UNKNOWN = 'shape', 'no_reason', 'not_offered'


def search_tools():
    """The worker's web-search tools: the ones its own web search replaces (#678/#701)."""
    from .bounded_execution import NATIVE_SEARCH_REPLACED
    return frozenset(NATIVE_SEARCH_REPLACED)


def subset_or_default(worker, requested, reason):
    """``(tools, replaced)`` for a planned subset: kept, or replaced by the full toolset (#735).

    Validation, not a judgment: a subset stands only when it removes the
    whole private-read category, or the whole web-search category, of the
    worker's offered tools (to keep the two apart, the one reason to narrow),
    removes nothing else, and states that reason.  Removing part of a
    category is not a separation and is replaced too.
    Every other subset becomes the worker's full offered toolset (None) and
    ``replaced`` records what was asked for and why it was not kept.
    """
    offered = frozenset(worker['tools'])
    requested = frozenset(requested or ())
    removed = offered - requested
    if not requested <= offered:
        why = SUBSET_UNKNOWN
    elif not removed:
        return None, None
    elif removed not in (offered & frozenset(worker.get('private_tools') or ()), offered & search_tools()):
        why = SUBSET_SHAPE
    elif not reason:
        why = SUBSET_NO_REASON
    else:
        return requested, None
    return None, {'requested': sorted(requested), 'why': why}


# --- one attempt -------------------------------------------------------------
class Attempt:
    """One worker run of a Work: from a validated plan, or the default fallback.

    ``tools`` is a frozenset (the validated subset) or None (the worker's usual
    set); ``sections`` is the set of context sections the worker receives.
    """

    __slots__ = ('number', 'worker', 'model', 'goal', 'criteria', 'sections', 'tools', 'reason', 'planned',
                 'fallback', 'digest', 'tools_reason', 'replaced', 'signature')

    def __init__(self, number, worker, *, model='', goal='', criteria=(), sections=SECTIONS, tools=None, reason='',
                 planned=False, fallback='', tools_reason='', replaced=None):
        self.number, self.worker, self.model = number, worker, model
        self.tools_reason = tools_reason
        #: #735: the subset the plan asked for when validation replaced it with the full toolset.
        self.replaced = replaced
        #: The worker, effective model and tool set this attempt ran with, fixed at validation.
        self.signature = None
        self.goal, self.criteria, self.sections = goal, tuple(criteria), frozenset(sections)
        self.tools = None if tools is None else frozenset(tools)
        self.reason, self.planned, self.fallback = reason, planned, fallback
        self.digest = digest({'goal': goal, 'criteria': list(criteria), 'sections': sorted(self.sections),
                              'tools': None if tools is None else sorted(self.tools)}) if planned else ''

    def brief(self, adjusted=False):
        """The brief section text a worker receives, or None for a fallback attempt."""
        if not self.planned:
            return None
        lines = [f'Goal: {self.goal}']
        if self.criteria:
            lines.append('Done when:')
            lines.extend(f'- {criterion}' for criterion in self.criteria)
        if adjusted:
            lines.append('An earlier attempt did not meet this goal; this brief was adjusted for this attempt.')
        return '\n'.join(lines)

    def section(self, name, value):
        """``value`` when this attempt's brief selected the section ``name``, else None."""
        return value if name in self.sections else None

    def native_search(self, enabled, reason, private_tools):
        """The CLI's own web search for this attempt: the existing gate, narrowed by the tool choice.

        A selected private-read tool turns it off (the two are never on in the
        same turn); a subset without ``web_search`` turns it off too.
        """
        if not enabled or self.tools is None:
            return enabled, reason
        if self.tools & frozenset(private_tools):
            return False, 'orchestrated_private_tools'
        if 'web_search' not in self.tools:
            return False, 'orchestrated_no_search'
        return enabled, reason


class Orchestration:
    """Plan, evaluate and re-delegate one Work (#710).

    ``judgments`` is the service's ``ConversationJudgments`` (its engine, its
    redactor, its ``goal_reached``); ``record(status, detail)`` appends one
    ``orchestrator`` event to the Work's Evidence; ``state`` is a
    ``(read, write)`` pair over the durable orchestration state used only for
    the once-said fallback notice.  ``pinned`` restricts the plan to the
    default worker (the turn carries material the owner approved for it).
    """

    def __init__(self, judgments, catalogue, *, request, conversation='', sections=None, budget=None, record=None,
                 state=None, pinned=False, work_id=None, policy=None):
        self.judgments, self.catalogue = judgments, catalogue
        self.request, self.conversation = str(request or ''), str(conversation or '')
        self.sections = dict(sections or {})
        self.budget, self.record = budget, record or (lambda status, detail: None)
        self.state, self.pinned, self.work_id = state, pinned, work_id
        self.policy = policy or DecisionPolicy()
        self.attempts = []
        self.history = []  # (attempt, evaluation, answer excerpt, factual summary)
        #: Signatures (worker, model, tools) of attempts that fell short (#729).
        self.failed = set()
        self.notice = ''
        self.orchestrated = False
        #: The evaluation of the last attempt when no further attempt followed
        #: (the caller keeps a CLI Work judged short from being stored as succeeded).
        self.terminal = None

    # -- the plan call --------------------------------------------------------
    def _redact(self, text, private=True):
        redact = getattr(self.judgments, 'redact', None)
        return redact(text, private=private) if redact else str(text or '')

    def budget_allows(self):
        """Whether the Work's deadline, Stop and turns still allow another model call
        and an attempt after it (checked before every plan and evaluation call)."""
        budget = self.budget
        if budget is None:
            return True
        try:
            if budget.interrupted() is not None or budget.remaining() < MIN_ATTEMPT_SECONDS:
                return False
            return getattr(budget, 'turns_used', 0) < getattr(budget, 'turns', 1)
        except Exception:
            return False

    def _interrupted(self):
        """Whether the owner stopped this Work (or its budget cannot say)."""
        try:
            return self.budget is not None and self.budget.interrupted() is not None
        except Exception:
            return True

    def _budget_text(self):
        budget = self.budget
        if budget is None:
            return f'at most {MAX_REDELEGATIONS} re-delegations'
        try:
            left = max(0, int(budget.remaining()))
            turns = max(0, getattr(budget, 'turns', 0) - getattr(budget, 'turns_used', 0))
        except Exception:
            left, turns = 0, 0
        return (f'{left} seconds and {turns} model turns left in this Work; at most {MAX_REDELEGATIONS} '
                f're-delegations after the first attempt')

    def _sections_text(self):
        parts = []
        for name in SECTIONS:
            value = self.sections.get(name)
            if name == 'history':
                parts.append(f'history ({int(value or 0)} earlier messages)')
            else:
                parts.append(f'{name} ({len(value)} chars)' if value else f'{name} (empty)')
        return ', '.join(parts)

    def _attempts_text(self):
        if not self.history:
            return 'none'
        rows = []
        for attempt, evaluation, answer, summary in self.history:
            rows.append(f'attempt {attempt.number}: worker={attempt.worker} model={attempt.model or "default"} '
                        f'tools={"worker default" if attempt.tools is None else ", ".join(sorted(attempt.tools)) or "none"} '
                        f'goal={one_line(attempt.goal, 300) or "the raw request"} '
                        f'what happened={one_line(summary, 500) or "no tool was called"} '
                        f'evaluation={evaluation} ({EVALUATION_REASON.get(evaluation, evaluation)}) '
                        f'answer excerpt (model-stated)={one_line(answer, ANSWER_EXCERPT_CHARS)}')
        return '\n'.join(rows)[-ATTEMPTS_CHARS:]

    def _ask(self, candidates):
        """``(data, failure)`` for one plan call over ``candidates``."""
        engine = getattr(self.judgments, 'engine', None)
        method = getattr(engine, 'structured', None)
        if method is None or not candidates:
            return None, FALLBACK_UNAVAILABLE
        # The Work's deadline is checked before the call, never after spending it.
        if not self.budget_allows():
            return None, FALLBACK_BUDGET
        request = self._redact(self.request, private=False)
        workers = render_catalogue(candidates)
        tools_text = render_tool_descriptions(candidates, getattr(self.catalogue, 'descriptions', {}))
        facts = {'owner_request': request,
                 'recent_conversation': self._redact(self.conversation[-CONVERSATION_CHARS:]) or 'none',
                 'context_sections': self._sections_text(),
                 'workers': workers,
                 'tool_descriptions': tools_text,
                 'budget': self._budget_text(),
                 'previous_attempts': self._redact(self._attempts_text())}
        context = DecisionContext(PURPOSE, facts, work_id=self.work_id,
                                  max_chars=MAX_CONTEXT_CHARS + len(request) + len(workers) + len(tools_text))
        try:
            decision = method(context, QUESTION, plan_schema(candidates), plan_shape)
        except Exception:
            return None, FALLBACK_UNAVAILABLE
        if decision.outcome == OUTCOME_MALFORMED:
            return None, FALLBACK_MALFORMED
        if decision.outcome != OUTCOME_DECIDED:
            return None, FALLBACK_UNAVAILABLE
        data = self.policy.structured(decision)
        if data is None:
            return None, FALLBACK_UNCONFIDENT
        return data, ''

    def validate(self, data, candidates, number):
        """``(Attempt, '')`` for a plan that passes every deterministic check, else ``(None, what)``."""
        if not isinstance(data, dict) or not plan_shape(data):
            return None, 'shape'
        worker = next((row for row in candidates if row['id'] == data['worker']), None)
        if worker is None or not worker['available']:
            return None, 'worker'
        model = data['model'].strip()
        if model and model not in worker['models']:
            return None, 'model'
        if not model and worker.get('default_refused'):
            # #735 review: the worker's default was refused for this account;
            # this attempt runs the substitute the catalogue chose, explicitly.
            model = worker['default_model']
        brief = data['brief']
        goal = brief['goal'].strip()[:MAX_GOAL_CHARS]
        if not goal:
            return None, 'brief'
        if any(name not in SECTIONS for name in brief['context']):
            return None, 'sections'
        criteria = [one_line(item, MAX_CRITERION_CHARS) for item in brief['completion_criteria'] if item.strip()][:MAX_CRITERIA]
        tools_reason = one_line(data['tools_reason'], MAX_REASON_CHARS)
        tools, replaced = None, None
        if data['tools_mode'] == TOOLS_SUBSET:
            tools, replaced = subset_or_default(worker, data['tools'], tools_reason)
        if self.signature(worker, model, tools) in self.failed:
            # #729: a combination that already fell short is not tried again unchanged.
            return None, 'repeat'
        if not self.budget_allows():
            return None, 'budget'
        attempt = Attempt(number, worker['id'], model=model, goal=goal, criteria=criteria, sections=brief['context'],
                          tools=tools, reason=one_line(data['reason'], MAX_REASON_CHARS), planned=True,
                          tools_reason=tools_reason if tools is not None else '', replaced=replaced)
        attempt.signature = self.signature(worker, model, tools)
        return attempt, ''

    def drop_model(self, worker_id, model):
        """The CLI refused ``model`` for this account: never offer it again in this Work (#735)."""
        worker = self.catalogue.worker(worker_id)
        if worker is None or not model:
            return
        worker['models'] = [item for item in worker['models'] if item != model]
        worker['model_tiers'] = {key: value for key, value in worker['model_tiers'].items() if key != model}
        if worker.get('default_model') == model:
            # #735 review: "" must not resolve to a refused default.  The next
            # runnable model stands in; with none left the worker is unavailable.
            worker['default_refused'] = model
            worker['default_model'] = worker['models'][0] if worker['models'] else ''
            if not worker['models']:
                worker.update(available=False, reason='default_model_refused')

    @staticmethod
    def signature(worker, model, tools):
        """Worker, effective model and effective tool set of an attempt (#729)."""
        return (worker['id'], model or worker.get('default_model') or '',
                frozenset(worker['tools']) if tools is None else frozenset(tools))

    # -- evidence -------------------------------------------------------------
    def _worker_label(self, attempt):
        worker = self.catalogue.worker(attempt.worker) or {}
        return f'{worker.get("name") or attempt.worker} · {attempt.model or DEFAULT_MODEL_LABEL}'

    def _planned(self, attempt):
        self.record(PLANNED, {'attempt': attempt.number, 'worker': attempt.worker, 'model': attempt.model or None,
                              'brief_digest': attempt.digest, 'sections': sorted(attempt.sections),
                              'tools': None if attempt.tools is None else sorted(attempt.tools),
                              'tools_reason': self._redact(attempt.tools_reason) or None,
                              'tools_replaced': attempt.replaced,
                              'reason': self._redact(attempt.reason),
                              'text': f'{attempt.number}번째 시도: {self._worker_label(attempt)} — {self._redact(attempt.reason)}'})

    def _set_state(self, value):
        if not self.state:
            return {}
        read, write = self.state
        try:
            previous = read() or {}
            if (previous or {}).get('state') != value:
                write({'state': value})
            return previous if isinstance(previous, dict) else {}
        except Exception:
            return {}

    # -- the loop -------------------------------------------------------------
    def first(self):
        """The first attempt: the validated plan, or the default Main AI with the raw request."""
        candidates = self.catalogue.available(self.pinned)
        data, failure = self._ask(candidates)
        attempt, invalid = (self.validate(data, candidates, 1) if data is not None else (None, ''))
        if attempt is not None:
            self.orchestrated = True
            self._set_state('active')
            self.attempts.append(attempt)
            self._planned(attempt)
            return attempt
        failure = failure or FALLBACK_INVALID
        attempt = Attempt(1, self.catalogue.default, fallback=failure)
        self.attempts.append(attempt)
        previous = self._set_state('fallback') if failure == FALLBACK_UNAVAILABLE else {}
        if failure == FALLBACK_UNAVAILABLE and previous.get('state') == 'active':
            self.notice = NOTICE_ONCE
        self.record(FALLBACK, {'attempt': 1, 'worker': attempt.worker, 'code': failure, 'invalid': invalid or None,
                               'notice': bool(self.notice), 'text': FALLBACK_TEXT[failure]})
        return attempt

    def evaluate_run(self, result, *, owner_needed=False):
        """What a direct-route run showed: its own #657 completion judgment, no new call."""
        outcome = getattr(result, 'outcome', 'succeeded')
        report = getattr(result, 'report', None) or {}
        if outcome == 'succeeded':
            return REACHED
        if owner_needed or report.get('question'):
            return OWNER_NEEDED
        if getattr(result, 'judgment', None) == 'unavailable':
            return UNJUDGED
        return NOT_REACHED

    def evaluate_answer(self, answer, observations, failed=''):
        """One ``goal_reached`` judgment over a CLI attempt's final answer and recorded tool evidence.

        Not asked when the Work's deadline no longer allows another attempt:
        the evaluation only serves a re-delegation (``NOT_JUDGED``, next step
        ``budget``).
        """
        goal_reached = getattr(self.judgments, 'goal_reached', None)
        if goal_reached is None:
            return UNJUDGED
        if not self.budget_allows():
            return NOT_JUDGED
        text = (f'The worker\'s final answer (model-stated, not an observation):\n{str(answer or "")[:1800]}\n\n'
                f'Tool results AgentOS recorded for this attempt:\n{observations or "none"}')[:OBSERVATION_CHARS]
        try:
            judged = goal_reached(self.request, text, str(failed or '')[:FAILURE_CHARS], work_id=self.work_id)
        except Exception:
            return UNJUDGED
        verdict = getattr(judged, 'outcome', None)
        if verdict == 'no' and self.owner_input_needed(answer):
            # #740: the worker asked the owner for what the request needs; another
            # worker cannot supply it, so the question is the reply.
            return OWNER_NEEDED
        return REACHED if verdict == 'yes' else NOT_REACHED if verdict == 'no' else UNJUDGED

    def owner_input_needed(self, answer):
        """Does the worker's final answer ask the owner for input the request needs (#740)?

        One judgment over the owner's request, the recent conversation and the
        answer, asked only after ``goal_reached`` said no.  A question the
        request or the conversation already answers is not needed; unavailable
        or unsure is no, so the attempt stays short.  It decides what the owner
        receives, not whether another attempt runs, so only an owner Stop
        skips it (the deadline was checked before ``goal_reached``).
        """
        judge = getattr(self.judgments, 'owner_input_needed', None)
        if judge is None or not str(answer or '').strip() or self._interrupted():
            return False
        try:
            judged = judge(self.request, self.conversation[-CONVERSATION_CHARS:],
                           str(answer)[:ANSWER_EXCERPT_CHARS * 3], work_id=self.work_id)
        except Exception:
            return False
        return getattr(judged, 'outcome', None) == 'yes'

    def next(self, attempt, evaluation, *, answer='', failed='', effect=False):
        """The next attempt after ``attempt`` was evaluated, or None (recorded either way).

        Only an orchestrated Work re-delegates: a fallback run is the owner's
        default Main AI exactly as before #710 and records no evaluation.
        """
        if not self.orchestrated:
            return None
        self.history.append((attempt, evaluation, answer, failed))
        worker = self.catalogue.worker(attempt.worker)
        if evaluation != REACHED and worker is not None:
            # The combination it actually ran with, even if the worker's default changed since (#735 review).
            self.failed.add(attempt.signature or self.signature(worker, attempt.model, attempt.tools))
        if evaluation == REACHED:
            stop = STOP_REACHED
        elif evaluation == OWNER_NEEDED:
            stop = STOP_OWNER
        elif effect:
            stop = STOP_EFFECT
        elif len(self.attempts) > MAX_REDELEGATIONS:
            stop = STOP_LIMIT
        elif evaluation == NOT_JUDGED or not self.budget_allows():
            # Not judged because the Work's time or turns ran short (an effect is named above).
            stop = STOP_BUDGET
        elif evaluation == UNJUDGED:
            stop = STOP_UNJUDGED
        else:
            stop = ''
        following, invalid = None, ''
        if not stop:
            candidates = self.catalogue.available(self.pinned)
            data, failure = self._ask(candidates)
            following, invalid = (self.validate(data, candidates, len(self.attempts) + 1) if data is not None
                                   else (None, ''))
            if following is None:
                stop = STOP_BUDGET if failure == FALLBACK_BUDGET else STOP_REPLAN
        after = NEXT_TEXT['redelegate'] if following is not None else NEXT_TEXT[stop]
        self.record(EVALUATED, {'attempt': attempt.number, 'worker': attempt.worker, 'model': attempt.model or None,
                                'brief_digest': attempt.digest or None, 'outcome': evaluation,
                                'next': 'redelegate' if following is not None else 'stop', 'stop': stop or None,
                                'invalid': (invalid or None) if not stop or stop == STOP_REPLAN else None,
                                'text': ' '.join(part for part in (EVALUATED_TEXT[evaluation], after) if part)})
        if following is not None:
            self.attempts.append(following)
            self._planned(following)
        else:
            self.terminal = evaluation
        return following
