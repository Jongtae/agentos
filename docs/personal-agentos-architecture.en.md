# Personal AgentOS Architecture

## Status and purpose

This is the canonical product-architecture definition: intended product boundary, meaning of **OS**, and authority between the personal AI kernel, installable AgentPackages, distribution and replaceable runtimes. It is not a claim that every described layer is shipped. Current support depends on merged implementation, the [roadmap](roadmap.md) and named acceptance evidence.

The [Owner Control Contract](owner-control-contract.en.md) maps this architecture to six observable owner rights and enforcement/acceptance. [Default Agent Usefulness](default-agent-usefulness.en.md) defines useful task outcomes and separate development/live-quality gates. These documents refine product acceptance; they do not replace the v0.1 schema authority or add another state store. [USE-01 readiness](use-01-goal-readiness.en.md) prepares the next narrow product goal without activating the heartbeat.

## Product identity

**Personal AgentOS is a local-first, owner-installed personal AI operating environment for one person: an AI environment the owner installs, owns and controls to do useful work.**

> **Personal AgentOS = Owner-authoritative Personal AI Kernel + Open Agent Distribution Platform**

Like a personal PC/OS, it gives one owner a durable environment across conversations, tasks, tools, agents, packages and models. Personal state and policy remain in AgentOS. Models, coding agents, packages, connectors and multi-agent frameworks are replaceable workers/capabilities, not its owners.

Personal AgentOS does not replace macOS/Linux; it is not a host kernel, hypervisor or general-purpose OS. The host still owns hardware, devices and processes. AgentOS is the persistent AI layer on an owner-controlled host or isolated owner runtime. A host/runtime compromise remains a limit of this trust model; local installation alone is not isolation or safety proof.

It is **not a coding harness or swarm framework**. Coding/orchestration may be capabilities, but do not define the product. Equally, control alone is insufficient: a few reliable, useful default capabilities must serve the owner before a marketplace grows.

## Architecture thesis

Separate owner-authoritative state/policy, non-authorizing package/distribution metadata, replaceable bounded workers, and owner experience surfaces. The kernel is **agent-independent**; the product and marketplace may be **agent-centric**.

```text
                              OWNER
                                |
                 conversation / work / inspect / approve
                                |
+-------------------------------------------------------------------+
|                         PERSONAL AGENTOS                           |
| Owner plane                                                       |
| identity/policy; Context/Memory; data/workspace; Grants/approvals;   |
| Work/Event; Artifact/Evidence; recovery/audit                       |
| Capability plane                                                  |
| tools/connectors; capability registry; Runtime Adapter boundary    |
| Distribution plane                                                |
| AgentPackage/Package Manager; Registry identity/version/trust;     |
| Marketplace discovery/reviews/commerce; compatibility adapters     |
| Experience plane                                                  |
| local conversation; supported Telegram/companion; package inspect;|
| useful result, observed progress, redacted receipts, owner controls|
+--------------------------------+----------------------------------+
                                 |
                   bounded Work / Context / effective Grant
                                 |
               Codex / Claude Code / model / local / Ruflo
                              nested workers
```

Everything above the worker boundary remains authoritative when a worker changes. No model, agent, Registry, Marketplace or framework becomes canonical Memory, Grant, approval, Work transition/recovery or Evidence authority. A receipt UI is a projection of these records, not another lifecycle database.

## Kernel primitives

D-AP-01 / [#334](https://github.com/Jongtae/personal-agentos/issues/334) supplies the v0.1 schema/specification foundation. This architecture retains ten responsibility boundaries:

### Owner
The human principal whose state is protected: identity, policies, devices/runtime claims, preferences and trust settings. Authority is not delegated to a package or marketplace.

### Context
Task-scoped attributable information assembled for a specific Work. Bounded/ephemeral by default, not automatically durable Memory.

### Memory
Durable owner knowledge with sources/provenance, confidence, sensitivity, retention/expiry, supersession and deletion. Third parties do not own or directly mutate canonical Memory by default.

### Artifact
Durable document, code, image, spreadsheet, data, draft or report with provenance and ownership independent of its producing package/runtime.

### Capability
Typed ability independently understood by AgentOS policy, such as research, file reading, spreadsheet creation, drafting, coding or sending; distinct from its implementation.

### Runtime
Replaceable environment/adapter performing bounded Work: model provider, Codex/Claude Code, local model, script/API, human-mediated executor or delegated framework.

### Grant
Explicit authority over resource/action/scope/destination/time/budget, issued by policy/owner, not by the requester.

### Work
Durable lifecycle with goal, package/capability/runtime identity, ContextSnapshot, current Grants, approvals, leases/checkpoints, artifacts/evidence, budgets, results and recovery.

### Event
Typed user/schedule/file/connector/system trigger. May prompt policy evaluation and Work creation, but grants no action authority itself.

### Evidence
Retained record of exact revisions, context/grants/tools/destinations, changes and validation/approval. Distinguish requested, attempted, observed and unknown, and fixture/local/external operating evidence.

## Observable owner control

The six rights are: inspect what is installed (OC-01), choose accessed data (OC-02), see and limit destinations (OC-03), bound actions (OC-04), stop/revoke (OC-05), and retain/move owner state when agents change (OC-06). Each right maps to actual enforcement and positive/negative evidence in the [control contract](owner-control-contract.en.md).

Enforcement lives in current Grant checks, capability broker, filesystem/network/process boundary and mediated secrets—not solely in model instructions. Useful approved reads can proceed without repeated prompts; new authority or consequential effects require covering explicit approval.

Expose concise progress derived from actual Work/tool events and expandable redacted receipts. Receipts show relevant structured inputs, destination, package/runtime revision where available, configured versus observed/provider-reported model, current authorization, evidence and actual effect. Unknown telemetry remains unknown. Hidden reasoning, system prompts and unrestricted raw tool payloads are not required and must not leak through logs/UI/exports.

Public reads, cart/hold/session mutations, personal-data entry, sending, reservation submission and payment are distinct effect classes. A cart mutation is not pure reading. Exact approvals bind target/item/quantity/recipient/currency/amount/fees/terms/parameters as applicable; changes invalidate non-covering approval. A progress message does not authorize a side effect.

Stop/revoke prevents new calls and stale queued replay. Supported local work is cancelled through its real execution boundary. Already completed effects may be irreversible; in-flight remote outcomes may be unknown. Do not promise undo, remote deletion or complete cancellation without evidence.

## Execution location and data limits

- **Local code/local model:** supported execution can remain on the owner host; network permissions still matter.
- **Local code/external model:** AgentOS owns state/tools while selected context is transmitted to an approved model endpoint. Local install is not local-only processing.
- **Remote-agent connection:** the installed component may be a connector; AgentOS controls outgoing requests/current credentials and local state, not the remote server's internals. Disclose retention/deletion/control limits.

Disconnecting new access, revoking Grants, removing packages and forgetting/deleting owner data are different operations. Specify local copies/indexes/caches, retained artifacts/evidence, backup retention and unresolved remote copies. Replacement needs fresh authority, not inherited grants. Removing an agent must not silently erase the owner's results.

## AgentPackage

The installable product unit appears as an agent/app/capability bundle, not a privileged mini-OS. Its machine-verifiable manifest declares:

- ID, publisher, version and compatible AgentOS API;
- capabilities/actions and runtime/model requirements;
- filesystem/data scopes, external destinations and mediated secret/connector references;
- Memory read/candidate-write policy and Event/background subscriptions;
- time/cost/resource budgets and consequential approval requirements;
- Artifact inputs/outputs, dependencies and sandbox profile;
- health/migration/install/update/rollback/remove expectations;
- licence, provenance, digest/signature/SBOM metadata where supported.

It describes requested potential authority only. Effective authority is resolved from current policy/Grants for each Work. A declaration/configuration-only package must not be advertised as arbitrary executable support.

## Package lifecycle and authority

```text
discovered → inspected → verified → staged → health_checked
→ installed_disabled → separately granted/enabled/connected
→ running under Work-scoped Grants → updated/rolled_back
→ disabled/quarantined → uninstalled
```

`downloaded != installed != enabled != connected != authorized-for-action`.

Install never creates or widens Grants. Credentials do not authorize every technically possible action. Event subscription and trust tier do not replace per-action authority. Grant-free health checks receive no owner-data or paid-provider authority.

Updates expanding data, destinations, Memory, background/events, budgets, dependencies or effects need fresh policy/owner review. Failed health checks cannot activate. Failed update preserves/restores supported known-good state; rollback cannot restore revoked authority. Disable/quarantine/uninstall revokes package authority while preserving owner artifacts/evidence under retention/deletion policy. Implementation—not merely a design or valid schema—must demonstrate isolation before arbitrary code is supported.

## Context and Memory boundary

AgentOS builds a Work-scoped **ContextSnapshot** from authorized sources. Packages get only needed context. Full conversations do not automatically become permanent Memory.

A third party returns a **MemoryCandidate** with source/confidence/sensitivity/expiry/retention/supersession. Policy/owner decides its canonical disposition. Declared package/runtime-local memory stays subordinate and removable/exportable. Revoked/deleted sources must not reappear through stale caches or replacement context. External sharing remains separate from local retrieval.

## Capability and Runtime contract

One capability can have several runtimes; one runtime can expose multiple capabilities. Minimum common semantic boundary:

- Capability List/Describe/Prepare/Invoke/Cancel/Health;
- Work Create/Get/AcquireLease/Checkpoint/Report/Transition;
- Grant Evaluate/ListEffective/RequestEscalation;
- Evidence Append/Seal/QueryRedacted;
- bounded ContextSnapshot; deadline/cost/resource/cancellation/idempotency;
- compatible Artifact/result/Evidence/MemoryCandidate output.

A worker may request escalation, append current evidence and propose memory; it cannot mint Grants, rewrite sealed history or self-certify final Work completion. AgentOS validates outcome evidence. Reroute/fallback needs covering destination/data/budget authority. A future remote runtime's unavailable model telemetry remains unknown.

### Ruflo's place

An optional delegated Runtime Adapter. Its swarm/agents/memory are runtime-local. Durable proposals return as MemoryCandidates; nested agents/tools cannot exceed current parent Grants. Swapping/removing Ruflo cannot erase owner state or rewrite history. It is not required for the first useful default assistant or Files package.

## Distribution plane

### Package Manager
Local exact-revision validation, verification, stage/health/install, enable/disable coordination, update/rollback/quarantine/remove. No authority minting.

### Registry
Publisher namespace, immutable version/digest, API/runtime compatibility, signatures/provenance/SBOM, trust/evaluation, advisories/revocation and optional binary location. Never private owner Context/Memory/Work storage.

### Marketplace / discovery
Search/recommendations/ranking/reviews/curation/install metrics and possible commerce. Prefer structured minimized capability metadata, not raw private prompts. Popularity/payment cannot override invalid or revoked releases, quarantine, policy or approval.

### Trust is multidimensional
Keep publisher identity, signing/integrity, build provenance/SBOM, static policy checks, behavioral evaluation, permission/destination risk, update/incident history, reviews/install base and curation distinct. A signed or popular package may still be unsafe. `Verified` must state exactly what was verified; quality and security are not one badge.

## Compatibility and ecosystem strategy

Wrap/import existing official MCP and selected OpenAI/Codex/Claude formats only where metadata/licence and authority map explicitly. Apply the same validation, Grants, isolation, Evidence, update and Memory rules; unsupported hooks/hidden authority fail closed or are labelled partial. A2A agents are external capabilities/runtimes, not implicitly privileged peers.

## Useful bootstrap/reference agents

Start with a capable default assistant and shared research/file/result/continuity tools. Few bundles is acceptable; weak supported tasks are not. Evaluate actual source-grounded outcomes, latency/friction and repeatability before adding more orchestration.

A first useful Files package proves the same public Package/Runtime/Grant boundary external authors use. General/Research/Coding references remain subsequent SDK work, not hidden privilege. The first integrated app must do useful work, then survive revoke/remove/restart and replacement with owner results intact; denying every task is not success.

[USE-01 #358](https://github.com/Jongtae/personal-agentos/issues/358) improves current defaults without waiting for the whole platform. [OBS-01 #359](https://github.com/Jongtae/personal-agentos/issues/359) projects actual progress and controls. [AGENT-UX-01 #360](https://github.com/Jongtae/personal-agentos/issues/360) consumes the existing #335/#337/#338/#340/#341/#342 contracts/implementations for install/run/revoke/remove/replacement. Preserve all unfinished update/rollback/event/SDK scope; downstream consumers are not reverse prerequisites of foundation tasks.

## Autonomous acquisition

L1 manual install; L2 recommendation; L3 exact owner-approved install plan; L4 trusted low-risk standing acquisition with separate grants; L5 package requests another capability through the kernel. Acquisition and action authority are independent. L4/L5 is not first-MVP scope and cannot silently accept new destinations, terms, payments, permissions or human-only identity/MFA/CAPTCHA gates.

## Durable state versus replaceable workers

Keep identity/policy, Grants/connection references, Context/Memory, material/results/provenance, Work/Event/approval/Evidence/recovery, package declarations/exact versions and capability bindings durable where supported. Models, coding runtimes, local engines, Ruflo, connectors/packages, Registry/Marketplace and experience surfaces remain replaceable. Reconstructing the owner's AI life from prompt history must not be required.

## Services and development harness

Research, files, coding, communication and scheduling use the same owner state/Grant/Work/Artifact/Evidence model, not isolated agent silos. Current file-workspace reuse proves a narrow owner-state property, not all future services.

Repository issues/branches/PR/CI, Constitution, Goal Execution Contract and handoff are **development infrastructure**, not end-user features. Spec Kit/BuilderMethods/Open AgentOS-style patterns may inform development, but are not mandatory runtime dependencies or evidence of live autonomy.

## Current implementation boundary

FILE-WORKSPACE-01 #314 is complete via PR #320 and #324: read-only approved references, managed writes, provenance, rebuildable-index separation and restart reuse with deterministic adapters/temp files. D-AP-01 #334 / PR #350 supplies v0.1 schema/fixture evidence, not a package manager. DOGFOOD-01 #351 / PRs #354–#356 adds documented owner steps and simulated-provider/local-HTTP/file/restart acceptance; it does not establish current live browser/provider quality.

GOV-USE-01 #357 / PR #361 aligns specifications and prepares USE-01 #358. Static evaluation cases are not a benchmark score. USE-01 remains non-executing until this preparation merges and the owner explicitly invokes it; #335–#346/#359/#360 stay inactive. No full-page-reader, live inventory, arbitrary package execution, Registry/Marketplace, Ruflo or L4/L5 claim follows from these documents.

Historical D-MP2-02 remains read-only recommendation authority. Optional Drive and SITE-01 publication remain deferred unless separately authorized. Earlier live evidence retains only its named prompt/provider/time scope; no history is rewritten.

## Design invariants

1. One owner, one durable personal state; workers/distribution do not own it.
2. Kernel agent-independent; product may be agent-centric.
3. Install is not authorization; download/install/enable/connect/action are distinct.
4. Local-first is not local-only; destinations and control limits are explicit.
5. Minimum current Work-scoped authority, including nested workers.
6. Consequential sends/payments/destructive changes/escalation/new destinations need explicit authority.
7. Canonical Memory remains owner-authoritative; third parties propose candidates.
8. Recoverable Work/Evidence across supported restart/update/replacement without duplicate effects.
9. Exact revisions/digests/provenance are attributable.
10. Identity, integrity, evaluation, popularity, risk and incidents remain separate signals.
11. Owner state is portable without treating credentials, sessions, caches or marketplace accounts as identity.
12. Evidence precedes capability claims; fixtures/design/harnesses are not live proof.
13. Utility and control are joint requirements: useful permitted results plus actual denied unauthorized effects.
14. Progress/receipts reflect observed state; hidden reasoning and raw secrets are not telemetry requirements.

The detailed v0.1 schemas remain normative for their version. Acceptance refinements here require separately authorized implementation; they do not silently migrate legacy records or broaden runtime authority.
