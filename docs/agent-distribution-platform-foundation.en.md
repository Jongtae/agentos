# Agent Distribution Platform Foundation

## Status

This is the canonical **foundation and migration plan** for the Agent Distribution Platform program. It translates the architecture into staged design and implementation work. It is not a shipped-capability claim and does not activate child issues. The selector remains the Goal Execution Contract and an explicitly delegated goal-ready delivery-plan entry.

Parent epic: [EPIC-ADP-01 / #333](https://github.com/Jongtae/agentos/issues/333).

D-AP-01 / #334 is development-complete through PR #350: v0.1 contracts, schemas and deterministic fixtures, not package execution. DOGFOOD-01 / #351 is development-complete through PRs #354–#356: simulated-provider/local-file/HTTP/restart evidence; real owner browser/provider acceptance remains separate. Other distribution children remain planned.

GOV-USE-01 / #357 and PR #361 add the [Owner Control Contract](owner-control-contract.en.md) and [Default Agent Usefulness](default-agent-usefulness.en.md). [USE-01 readiness](use-01-goal-readiness.en.md) prepares #358 as the sole next goal after #361 merges. Preparation is not execution: the heartbeat stays non-active and a later explicit owner Goal invocation starts product work.

## Thesis

> **Personal AgentOS = Personal AI Kernel + Agent Distribution Platform**

The kernel owns durable personal state and authority. Distribution makes useful third-party packages discoverable/installable without taking that authority. Owner choice and replaceability remain the strategy, but the product must be useful before a marketplace is large. **Few bundles is acceptable; deliberately weak basic functionality is not.** Reference agents use the same public contract as third parties, not hidden privilege.

## Authority boundary

AgentOS remains authoritative for Owner identity/policy, Context/Memory semantics, Artifact ownership/provenance, Capability/Runtime registration, Grants/approvals, Work/Event lifecycle and retained Evidence/recovery/audit. A package, runtime, Registry or Marketplace may request, describe or recommend authority; it cannot grant itself authority.

OC-01–OC-06 map this architecture to inspectable packages, chosen data, disclosed destinations, bounded effects, stop/revoke and retained portable owner state. Each promised control needs an enforcement point and useful-positive/denial tests. Local installation is not proof of local processing: distinguish local code/local model, local code/cloud model and remote-agent connection; disclose remote control/deletion limits.

## Distribution components

### AgentPackage

Installable unit declaring identity, capabilities, runtimes, permissions/data scope, egress, secret/connector references, memory policy, events/background behavior, budgets, approvals, artifacts, dependencies, sandbox, health, lifecycle, provenance and integrity metadata.

### Package Manager

Owner-local lifecycle mechanism: validate/verify exact revisions, stage, health-check, record package state, coordinate enable/disable, review update diffs, recover/roll back, quarantine and uninstall package-local state while preserving owner artifacts/evidence under policy. No second permission database or installer in integration work.

### Registry

Publisher/package/version/digest, compatibility, trust metadata, advisories/revocation/quarantine and optional package-location authority. It must not hold owner Context/Memory/Work content.

### Marketplace / Discovery

Search, recommendation, ranking, curation, reviews and future commerce. Signals help discovery, not authority; popularity cannot override kernel policy.

### Trust / Verification

Keep publisher identity, signature/integrity, build provenance/SBOM, static checks, behavioral conformance/evals, permission risk, update/incident history, revocation, reviews and curation distinct. Signing is not behavioral safety or useful task quality.

## Lifecycle

```text
discover → inspect → exact version/digest → verify → isolated staging
→ preflight/health → installed-disabled → separately permitted connection
→ owner/policy Grant and enable → Work-scoped execution
→ update with authority diff → supported rollback → disable/quarantine → uninstall
```

`downloaded != installed != enabled != connected != authorized-for-action`.

A grant-free health check cannot access owner data or call a paid model. A valid manifest is not permission to execute arbitrary code. Disconnect, revoke, remove and forget/delete are different operations; retained artifacts, caches, backups and remote copies need explicit semantics. Removing an agent preserves owner results according to policy, while a replacement still requires its own authority.

## Security invariants

1. Install cannot create a Grant; runtime/package cannot mint or widen authority.
2. Updated authority cannot inherit an old non-covering approval; approvals bind exact current parameters, resource, revision and expiry.
3. Exact package/runtime revisions are attributable in Evidence.
4. External destinations are explicit policy, not hidden implementation details.
5. Secrets are mediated references, not package metadata/evidence.
6. Third-party durable Memory writes are candidate-only by default.
7. Nested agents/tools stay within current parent Work authority.
8. Registry/Marketplace inputs are untrusted data, not executable policy.
9. Signature/provenance is identity/integrity evidence, not behavioral safety.
10. Quarantine/revocation overrides popularity; rollback cannot revive revoked authority.
11. Owner Artifacts and retained Evidence survive removal as policy requires.
12. Stop prevents supported new work, but cannot promise undo or remote erasure of already completed effects. In-flight unknowns require reconciliation.

## Development-framework adoption

### GitHub Spec Kit — adapt, do not depend

Use Constitution/Specify/Plan/Tasks/Implement/Converge discipline, extended as:

`Constitution → Spec → Authority/Threat Model → Plan → Tasks → Implement → Verify → Converge`.

No product runtime dependency is required.

### BuilderMethods Agent OS — adapt context/standards discipline

Inject applicable development/security context; never make the framework personal Memory or package-state authority.

### Open AgentOS-style governance — adapt explicit state/authority

Use explicit workflow state, role separation, live authority checks and receipts for repository development. GitHub workflow state is not end-user Work state.

### Ruflo — optional Runtime Adapter

A delegated implementation behind the common Runtime contract. Its internal swarm/memory is subordinate package/runtime-local state, not the kernel and not a prerequisite for useful defaults.

### MCP / A2A / foreign skills — compatibility protocols

Describe/connect/import capabilities without supplying owner authority. Ambiguous or unmappable authority fails closed. No universal compatibility claim.

## Bootstrap strategy

Begin with a capable default assistant and reusable research/file/result/continuity tools. Add bounded specialists where measured results justify them, not a swarm for every task. Then package one useful Files reference first, using public contracts and real artifact-quality plus revoked-access tests. General, Research, Coding and MCP references remain #342 work; one Files example does not close its remaining scope.

Reference packages are not privileged kernel modules or guaranteed best-in-class, but they must perform their supported tasks well enough to use. Evaluate actual results, not installer status or file existence alone.

Existing-ecosystem wrappers may reduce cold start where official formats/licences and authority mapping permit. MCP and selected OpenAI/Codex/Claude formats use the same manager, Grant, isolation, Memory and Evidence rules. Catalogue size is not compatibility or quality evidence.

## Outcome-first priority overlay

1. [USE-01 / #358](https://github.com/Jongtae/agentos/issues/358): evaluator first, baseline next, then bounded public-page research, useful file artifacts and follow-up/restart. It need not wait for the platform epic.
2. [OBS-01 / #359](https://github.com/Jongtae/agentos/issues/359): actual progress/parameters/effects, minimal redacted receipts and supported cancellation on existing Work. Coordinate without circular dependencies.
3. #335/#337/#338 define compatible minimum lifecycle/security/runtime boundaries; #336 governs Memory where used.
4. #340/#341/#342 implement lifecycle, manual package Work first, then event/SDK coverage and one useful Files package. Downstream consumers are not reverse prerequisites of foundation tasks. Preserve all unfinished update/rollback/event/reference scope.
5. [AGENT-UX-01 / #360](https://github.com/Jongtae/agentos/issues/360): install → grant → useful result → inspect → revoke → denied retry → remove → restart → separately authorized replacement/reuse.
6. Broader Registry/import/commerce/autonomy follows demonstrated utility and lifecycle control, not the reverse.

This overlay does not erase the phases or activate a top-level automatic program. Each issue's actual dependencies, current evidence and separate activation govern execution.

## Phased roadmap — preserved scope

### Phase A — Foundation contracts

- [#334](https://github.com/Jongtae/agentos/issues/334) D-AP-01: complete contracts/schemas/fixtures, not execution.
- [#335](https://github.com/Jongtae/agentos/issues/335) D-AP-02: trust/permission/lifecycle.
- [#336](https://github.com/Jongtae/agentos/issues/336) D-MEM-01: third-party Context/Memory.
- [#337](https://github.com/Jongtae/agentos/issues/337) D-SBX-01: isolation/supply-chain/broker.
- [#338](https://github.com/Jongtae/agentos/issues/338) D-RT-01: common Runtime Adapter.
- [#339](https://github.com/Jongtae/agentos/issues/339) D-REG-01: Registry/Marketplace separation.

Exit: independently reviewable contracts and negative cases. Design completion requires no package execution and proves no implemented isolation.

### Phase B — Local package platform

- [#340](https://github.com/Jongtae/agentos/issues/340) I-AP-01: validator/Package Manager.
- [#341](https://github.com/Jongtae/agentos/issues/341) I-EVT-01: Work/Event integration.
- [#342](https://github.com/Jongtae/agentos/issues/342) I-SDK-01: SDK/CLI/reference packages.

Exit: a signed fixture package validates/stages/installs-disabled, is explicitly granted, performs useful bounded Work, updates/rolls back/removes and survives restart correctly. #360 adds owner-visible integration and replacement evidence. Arbitrary executable support requires actual independent isolation/egress enforcement evidence.

### Phase C — Ecosystem ready

- [#343](https://github.com/Jongtae/agentos/issues/343) I-ECO-01: compatible foreign formats.
- [#344](https://github.com/Jongtae/agentos/issues/344) I-RT-RUFLO-01: optional bounded runtime.

The full phase's existing scope includes a foreign representation and a sophisticated delegated runtime through common authority/evidence contracts in deterministic/local validation. Useful defaults and the first app do not depend on finishing this optional expansion.

### Phase D — Registry ready

[#345](https://github.com/Jongtae/agentos/issues/345) I-REG-01 resolves exact releases/trust/advisories without private owner data or implicit installation/enablement.

### Phase E — Acquisition autonomy design

[#346](https://github.com/Jongtae/agentos/issues/346) defines L1–L5. L4/L5 is not first-MVP scope. Safe visible installation precedes autonomy.

## Historical migration rule

Closed/deferred work remains evidence of its original scope. Historical D-MP2-02 was owner-local read-only recommendation, explicitly not Marketplace/download/install/activation. These are successors, not retroactive claims. Preserve file-workspace, D-AP-01 and DOGFOOD evidence classes, optional deferred Drive, repository handoff and SITE-01 deferral.

## Do not implement yet

Without the corresponding explicitly activated goal and current predecessor evidence, do not launch a store/Registry, add commerce, execute arbitrary packages, grant broad shell/network/home access, allow direct canonical Memory writes, accept OAuth/credentials/vendor terms, implement L4/L5, make any framework kernel authority, turn popularity into permission, or create another workflow authority/heartbeat.

## Evidence rule

A specification, manifest, listing, signature, fixture or static seed test proves only its own class. Progress/receipts derive from real Work events. Useful positive outcomes and correct denied effects both matter. The [usefulness specification](default-agent-usefulness.en.md) separates deterministic development completion from live-quality promotion: an unrun live evaluation is pending, never passed. Exact live package/provider/Registry operation requires current configured and observed evidence.
