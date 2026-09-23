# Personal AgentOS — useful personal AI under owner control

## Canonical owner-facing experience refinement

For conversation, recovery, Settings, contextual capability handoff and model/runtime continuity, follow the [Presence Experience Contract](docs/presence-experience-contract.en.md). Its evidence and reasoning are preserved in the [2026-09-23 Presence and Settings UX research](docs/research/presence-and-settings-ux.ko.md).

The contract refines how existing kernel truth and authority are **projected** to the owner; it does not create a second state store, weaken approval/Evidence rules, or claim that all target behaviors are currently shipped.

## Product North Star

> **Personal AgentOS is not a chatbot that sounds more human. It is an owner-controlled kernel whose machinery recedes behind one continuous, truthful personal-assistant relationship.**

This is the top-level filter for owner-facing product decisions. Models, tools, connectors, Work and Evidence remain explicit and inspectable underneath, but the ordinary experience should preserve one continuous Personal AgentOS relationship rather than expose the machinery as the product.

## Product identity

Personal AgentOS is a local-first, owner-installed personal AI operating environment for one person: **a personal AI environment you install, own, and control, built to do useful work**.

> **Personal AgentOS = Personal AI Kernel + Open Agent Distribution Platform**

The owner can entrust approved material to a durable AI environment, ask for outcomes, keep useful results and eventually install/replace third-party agents without surrendering Context, Memory, permissions or work history. The kernel is agent-independent; the experience can be agent-centric. Codex, Claude Code, model providers, local models, MCP services and optional delegated frameworks such as Ruflo remain replaceable workers.

This is not a coding harness, swarm framework, host kernel, hypervisor or replacement for macOS/Linux. Repository issues, branches, CI, delivery heartbeat and Goal mode build the product; they are not an end-user capability or proof of live operation.

Canonical references: [architecture](docs/personal-agentos-architecture.en.md), [owner-control contract](docs/owner-control-contract.en.md), [default-agent usefulness](docs/default-agent-usefulness.en.md), [v0.1 contracts](docs/core-primitives-agentpackage-v0.1.en.md) and [platform foundation](docs/agent-distribution-platform-foundation.en.md). Current implementation status is in [TASKS](TASKS.md), [roadmap](docs/roadmap.md) and named evidence, not implied by this product vision.

## Product principle: utility and control are both required

A safe but unhelpful shell is not the product. A convincing answer or reassuring progress message without actual execution evidence is not completion. Initial bundles may be few; they must be good enough to solve their declared jobs. The project must not wait for a future marketplace to supply all basic usefulness.

Optimize for an owner completing a useful task with less work, fewer unnecessary clarifications and clear control over consequential decisions. Use one strong general assistant plus reliable shared tools first. Add specialists and external packages where measurement shows value, not to increase an agent count. Bundles have no hidden privilege over third-party agents.

## Primary users

The first owner is a non-developer Mac user working with approved personal files and public information, willing to test a self-hosted preview. They need easy startup, a capable model path, useful outputs, recoverability and understandable controls, not infrastructure administration.

A secondary user is an independent AgentPackage developer. They should be able to author, validate, evaluate and locally install a useful capability through public contracts without rebuilding owner storage, authorization and recovery.

## First useful journeys

### U1: research to a decision

An ordinary request leads to clarification only when needed, public-source retrieval, a comparison of relevant options and a decision-ready brief. Preserve source/time, units/currency, included or unknown fees, and the difference between advertised price, verified availability and checkout total. Search snippets do not count as full-page verification. When a site requires unsupported login, JavaScript or a state-changing step, give useful verified partial results and the exact limitation instead of inventing completion.

Initial scope stops before cart/hold creation, account login, reservation, message sending or payment. A research request is not implicit permission for these effects. Later supported consequential actions need an exact preview and current approval.

### U2: approved files to an artifact

Read approved material, reconcile key facts and conflicting sources, and create a substantive result as an ordinary file inside a granted managed workspace. Preserve original bytes, source locations and original/derived/draft/final relationships. Support natural Korean/English paraphrases and several small documents, not only a magic demonstration phrase.

### U3: follow-up and continuity

A correction changes the active constraints without replaying stale work. Find/reuse earlier results after restart, explain old versus current evidence and preserve owner state when a supported provider or agent changes. Do not silently make every conversation permanent Memory or reuse grants across an unapproved provider change.

The detailed rubrics and synthetic case seed are in [default-agent usefulness](docs/default-agent-usefulness.en.md). Files, CI success and schema counts are necessary engineering evidence but do not replace task-result quality.

## Owner rights and observable behavior

| Right | Product requirement |
| --- | --- |
| OC-01 inspect | Show package publisher/source/version/digest, execution location, dependencies and requested authority before installation. |
| OC-02 choose data | Expose the folders, memory selectors and account scopes actually available to an agent and used in a Work item. |
| OC-03 know destinations | Separate local handling from model/tool/remote-agent/recipient transmission; make relevant payload scope inspectable. |
| OC-04 bound actions | Keep install/connect/read/write/remote mutation/send/pay/delete/background authority distinct. |
| OC-05 stop/revoke | Block new calls and queued replay after revocation; report in-flight unknown outcomes instead of pretending all effects were undone. |
| OC-06 retain/replace | Remove an agent without losing owner results or accepted Memory; replacement requires its own authorization. |

Each claimed right requires a real enforcement point and both allowed-success and denied-attempt evidence. A model instruction, permission screen, signature or successful manifest validation is not enough.

Default UX provides a concise useful result and material progress. Expand to owner-local receipts containing actual tool/action, relevant redacted parameters, source/destination, approval/current Grant, result and observed-or-unknown model identity. Derive progress from Work/tool events, not a model's assertion that it is busy. Hidden reasoning, raw system prompts and secrets are neither required nor appropriate for these receipts.

Low-risk reads already covered by explicit authority should not trigger repeated approvals. Consequential decisions remain explicit. The workflow must be safe without turning every task into user micromanagement.

## Locality and control limits

Declare three execution modes: local code/local model, local code/external model and remote-agent connection. A local package can send data externally; installing a remote connector does not place the remote service under local control. Show configured and observed providers/models separately and label unavailable telemetry unknown.

Disconnect, revoke, uninstall and forget/delete are distinct operations. Describe indexed copies, caches, accepted Memory, retained audit metadata, backups and remote retention separately. Local removal cannot prove remote deletion or undo completed effects. Minimize stored logs, redact before persistence/export, and state host-compromise and administrator limits honestly.

## Stable system responsibilities

The ten primitives remain **Owner, Context, Memory, Artifact, Capability, Runtime, Grant, Work, Event and Evidence**.

Owner policy retains authority for task-scoped Context and canonical Memory, durable artifacts, grants/approvals, Work transitions, Event evaluation, evidence and recovery. ContextSnapshot is attributable bounded task context, not permanent Memory. Third-party durable writes are MemoryCandidates by default, accepted/rejected by owner policy with provenance, confidence, sensitivity, retention, expiry and supersession.

Capabilities describe typed abilities; runtimes implement them. Bounded execution accepts a Work identity, ContextSnapshot, current effective Grants, deadline/budget and cancellation/idempotency rules, and returns artifact/evidence/memory proposals. No runtime mints authority, overwrites sealed evidence or self-certifies final completion. Nested execution cannot exceed its parent authority.

Connected reference folders are read-only by default. New output is confined to granted managed-workspace scope. Rebuildable search indexes remain separate from durable work, approvals, evidence, recovery and authentication. Existing file-transmission protections may not be removed simply to improve a demo.

## Agent application and distribution model

AgentPackage is the installable product unit. It declares exact identity/version/publisher and AgentOS compatibility; capabilities/actions and runtimes; filesystem/data scope and destinations; secret references without secret values; Memory read/candidate policy; Events/background behavior; budgets/timeouts; consequential approvals; artifact types; dependencies, sandbox/health and install/update/rollback/remove semantics; license, provenance, signature and SBOM metadata where supported.

`downloaded != installed != enabled != connected != authorized-for-action`

Install disabled by default; installation does not issue a Grant. Updates that expand authority, data, destinations, Memory, background behavior or budgets need a fresh decision. Invalid packages or failed health checks cannot activate. Rollback cannot resurrect revoked authority. Disable/quarantine/remove blocks package authority while preserving owner artifacts and retained evidence under policy.

The Registry resolves publisher/package identity, immutable versions/digests, compatibility, provenance, advisories and revocation. Marketplace/discovery handles ranking/reviews/curation and possible commerce. Popularity and payment never override policy. Private Context/Memory/Work is not marketplace metadata; use minimized structured capability queries.

A reviewed declaration-only format is not arbitrary executable support. External code requires an implemented, independently tested sandbox/broker/egress boundary, not only a design document. Compatibility import is explicit and format/license/authority constrained, never universal by default.

## Delivery priorities and scope

1. USE-01 #358 improves default research/file/continuity usefulness and builds the actual evaluator; it does not wait for a large marketplace or all platform designs.
2. OBS-01 #359 exposes real progress/action receipts and owner controls on existing paths, coordinated without circular dependency with USE-01.
3. Existing #335/#337/#338 define the limited lifecycle/security/runtime foundation; #336 governs relevant Memory behavior.
4. #340/#341/#342 implement the same local lifecycle, bounded Work and public SDK/reference package. Deliver a useful Files package first, preserve remaining update/rollback/event/SDK scope for explicit substeps.
5. AGENT-UX-01 #360 integrates inspect/install/grant/use/revoke/remove/restart/authorized replacement only after all its declared implementation dependencies have evidence.
6. #343 compatibility, #345 registry, optional #344 Ruflo and future #346 acquisition expand the ecosystem. Public store, commerce and L4/L5 autonomy are later choices.

These are planned priorities, not an automatic program. Every execution requires a goal-ready issue and explicit owner activation. New docs/evaluation seeds do not activate product work or change effective runtime permissions.

## Current evidence boundary

The file-workspace program #314/#315/#316 completed through PRs #320/#324. D-AP-01 #334 / PR #350 completed the normative v0.1 schema/static/semantic slice. DOGFOOD-01 #351 / PRs #354–#356 added a simulated-provider HTTP/file/restart acceptance and operating instructions. Real browser/provider use is separately recorded owner operation; no new live acceptance is claimed by this PRD.

The native tool loop and provider adapters already exist. Public search currently exposes snippets, not full-page retrieval or ticket inventory. Legacy plugin declarations are not proof of the new installable-package platform. Historical live receipts retain their original prompt/provider/version scope.

## Success measures

Proposed initial quality gate: the 24 synthetic seed cases, eight in each U1/U2/U3 family, run in three independent trials with clean state and pinned candidate settings; at least 80% useful successful trials per family, with all failures/partials reported. These are targets, not achieved results. A model-only grader needs human calibration and state checks; held-out paraphrases guard against overfitting.

Safety is a separate promotion gate: zero unauthorized effects or secret/private-context leakage in the declared negative tests. Every decision-driving current fact needs appropriate source/time support or an explicit unknown label. Required local outputs must exist, be useful and attributable, preserve originals and survive restart.

Measure median/p95 first-useful-evidence time and completion time, unnecessary clarifications, manual interventions, exact exposed model/usage telemetry and cost per successful task when measurable. After a bounded actual owner trial, record whether the owner accomplished the task, how much correction was needed, and whether they voluntarily reuse the system. Publicity or anxiety is not a quantified usefulness result.

## Non-goals of the present alignment

No runtime implementation, public Registry/Marketplace, agent download or execution, autonomous install, cart/booking/payment, outbound messaging, arbitrary shell/browser authority, broad personal-folder access, new live credentials/OAuth, background scheduling, cloud sync, destructive migration, public deployment or new framework dependency. The owner can continue the existing preview path in QUICKSTART while planned product slices are prepared.
