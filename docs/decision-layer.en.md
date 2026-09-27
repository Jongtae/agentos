# Provider-independent Decision Layer

## Pilot posture — #653 (2026-09-26)

Under SECRETARY-01 the DecisionEngine is the gate that lets the assistant choose and change paths (provider, site, query, recovery, goal-reached judgment), not a request-time blocker. The `lookup_term_sensitivity` judgment and its qualification case are removed by SEC-PILOT-01 #654; SEC-LOOP-01 #657 adds a `goal_reached` judgment. See the [Secretary Agency Contract](secretary-agency-contract.en.md).

## Amendment — #710 (2026-09-27)

ORCH-01 makes the DecisionEngine the **orchestrator** of each Work under Constitution C16: per request it chooses the AI worker and model, writes the brief and the tool subset, and re-delegates when the goal is not shown. It still never acts and never grants authority; see "Orchestration (ORCH-01 / #710)" below.

## Status and purpose

This document defines the intended **AgentOS-owned decision boundary** for bounded judgment such as Attention relevance, capability/runtime selection, result scoring, and “do we need another reasoning/evidence step?” routing.

It is an architecture contract, not a claim that the runtime interface is already implemented. On 2026-09-24 the owner selected this boundary as the semantic foundation for PRESENCE-01: production semantic decisions should be model-backed by default, initially through OpenAI `gpt-4o-mini`, while the interface remains provider-neutral. Current support still depends on merged code and named acceptance evidence.

The owner decisions recorded in [#415](https://github.com/Jongtae/agentos/issues/415) are:

> **Absorb the decision-layer interface and engineering principle; do not make Jev a required dependency.**
>
> **Minimize rule-based product logic. Use a model-backed DecisionEngine for ordinary semantic judgment, initially `gpt-4o-mini`, while keeping exact security/authority/truth/protocol invariants deterministic.**

The durable rule is:

> **Core depends on contracts/capabilities, never providers. AgentOS owns the decision contract; providers only implement it.**

## Why this boundary exists

Many agent loops use a general LLM for both generative reasoning and small repeated judgments: relevance, routing, confidence, completion checks, reference resolution or candidate selection. Personal AgentOS should not replace those semantic judgments with an accumulating rule engine merely because a keyword/regex branch is easy to add. Ordinary semantic product behavior is model-backed by default; deterministic logic is reserved for exact invariants and test fixtures.

Personal AgentOS must be able to change that implementation without changing owner authority, canonical state, or the meaning of Work.

The decision layer therefore separates:

1. **judgment/inference** — a bounded answer plus uncertainty/evidence;
2. **policy/authority** — deterministic AgentOS rules that decide what may happen;
3. **execution** — capability/runtime invocation under current Grants.

A provider can help answer “which candidate looks relevant?” It cannot answer “what authority does this Work have?” in a binding way.

## Neutral AgentOS vocabulary

Core contracts use provider-neutral names. The conceptual model includes:

- **DecisionContext** — minimal, attributable Work-scoped state supplied for a bounded question.
- **SelectionDecision<T>** — selection among declared candidates.
- **SelectionSetDecision<T>** — zero or more of the declared candidates (`choose_many`). Its first caller, the #605 lookup sensitivity judgment, was removed by SEC-PILOT-01 #654; the envelope remains. An engine that cannot answer one returns an explicit non-answer; the Jev route does not offer it and answers unavailable.
- **ScoreDecision** — evaluation against a declared scale or rubric.
- **BinaryDecision** — bounded yes/no judgment with confidence/probability.
- **DecisionConfidence** — confidence/probability (calibration is measured per provider, not assumed) plus available provenance/telemetry.
- **DecisionEngine** — provider-independent judgment interface.
- **DecisionPolicy** — AgentOS-owned deterministic thresholds, escalation/fallback rules and authority checks.

Illustrative shape only:

```ts
interface DecisionEngine {
  choose<T>(
    context: DecisionContext,
    candidates: readonly T[],
    question: string,
  ): Promise<SelectionDecision<T>>;

  score(
    context: DecisionContext,
    question: string,
    scale: DecisionScale,
  ): Promise<ScoreDecision>;

  judge(
    context: DecisionContext,
    proposition: string,
  ): Promise<BinaryDecision>;

  choose_many<T>(
    context: DecisionContext,
    candidates: readonly T[],
    question: string,
  ): Promise<SelectionSetDecision<T>>;
}
```

Exact runtime types require a separately activated implementation design. Provider SDK types and vendor terms do not leak into these core contracts.

## Decision is not authority

A decision provider returns bounded judgment. AgentOS policy determines what may happen next.

Example:

```text
DecisionEngine
  merge_ready = true
  confidence = 0.93

DecisionPolicy / AgentOS authority
  current Grant covers requested action?
  current approval covers target/parameters/destination?
  confidence threshold satisfied?
  consequence class requires human approval regardless?
  evidence/fallback requirement satisfied?
```

A model or decision provider must never:

- mint, widen or inherit a Grant;
- bypass a denial or covering approval requirement;
- authorize new data egress or a new external destination;
- directly mutate canonical Memory because its confidence is high;
- rewrite sealed Evidence;
- self-certify final Work completion;
- turn an Attention candidate into accepted Work without the normal boundary.

Deterministic code is reserved for distinctions that must be exact and mechanically enforced: Grants/authority, approval binding, idempotency, effect/Evidence qualification, cancellation/revocation, schema/protocol validation and similarly strict invariants. Language, intent, relevance, reference, routing, recovery choice and conversational projection should normally remain behind the model-backed decision boundary. A new natural phrasing should not normally require a new code branch.

## Replaceable implementations

The intended dependency direction is:

```text
Personal AgentOS Core
        |
        +-- DecisionEngine contract
              |
              +-- default OpenAI adapter: gpt-4o-mini
              +-- owner-selected AI adapter
              +-- local/small-model implementation
              +-- Jev adapter (optional / experimental)
              +-- deterministic/mock fixture implementation
              +-- future provider adapters
```

`gpt-4o-mini` is the initial production default, not part of the kernel contract. A later owner-selected AI, local model, Jev or another adapter may replace it without changing callers. Provider failure/removal must produce an explicit unavailable/unknown/clarification or other safe-stop outcome; it must not silently fall back to a growing phrase/regex rule tree.

## Candidate uses

The contract is intended to be introduced incrementally at bounded judgment points, including:

1. **Attention relevance/prioritization** — select or score authorized candidate facts, observations, memories or pending outcomes.
2. **Capability / skill / runtime routing** — choose among candidates that are already eligible under AgentOS policy.
3. **Retrieval/result scoring** — estimate relevance/quality while retaining source/evidence provenance.
4. **Reasoning escalation** — decide whether a cheap/deterministic path is insufficient and a stronger reasoning path is needed.
5. **Completion/quality confidence** — contribute to validation, never replace actual requirement-to-evidence checks.
6. **Risk/ambiguity classification** — inform deterministic policy, never act as the sole authorization gate.

The interface is not a requirement to route exact protocol or authority invariants through a learned model. For ordinary semantic product judgment, however, model-backed inference is the default and rule-based branching is the exception.

## Relationship to Attention and BDI-inspired design

Attention is a product/design mechanism for focusing on what is relevant now: owner outcome, current state, permitted context, urgency, unresolved decisions and possible next work.

A DecisionEngine may help evaluate Attention candidates. It does not replace the higher-level product concept and does not make a BDI state machine mandatory.

Likewise, the decision layer does not create:

- a second Context or Memory store;
- a new source of owner authority;
- a new Work lifecycle;
- a privileged hidden reasoning log;
- a mandatory distributed/multi-agent system.

The existing Owner, Context, Memory, Artifact, Capability, Runtime, Grant, Work, Event and Evidence responsibilities remain authoritative.

## External-provider boundary

An external decision provider is subject to the same owner-control rules as any other external runtime/provider:

- build the smallest useful Work-scoped DecisionContext;
- send only data covered for that destination and purpose;
- do not send private owner material merely because it may improve routing accuracy;
- preserve source/provenance where decisions depend on retrieved evidence;
- record configured provider/model and observed/provider-reported identity truthfully when available;
- retain decision result, confidence and relevant redacted metadata without hidden chain-of-thought;
- apply time, cost, resource and cancellation bounds;
- treat timeout, malformed output, unavailable telemetry and provider failure as explicit states;
- use a declared fallback or safe stop rather than widening authority.

## Jev adapter boundary

Jev is one possible implementation of the neutral contract, not the contract itself.

If a Jev adapter is later authorized, its provider concepts map at the adapter boundary:

| Jev concept | AgentOS contract |
| --- | --- |
| `Choice` | `SelectionDecision` |
| `Score` | `ScoreDecision` |
| `Noul` | `BinaryDecision` |

Jev/TypeSafe-specific request types, SDK objects and terminology must remain outside AgentOS core types.

Jev is currently:

- **not** a mandatory dependency;
- **not** the current default provider (`gpt-4o-mini` is the initial default behind the neutral interface);
- **not** required for AgentOS startup or normal operation;
- **not** evidence that a System-One architecture is already implemented;
- **not** exempt from normal data/egress/Grant controls.

A future adapter or provider promotion requires separately authorized implementation and comparable AgentOS-side evidence.

DECISION-ROUTE-01 / [#580](https://github.com/Jongtae/agentos/issues/580) authorized and added an optional Jev adapter (`decision_adapters.JevDecisionEngine`) over TypeSafe AI's documented HTTP API. It remains optional, off unless the owner saves a TypeSafe key **and** explicitly activates it, not a startup dependency and not the default. The mapping above is implemented at the adapter boundary only: `noul` → `BinaryDecision` (answer `noul ≥ 0.5`, probability of the chosen side), `choice` → `SelectionDecision` (criteria are the declared candidates plus `none-of-these`, Jev's `confidence` kept), `score` → `ScoreDecision` (five evenly spaced levels of the AgentOS scale, mapped back). TypeSafe documents English as its strongest language; Korean accuracy is an owner-visible caveat and is exactly what the qualification suite below measures.

## DecisionEngine routes (#580)

The DecisionEngine route is a **third role**, distinct from (1) the Personal AgentOS assistant identity and (2) the Work-execution route owned by [#504](https://github.com/Jongtae/agentos/issues/504). A provider or subscription may technically back more than one role; the roles stay separate in configuration, policy, telemetry and Evidence.

### Routes

| Route | Adapter | Destination | Credential | Model identity |
| --- | --- | --- | --- | --- |
| `direct_api` | `ModelDecisionEngine` over the existing `ModelAdapter` tool call | `api.openai.com` (initial default `gpt-4o-mini`; other `decision_model` providers as before) | a decision-only OpenAI key, or the Work OpenAI key when the owner's Work API is already OpenAI (#417 default) | requested = configured model; observed = the response `model`, else `not reported` |
| `jev` | `JevDecisionEngine` over the existing bounded `request_json` transport | `api.typesafe.ai` (`POST /v1/systemone`) | owner's TypeSafe API key (`decision_jev_key` secret) | requested = `jev-latest` or an owner-entered pinned id; observed = the response's versioned `model` |
| `subscription_cli` | `SubscriptionCliDecisionEngine` over `BoundedExecutionAdapter` isolation | the subscription account's provider (OpenAI for Codex, Anthropic for Claude Code) | the CLI's own official login (Codex `CODEX_HOME`; Claude Code `CLAUDE_CODE_OAUTH_TOKEN` from #571) | requested per model policy; observed only when the CLI reports it (Claude Code `modelUsage`), otherwise `not reported` (Codex `exec --json` reports none) |
| `off` | `UnavailableDecisionEngine` | none | none | none |

When no route has been chosen, the #417 default applies unchanged. Every route receives exactly the `DecisionContext` the caller built (bounded by `MAX_CONTEXT_CHARS`); no route adds conversation history, Memory, files or connector content, and callers never branch on the route (`RoutedDecisionEngine`).

### Configuration and owner actions

- `decision_route` (config row) is the **active** route. It is written only by an explicit owner activation that passed its check; it is never written by saving a key or by a login check. The legacy Work-route calls `select_ai_route` / `connect_subscription_engine` never write it, and decision-route activation never writes `subscription_engine` or `model`.
- **Follow mode (PRESENCE-SETTINGS-02 / #619).** The Judgment AI has three modes: `follow_main` (the default for a fresh install and for owners with no `decision_route` row), explicit (a #580 route chosen under 판단 AI › 고급) and `off`. A `follow_main` row names the Main AI it was resolved for (`main`) and the model that Main AI's ranked cheapest-first list qualified (`decision_routes.FOLLOW_CANDIDATES` over `RANKED_MODELS`, SEC-JUDGE-01 #679; see *Judgment model policy* below): OpenAI API → `gpt-4o-mini`, then `gpt-6-luna`; Anthropic API → `claude-haiku-4-5`; OpenRouter → `openai/gpt-4o-mini`, each over `direct_api` with **the Main AI's own probed Work key** (`model_key`, read live and used only while that provider is the current Main AI; a newly saved but not yet confirmed provider key is never used); Claude Code → `subscription_cli`, `haiku` then `sonnet`; Codex → `subscription_cli` under the strict profile (below), `gpt-6-luna`, `gpt-5.6-luna`, `gpt-5.6-terra` filtered by the installed binary's bundled model listing. Every follow resolution runs `lowest_qualified`: each candidate in order through the full qualification suite, the first that passes is used, none passing leaves the row needing attention. A Main AI outside the chooser cannot be followed; the reason is shown and nothing is substituted. The **only** Work-route action that writes `decision_route` is the Main AI switch **확인하고 사용** (`/api/main-ai/activate`), and only while the mode is `follow_main`: after the Main AI probe passed and the Main AI was committed, the Judgment AI is re-resolved with its own synthetic probe. A failed judgment probe writes a `follow_main` row with `transport: off` (needs attention); it never keeps the previous destination and never falls back to another route, key or account. An explicit or `off` Judgment AI is never changed by a Main AI switch. A `follow_main` row whose `main` differs from the current Main AI (for example after a legacy switch) answers `provider_unavailable` until it is re-resolved. Choosing 기본 AI 따라가기 explicitly (`/api/decision-route/activate` with `transport: follow_main`) keeps the previous route on failure, like every other activation.
- Saving a key (`/api/decision-route/credential`) stores **only the key** and does **not** activate a route or start egress. `decision_model` (which the #417 resolver treats as a configured provider) is written only by a successful `direct_api` activation. With no `decision_route` row the pre-#580 default behaviour is unchanged. Removing a decision-only key after activation leaves the chosen route needing attention (`available: false`); it does not fall back to the Work OpenAI key.
- One activation runs at a time; a concurrent activation is refused ("already checking").
- Activation (`/api/decision-route/activate`) sends synthetic judgments (no owner content) through the candidate route: the full qualification suite for every model choice (`lowest_qualified` and `explicit`, including a direct API model, #679), one probe judgment for `engine_default`, Jev and `off`-adjacent checks; only a passing check commits. Any failure raises, records a content-free check, and leaves the previous route unchanged.
- Opening Settings reads configuration only: no subprocess, no model or HTTP call.
- There is **no cross-route fallback**. An unavailable active route answers `provider_unavailable`; it never falls back to another provider, account, subscription engine or the engine default.
- **Honest display (#679).** `DecisionRoutes.status()['effective']` names what answers the next judgment and why, as a translatable template: `active` ("기본 AI(Codex)를 따라가는 중 — gpt-5.6-luna, 검증됨"), `fallback`, `attention` or `off`. With no `decision_route` row the #417 default OpenAI API still answers when an OpenAI Work key exists; that is shown as a fallback with its reason ("구독 판단을 쓸 수 없어 OpenAI API(gpt-4o-mini)를 쓰는 중: …", with 확인 to resolve the follow route) instead of reading as "follow Main AI". Before #679 every recorded judgment of the owner's store ran on that default while Settings said "follow Main AI".

### Subscription model policy

- `engine_default` — no model flag; the isolated CLI answers with its own default. Because the owner's user configuration is ignored, this is not a user-configured default. Offered, never preselected (for Claude Code it is Opus).
- `explicit` — offered only when the installed CLI's own `--help` declares `--model` (checked on explicit owner action, recorded in `decision_cli_capabilities`). The owner-entered or listed identifier is then run through the **full qualification suite** on the owner's account (#679; a single probe before); a refusal is recorded as `model-not-verified`, a model that answers but does not qualify as `not-qualified`, never emulated through owner configuration, and the previous route stays.
- `lowest_qualified` — **the default in follow and separate mode (#679)**. Candidates are the owner's 1–3 (lightest first) or, when none are given, the route's ranked cheapest-first list. Each candidate in order runs the qualification suite; the first that passes is activated. If none passes the route is not changed and the failure is `no-qualified-candidate`; no stronger/different model or route is tried.

### Judgment model policy (SEC-JUDGE-01 / #679)

- **Ranked candidates are data** (`decision_routes.RANKED_MODELS`, each with its source URL and check date in a comment; no new component): Codex `gpt-6-luna`, `gpt-5.6-luna`, `gpt-5.6-terra`; Claude Code `haiku`, `sonnet`; OpenAI API `gpt-4o-mini`, `gpt-6-luna`; Anthropic API `claude-haiku-4-5`. Codex's list is filtered by what the installed binary bundles; codex-cli 0.153.4 does not bundle `gpt-6-luna` (`-m gpt-6-luna` warns "Model metadata … not found"), so on it the effective cheapest candidate is `gpt-5.6-luna`, and a newer CLI that bundles `gpt-6-luna` makes it first after requalification. `gpt-4o-mini` stays first for the OpenAI API because `gpt-6-luna` over Chat Completions (the `ModelAdapter` transport) is unverified; it is promoted only after an owner live check in which an explicit `gpt-6-luna` choice passed the full qualification on the owner's key, recorded here.
- **Model lists.** Settings fills a model list only on the owner's explicit **모델 목록 새로고침** (`POST /api/decision-route/models` with `{route}`, never on page open, the #609 pattern). Because it runs a CLI or sends a saved key to its provider it is a POST that needs an owner session and this page's own `Origin`; a cross-origin or Origin-less request is refused with 403 (#679 review P2-2): Codex `codex debug models --bundled` only (the catalogue compiled into the binary, no network, run with an empty per-call `CODEX_HOME`; the plain `codex debug models` rewrites the shared `$CODEX_HOME/models_cache.json` and is never run); Claude Code the documented aliases (`haiku`, `sonnet`, `opus`; the CLI has no machine-readable list); OpenAI and Anthropic the provider's official `GET /v1/models` with the key that route would use, narrowed to the ranked candidates (any other id can still be typed). Every entry is labelled **목록에 있음(검증 전)**: a listing is not account support. Choosing one is an ordinary activation that runs the full qualification; on failure the previous route is kept and the reason shown.
- **Effort.** A judgment asks for low reasoning effort where the model supports it: Codex `-c model_reasoning_effort="low"` checked against that model's `supported_reasoning_levels` in the bundled listing, Claude Code `--effort low` for `sonnet`/`opus` (Haiku 4.5 takes no effort setting, so none is sent), and only when the installed CLI's own `--help` declares `--effort`; otherwise nothing is sent and the route records `effort_note: effort-flag-missing`, shown in Settings (#679 review P2-3). The owner may pick another supported level with an explicit model; an unsupported level is refused before any call.
- **Work route model.** The Work route runs each CLI with the owner's user configuration ignored (Codex `--ignore-user-config`), so a model in `~/.codex/config.toml` never reached Work. The Main AI chooser now records an explicit model per subscription CLI (`subscription_engine_models`; empty is the CLI's own default) and `BoundedExecutionAdapter.command()` passes it as the CLI's `--model`, recorded as the turn's `requested_model`. Settings shows it and states that the Codex config model is not used. The isolated sidecar deployment keeps its closed request contract (prompt, engine, bearer, task id; `isolated_engine_sidecar._validate` rejects any other field) and takes no model: there the setting is hidden, a non-empty model is refused, and a Work model stored before isolation was configured makes the Work fail with a named reason instead of silently running the CLI default (확인하고 사용 clears it).
- Every subscription route (including `engine_default`) is tied to the CLI binary fingerprint (resolved path, size, mtime) and version recorded at activation, because the isolation-flag check, the Codex tool-surface plan and any verified model describe that binary. A changed binary makes the route answer `provider_unavailable` with `requalification-needed`, and Settings shows it as needing a re-check, until the owner re-activates.

### Qualification suite

`decision_qualification.py`, `SUITE_VERSION = decision-qualification/3` (#654 removed the `lookup-withholds-the-identifier` case that #605 had added in `/2`, so every route including Jev qualifies on the same cases; `/1` and `/2` qualifications recorded earlier stay as historical evidence), all cases must pass. Cases run through the production caller (`ConversationJudgments`) or `DecisionEngine.choose` + `DecisionPolicy`: retry after failed Work, correction, reference, a new topic is not a follow-up, an ambiguous referent abstains, declared-candidate selection, no invented candidate, parked-request withdrawal, and failed/partial/unknown projections that must not be upgraded. Contexts are synthetic. A provider failure is a failed case, never a pass. Changing any case requires a new suite version.

### Authority and threat model

- **Data sent.** Only the caller-built `DecisionContext` (short attributable facts such as the current short utterance plus prior intent/status) and the question/schema; the existing caller-side guards (for example, locally handled note/private-search requests are never sent) apply identically to every route. Probes and qualification send synthetic text only.
- **Destinations.** Exactly the active route's destination above, shown in Settings before activation. Switching routes is the owner's explicit destination decision; nothing switches implicitly. With `follow_main` (#619) the Judgment AI destination can change as a consequence of the owner's Main AI switch; the Main AI chooser lists **both** destinations (Main AI and the following Judgment AI) for the selected row before 확인하고 사용, inside the same explicit action. The follow candidate always goes to the same provider/account as the new Main AI.
- **Subscription isolation.** Each judgment runs in a fresh empty per-call directory that is also `HOME`, with `PATH=/usr/bin:/bin` (+ the CLI's own directory for Codex), no inherited environment, no shell, in its own process group (a timeout kills the whole group, including the native binary behind Codex's `codex.js` wrapper). The AgentOS MCP bridge is **not** attached: a judgment has no AgentOS tools. Activation refuses a CLI whose `--help` lacks the isolation flags (whole-flag match).
  - **Codex (#679: strict-isolated).** A Codex judgment launches with the #616 strict profile's own arguments (`bounded_execution.strict_launch_arguments`, reused unchanged): the `agentos-strict-isolated` permissions profile (platform `:minimal` and the per-call directory read-only, no network for sandboxed commands) **replaces** `--sandbox read-only`, whose policy could read the home folder and the store (`TRUSTED_LOCAL_LIMITATION`); `--ignore-rules`; and one `--disable` per non-allowlisted feature from the verified plan. Activation additionally runs the #616 no-model qualification (`BoundedExecutionAdapter.qualify_strict`): tested platform (macOS) and CLI version (0.153.4), an engine runtime root outside the baseline-readable paths, Codex's own sandbox runner under the exact profile **denying the home folder, the login profile, the owner store and a sibling turn directory** while the turn directory stays readable, and the strict feature plan. A failure refuses activation (`strict-profile-unqualified`) and keeps the previous route; a stored Codex route without a strict record for this platform answers `provider_unavailable`. The route stores the complete qualification record (binding: platform, resolved launcher and native binary with fingerprints, home, engine runtime root, owner store, `CODEX_HOME`; launcher and native sha256 digests; version), and **before every judgment** the guard applies exactly the strict Work route's checks (`strict_binding_mismatch`, both digests, and the version the CLI reports for `--version` in the AgentOS environment, one local model-free subprocess): any mismatch answers `provider_unavailable` with `requalification-needed` and makes no call (#679 review P1). Settings shows the binding mismatch from local stats only. The feature allowlist is `strict_allowed_features()`: `unified_exec` may stay listed as enabled (it cannot be disabled on 0.153.4 or 0.158) because `shell_tool` is disabled, so no command tool is offered, and the permissions profile would still confine a command. The full argv is `exec --json <strict arguments> --skip-git-repo-check --ignore-user-config --ephemeral --output-schema <file> [-c model_reasoning_effort=…] [--model …]`, no MCP servers, plus official `-c` overrides `web_search="disabled"`, `project_doc_max_bytes=0` (no project docs; see the global-instruction limitation below), `skills.include_instructions=false`, `include_environment_context=false`, `include_permissions_instructions=false`, `include_collaboration_mode_instructions=false`, `include_apps_instructions=false`, `tools.update_plan.enabled=false`. Tool-bearing features are handled as an **allowlist**: at activation AgentOS reads `codex features list` (local, no model call) with an empty `CODEX_HOME` (the defaults `--ignore-user-config` runs with), disables **every** listed, non-removed feature outside a small non-tool allowlist, whatever its default in that listing (so a feature that is off there but on under the owner's profile is still disabled; this covers `memories`, `multi_agent*`, `web_search_*`, `external_agent_memory_import`, `chronicle`), re-reads the listing with those disables, and refuses activation unless only allowlisted features remain; unknown stages/lines fail closed, and the CLI itself rejects an unknown feature name. Observed on the installed Codex CLI 0.153.4 (local listing only, 2026-09-25): `unified_exec` (command execution) still lists as enabled after `--disable unified_exec`; under the #580 decision allowlist that failed closed and Codex could not be activated. Since #679 the strict allowlist accepts it (above), and the no-model process test `tests/test_strict_isolation.py::CodexDecisionInstructionFiles::test_a_judgment_under_the_strict_profile_cannot_read_the_home_folder` (opt-in `AGENTOS_CLI_QUALIFICATION=1`, real codex-cli 0.153.4, loopback scripted model, synthetic `CODEX_HOME`) observed that the exact judgment argv offers no command tool and that, with the shell re-offered by a test-only argv edit, reads of a home canary and a store canary were denied ("Operation not permitted"). Claude Code and the API/Jev routes are unaffected. The same exposure exists on the separate Work-execution route and is out of #580's scope. **Unverified even where the check passes:** the resulting model-visible tool list is not observable locally (`codex debug prompt-input` shows messages, not tool definitions); it still shows a `multi_agent_role` developer message after `--disable multi_agent`, so "no tools" for Codex is a best-effort configuration, not a verified empty tool surface. Residual: `CODEX_HOME` stays the owner's real profile because Codex reads (and refreshes) its official login there and AgentOS does not read or copy it; with `--ignore-user-config` and the overrides above its `config.toml`, project docs and skill instructions are not loaded, but files such as bundled system skills may still be written there by the CLI. `--ignore-rules` (activation requires it in `codex exec --help`) keeps `$CODEX_HOME/rules` execpolicy rules from allowing a command outside the sandbox, reusing the #616 review P1 finding.
  - **Codex global instruction files (#624, observed limitation).** `project_doc_max_bytes=0` limits project docs only. **The global `$CODEX_HOME/AGENTS.override.md`, or when it is absent `$CODEX_HOME/AGENTS.md`, still reaches the Codex model context as a `# AGENTS.md instructions` user message under the full decision argv above.** Observed on Codex CLI 0.153.4 (2026-09-26) with `codex debug prompt-input` (no model call) and with the exact `SubscriptionCliDecisionEngine` argv against the real `codex exec`, a synthetic populated `CODEX_HOME` and a loopback scripted model (`tests/test_strict_isolation.py::CodexDecisionInstructionFiles`, opt-in `AGENTOS_CLI_QUALIFICATION=1`; no owner profile, account or live model). With neither file present no instruction-file content from `CODEX_HOME` reaches the prompt (Codex still reads its login there). No official option stops it: `codex exec --help` offers `--ignore-user-config` (config.toml only) and `--ignore-rules` (execpolicy only), and `-c instructions=...`, `project_doc_fallback_filenames=[]`, `project_root_markers=[]` did not remove it. A separate synthetic `CODEX_HOME` per judgment would stop it, but Codex keeps its login there (file or keyring store, refreshed by the CLI), so it would require AgentOS to copy or link the owner's credential, which this route does not do; that was rejected. Therefore that file's content is treated as **owner-authored, untracked, untrusted input** to a Codex judgment: AgentOS does not read, record or attribute it, a judgment remains advisory under the rules above (validated schema, closed options, no authority), and it goes to the same destination the route already names (OpenAI via the owner's Codex account). **Activation enforces this: Codex decision-route activation fails closed with `instruction-files-unqualified` unless the installed CLI version is listed in `CODEX_INSTRUCTION_FILES_QUALIFIED` (`decision_routes.py`), which may only be extended after that no-model harness was re-run for the version.** #679 lists `0.153.4` under the owner's pilot relaxation (#677 item 5): the harness above was run on exactly that version, and activation checks only the **size** of `$CODEX_HOME/AGENTS.override.md` and `AGENTS.md` (a stat, never their content) and shows a warning in Settings when one is non-empty (`instruction_files_present`); any other version still fails closed; a stored Codex route whose recorded CLI version is not listed answers `instruction-files-unqualified` at judgment time and is shown as unavailable; the Codex engine row in Settings (and the active-engine row) shows the limitation (`instruction_files`).** This finding is about Codex only; the Claude Code controls above are unchanged and their instruction-file effect remains as stated there.
  - **Claude Code:** `-p … --output-format json --json-schema … --tools "" --restricted --strict-mcp-config` (no `--mcp-config`) `--setting-sources ""`; `--restricted` (listed by the installed CLI's `--help`; its compatibility with the structured-output call was checked from `--help` only, not by a run) removes code-running tools and WebFetch unless `--tools` names them; (no user/project/local settings files) `--no-session-persistence --system-prompt …`, with `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` and `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` so no CLAUDE.md is discovered up from the working directory and no auto-memory is used. These env names were read from the 2.1.280 binary; their effect was not run-verified.
  - Residual risk: each CLI still reads its own official login profile, and Codex's strict permissions profile (Seatbelt on macOS) is enforced by Codex itself; its `:minimal` baseline keeps OS paths, /tmp and /private/var/tmp readable (`STRICT_ISOLATED_LIMITATION`), and the strict qualification is bound to the tested version and platform.
- **Credentials.** Keys are stored in the local secret store, never returned by the read model, and redacted from provenance (`decision_jev_key` added to the redaction list). Subscription logins are the CLI's own; AgentOS reads no credential file.
- **Authority.** Decisions remain judgment only: no route can mint/widen a Grant, add a destination for Work, mark Work complete, change effect/Evidence truth, or change the Work route. `DecisionPolicy` thresholds are unchanged.
- **Failure paths.** `timeout`, `provider_unavailable` (with `failure` = `auth`, `usage-limit`, `request-rejected`, `not-configured`, `cli-not-found`, `requalification-needed`, …), `malformed`, `context_rejected`, `cancelled` are explicit and tested; cancelled/oversized contexts make no call.
- **Provenance.** Each audit row records `route`, `engine`, `model_policy`, `requested_model` and `observed_model` (`not reported` when absent); the developer trace shows them apart from the Work executor.

### Verified capability sources

Recorded from the installed tools' own help and the provider's documentation on 2026-09-25 (and 2026-09-27 for #679), not from live runs: Codex CLI 0.153.4 (`codex exec --help`, `codex features list`, `codex debug models --bundled`, `-c model_reasoning_effort`); Claude Code 2.1.280 `--effort`/`--model`; Claude Code 2.1.280 (`claude --help`; the result record's `structured_output` field for `--json-schema`); TypeSafe HTTP API reference (`docs.typesafe.ai/api`, `/models`). Evidence class for #580: deterministic unit and DOM tests with fixture transports/runners shaped after those sources. In addition, one synthetic development-time local observation per CLI (outside AgentOS and outside the per-call isolated `HOME`, on the developer's own login) confirmed the argv shapes: Claude Code returned `structured_output` with `--tools ""` and reported `modelUsage`; Codex returned the schema answer as its last `agent_message` and reported no model; an unknown `--model` was refused by Codex with a structured `status: 400` and by Claude Code with `is_error` plus a `[claude-code:unrecognized_model]` stderr tag. **No AgentOS-mediated live Jev, OpenAI or subscription-CLI judgment was observed**, and no claim is made that a given account accepts a given model.

## Orchestration (ORCH-01 / #710)

Owner direction 2026-09-27 and Constitution C16: the owner's AI tools do the work; the decision model **orchestrates**. It is not a rule engine and it does not execute the task. `src/personal_agent/orchestrator.py` adapts the existing seams (decision `Adapt`, no framework):

- **Structured answer on the same contract.** `DecisionEngine.structured(context, question, schema, valid)` returns a `StructuredDecision` (object plus the usual confidence and non-answer outcomes). `SchemaDecisionEngine` implements it for the direct-API and subscription-CLI routes through their existing `_ask` (tool call, `--output-schema`, `--json-schema`); the adapter adds `confidence` to the caller's schema. Jev, `UnavailableDecisionEngine` and an unscripted `FixtureDecisionEngine` answer `provider_unavailable` (`structured-unsupported`). `DecisionPolicy.structured` applies the selection threshold. The audit row keeps no part of the answer (it may carry owner-derived text).
- **Worker catalogue (data).** Built per Work from stored configuration only: every Main AI route (`main_ai`) with its kind, destination, whether it is the default, its models (the owner's configured model, `decision_routes.known_models`: ranked cheapest-first candidates, documented aliases and the last explicit 모델 목록 새로고침 listing; an API route offers only its tool-call-verified model), a cost tier per model (rank in the cheapest-first list) and per route kind (subscription usage vs metered API; agent CLI vs direct API latency), the #701 agency (own web search, browser tools) and the AgentOS tools of that route (the host CLI profile's bridge actions plus `web_search`, or the package tools on the direct route), with private-read tools marked. A route other than the current Main AI is **available** only when the owner already passed 확인하고 사용 for it and nothing observed since says it cannot run: a CLI must be installed and not signed out (the isolated deployment serves only its own engine; a strict-isolated CLI needs its own qualification); an API route must still hold the key that passed the tool-call probe (the probe's content-free fields are kept with the route's check by 확인하고 사용 and by a passing 확인 recheck while the probed key is the route's saved key). Credentials are never part of the catalogue a model sees.
- **The plan.** Before a Work runs, one `structured` call over the owner's request (whole), a bounded recent-conversation excerpt (only rows a worker could be shown: no file-workspace document job and no Work whose recorded sources name a store whose turn envelope is withheld; a Work without a source record is left out), the names and sizes of the available context sections, the catalogue, the Work budget and any earlier attempts returns `{worker, model, brief: {goal, context, completion_criteria}, tools_mode, tools, reason}`. Deterministic code **only validates**: the worker is offered and available, the model is `""` (the worker's default) or listed for it, the context sections are declared names, the tools are a subset of that worker's tools, and the Work budget still allows an attempt (`MIN_ATTEMPT_SECONDS`). The brief reaches the worker as its own turn-context section (`agent_runtime.BRIEF_HEADING`) before the owner's request, which stays verbatim and takes precedence; unselected sections are not sent. A Work that carries spliced private material (documents, Drive, context inbox, notes) or an attachment approved for the default destination is **pinned**: only the default worker is offered.
- **Tools per request.** A subset narrows `Capabilities.allowed_tools`, the bridge's list (`--only`) and Claude Code's `--allowedTools`; it can never widen them. The existing invariant is kept: a private-read tool and the CLI's own web search are never on in the same turn. A selected private-read tool turns the CLI's own search off for that attempt (`orchestrated_private_tools`), a subset without `web_search` turns it off (`orchestrated_no_search`), and on a native-search turn private reads stay withheld as before (#678/#701). This is how a natural-language notes request on a native-search route can read notes (the #711 gap) without a request-specific rule.
- **Evaluate and re-delegate.** Direct route: the run's own #657 completion judgment (`run_agent` now exposes it as `result.judgment`). CLI route: one `goal_reached` judgment over the final answer and the tool evidence AgentOS recorded for that attempt. On `not_reached` or a raised worker failure the orchestrator is asked again with the earlier attempts listed and may change the brief, worker, model or tools; at most `MAX_REDELEGATIONS = 2` re-delegations, within the Work's one shared `WorkBudget`. No re-delegation after an attempt that ran any action outside the effect-free reads or left an unknown effect (C8), after an owner question/approval need, or when the evaluation is unavailable. The Work's deadline and turns are checked before every plan and `goal_reached` call; when they no longer allow another attempt neither call is made and the next step is recorded as `budget`. A later attempt inherits the private-store labels this Work's earlier attempts recorded (`recorded_private_sources`): they close AgentOS-composed egress, keep the CLI's own web search off for that attempt (`private_turn`; the browser-session label excepted, as on the first attempt) and keep its local envelope to size and digest. A CLI attempt that ends judged `not_reached` or unjudged without a further attempt (limit, budget or no new plan) is never stored as succeeded: not reached is `partial` when the attempt observed a successful tool result and `failed` otherwise, unjudged is `partial`, each with the #657 unknown statement. An explicit `/search` preflight is a `web_search` call and is skipped when the attempt's tool subset leaves `web_search` out.
- **Fallback.** When the Judgment AI cannot answer (`judgment_unavailable`) or its plan is malformed, unconfident or invalid, the owner's default Main AI runs the raw request exactly as before #710, with no brief, subset or model change, and never re-delegates. Why is recorded once per Work. When orchestration had been working and the Judgment AI becomes unavailable, the reply says so once (`orchestrator.NOTICE_ONCE`); an installation where it never worked sees no change.
- **Evidence.** `orchestrator` tool events per Work: `planned` (attempt, worker, model, brief digest, sections, tools, one-line reason, owner text), `fallback` (code, owner text) and `evaluated` (outcome, next: `redelegate` or `stop` with the reason). The brief text itself is not stored; the digest identifies it. These statuses are not attempts of the Work's trail (`event_trail` reads only `succeeded`/`failed`).
- **No task-specific code.** The question text is generic; no request, site, provider or category is named. `tests/test_no_scenario_code.py` scans `orchestrator.py`.
- **ORCH-02 (#729): full toolset by default, learning from failed attempts.**
  - `tools_mode` defaults to `worker_default` (the worker's full offered toolset). A `subset` is valid only with a stated `tools_reason` (recorded in the `planned` event); without one the plan is invalid. The plan call carries one declared line per tool (`tool_descriptions`: the first sentence of the host action's own model-facing description, not text written for the planner).
  - The next plan call reads a factual summary of each earlier attempt: the tools called, those that failed (with their code) or started and never completed, own web searches that reported no source URL, the evaluation and its reason, and the answer excerpt labelled model-stated. Validation refuses a worker + effective model + effective tool set that already fell short (`invalid: repeat`).
  - **Bridge tool timeout.** Codex's per-MCP-server `tool_timeout_sec` (verified on codex-cli 0.153.4: present in the binary's `RawMcpServerConfig` fields next to `startup_timeout_sec`, and a parse-only `codex -c mcp_servers.agentos.tool_timeout_sec=300 mcp get agentos --json` with an empty `CODEX_HOME` reports `"tool_timeout_sec": 300.0`; a string is refused at config load, an unknown key is ignored) is set for the `agentos` server only: the longest own bound of the bridge tools the turn offers (`bounded_execution.bridge_tool_bound`: a browser step the relay's `CALL_SECONDS`, bounded research one search plus its page reads, a search the slower of a provider search and a native search, which may send `search_providers.NATIVE_MAX_REQUESTS` sequential requests (the first plus each `pause_turn` continuation) of `NATIVE_TIMEOUT_SECONDS` each, weather its two requests; others Codex's own 60 s) plus 30 s, never beyond the turn's own time (the Work's remaining budget; `MAX_TIMEOUT_SECONDS` is 600 since #733). With the current constants: a search 4 × 45 = 180 s, bounded research 180 + 3 × 12 = 216 s, a browser step 300 s, so a turn without browser tools gets 246 s and one with them 330 s, each lowered by a shorter remaining budget. Unset, Codex cancelled a bounded research call at its 60 s default.
  - A bridge call that went `running` and has no result when the CLI turn ends is recorded as a typed `tool_incomplete` failure (transient); its effect is `unknown` unless the action is an effect-free read, so it is never repeated blindly.
  - A CLI attempt's `goal_reached` input includes the worker's final answer labelled *model-stated, not an observation*, next to the recorded tool results, including a native search that reported no URLs.

Authority: the plan chooses among destinations the owner already configured and verified; it cannot add a destination, a Grant or a tool, and approvals bound to a destination (document sharing, page approvals, context attachments) are evaluated for the chosen worker's own config. Which configured AI receives owner context therefore becomes a per-request choice, which is why independent review applies. Evidence class: deterministic tests with a scripted `FixtureDecisionEngine`, a fixture HTTP transport and a fake CLI (`tests/test_orchestrator.py`), plus the real `mcp_bridge.serve` for the tool subset. No live orchestration with the owner's accounts was observed; the four owner live checks named in #710 remain.

## Provider evaluation

A provider should not become default because of vendor benchmark claims or novelty. Evaluate providers on a fixed AgentOS task set using the same contract and declared environment.

At minimum compare:

- decision accuracy against the frozen expected behavior;
- confidence calibration;
- false-positive/false-negative behavior where relevant;
- latency and tail latency;
- request/token/cost characteristics where observable;
- failure/timeout/degraded-mode behavior;
- data/egress requirements;
- deployment/availability dependency;
- provider lock-in and removal cost;
- maintenance/security/licence/provenance fit.

The evaluation must distinguish deterministic tests, synthetic fixtures, local model tests and live external-provider observations.

## Reuse-first implementation rule

This architecture follows the repository's **Adopt → Adapt → Build** direction:

1. adopt official/mature provider mechanics when they satisfy the non-sovereign need;
2. adapt them behind the AgentOS-owned decision contract;
3. build only the policy/contract glue or missing mechanics that must remain under AgentOS control.

An implementation Existing Solutions Review should consider at least:

- the repository's existing LLM/provider paths;
- deterministic/mock fixtures and exact-invariant checks (not a general production semantic rule engine);
- suitable local/small-model options;
- Jev/System-One-style decision providers;
- maintained libraries that solve commodity classification/routing mechanics.

The review must preserve AgentOS sovereignty over Grants, approvals, canonical Context/Memory, Work/Event/Evidence, Artifact provenance, egress policy, recovery and revocation.

## Implementation status

PRESENCE-DEC-01 / [#417](https://github.com/Jongtae/agentos/issues/417) introduced the first code boundary in `src/personal_agent/decision.py`: `DecisionContext`, `DecisionConfidence`, `BinaryDecision` / `SelectionDecision` / `ScoreDecision` with explicit non-answer outcomes (`provider_unavailable`, `timeout`, `malformed`, `context_rejected`, `cancelled`; a low-confidence answer is `decided` and reduced to unknown by policy), the `DecisionEngine` interface, `UnavailableDecisionEngine` and `FixtureDecisionEngine` for tests, `DecisionPolicy` thresholds, and `ModelDecisionEngine`, which adapts the repository's existing `ModelAdapter` tool-call shape so one `decide` tool call yields a typed answer on every supported provider. The first integration point is the conversation's parked-request withdrawal and bare-추천 capability-recommendation judgments (`conversation_handoff.ConversationJudgments`). Provider selection is service configuration (`decision_model` / `decision_model_key`; otherwise `gpt-4o-mini` on the OpenAI endpoint when the owner's configured model provider is OpenAI); with nothing configured no call is made and the judgment is unavailable. Evidence class: deterministic tests and recorded provider response shapes only; no live-provider calibration or availability is claimed. DECISION-ROUTE-01 / #580 makes the route owner-selectable among direct API, Jev and subscription AI; see "DecisionEngine routes (#580)" above.

PRESENCE-INTENT-01 / [#597](https://github.com/Jongtae/agentos/issues/597) (from #512 findings D1/J1) adds two judgment points on the same seam and route:

- **Capability need** (`ConversationJudgments.capability_need`, purpose `capability-need`): every turn of at most 500 characters that is not an exact slash command or a pending calendar draft's follow-up is asked which declared capability it needs (`CAPABILITY_NEEDS`: `mail-search`, `calendar-create`, `drive-read`, `several-tasks` plus the declared-unsupported mail actions). The context is the one owner utterance, with stored secret values and credential shapes removed first; every `ConversationJudgments` context is built by one redacting builder, and non-owner facts also lose the current Work's saved private values (#672 review). A turn a local rule claimed (notes, settings, private searches, workspace, mail) is asked too: when the judgment selects a capability the rules did not find, or `several-tasks`, the turn is mixed and nothing runs; the owner is told which parts it holds and asked for one at a time, so no part is done while another is silently dropped. A Work parked for a connection after a judged `calendar-create` or `drive-read` keeps that judgment (capability id, the Work whose message is the utterance, and a digest - never the text) and runs it on resume without a second judgment. Since #672 `calendar-create` and `drive-read` are selected only here, never by request words: a selected `calendar-create` takes the utterance to the existing draft-and-exact-preview path (write-connector handoff first when missing; only the owner's approval executes), and a selected `drive-read` reads the owner's Picker-selected Drive files into that turn or parks a Telegram Work as `awaiting_drive` with the Drive connection offer. Public web research has no routing rule: the Work model loop chooses `web_search` or `bounded_public_research` itself. A selected `mail-search` parks the Work for a missing Gmail connection exactly like a cue-bearing request; the Gmail query is a quoted phrase, or one of the owner's own words selected by a second content-free judgment (`mail-query-term`, index labels only); with no selection the owner is asked what to look for, and the whole question is never sent as a query. Unavailable, unsure or `none-of-these` keeps the ordinary conversation route, so no handoff is invented. Cue-bearing mail requests keep the existing local cue path and its unsupported-action judgment over a minimized cue summary, which avoids sending the raw mail query.
- **Explicit remember request** (`ConversationJudgments.explicit_memory_request`, purpose `explicit-memory-request`): replaces the `explicit_memory_request` regex. It is asked at most once per Work and only when a `save_memory` write is actually proposed. A yes lets AgentOS issue the existing message-bound owner-request approval; the deterministic value-coverage and key-replacement checks still decide canonical write versus MemoryCandidate. No or unavailable issues nothing, so the write stays a pending candidate and the turn reports it truthfully. The old regex remains only as `memory_followup_prefilter`, which keeps memory-looking turns away from the remote follow-up judge (#557) and grants nothing.

Evidence class for #597: deterministic tests with fixture DecisionEngines. The decision-qualification suite is unchanged (`decision-qualification/1`); no live-provider accuracy for these judgments is claimed.

AGENCY-EGRESS-01 / #605 added a third judgment point, **lookup term sensitivity** (`ConversationJudgments.lookup_term_sensitivity`, purpose `public-lookup-sensitivity`, the `choose_many` envelope), asked before a public lookup that carried words of the owner's current message. **Removed by SEC-PILOT-01 / [#654](https://github.com/Jongtae/agentos/issues/654)** under the pilot posture: no per-request judgment precedes a public lookup on either route, and the qualification case that probed it is gone (`decision-qualification/3`). Deterministic redaction of saved private values remains in `agent_runtime`.

SEC-ATTN-01 / #659 adds **explicit preparation request** (`ConversationJudgments.explicit_preparation_request`, purpose `explicit-preparation-request`, the `judge` envelope). It is asked only when the model calls `schedule_preparation` in a Work whose prompt is the owner's own stored message and which no preparation started; the context is that message and a one-line summary of the proposed preparation (kind, local due time, repetition, goal). A yes schedules the preparation as accepted by the owner's request; no or unavailable keeps it a proposal the owner accepts with the Telegram button or in Settings. It never authorizes an effect beyond the Grants the preparation's Work has when it runs. Evidence class: deterministic tests with a fixture DecisionEngine (`tests/test_preparations.py`); no live-provider accuracy is claimed.

SEC-JUDGE-01 / #679 changes which model answers, not what is asked: cheapest-first `lowest_qualified` defaults per route, strict-isolated Codex judgments, explicit model lists, effort and the effective-route display (see *Judgment model policy*). Evidence class: deterministic unit and DOM tests with fake CLIs, transports and the #616 qualification runner, plus the opt-in no-model process test against the real codex-cli 0.153.4 and a loopback scripted model named above. **No live judgment with the owner's accounts was observed**: which ranked model an account actually qualifies, `gpt-6-luna` over Chat Completions, and a real `GET /v1/models` response remain owner live checks.

## Staged implementation

### Stage A — contract (done in #417)

Define neutral types, errors, confidence/provenance fields, fallback semantics and test doubles. No Jev dependency is required.

### Stage B — narrow integration (first point done in #417)

Choose one existing semantic judgment point with low authority risk and measurable behavior. Integrate the model-backed adapter (initial default `gpt-4o-mini`) through the neutral interface, keep a deterministic/mock adapter for tests, and prove provider replacement does not change caller policy/authority code.

### Stage C — provider experiments

Run optional providers, including Jev if authorized, behind the same contract and benchmark cases. No provider becomes mandatory during experimentation.

### Stage D — evidence-based promotion

Promoting a provider to a recommended/default implementation is a separate decision based on current AgentOS-side evidence, owner-control impact and operational risk.

## Non-goals

This contract does not authorize:

- Jev installation or dependency changes;
- a broad hand-authored semantic rule engine or phrase/regex fallback;
- replacement of current Grant/approval checks;
- hidden autonomous action based on confidence;
- a mandatory System-One model;
- a new BDI runtime;
- benchmark or performance claims that have not been observed in AgentOS.

## Related work

- [#415 — ARCH-DECISION-01](https://github.com/Jongtae/agentos/issues/415)
- [#383 — scoped Attention / personal-assistant design](https://github.com/Jongtae/agentos/issues/383)
- [PR #384 — draft Attention design](https://github.com/Jongtae/agentos/pull/384)
- [#412 — reuse-first engineering governance](https://github.com/Jongtae/agentos/issues/412)
- [PR #414 — reuse-first engineering governance](https://github.com/Jongtae/agentos/pull/414)
