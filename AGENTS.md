# AgentOS contribution workflow

## Product priority

Personal AgentOS is a local-first, owner-installed personal AI operating environment for one person. The product owns the durable personal state and policy boundary across conversations and engine changes: personal context, owner material/workspace, permissions, approvals, work state, evidence, recovery, and capability/runtime boundaries. A connected Codex or Claude Code process is a bounded execution engine, not the owner of that state. See the canonical [Personal AgentOS Architecture](docs/personal-agentos-architecture.en.md).

The repository's issue/branch/PR workflow, Goal Execution Contract, CI, delivery heartbeat, and state-driven implementer/reviewer handoff are **development infrastructure used to build Personal AgentOS**. Do not treat those repository mechanics as an end-user AgentOS feature, an OS runtime dependency, or evidence of live autonomous product operation. A coding harness may be a service or development aid; it is not the product identity.

The current first usable product slice has owner files and folders as its material foundation and conversation/work as its experience. AgentOS owns the assistant policy, tool boundary, work queue, approvals, evidence, recovery, and managed workspace while keeping owner state independent of replaceable workers.

Every active Hub v2 task must advance one or more outcomes:

- no-API-key consumer onboarding through an existing AI subscription
- reliable Telegram-based personal work completion
- owner-controlled memory, context, tools, and approvals
- transparent execution evidence and recoverable failures
- lower setup and operating burden without broad host access
- preserve owner originals while creating reusable ordinary-file results that later conversations can find

Do not expand Kubernetes, appliance, task-card polish, or UI work unless it directly advances these outcomes.

File-workspace changes must preserve the following product boundary: connected
reference folders are read-only by default; managed-workspace writes stay inside
explicit owner scope; originals, derived material, drafts, and final records
remain distinguishable; rebuildable indexes stay separate from durable
task/approval/evidence/recovery/auth state. A folder grant never implies broad
home-directory access, arbitrary shell execution, overwrite/delete/bulk-move,
or external transmission. Drive and other connectors are optional capabilities,
not a prerequisite for core local file work; websites are not OAuth/data relays.

## Required lifecycle

Every milestone and iteration uses:

1. a GitHub issue with user outcome, runtime impact, acceptance criteria, non-goals, and validation plan
2. a matching branch
3. small intentional commits
4. a pull request with automated validation evidence
5. merge, issue closeout, and a ledger entry

Before making an implementation or documentation change, create the issue and
switch to its matching branch. Enable the repository hooks once per clone with
`git config core.hooksPath .githooks`; they reject commits and pushes directly
to `main` or `master`.

The active delivery order is `delivery-plan.yaml`. Historical v1/P7 plans are archived rather than deleted. An iteration cannot advance until its predecessor is complete or its explicitly recorded external blocker is resolved.

Every active iteration must also satisfy the English canonical [Goal Execution Contract](docs/goal-execution-contract.en.md): establish its goal-ready record before activation, preserve declared authority and non-goals, and close only with current evidence. Vision and reserved proposals never activate implementation work by themselves. For file-workspace work, the English canonical [first-experience contract](docs/file-workspace-first-experience-contract.en.md) must be reviewed before implementation; a PR review must verify provenance, grant containment, original preservation, index/durable-state separation, and explicit external-send boundaries. Internal development standards, designs, and execution guidance use English as their single canonical source. Korean is used for owner-facing progress and completion reports; README and product-site translations remain user-facing translations rather than internal canonical sources.

## Autonomous goal execution

An owner may explicitly activate one goal-ready iteration or one goal-ready
top-level program and delegate its delivery cycle. The Agent then continues
safe, in-scope work without waiting for routine owner review or a manual
automation trigger. A top-level program may advance only to its already
enumerated, dependency-satisfied substep; substep closeout does not end the
top-level goal. It may not select an unlisted successor, start a new feature,
reactivate a reserved proposal, or widen authority merely because a substep
ends.

There is one existing delivery heartbeat. It may resume only the explicitly
active goal after inspecting current repository and GitHub state; it must not
create another automation or concurrent execution. It stays paused when no
top-level goal is active or after top-level closeout, not after an in-scope
substep closeout. A changed external condition is required before retrying a
recorded authentication, permission, environment, or usage failure.

Use role-appropriate delegation only for independent bounded work. Record the
requested model and reasoning level, the tool-accepted setting when available,
the observed execution result, and exclusive file ownership. Do not claim a
model change that was not accepted or observed. Relevant security, recovery,
external-boundary, and final-completion work requires an independent review
artifact; this is an automated/agent review, not a routine owner live-test
gate.

Completion is rejected unless a current requirement-to-evidence audit maps
every acceptance criterion to merged artifacts, required CI, and tracker,
roadmap, and ledger closeout. A local command, fixture, closed issue, branch,
or PR alone never proves completion.

## Truthfulness and safety

The canonical process is [development governance](docs/development-governance.en.md). It applies to all repository work; Master Plan delivery adds its own phase contracts on top of it.

- During Master Plan delivery, every external integration and agent capability is completed against its documented contract, fixtures, and mock-based automated validation. Real provider credentials, OAuth clients, endpoints, and activation are deferred until the owner performs one operating-mode deployment after the entire Master Plan is complete.
- A capability is complete for Master Plan delivery when its declared automated validation passes; do not claim that an external service has been connected or operated from mock evidence.
- Tests, mocks, connection checks, and operating-mode observations are different evidence and must be named separately. Connection checks and operating-mode observations are deployment evidence, not a development gate.
- AgentOS must retain ownership of personal state when an external execution engine is selected.
- Each owner runtime is isolated from the host home directory and other owner runtimes. Engines receive only declared AgentOS tools; do not add arbitrary shell access, unapproved folders, host mounts, Docker socket access, external writes, or direct broad network access without a dedicated approval design and acceptance suite.
- Context capture is opt-in, local-first, sensitive-data filtered, and shared externally only under the selected assistant's policy.
- The managed control plane must not persist message bodies, personal history, documents, tool payloads, provider credentials, or Telegram bot tokens. Owners create dedicated Telegram bots in BotFather and enter the token only into their local AgentOS runtime.
- Never claim a Codex, Claude Code, Telegram BotFather setup, consumer installer, hosting path, or external connector works unless that exact operating deployment path has been configured and observed.

## Pull request closeout

Every PR states what changed, why, automated validation evidence, known limitations, data/security impact, and the issue it closes. Squash merge feature work into `main` after validation passes. Record completed work in `TASKS.md`, `docs/roadmap.md`, and `docs/issue-branch-ledger.jsonl` together.
