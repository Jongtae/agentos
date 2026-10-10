# AgentOS contribution workflow

## AI is the engine — Constitution C16 (#712, 2026-09-27)

**Read this before every proposal, issue and PR.** The owner's chosen AI does the work of meeting the owner's needs as a secretary. That can be a subscription CLI (Codex, Claude Code) or a configured model API. The **decision model orchestrates**: per request it chooses the AI tool and model, writes and adjusts the brief, evaluates the result, and re-delegates on shortfall. **AgentOS code never implements a specific owner request.** That rules out directions, cart or lookup logic, task-named guidance, and site/provider/category branches in AgentOS code. Domain or site know-how may exist only as explicit, versioned skill content that the owner's AI chooses to load (C16 amendment #974). It never grants authority, and core code never names a particular skill. AgentOS code only keeps owner-state, authority, secret, payment-approval and budget invariants, and **removes blockers** that stop the AI tools. Prefer known public code (C15) over self-implementation. Never make the owner operate the machinery. Ask on every change: *which AI does the work, and am I removing a blocker or scripting the task?* See [Development Constitution C16](docs/development-constitution.en.md). Before proposing or briefing connection, delegation, skill or domain use-case work, read the [Connection and Delegation Contract](docs/connection-delegation-contract.en.md): capability search order, connection precedence, control levels, the trust ladder and the owner's way.

## Secretary agency re-plan — #653 (2026-09-26)

Owner direction 2026-10-06, recorded by GOV-UPSTREAM-ACT-01 [#1029](https://github.com/Jongtae/agentos/issues/1029), selects **UPSTREAM-01 [#1022](https://github.com/Jongtae/agentos/issues/1022)** as the sole current parent. UPSTREAM-MAP-01 [#1023](https://github.com/Jongtae/agentos/issues/1023) merged through [#1031](https://github.com/Jongtae/agentos/pull/1031); GOV-UPSTREAM-NEXT-01 [#1032](https://github.com/Jongtae/agentos/issues/1032) selects UPSTREAM-UPDATE-01 [#1024](https://github.com/Jongtae/agentos/issues/1024) as the current child. Advance #1025 through #1027 one child at a time after the current child's validation, review, pull request and merge and its issue-declared prerequisites. The root `delivery-plan.yaml` owns the current selection and order. The checked-in `owner-activated-goal-ready` state still leaves the delivery heartbeat paused; it does not start a scheduler, model/provider call, live account operation, package application or deployment. Public upstream reading and disposable model-free compatibility work stay distinct from live AgentOS evidence. External issue, discussion or pull-request submission requires separate owner approval.

SECRETARY-01 [#662](https://github.com/Jongtae/agentos/issues/662) is paused before OWNER-MODEL-01 [#794](https://github.com/Jongtae/agentos/issues/794) phase 3. GOV-DELIVERY-06 [#1021](https://github.com/Jongtae/agentos/issues/1021) and the bounded [#794 phase-3 delivery contract](docs/owner-model-phase3-delivery.en.md) remain the exact resume point: #794 phase 3 → #660 owner-operated closeout → separately made-ready #875 Track A implementation → #661. No Secretary acceptance is complete or waived by this priority change, and closed backlog is not reopened.

The #880 Pages decision is unchanged: management happens in conversation, and pages exist only for results that text cannot carry and inputs that conversation cannot safely carry (Presence Experience Contract, *Pages*). Merged owner-directed follow-ups are regression inputs. PRESENCE-01 #508 remains paused; its merged work is regression input.

**Pilot posture.** One owner, own machine, own accounts. Enforced at request time: secrets never enter a model prompt, log or Evidence; payment needs per-action owner approval. Per-request sensitivity judgments, re-asks, per-provider gating and the "no cart authority" rule are removed from the request path and deferred to a separately activated hardening program. The #625 paragraph below and the AGENCY/#605 egress-composition rules are historical for this program; Attention preparations and phase-2 family delegation are explicitly selected, not deferred. Owner decision 2026-09-28 (#826): the separation between private reads and web search (census class g) is removed; instead each Work shows an information-use audit of which owner information it used and where it went. Folder grants, owner scope, secrets, per-action payment approval, no replay and Memory authority are unchanged.

**No scenario-specific code.** Probes (book → cart, calendar reminder, lunch with allergies, one held-out) are observation windows, not completion criteria. Decision/runtime code must not branch on a named site, provider or question category; every PR states whether it generalizes the loop or only makes a probe pass. A skill package may carry site know-how as content (#974); core code still never branches on it. Skill content written to make one probe pass is rejected like such code.

## Current-context adoption — #625 (2026-09-26)

For the selected single-owner current-state scope, read [Current context contract](docs/current-context-contract.en.md) and [Implementer playbook](docs/current-context-implementation.en.md). This selectively adopts #383 observation/time/current-state principles, not background Attention or multi-person collaboration. The plan is existing #605 → #606 → #607 → #626 input/time → #627 current-state consumption → #608/#512/#513; #625 is the immediate documentation adoption. Existing #616 and other independently directed work are preserved. Current-context claims remain unimplemented until those children deliver. Earlier blanket #383 deferrals do not exclude these two explicitly selected slices. #612 unit-test-first verification and concrete reuse still govern; no extra evaluator, graph platform or per-tick model calls. The new source-time, retention, inference/disclosure defaults and migration/test details are canonical in the two linked documents rather than duplicated here.

## Unit-test-first verification and concrete reuse — #612

Owner-approved 2026-09-25 amendment to #600/#602. Follow the [execution contract](docs/assistant-execution-contract.en.md) and [delivery/ownership](docs/assistant-execution-delivery.en.md). This replaces the earlier blanket baseline/mutation/trace-packet, all-profile three-trial model evaluation and 90% score requirements. Root `delivery-plan.yaml` still owns goal selection, order and authority; its older qualification prose and linked historical evaluation targets do not reinstate the superseded blanket verification workload. No new coordinator or runtime plan mirror.

Normal development uses focused unit tests with injected model/tool transports, fake clocks and temporary stores. Add a small model-free integration test when a changed serializer, broker, process or resume boundary needs it; do not mock away that boundary. Reserve mutations/counterexamples for load-bearing authority, idempotency or reachability checks. Existing required exact-head CI and genuinely risk-triggered security review remain. On success report a short summary; inspect only relevant failure diagnostics, not every full trace. No routine live-model requests, duplicate judge calls or per-answer model verification by default.

Real-model checks are opt-in, change-triggered and explicitly budgeted; select affected cases/profiles, not the whole Cartesian matrix. Model/prompt/tool-description changes, an unexplained model-dependent defect or a scoped quality claim can justify a small sample. Additional trials need evidence of uncertainty, not an automatic quota. Missing live authorization does not prevent development closure; it prevents claims of unobserved live behavior. Relevant known regressions still must pass.

Reuse means naming the existing symbol or supported package API, the thin AgentOS glue, and the duplicate implementation removed or avoided. Reuse prior reviews such as #426 and inspect only changed requirements/versions. New capability/step/result names in a design are conceptual mappings, not mandates to build new classes, stores or frameworks. Ownership of Grants, Memory and effects does not require owning commodity SDK internals. Dependency attack surface and actual runtime network authority are separate reviews; neither library installation nor model output grants authority. A custom Build needs a concrete unsupported contract after a small compatibility test, not preference or dependency count alone.

## Product priority

Personal AgentOS is a local-first, owner-installed personal AI operating environment for one person. Its long-term product contract is **Personal AI Kernel + Agent Distribution Platform**. The product owns durable personal state and policy across conversations, packages and engine changes: Context/Memory authority, owner material/workspace, Grants, approvals, Work/Event state, Artifacts, Evidence, recovery, and capability/runtime boundaries.

A connected Codex, Claude Code, model provider, local model, MCP server, AgentPackage, or delegated runtime such as Ruflo is a bounded worker/capability, not the owner of that state. See the canonical [Personal AgentOS Architecture](docs/personal-agentos-architecture.en.md) and [Agent Distribution Platform Foundation](docs/agent-distribution-platform-foundation.en.md). For owner-facing conversation, recovery, Settings, model-route and contextual capability-handoff work, also follow the canonical [Presence Experience Contract](docs/presence-experience-contract.en.md), grounded in the preserved [2026-09-23 Presence research](docs/research/presence-and-settings-ux.ko.md).

The repository's issue/branch/PR workflow, Goal Execution Contract, CI, delivery heartbeat, and state-driven implementer/reviewer handoff are **development infrastructure used to build Personal AgentOS**. Do not treat those repository mechanics as an end-user AgentOS feature, an OS runtime dependency, or evidence of live autonomous product operation. A coding harness may be a service or development aid; it is not the product identity.

The current first usable product slice remains owner files and folders as the material foundation with conversation/work as the experience. D-AP-01 #334 is contract/schema-complete and DOGFOOD-01 #351 is development-complete in their named evidence classes. The remaining Agent Distribution Platform #333 children and the useful-default-agent issues #358–#360 were closed as not planned on 2026-09-24 (GOV-PRESENCE-ACT-01 #523); their historical records do not activate anything. The active top-level goal is recorded only in `delivery-plan.yaml` `next_goal`.

Every active task must advance one or more durable outcomes:

- owner-controlled memory, context, tools, packages, permissions and approvals;
- transparent execution evidence and recoverable failures;
- lower setup and operating burden without broad host access;
- preserve owner originals while creating reusable, portable Artifacts;
- keep personal state independent of replaceable models/agents/runtimes;
- allow reviewed third-party capabilities to be installed/updated/removed without implicit authority expansion;
- make external data destinations and consequential actions explicit;
- preserve truthful evidence boundaries between design, fixture, local operation and live external operation;
- complete useful research/file/continuity tasks with accurate, substantive outputs and less unnecessary owner work.

Do not expand Kubernetes, appliance, cosmetic task-card/UI work, marketplace commerce, or infrastructure complexity unless an explicitly activated goal shows how it advances these outcomes.

## Useful outcomes and observable owner control

Follow [Owner Control Contract](docs/owner-control-contract.en.md) and [Default Agent Usefulness](docs/default-agent-usefulness.en.md) for relevant successor work. These requirements do not themselves activate product implementation.

- Few bundles is acceptable; intentionally weak basic functionality is not. Start with a capable default assistant and reliable tools, then justify extra agents/frameworks by task evidence.
- Measure actual task outcomes: source-supported comparisons, substantive artifacts, unchanged originals, successful restart/reuse, and relevant denied unauthorized attempts. Schema counts, test counts, reassuring prose and a file's mere existence are not usefulness scores.
- The 24-case evaluation seed and its static tests are specification evidence only. A runnable evaluator, repeated trials and calibrated outcome graders are separately required before reporting agent performance.
- Progress and action receipts must derive from observed Work/broker/tool events. Separate requested, observed, failed and unknown states. Never invent an ETA, tool execution, model identity or successful external effect.
- Owner-inspectable redacted parameters/destinations/approval/effects do not require hidden reasoning, raw system prompts, secrets or unrestricted payload logging. Apply redaction and retention before persistence and export.
- A public read, cart/hold mutation, identity entry, reservation, send and payment are different effects. Default research does not authorize checkout/cart actions. Parameter or authority changes invalidate non-covering approval.
- Private-document transmission/search guards were removed for the pilot by owner decision on 2026-09-28 (#826) and replaced by each Work's information-use audit. Folder grants and owner scope still bound every read. Review precise data/egress semantics before widening any other boundary; utility is not authority to remove a safety boundary.
- Local install is not local-only processing. Remote connectors do not place remote services under local control. Disconnect, revoke, remove and forget/delete have different scopes.
- Independent review is a risk-based escalation mechanism, not a default product-change gate. Require it when a change materially alters owner authority, security/privacy boundaries, consequential-action approval semantics, sandbox/isolation, private-data egress, package/supply-chain trust, canonical owner-state ownership, or weakens a declared safety invariant. Routine product-facing changes use the normal acceptance/evidence audit and required CI. Existing historical areas need re-audit only when a concrete dependency or contradiction requires it.

## Development constitution

All material work follows the canonical [Development Constitution](docs/development-constitution.en.md).

The repository adapts useful ideas from spec-driven development and explicit authority/state governance without adding those frameworks as Personal AgentOS runtime dependencies:

`Constitution → Spec → Authority/Threat Model → Plan → Tasks → Implement → Verify → Converge`

- **Constitution**: check durable owner-authority, safety, evidence and portability invariants.
- **Spec**: define owner outcome, behavior, boundaries, non-goals and acceptance criteria.
- **Authority/Threat Model**: enumerate data, Grants, packages/runtimes, networks, secrets, external effects and abuse/failure paths.
- **Plan**: choose architecture/compatibility/migration and evidence strategy.
- **Tasks**: create bounded issue-linked work units and dependencies.
- **Implement**: modify only the explicitly activated bounded goal.
- **Verify**: map acceptance criteria to current positive and negative evidence.
- **Converge**: reconcile code, docs, trackers, findings and current GitHub state before closeout; add independent review only when the risk-based escalation criteria below apply.

This process borrows the Constitution/Specify/Plan/Tasks/Implement/Converge discipline associated with GitHub Spec Kit, relevant standards/context injection ideas associated with BuilderMethods Agent OS, and explicit role/state/authority/receipt patterns seen in Open AgentOS-style governance. Those are development patterns only. Ruflo remains a possible product Runtime Adapter, not the repository governance system or AgentOS kernel.

## Reuse-first engineering

The Development Constitution's **Reuse first: Adopt → Adapt → Build** principle applies to every contributor, including Claude Code, Codex, GitHub Copilot, Gemini, Cursor, Windsurf, other coding assistants, future tools, and humans. Tool-specific instruction files are compatibility entrypoints only. If a tool does not recognize one, that does not relax this repository contract.

Before writing non-trivial implementation code that introduces or replaces a component, abstraction, integration, dependency, framework, or commodity infrastructure, perform an **Existing Solutions Review**. The review starts inside this repository: search for an existing AgentOS component, adapter, utility, seam, fixture, or pattern that can be reused or extended without violating its contract. Then check standard-library/platform facilities, relevant standards and official SDK/reference implementations, and mature maintained open-source frameworks/libraries. This applies especially to protocols, SDK/client behavior, OAuth/auth flows, provider adapters, MCP/A2A or other protocol plumbing, HTTP/transports, parsers, schema validators, schedulers, storage/migration utilities, connector mechanics, sandbox helpers, and other general-purpose infrastructure.

**The review also applies at proposal time.** Before proposing, recommending or recording a new design, contract, architecture element or loop, or a new component, integration or framework adoption, run the same review first. This covers recommendations made in conversation, design documents, contracts, issues and plans. Search the repository's existing contracts and implementations, then standards and installed or official tools (their own `--help` or documentation is authoritative), then maintained external options. Present the proposal as **Adopt**, **Adapt** or **Build** with that evidence. A proposal made without this review is incomplete and must not be offered as the recommended next step. For a behavior-only specification, the review asks whether an existing contract, standard or concept already covers the behavior (**Adopt** or **Adapt** it) or a new specification is needed (**Build**); it does not select an implementation, which remains a Plan decision.

The issue or implementation plan must record:

- the exact problem/boundary that needs implementation;
- existing internal repository components/adapters/utilities/patterns considered, with search evidence;
- standard-library/platform facilities considered;
- official SDKs/reference implementations/standards considered;
- mature maintained open-source/framework candidates considered;
- maintenance status and release activity relevant to the required path;
- security and supply-chain implications;
- licence compatibility;
- runtime/deployment/platform compatibility;
- the decision: **Adopt**, **Adapt**, or **Build**;
- why rejected candidates cannot satisfy the contract.

Decision order:

1. **Adopt** an existing AgentOS component, standard-library/platform facility, official SDK/reference implementation, or established implementation when it fits.
2. **Adapt** a mature maintained external implementation behind a narrow AgentOS adapter when direct adoption would couple external semantics to kernel policy.
3. **Build** only when the issue documents a concrete unsatisfied requirement after the internal and external search above.

A pure bug fix or data/content change that introduces no new component, abstraction, integration, dependency, or framework may record the review as `N/A`, but it must state that concrete reason. Do not use `N/A` merely to skip the search.

"Fewer dependencies", "simpler to write ourselves", implementation familiarity, or a coding agent's preference are not sufficient Build reasons. Conversely, reuse-first is not permission to add dependencies casually: every new dependency still needs licence/provenance/security/maintenance/compatibility review, and must not silently expand runtime authority, egress, secrets, or durable-state ownership.

Keep custom AgentOS code concentrated on owner sovereignty: canonical Owner/Context/Memory state, Grants/approvals, Capability/Runtime mediation, data/egress policy, Work/Event/Evidence semantics, Artifact provenance, recovery/revocation, and the adapters that enforce those boundaries. External implementations remain replaceable and subordinate.

Do not opportunistically rewrite already-stable custom code merely because an OSS alternative exists. Replacement of existing code needs a bounded issue with migration, regression, security and evidence criteria; classify candidates through the repository reuse audit rather than mixing unrelated refactors into feature work.

## Product and package invariants

### Owner state

AgentOS remains authoritative for Owner, Context, canonical Memory, Artifact ownership/provenance, Capability/Runtime registration, Grants, Work, Event and Evidence. A package/runtime/marketplace may request or describe authority but cannot grant itself authority.

### File workspace

File-workspace changes preserve this boundary: connected reference folders are read-only by default; managed-workspace writes stay inside explicit owner scope; originals, derived material, drafts and final records remain distinguishable; rebuildable indexes stay separate from durable task/approval/evidence/recovery/auth state. A folder grant never implies broad home-directory access, arbitrary shell execution, overwrite/delete/bulk-move, or external transmission.

### AgentPackage lifecycle

For package/distribution work:

`downloaded != installed != enabled != connected != authorized-for-action`.

- installing/updating/discovering a package never issues or widens a Grant;
- exact package/runtime revision and digest are attributable where applicable;
- permission, owner-data scope, network destination, Memory behavior, Event/background behavior, budgets and consequential-action deltas are reviewed on updates;
- failed health checks do not activate a package;
- failed updates define a known-good rollback/recovery path where supported;
- disable/quarantine/uninstall revokes package-scoped active authority while preserving owner Artifacts and retained Evidence according to policy;
- package/runtime-local memory is not canonical owner Memory; third-party durable writes are MemoryCandidates by default;
- package signatures/provenance establish identity/integrity, not behavioral safety;
- Registry/Marketplace popularity or review scores never create execution authority.

### Runtime adapters

Runtimes receive Work-scoped Context and effective Grants only. A Runtime may request escalation but cannot mint/widen a Grant, directly mutate canonical Memory, rewrite sealed Evidence, or declare final completion without AgentOS validation. Nested agent/tool authority is a subset of the parent Work authority.

## Required lifecycle

Follow the [Development Constitution](docs/development-constitution.en.md) first, then [Development Governance](docs/development-governance.en.md) for the ordinary contribution workflow. The [Goal Execution Contract](docs/goal-execution-contract.en.md) adds autonomous goal-ready/delegation rules, and [Incremental Delivery and Merge Handoff](docs/incremental-delivery.en.md) defines integration-pending and merge/handoff receipts.

The repository-level invariants contributors need before editing are:

- create the Issue and matching `codex/` branch before changing implementation or documentation;
- use one worktree per concurrent session; never mutate the owner's main working copy from a session worktree;
- GitHub Issues/PRs/Checks own execution status; root `delivery-plan.yaml` owns current goal selection/order/scope/dependencies/authority;
- do not mirror GitHub status into roadmap/ledger/planning files unless their own plan/decision/evidence meaning changes;
- required CI/exact-head validation always applies; independent review applies only for the Constitution's material security/authority escalation boundaries;
- English internal development documents are canonical; public README locale parity remains required;
- after merge, remove only your own worktree/branch and leave other sessions' worktrees alone.

Enable repository hooks once per clone with `git config core.hooksPath .githooks`. In a worktree, run tests with `PYTHONPATH=src` because the editable install may point at the main working copy.

## Licensing and marks

Personal AgentOS is licensed under `AGPL-3.0-only` ([LICENSE](LICENSE), [NOTICE](NOTICE)). Contributions are accepted under that same licence (inbound = outbound); there is no CLA. A contribution must not add code whose licence is incompatible with AGPL-3.0 or that obliges redistribution under different terms; record the licence of every new dependency in its reuse review. The "Personal AgentOS" name and logo are governed by [TRADEMARKS.md](docs/TRADEMARKS.md), not by the code licence.

## AgentPackage / runtime issue requirements

A package/runtime/distribution issue must explicitly state where applicable:

- exact package/runtime identity/revision or schema version;
- requested filesystem/data scopes;
- external network destinations;
- secrets/connector boundary;
- Memory read and write-candidate behavior;
- Event/background subscriptions;
- consequential actions and required approvals;
- budgets/timeouts/resources;
- install/update/rollback/uninstall semantics;
- supply-chain/signature/provenance evidence;
- negative tests for undeclared/excess authority;
- evidence class that will support completion.

Use the dedicated issue templates when available.

## Autonomous goal execution and verification

The detailed lifecycle, delegation, terminal-state discipline, requirement-to-evidence audit and stable-head verification budget are canonical in the [Goal Execution Contract](docs/goal-execution-contract.en.md). Merge/integration waiting and handoff receipts are canonical in [Incremental Delivery](docs/incremental-delivery.en.md).

An owner may delegate only an explicitly activated goal-ready unit/program. No substep completion selects an unlisted successor or widens authority. Independent review is risk-triggered by material security/authority boundary changes, not by ordinary completion. Required CI, exact-head validation and truthful evidence remain mandatory; do not weaken gates to save time.

## Truthfulness and safety

The canonical process is [development governance](docs/development-governance.en.md) plus this Constitution. Older Master Plan contracts continue to govern their historical scopes; successor Agent Distribution Platform work uses its newly activated contract when selected.

- Tests, mocks, schema validation, connection checks, local operating observations and live external observations are different evidence classes and must be named separately.
- AgentOS retains ownership of personal state when an external execution engine, AgentPackage or delegated framework is selected.
- Each owner runtime is isolated from the host home directory and other owner runtimes. Engines/packages receive only declared AgentOS tools/Grants; do not add arbitrary shell access, unapproved folders, host mounts, Docker socket access, external writes or broad network access without a dedicated authority/threat design and acceptance suite.
- Context capture is opt-in/local-first/sensitive-data filtered and shared externally only under current policy.
- Registry/Marketplace/discovery requests must not leak raw private owner Context when structured/minimised capability metadata is sufficient.
- The managed control plane must not persist message bodies, personal history, documents, tool payloads, provider credentials or Telegram bot tokens unless a separately reviewed product contract explicitly changes that boundary.
- Secrets are referenced/mediated, not embedded in package manifests, logs or Evidence.
- Never claim a Codex/Claude/Ruflo/MCP/Registry/Marketplace/package/connector path works merely because its manifest, adapter, mock or fixture exists. The exact operating path must be configured and observed before making that claim.
- Historical closed/deferred contracts remain evidence of their original scope. Add successor references instead of retroactively widening them.

## Pull request closeout

Use the structured PR closeout required by [Development Governance](docs/development-governance.en.md) and the handoff receipt in [Incremental Delivery](docs/incremental-delivery.en.md). Every PR states what changed, why, validation evidence, known limitations, data/security impact and the Issue it closes. Package/runtime/distribution changes additionally state authority/egress, provenance/revision and rollback impact. Squash merge only after required validation and any genuinely triggered independent review.

## Cross-role product semantics and Presence (2026-10-10)

Read [Professional Roles and Communication Contract](docs/professional-roles-and-communication-contract.en.md) for any ontology, Decision Model, Presence, skill, professional-domain or UX change. “Secretary” in historical program names and C16 describes the persistent owner-facing assistant relationship, **not an exclusive product domain**. Domain/role/mandate interpretation must precede tool selection; role and mandate never confer Grant, regulated status or external-effect authority. Presence must allow meaningful, evidence-grounded communication and owner correction of in-flight Work, not just fixed tool-progress strings. Do not introduce role-specific branches, new authority, extra state stores or live-capability claims by editing documentation. Root delivery-plan selection and existing paused program gates remain unchanged.
