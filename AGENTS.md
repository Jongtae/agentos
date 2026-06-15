# AGENTS.md

## Purpose

This repository uses an issue-first, PR-centered, agent-assisted development workflow.

The public project should not depend on, advertise, or require any specific
AI coding assistant. Contributors may use whatever tools they prefer, but the
repository history should explain the product change, validation, and review
path rather than the tool used to make the change.

The core operating set for this repo is:
- `PRD.md`
- `TASKS.md`
- `AGENTS.md`
- `.agents/*`

Every phase, milestone slice, and task-sized issue must be tracked through:
- a GitHub issue
- a matching working branch
- one or more intentional commits
- a pull request for public review, CI, and discussion
- a closeout step that closes the issue after merge
- a merge step that lands the branch into its parent branch or `main`

Large host temp artifacts created by AgentOS remaster, packaging, or VM-proof work must also be tracked operationally:
- stale AgentOS temp artifacts are not acceptable hidden debt
- they must be checked before signoff-sensitive closeout
- they must be cleaned or explicitly justified before new remaster/bootstrap-heavy runs

Large local build artifacts under `build-output/` must be tracked the same way:
- stale release ISOs, remaster workdirs, iso-asset bundles, boot-test images, and vsmoke/debug leftovers are not acceptable hidden debt
- they must be checked before phase/task closeout when build, remaster, or packaging work was involved
- they must be cleaned or explicitly justified before final signoff

## Product priority lock

The primary product goal is not “an AgentOS-like appliance shell.”

The primary product goal is:
- make the managed agent runtime the default post-boot interface of AgentOS
- ensure boot, install, reboot, recovery, and rejoin converge back to a managed AgentOS runtime session
- treat welcome/install/recovery UX as support surfaces for the runtime, not as the product itself

Non-negotiables:
- work that only improves boot resemblance, theming, or appliance polish without advancing or protecting the managed runtime is not sufficient
- every new phase/task must explicitly state how it advances runtime behavior, supervision, continuity, or proof
- when a tradeoff exists between prettier appliance UX and stronger runtime ownership, prefer stronger runtime ownership

Post-MVP planning lock:
- the completed MVP remains the baseline and must not be reframed as incomplete
- post-MVP work must extend the baseline toward OS-native capability ownership rather than reset the runtime-first proof chain
- every post-MVP phase/task must explicitly state whether it advances `capability ownership`, `mediation cost reduction`, or `OS-native runtime defaults`
- browser and tool work should prefer turning common access patterns into internal substrate capabilities before expanding external adapter dependence

## Required workflow

### 1. Start from an issue

Before implementation begins:
- create the issue
- record the issue in `docs/issue-branch-ledger.jsonl`
- create or switch to the matching branch

Naming rules:
- phase issue title:
  - `EPIC: Stage <stage> / Phase <phase> <name>`
- task issue title:
  - `[P<phase>-NN] <verb phrase>`

Branch rules:
- public feature branch:
  - `feature/<short-slug>`
- public bugfix branch:
  - `fix/<short-slug>`
- public docs branch:
  - `docs/<short-slug>`
- public release/build tooling branch:
  - `build/<short-slug>`
- experimental branch:
  - `experiment/<short-slug>`

Avoid naming public branches after the development tool used to create them.
Branch names should describe product intent, user-visible behavior, or the
technical area being changed.

### 2. Commit in meaningful slices on a branch

Do not hold large uncommitted blobs of work.

Required:
- commit after each meaningful implementation slice
- commit before asking for review or summarizing completion
- commit before opening or updating a PR
- if the slice touched remaster, packaging, acceptance, or build-output heavy paths, run cleanup checks before the final completion commit

Commits on a feature branch may be iterative. Prefer squash merge or a small,
curated merge set so `main` tells a clean public story.

### 3. Open a PR before merging

Every public-facing change should go through a pull request unless it is an
urgent maintainer-only repository repair.

The PR must state:
- what changed
- why it changed
- how it was validated
- known limitations or follow-up work
- whether the change touches generated artifacts, secrets, build output, or VM proof flows

### 4. Close the issue only after completion

When the issue goal is complete and the PR is ready:
- run the targeted validation for that issue
- create the final completion commit
- merge the PR
- close the issue with the landed PR reference
- record the closeout in `docs/issue-branch-ledger.jsonl`

### 5. Merge upward by structure

Branch merges should follow the work hierarchy:
- task branch merges into its phase branch
- phase branch merges into its stage branch or current parent branch
- public feature branches merge into `main` through a PR

Do not leave completed issue branches dangling.

### 6. End every completed slice with branch cleanup

When a work item is done:
- confirm which branch was completed
- merge it into the correct parent branch
- delete the completed child branch when safe
- state the final branch status in the wrap-up message
- run cleanup immediately after completion:
  - `python3 scripts/cleanup_temp_artifacts.py --delete --json`
  - `python3 scripts/cleanup_build_artifacts.py --delete --json`
- if either command still reports stale candidates, either delete them now or record an explicit closeout exception with reason and recovery action
- do not treat a task/phase as closed until cleanup is confirmed or an explicit exception is recorded

## Helper scripts

Use:
- `scripts/work_item_lifecycle.py start ...`
- `scripts/work_item_lifecycle.py close ...`
- `scripts/backfill_historical_phase_issues.py --commit <sha>`

These commands:
- create issue titles with the required naming
- create matching branches
- append records to `docs/issue-branch-ledger.jsonl`
- support dry-run verification for tests and smoke checks

Historical phase backfill:
- use `scripts/backfill_historical_phase_issues.py` only for phases that were already completed before strict issue-first enforcement
- backfill records must set `historical_backfill=true`
- backfill records may use `branch=null` together with `planned_branch=<expected branch name>` so the record stays truthful

## Autonomous startup order

At the beginning of an autonomous run, read in this order:
1. `AGENTS.md`
2. `PRD.md`
3. `TASKS.md`
4. `docs/next-roadmap.md`

Then:
- confirm the active issue/branch state
- confirm the parent branch
- define the targeted validation set before editing
- record one explicit `runtime impact statement` before implementation begins
- run or consult the roadmap direction judge before deciding that another
  smoke-only hardening pass is sufficient
- when the roadmap direction judge returns `accept_with_risk`, prefer opening
  the next small safe forward-progress issue over repeating the same phase
  indefinitely
- when the roadmap direction judge returns `reject`, stop autonomous apply work,
  preserve evidence, and hand off or open a repair issue before continuing

## Repo-local agent roles

Preferred repo-local roles:
- `.agents/phase-orchestrator.md`
- `.agents/validation-agent.md`
- `.agents/docs-sync-agent.md`
- `.agents/release-signoff-agent.md`
- `.agents/vm-proof-agent.md`
- `.agents/codex-runtime-agent.md`
- `.agents/architecture-judge.md`
- `.agents/runtime-judge.md`
- `.agents/proof-judge.md`
- `.agents/test-judge.md`
- `.agents/roadmap-direction-judge.md`

Use subagents only for bounded, non-overlapping work that materially advances the current issue.

## Subagent Operating Policy

- use subagents for bounded, non-overlapping work that materially advances the active issue or phase
- do not delegate the immediate blocking architecture decision or the final integration decision
- do not default subagents to the same strongest model as the main integrator; strong-model delegation must be justified by the task shape
- every delegated subagent must have:
  - a concrete mission
  - a disjoint ownership boundary
  - a clear deliverable
  - a declared model choice matched to purpose
- worker and judge roles must be separated when both are used on the same phase
- judge agents do not implement; they return `accept`, `accept_with_risk`, or `reject` against the phase acceptance criteria
- every substantial post-MVP phase should identify:
  - which subagents are used
  - each agent's ownership boundary
  - which judge verdicts are required before closeout
- if no subagents are used for a substantial phase, the plan should briefly justify why

Autonomous hardening loops are not complete when they only prove that existing
Phase 2 smokes still pass. They must also ask whether the loop is advancing the
project toward completion. A direction judge should identify stable-phase
repetition, explicit blockers, and the next safe forward-progress candidate.

The main agent remains responsible for:
- lifecycle correctness
- merge order
- final runtime-proof truthfulness
- resolving disagreements between workers and judges

## Temp Artifact Hygiene Policy

AgentOS work frequently creates large host-side temp artifacts during:
- ISO remaster
- packaging
- acceptance
- UTM-backed VM proof

These artifacts can silently consume hundreds of gigabytes under `/private/tmp` and `/private/var/folders`, especially on macOS.

Required policy:
- before starting a new remaster/bootstrap/acceptance-heavy run, check for stale temp artifacts with `python3 scripts/cleanup_temp_artifacts.py --json`
- before starting a new build/remaster/package-heavy run, check for stale build artifacts with `python3 scripts/cleanup_build_artifacts.py --json`
- before closing a phase or task that touched remaster, packaging, bootstrap, or VM proof flows, run both checks with `--delete`
- before closing a phase or task that touched build-output, release, manifest, remaster, or iso-asset paths, run both checks with `--delete`
- before final signoff, no stale temp artifacts or stale build artifacts may remain
- if stale temp artifacts remain intentionally, the override must be explicit in the closeout and must explain why cleanup is unsafe
- if stale build artifacts remain intentionally, the override must be explicit in the closeout and must explain why cleanup is unsafe

Do not treat host temp sprawl as “just local noise.”
If it can distort disk availability, System Data, remaster reliability, or fresh-ISO truthfulness, it is signoff-relevant.
Do not treat `build-output` sprawl as harmless history either.
If it can distort which release is current, consume significant disk, or keep obsolete boot-test artifacts around, it is signoff-relevant.

### Agent/Tool Fit

- use the smallest reliable tool or agent for the task
- keep mechanical git, branch, issue, and ledger work boring and auditable
- keep architecture and runtime-proof decisions with a responsible maintainer or integrator
- separate implementation workers from review/judge roles when both are used
- do not name public branches, PRs, or commits after the AI tool used to produce them
- wrap-ups should explain product impact, validation, and residual risk rather than internal assistant mechanics

## Safety rules

- refuse lifecycle branch operations on a dirty worktree unless explicitly overridden
- do not push directly to `main` for normal public work; use a branch and PR
- do not close an issue before its completion commit exists
- do not merge a completed branch into the wrong parent branch
- if the branch structure is unclear, stop and realign before merging
- do not treat full acceptance/signoff long-runs as complete unless their success was actually observed
- when `gh` sees a stale `GITHUB_TOKEN`, prefer passing a Keychain-backed token as `GH_TOKEN` for that command invocation
- refuse to reframe the MVP as appliance resemblance only; the MVP must stay centered on managed runtime reachability, supervision, and recovery
- refuse to close a phase or task unless `runtime proof completed` can be stated truthfully in the closeout
- refuse to treat stale AgentOS remaster/bootstrap temp artifacts as harmless when they materially inflate host disk usage
- refuse to sign off remaster/bootstrap-sensitive work unless `python3 scripts/cleanup_temp_artifacts.py --delete --json` passes or an explicit override is recorded truthfully
- refuse to sign off build/remaster/package-sensitive work unless `python3 scripts/cleanup_build_artifacts.py --delete --json` passes or an explicit override is recorded truthfully
- refuse to leave obsolete `build-output/release` ISOs, boot-test images, remaster directories, or `vsmoke` artifacts behind after a task or phase that created them
