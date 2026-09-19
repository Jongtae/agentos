# AgentOS contribution workflow

## Product priority

Personal AgentOS is a local-first, owner-installed personal AI operating environment for one person. Its long-term product contract is **Personal AI Kernel + Agent Distribution Platform**. The product owns durable personal state and policy across conversations, packages and engine changes: Context/Memory authority, owner material/workspace, Grants, approvals, Work/Event state, Artifacts, Evidence, recovery, and capability/runtime boundaries.

A connected Codex, Claude Code, model provider, local model, MCP server, AgentPackage, or delegated runtime such as Ruflo is a bounded worker/capability, not the owner of that state. See the canonical [Personal AgentOS Architecture](docs/personal-agentos-architecture.en.md) and [Agent Distribution Platform Foundation](docs/agent-distribution-platform-foundation.en.md).

The repository's issue/branch/PR workflow, Goal Execution Contract, CI, delivery heartbeat, and state-driven implementer/reviewer handoff are **development infrastructure used to build Personal AgentOS**. Do not treat those repository mechanics as an end-user AgentOS feature, an OS runtime dependency, or evidence of live autonomous product operation. A coding harness may be a service or development aid; it is not the product identity.

The current first usable product slice remains owner files and folders as the material foundation with conversation/work as the experience. D-AP-01 #334 is contract/schema-complete and DOGFOOD-01 #351 is development-complete in their named evidence classes. Uncompleted Agent Distribution Platform #333 children and useful-default-agent issues #358–#360 are planned; their existence does not activate them.

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
- For product-facing changes, independent review includes task-result usefulness and affected UI behavior as well as security. Existing historical areas need re-audit only when a concrete dependency or contradiction requires it.

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
- **Converge**: independent review reconciles code, docs, trackers, findings and current GitHub state before closeout.

This process borrows the Constitution/Specify/Plan/Tasks/Implement/Converge discipline associated with GitHub Spec Kit, relevant standards/context injection ideas associated with BuilderMethods Agent OS, and explicit role/state/authority/receipt patterns seen in Open AgentOS-style governance. Those are development patterns only. Ruflo remains a possible product Runtime Adapter, not the repository governance system or AgentOS kernel.

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
5. independent review when security, package authority, recovery, external-boundary, historical-authority or final-completion risk requires it;
6. merge, issue closeout and tracker/ledger reconciliation.

Before making an implementation or documentation change, create the issue and switch to its matching branch. Enable the repository hooks once per clone with `git config core.hooksPath .githooks`; they reject commits and pushes directly to `main` or `master`.

The active delivery order is `delivery-plan.yaml`. Historical v1/P7/Master Plan work and later successor plans are preserved rather than rewritten. An iteration cannot advance until its predecessor is complete or its explicitly recorded external blocker is resolved.

Every active iteration must satisfy the English canonical [Goal Execution Contract](docs/goal-execution-contract.en.md): establish its goal-ready record before activation, preserve declared authority and non-goals, and close only with current evidence. Vision, roadmap order, issue creation and reserved proposals never activate implementation by themselves.

Internal development standards, designs and execution guidance use English as the single canonical source. Korean is used for owner-facing progress/completion and user-facing companion docs where useful; translations do not silently create new authority.

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

Uncompleted Agent Distribution Platform issues and #358–#360 are not an autonomous queue. D-AP-01 #334 and DOGFOOD-01 #351 completion does not activate a successor. Each execution unit still requires explicit owner activation and a goal-ready delivery-plan state. GOV-USE-01 #357 authorizes only its bounded documentation/governance alignment, not product execution.

Use role-appropriate delegation only for independent bounded work. Record the requested model/reasoning setting when material, the tool-accepted setting when observable, the observed execution result, and exclusive file ownership. Do not claim a model/runtime change that was not accepted or observed.

Relevant security, package authority, sandbox/supply-chain, recovery, external-boundary, historical-contract and final-completion work requires an independent review artifact. An implementer's self-review or a label transition alone is not independent review.

Completion is rejected unless a current requirement-to-evidence audit maps every acceptance criterion to merged artifacts, required CI, and relevant tracker/roadmap/ledger closeout. A local command, fixture, signature, package manifest, closed issue, branch or PR alone never proves live capability completion.

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

Squash merge feature work into `main` after validation and required review pass. Record completed work in `TASKS.md`, `docs/roadmap.md`, and `docs/issue-branch-ledger.jsonl` together when the activated goal's contract requires those records.
