# Goal-directed assistant execution contract

## Status and authority

Owner-directed on 2026-09-25. Integration parent: [#600](https://github.com/Jongtae/agentos/issues/600); specification and gate infrastructure: [#601](https://github.com/Jongtae/agentos/issues/601). This is the normative execution/acceptance refinement for the finite AGENCY track within PRESENCE-01, not a replacement kernel, second active coordinator or shipped-capability claim. [Delivery and ownership](assistant-execution-delivery.en.md) defines the work breakdown. GitHub owns execution status; repository-root `delivery-plan.yaml` owns selection/dependencies. The retired runtime plan mirror must not be recreated.

Retain the [architecture](personal-agentos-architecture.en.md), [Owner Control Contract](owner-control-contract.en.md), [Presence contract](presence-experience-contract.en.md), [DecisionEngine boundary](decision-layer.en.md) and [usefulness rubric](default-agent-usefulness.en.md). This refinement supersedes interpretations equating a declaration, semantic seam, fixture, fluent copy or successful worker exit with a functioning assistant. Historical evidence and closed scopes are not retroactively enlarged. Publishing this contract does not authorize credentials, live evaluation, deployment, account mutation or another automation.

**Outcome:** in explicitly supported, qualified profiles, the assistant understands an ordinary goal, selects an admissible method, executes it, observes results, repairs recoverable failures, and supplies a useful verified result or accurately scoped blocker. Minimize unnecessary owner work, not truthful disclosure. Refusing everything and fabricating success both fail the product contract.

## Audited findings versus inference

Source baseline: `4a0d3e6fba987121298addb7349778a0a1b349bc`. These are source/test observations, not a reproduction on the owner's Mac.

| Finding | Baseline evidence | Owner |
| --- | --- | --- |
| Agent loop exists | `agent_runtime.run_agent` feeds tool results back to bounded model turns | #606 adapts it |
| Route tool exposure differs | `Capabilities.definitions`, `bounded_execution.MCP_TOOLS`, `mcp_bridge.serve`, isolated facade | #604 |
| CLI public preflight is lexical | `subscription_public_lookup_query` admits commands or selected city/weather wording | #606, after #605 |
| Prior assistant messages can close public egress | `quickstart_service.run_one` history provenance and `Capabilities.execute` | #605 |
| Bridge errors lose recovery distinctions | `mcp_bridge.serve` collapses different failures | #607 |
| Attempt failure and goal success are entangled | `run_agent` accumulates failure; CLI exit has different treatment | #607 integrating #598 |
| Fixtures do not establish model/deployed quality | [#512 record](presence-eval-01.en.md) and reported live mismatch | #603/#608 |

Their combination is a plausible cause of the reported weather/search behavior, not a proven account of that private incident. Installed revision, effective profile and exact events remain to be verified. #597 already owns semantic capability/remember fixes, #598 owns result truth, and #581 owns Telegram client behavior. Do not duplicate them.

## Requirements

The [machine-readable manifest](evals/assistant-execution-v1.json) is development data, never a runtime phrase table. Stable IDs map to one primary implementation owner; an integration dependency is not duplicate ownership.

| ID | Required outcome | Primary owner |
| --- | --- | --- |
| AX-01 | Meaning selects declared capability needs; exact protocol stays deterministic | #597 |
| AX-02 | One capability contract reaches every advertised qualified route | #604 |
| AX-03 | Discovery/installation/connection/grant/availability/health stay distinct | #604 |
| AX-04 | Source/destination-authorized public/private composition | #605 |
| AX-05 | Existing Work/loop supports observe-act-replan | #606 |
| AX-06 | Typed recoverable results preserve actionable failure distinctions | #607 |
| AX-07 | Requested obligations and Evidence determine goal completion | #607 |
| AX-08 | Resume/retry/restart/Stop/revoke preserve current authority and effect truth | #607 |
| AX-09 | Source-grounded facts and substantive, attributable artifacts | #606 |
| AX-10 | Shared finite budgets and actual cancellation outside the model | #607 |
| AX-11 | Exact source/artifact/config/catalog/policy/runtime identity | #603 |
| AX-12 | Separate evidence layers and enforced product promotion | #608; infrastructure #601 |
| AX-13 | Useful, truthful partial/unknown projection in one assistant voice | #598 |
| AX-14 | Explicit owner-memory instructions generalize without fabricated authority | #597 |

## Architecture decision — Adapt

These are responsibilities at existing seams, not new services or databases:

```text
owner turn / authenticated continuation
 -> exact protocol/state handling OR bounded semantic goal interpretation
 -> existing Work + admissible ContextSnapshot + effective profile
 -> model/native CLI proposes next step
 -> AgentOS broker checks schema, revision, owner, grant, egress, effect, budget
 -> tool/connector/runtime execution
 -> typed observation + retained Evidence
 -> continue / repair / ask / await authority / finalize
 -> goal-obligation and effect checks
 -> one truth-qualified assistant reply
```

Start from `run_agent`. A qualified CLI can keep its native planning loop behind the same broker; do not wrap an unbounded CLI in another unbounded planner. DecisionEngine remains an auxiliary provider-neutral semantic worker, not necessarily the decision-maker for every tool turn. Neither every greeting nor an exact local command requires a remote semantic call. Existing local-only processing must not silently become remote classification.

Rules enforce schemas, exact approval, state, budgets, destinations, idempotency and security. They do not form a growing catalogue of Korean/English requests. A lexical prefilter cannot permanently exclude an ordinary-language capability candidate before semantic interpretation. Abstention is not permission to invent a tool or change provider. Work route and auxiliary semantic route remain independently selected and authorized.

### Typed interfaces

Adapt existing types rather than introducing parallel stores.

**CapabilityDescriptor:** stable capability/action ID, revision/schema digest, description, input/output schema, effect class, source/destination restrictions, required grants, profile binding, availability reason, timeout/retry/idempotency/cancellation contract. Implementation, install/enablement, connector state, current authorization, route availability and qualification are independent facts. Discovery does not grant; invocation rechecks current state.

**StepProposal:** Work/goal revision; kind `answer | invoke | discover | clarify | request_authority | stop`; declared candidate ID; normalized proposed inputs/source references; expected goal obligation; inherited deadline/budget. It is not an authorization token. Audit requires observable choices, not hidden reasoning.

**StepResult:** invocation/attempt ID; capability revision; execution state; `effect = none | confirmed | unknown`; stable code; verified Evidence/Artifact references; unavailable portions; retry class; needed input/authority; bounded recovery candidates. Codes include `ok`, `partial`, `input_required`, `connection_required`, `approval_required`, `policy_denied`, `route_unavailable`, `invalid_arguments`, `transient_failure`, `deadline_exceeded`, `cancelled`, `effect_unknown`. Normal tool failures use MCP tool-result errors/structured content; invalid envelopes or unsupported methods remain protocol errors. Redacted diagnostics must retain the information needed for safe recovery.

**GoalResult:** requested obligations, satisfied obligations with evidence, unresolved obligations, outstanding effect uncertainty, final qualifier and result references. Discovery is not a weather lookup; HTTP success is not a grounded answer; zero exit is not completion. An earlier failed attempt stays in the audit even after a valid alternative satisfies the goal. A successful unrelated read cannot erase an unknown consequential effect.

Reject unknown/missing fields where exactness is required, foreign IDs, stale revisions and oversized payloads. External package descriptions, pages, connector content and delegated reports are untrusted data, not authority.

## Capability profiles and discovery

The target full profile is independently tested on `direct-api`, `codex` and `claude-code`. These name transports, not assumed capability or approved versions. Qualification binds exact runtime version, sandbox/configuration and catalog digest. A CLI unable to disable forbidden ambient tools remains unqualified. Never unlock shell, home or broad network access to make parity pass.

| Group | Target supported behavior | Excluded |
| --- | --- | --- |
| Public reads | Weather with resolved place/time, search, bounded source-page read and follow-up | Authenticated browsing, cookies, arbitrary JavaScript, CAPTCHA bypass, private hosts |
| Granted private reads | Existing notes, approved files, supported mailbox metadata, calendar queries | New mailbox/body scope, ambient folders, connected=authorized assumptions |
| Drafts/artifacts | Exact calendar draft/approval, explicitly requested memory/note/output under existing policy | Auto-approval, unsupported invitations/recurrence, arbitrary original mutation |
| Discovery | Find/describe existing reviewed declarations, load qualified schema, request needed connection/grant | Automatic download/install/update, account creation or grant expansion |
| Recovery | Safe alternative/read retry, current-authority resume and actual Stop | Hidden provider switch, duplicate uncertain write, false cancellation |

A deliberately restricted isolation profile can be separately offered with explicit tested scope; it is not a full-profile pass. Removing a profile from a frozen qualification run to improve scores is forbidden. De-scoping requires a reviewed product decision and truthful Settings/README changes, retaining failure history.

Use the existing packages/manifests and broker as the single binding source. Do not revive the retired Settings CapabilityRegistry as a second live connection database. Native, stdio MCP and isolated MCP must derive from the same action contract. Prove description, actual serialization, actual host invocation, Evidence and returned observation on every advertised profile; equal tool-list text is insufficient.

## Public/private information flow

A public lookup is still an external disclosure. Owner-authored text can contain credentials or private material. Permission to send content to one AI provider is not permission to send it to search/weather or another provider. Semantic confidence, sensitivity labels and model-authored sanitization are not Grants.

Preserve current provenance/public-egress guards until the reviewed replacement qualifies. No blanket history-taint removal, weather exemption, label stripping, delegate laundering or LLM-certified declassification.

For a separable public subtask, construct a fresh minimal context **before** private material enters it. Its inputs are an explicitly authorized public goal and admissible source records, never a private parent's free-form summary. A broker-owned request ticket binds owner, Work/goal revision, source IDs/revisions, normalized payload digest, destination/action, grant/policy revision, expiry and budget. Models cannot mint or modify tickets. Revalidate on invocation, restart and revocation.

Weather arguments should refer to an authorized location identity; trusted host code resolves and serializes the necessary coordinates/country/timezone. An arbitrary bounded string is not an information-flow control. Open-ended search also requires admissible source roots and covering destination permission. If private-derived input is necessary or admissibility cannot be established, ask for exact disclosure approval or the genuinely missing input. Do not evade denial through another worker.

Public results may return to a private task as untrusted evidence. Private results cannot flow outward without covering authorization. Summaries, caches, delegated reports and retained memory preserve provenance; unknown historical records remain restrictive. Migration never guesses that old material was public. Tests inspect exact outbound fields and admissible source references, not merely absence of one sentinel. Preserve SSRF/DNS pinning, redirects, size/decompression, encoding and deadline controls.

## Goal policy and factual quality

Determine what the owner wants to decide or change. Resolve relevant date/timezone, scope and references from authorized context. Ask only when the answer/action materially depends on missing or ambiguous information. A prior location is neither permanent inferred Memory nor precise nearest-store coordinates; check relevance and disclosure authority.

Weather answers need resolved location, observation/forecast time and data semantics. A model-based forecast is not a claimed rain-gauge reading at the owner's door. Holiday opening needs the specific branch and date; normal weekly hours alone are insufficient. Search snippets are not full-page reads. Stale evidence retains its timestamp/limitation. Source failure permits another authorized source, not invented facts.

Choose fallback from the observed reason, not a universal fixed chain. An equivalent same-authority method, one schema repair, one idempotent transient read retry, an exact authority handoff, a decision-critical question, or useful verified partial output can be appropriate. Auth/policy denial is not a transient retry. The assistant need not exhaust every tool, and casual conversation should not trigger unnecessary external work.

Obligations specify required entities/facts, freshness, artifact fidelity or exact effect. Deterministic checks cover IDs, units, timestamps, hashes and effects; nuanced completeness may use calibrated bounded semantic judgment. Neither confidence nor prose upgrades unknown evidence. Attempt outcome, goal outcome and external effect remain separate.

## Durable lifecycle and resource policy

Reuse current Work/pending registries. Do not promise universal exactly-once remote execution. Use durable single-claim/resume, action-specific idempotency where supported and reconciliation when an external request may already have taken effect.

Before consequential dispatch, retain the exact approved payload/idempotency key and attempt state. A crash after dispatch is not proof of failure. Never blindly retry an unknown mutation. Reconcile against authoritative external state through an allowed read where available; otherwise preserve unknown and the proper owner action. Changes to parameters, target, account, grant or connection revision invalidate non-covering approval. A draft is not an applied effect.

Initial bounds preserve nine model turns and twelve total tool attempts, including failures; at most one classified transient read retry and one argument repair. Nested work shares the budget. Enforce a total wall-clock deadline and per-tool/process timeouts outside the model; extensions require existing policy. Measure usage/cost when reported, not from guessed model prices. No new call after Stop/revoke/expiry. Detect repeated no-progress without preventing the explicitly permitted transient retry. A profile unable to enforce a required bound is unqualified until its adapter provides it.

Stop presentation immediately, and stop execution at its real boundary. Observe process-group/descendant death, not a mocked terminate call. A remote in-flight effect may remain unknown. Restart, retry controls, context restoration and rollback cannot revive revoked authority or duplicate possible effects. Settings-based setup and contextual handoff share the same pending claim where resumption is promised.

## Owner experience and diagnostics

Provide the useful result, material uncertainty and necessary next action in one assistant voice; #581 retains Telegram-native responsibility. Do not prohibit words such as unable or failed. Keep safe action parameters/destinations, evidence/effects and limitation reasons inspectable on demand.

A local diagnostic reports source revision, installed artifact digest, entrypoint/module origin, process start, effective route/isolation/CLI version, requested versus observed model, and configuration/catalog/policy digests. It reads existing state without invoking models or reinstalling anything. Exports are redacted before persistence and retention-bounded. A stale installation and missing route binding are different failures.

## Four evidence layers and promotion policy

The manifest is not runtime input. Freeze rubrics and held-out paraphrases before tuning. Report complete denominators, failures and unqualified profiles; never best-of-three.

| Layer | Proves | Does not prove |
| --- | --- | --- |
| Contract | Actual service/state/security behavior under controlled transports | Real-model or live service quality |
| Protocol | Actual serialization/process/MCP/proxy and observed host action | A real model chose correctly |
| Real model | Actual selected model/qualified CLI acts on synthetic controlled tasks, three independent trials | Live external facts when the world/effects are simulated |
| Owner smoke | Bounded real Telegram/macOS interaction on exact installed artifact | Universal reliability or statistical safety |

A behavioral fix requires baseline-red, candidate-green and an opposing case/mutation. Remove a binding, swallow an observation, bypass a claim, corrupt an artifact or relabel a fixture as live: the corresponding assertion must fail. File existence, text presence or pre-scripted final answers cannot certify usefulness. A different harmless action order is valid if it satisfies the same goal and authority.

Initial product targets: all mandatory contract/protocol and critical safety regressions pass; three real-model trials per required case/profile, at least 90% useful success per family/profile, and at least one success on every required positive case; zero observed unauthorized effects/egress, false completion, wrong-owner access or blind unknown-effect retry. Existing U1/U2/U3 criteria remain. These are engineering targets, not measured performance or safety proof. Calibrate latency/cost/friction SLOs from baseline before promotion; report p50/p95 and uncertainty.

#601's validator checks spec structure and report consistency against content-addressed JUnit/trace artifacts. It rejects missing/duplicate cells, skipped/xfail evidence, stale identities, assertion/JUnit disagreement and fixture-as-live substitution. **It cannot authenticate arbitrary self-authored files.** #608 must connect trusted runner/CI artifacts, required security review, frozen holdout and owner attestation to the actual promotion path and prove refused promotion. A validator unit test is infrastructure evidence, not product readiness.

Closeout stages are separate: specification/gate infrastructure, merged runtime integration, and product qualification. Missing authorized live evidence permits safe development but blocks product-ready claims. A parent cannot close just because each child has some merged PR. Mandatory findings, skipped routes, stale builds and fixture/live disagreement remain release blockers. Explicit de-scoping cannot erase history.

## Migration, rollout and risk disposition

Serialize shared seams after #597/#598. New binding/context paths are initially disabled/unqualified behind per-profile flags; restrictive current behavior remains until reviewed qualification. No silent provider fallback. Any read-only shadow comparison stays within existing data/destination/budget authority and never duplicates writes.

Rollout: baseline → reviewed broker/context contracts → opt-in qualified profile → real-model trials → pinned installed-artifact smoke → explicit promotion. Rollback preserves Artifacts, Evidence, pending effect uncertainty and revoked grants; it does not replay Work. Pin tested executable/runtime/schema versions and requalify affected profiles after upgrades.

#607 owns relevant #594 retry/atomicity/secret-chain/process/effect/saved-item/resume findings. #608 dispositions remaining retention and owner-local Host-boundary risks. Google-connected profile promotion requires #588 disconnect/revoke resolution or explicit narrower product scope. A historical non-blocking label is not evidence of safety. Attention, marketplace acquisition, multi-owner collaboration, new mail-send/body scope and purchases are excluded.

## Existing Solutions Review — Adapt

Internal first: current `run_agent`, Capabilities/manifests, DecisionEngine, Work/Context/Grant/Approval/Evidence, folder/connector handoff, #512 harness, usefulness seed, doctor/provenance and process tests. Adapt integration; no new product framework or dependency is selected.

Primary references verified 2026-09-25:

- [ReAct](https://arxiv.org/abs/2210.03629): observation-driven reasoning/action, not privacy or authority enforcement.
- [LangGraph workflows/agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents): comparison for loop patterns; wholesale replacement is not selected without migration evidence preserving current state/policy.
- [Anthropic effective agents](https://www.anthropic.com/engineering/building-effective-agents): workflow/agent tradeoffs and tool interfaces, not an AgentOS benchmark.
- [Anthropic evaluations](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents): outcomes distinct from prose, repeated trials and calibrated graders; our thresholds are our policy.
- [Versioned MCP tools specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools): discovery, structured results and tool-versus-protocol errors. Negotiate the actually supported revision; this historical URL is not a claim about the latest revision.

Python standard-library JSON/hashing/XML/path/unittest supports the bounded development validator. Reuse existing MCP types only when strict envelopes are preserved. Any new dependency requires exact version, maintenance, AGPL-3.0 compatibility, supply-chain, deployment/isolation and migration review. No framework owns canonical memory, Grants or completion truth.
