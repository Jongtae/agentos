# AgentOS contribution workflow

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
- Preserve existing private-document transmission/search guards. Review precise data/egress semantics before combining public research and private context; utility is not authority to remove a safety boundary.
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

Every milestone and iteration uses:

1. a GitHub issue with user outcome, runtime impact, acceptance criteria, non-goals, dependencies/authority and validation plan;
2. a matching branch;
3. small intentional commits;
4. a pull request with current automated validation evidence;
5. independent review only when the change materially alters a security/authority boundary or weakens a declared safety invariant; ordinary recovery, historical reconciliation and final completion do not trigger review by themselves;
6. merge, issue closeout and tracker/ledger reconciliation.

Before making an implementation or documentation change, create the issue and switch to its matching branch. Enable the repository hooks once per clone with `git config core.hooksPath .githooks`; they reject commits and pushes directly to `main` or `master`.

The active delivery order is `delivery-plan.yaml`. Historical v1/P7/Master Plan work and later successor plans are preserved rather than rewritten. An iteration cannot advance until its predecessor is complete or its explicitly recorded external blocker is resolved.

Every active iteration must satisfy the English canonical [Goal Execution Contract](docs/goal-execution-contract.en.md): establish its goal-ready record before activation, preserve declared authority and non-goals, and close only with current evidence. Vision, roadmap order, issue creation and reserved proposals never activate implementation by themselves.

Internal development standards, designs and execution guidance use English as the single canonical source. Korean is used for owner-facing progress/completion and user-facing companion docs where useful; translations do not silently create new authority.

The four public README files are one user-facing product surface: `README.md` is canonical for factual claims, while `README.ko.md`, `README.ja.md` and `README.zh-CN.md` must preserve semantic/structural parity. A canonical README change must update all public locales in the same PR. Prefer language-neutral visuals; if essential copy is embedded in an image, provide localized variants. Never let an illustrative product-direction scene read as current shipped capability.

## Licensing and marks

Personal AgentOS is licensed under `AGPL-3.0-only` ([LICENSE](LICENSE), [NOTICE](NOTICE)). Contributions are accepted under that same licence (inbound = outbound); there is no CLA. A contribution must not add code whose licence is incompatible with AGPL-3.0 or that obliges redistribution under different terms; record the licence of every new dependency in its reuse review. The "Personal AgentOS" name and logo are governed by [TRADEMARKS.md](TRADEMARKS.md), not by the code licence.

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

## Autonomous goal execution

An owner may explicitly activate one goal-ready iteration or one goal-ready top-level program and delegate its delivery cycle. The Agent then continues safe, in-scope work without waiting for routine owner review or a manual automation trigger. A top-level program may advance only to its already enumerated, dependency-satisfied substep; substep closeout does not end the top-level goal. It may not select an unlisted successor, start a new feature, reactivate a reserved proposal, or widen authority merely because a substep ends.

There is one existing delivery heartbeat. It may resume only the explicitly active goal after inspecting current repository and GitHub state; it must not create another automation or concurrent execution. It stays paused when no top-level goal is active or after top-level closeout, not after an in-scope substep closeout. A changed external condition is required before retrying a recorded authentication, permission, environment or usage failure.

Retired Agent Distribution Platform issues and #358–#360 are historical evidence, not an autonomous queue. D-AP-01 #334 and DOGFOOD-01 #351 completion does not activate a successor. Each execution unit still requires explicit owner activation and a goal-ready delivery-plan state. GOV-USE-01 #357 authorizes only its bounded documentation/governance alignment, not product execution.

Use role-appropriate delegation only for independent bounded work. Record the requested model/reasoning setting when material, the tool-accepted setting when observable, the observed execution result, and exclusive file ownership. Do not claim a model/runtime change that was not accepted or observed.

Independent review is required only for a material security/authority boundary change. Triggers include widening filesystem/network/secret/connector/runtime authority; OAuth or credential-boundary changes; consequential-action approval changes; sandbox/isolation/privilege changes; private-data egress or recipient-boundary changes; package/dependency supply-chain trust or install/update authority changes; canonical owner-state/authority ownership changes; or weakening/removing a declared safety invariant. Recovery work requires independent review only when it changes one of those semantics. Final completion, ordinary UI/conversation/Settings work, non-authority bug fixes/refactors/docs, and tracker/ledger reconciliation do not trigger review by themselves. When review is required, an implementer's self-review or a label transition alone is not independent review.

Completion is rejected unless a current requirement-to-evidence audit maps every acceptance criterion to merged artifacts, required CI, and relevant tracker/roadmap/ledger closeout. A local command, fixture, signature, package manifest, closed issue, branch or PR alone never proves live capability completion.


## Verification budget and stable-head review

Required CI, branch protection, exact-head validation and truthful evidence remain mandatory. Independent review is mandatory only when the risk-based escalation criteria above apply. Verification efficiency governs both when broad validation is triggered and whether an independent-review escalation is justified.

- During implementation and review remediation, run focused tests for the contract being changed. Keep related fixes together and prefer coherent checkpoint pushes over pushing every micro-edit when a push triggers full CI or review.
- Request full repository validation on a stable, review-ready head. If the change crosses a material security/authority boundary, request independent review on that same stable head. After any review, collect compatible findings and remediate them in one batch.
- Normal soft budget after review-ready is one stable-head full validation. When independent review is risk-triggered, add one review pass. If review findings require remediation, run one consolidated post-remediation full validation; re-review only when the remediation itself changes the triggering security/authority boundary or introduces a new review-triggering boundary. A third or later broad cycle is allowed when necessary, but the PR must record why another cycle is required (for example a new security finding, changed shared contract, flaky/unknown root cause, or material cross-worktree conflict).
- Never request re-review for an unchanged head, request duplicate review while one is already running, or repeatedly poll CI/review when no decision can be made from a new result. Inspect gates at meaningful transitions.
- A narrow mechanical fix should use focused tests first and be batched before the eventual exact-head merge gate. Changing a previously reviewed head does not automatically require re-review: re-review only when the remediation changes the boundary that triggered review or introduces another review-triggering change. Do not weaken, skip, or relabel required tests or a genuinely triggered review to save compute, time, or context.
- Broaden validation earlier when security, authentication/OAuth, privacy, external effects, shared contracts, replay/idempotency/recovery, or an uncertain root cause is involved. Escalate to independent review only when the material security/authority criteria above are actually crossed.

A critical execution profile is not permission for unlimited validation churn. If broad cycles keep repeating, stop micro-fixing, establish the root cause, batch the remediation, and document the reason for any additional cycle.

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

Every PR states what changed, why, automated validation evidence, known limitations, data/security impact and the issue it closes.

Package/runtime/distribution PRs additionally state:

- permission/data/egress delta;
- Memory/Event/background delta;
- supply-chain/provenance evidence;
- exact revision/digest behavior;
- update/rollback/uninstall impact;
- negative authority/security tests;
- whether any live external operation was actually observed.

Squash merge feature work into `main` after validation and any risk-triggered required review pass. Record completed work in `TASKS.md`, `docs/roadmap.md`, and `docs/issue-branch-ledger.jsonl` together when the activated goal's contract requires those records.
