# Provider-independent Decision Layer

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

PRESENCE-DEC-01 / [#417](https://github.com/Jongtae/agentos/issues/417) introduced the first code boundary in `src/personal_agent/decision.py`: `DecisionContext`, `DecisionConfidence`, `BinaryDecision` / `SelectionDecision` / `ScoreDecision` with explicit non-answer outcomes (`provider_unavailable`, `timeout`, `malformed`, `context_rejected`, `cancelled`, `low_confidence`), the `DecisionEngine` interface, `UnavailableDecisionEngine` and `FixtureDecisionEngine` for tests, `DecisionPolicy` thresholds, and `ModelDecisionEngine`, which adapts the repository's existing `ModelAdapter` tool-call shape so one `decide` tool call yields a typed answer on every supported provider. The first integration point is the conversation's parked-request withdrawal and bare-추천 capability-recommendation judgments (`conversation_handoff.ConversationJudgments`). Provider selection is service configuration (`decision_model` / `decision_model_key`; otherwise `gpt-4o-mini` on the OpenAI endpoint when the owner's configured model provider is OpenAI); with nothing configured no call is made and the judgment is unavailable. Evidence class: deterministic tests and recorded provider response shapes only; no live-provider calibration or availability is claimed.

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
