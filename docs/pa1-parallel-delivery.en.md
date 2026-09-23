# PA1 Parallel Delivery Contract

## Status

This is the execution contract for [EPIC-PA1 / #386](https://github.com/Jongtae/agentos/issues/386), prepared by [GOV-PA1-01 / #385](https://github.com/Jongtae/agentos/issues/385).

It defines how **one explicitly active top-level PA1 goal** may use multiple isolated child branches/worktrees without making the owner manually create or coordinate those worktrees. It is development infrastructure only. It does not add an AgentOS runtime scheduler, a second delivery heartbeat, credentials, provider access, deployment, or external actions such as purchases, bookings, or payments.

EPIC-PA1 remains inactive until this contract and its delivery-plan registration merge and the owner explicitly activates #386.

## Program model

```text
one owner conversation
        |
        v
   EPIC-PA1 coordinator
        |
        +-- Wave 0: PA1-FDN-01 (#387)
        |
        +-- Wave 1, parallel-safe after #387
        |     +-- PA1-INSTALL-01  (#388)
        |     +-- PA1-GMAIL-01    (#389)
        |     +-- PA1-CALENDAR-01 (#390)
        |     +-- PA1-RESEARCH-01 (#391)
        |     +-- PA1-MEMORY-01   (#392)
        |     +-- WEB-ADMIN-01     (#382)
        |
        +-- Wave 2: PA1-CONV-01 (#393)
        |
        +-- Wave 3: PA1-INT-01  (#394)
```

The coordinator is the only authority to declare which dependency-satisfied children are active. A child worker is never allowed to select a sibling or successor by itself.

## One-thread execution behavior

When the owner says to execute EPIC-PA1, the controlling conversation should:

1. refresh `main`, #386, this contract, `delivery-plan.yaml`, open PA1 child issues/PRs, and current CI;
2. activate only the next dependency-satisfied wave recorded in the source plan;
3. create a distinct branch/worktree for each independent child in that wave;
4. give each worker its issue as the complete bounded Goal and record the starting main SHA;
5. require each child PR to stay within its declared ownership;
6. keep integration-owned files out of parallel Wave 1 branches;
7. converge only stable child PRs through the declared later wave;
8. run the final requirement-to-evidence audit in #394;
9. stop at EPIC-PA1 closeout without selecting an unlisted successor.

The user should not need to create worktrees or carry implementation context between separate chats.

## Branch/worktree convention

Preferred branch names:

- `codex/387-pa1-connector-foundation`
- `codex/388-pa1-install-service`
- `codex/389-pa1-gmail`
- `codex/390-pa1-calendar`
- `codex/391-pa1-research`
- `codex/392-pa1-memory`
- #382 keeps its issue-declared branch convention.
- `codex/393-pa1-conversation-handoff`
- `codex/394-pa1-integration`

The worktree path is local implementation detail. GitHub issue/branch/PR state is authoritative; a worktree directory name is not.

## Ownership rule

A parallel child may edit only files listed in its issue `Owns` section, plus a file explicitly transferred to it by an issue update before editing.

Wave 1 integration-owned shared files are:

- `src/personal_agent/quickstart.py`
- `src/personal_agent/quickstart_service.py`
- `src/personal_agent/web/index.html`
- `src/personal_agent/web/app.js`
- `src/personal_agent/web/style.css`
- `delivery-plan.yaml`
- `src/personal_agent/delivery-plan.yaml`
- `TASKS.md`
- `docs/roadmap.md`
- `docs/issue-branch-ledger.jsonl`

#382 is the explicit web-file exception because its existing scope is the management-only web shell. Other Wave 1 children must not edit those web files.

If a child discovers that it needs a shared seam, it should implement and test the smallest child-owned adapter boundary, record the missing integration in its PR, and leave the central wiring to #393 or #394. It must not widen its ownership silently.

## Merge and conflict discipline

Parallel work exists to reduce wall-clock implementation time, not to create competing integration branches.

- Child PRs target current `main`.
- A child does not merge sibling branches merely for convenience.
- Each child must pass its own targeted tests and the repository-required suite on its exact head as required by its issue.
- When a child merges, remaining parallel children rebase/update only when necessary and must not use that update to absorb sibling scope.
- Shared-file conflicts are resolved by #393/#394 after child contracts are stable.
- A changed shared contract requires the owning issue to be updated before implementation continues.
- #394 owns the final central routing, packaging, tracker reconciliation and requirement-to-evidence matrix.

## Delegation record

For every delegated worktree, record in the issue/PR or ledger:

- issue and branch;
- base `main` SHA;
- declared owned files;
- requested worker/model/reasoning when material;
- tool-accepted model/reasoning setting when observable;
- observed execution model/reasoning setting when observable, otherwise explicit `unknown`;
- targeted and full validation actually run;
- implementation state;
- PR/head SHA;
- review state/findings;
- operating evidence state.

Do not record secrets, private owner payloads, raw mail/calendar contents, hidden reasoning, or credentials.


## Dynamic worker capability routing

The owner should not need to choose a worker model or reasoning effort for every PA1 child. The EPIC-PA1 coordinator selects an execution profile from the current task, uses the cheapest profile that is appropriate, and escalates when the task crosses a higher-risk boundary.

These profiles describe required capability/risk handling. Exact model names are preferred mappings only when the execution environment explicitly supports and confirms them.

### Profiles

- **economy** — bounded mechanical implementation, straightforward tests/fixtures/documentation, or a narrow repair with an established root cause. Preferred mapping: Luna Medium or equivalent.
- **standard** — ordinary feature implementation with clear acceptance criteria and isolated ownership. Preferred mapping: Sol Medium or equivalent.
- **critical** — architecture/shared contracts, OAuth/credential boundaries, authorization/privacy/external effects, replay/idempotency/recovery, cross-worktree reconciliation, central orchestration, security-sensitive repairs, or release convergence. Preferred mapping: Sol High or equivalent.

If an exact preferred model/effort is unavailable, use the closest available capability level that is appropriate. Do not block safe progress merely because a preferred model name is unavailable.

Never claim that a model or reasoning effort was actually used merely because a tool accepted the request. Record three distinct fields when material: `requested`, `tool_accepted`, and `observed_execution`. If the environment does not expose the setting actually used for execution, record `observed_execution: unknown`; do not promote `tool_accepted` into observed evidence.

### Initial PA1 routing

- PA1-FDN-01 / #387 — `critical`
- PA1-INSTALL-01 / #388 — `standard`
- PA1-GMAIL-01 / #389 — `standard`; escalate for OAuth/security/credential decisions
- PA1-CALENDAR-01 / #390 — `standard`; escalate for OAuth/approval/idempotency/external-effect decisions
- PA1-RESEARCH-01 / #391 — `standard`; escalate for SSRF/private-egress/security-boundary changes
- PA1-MEMORY-01 / #392 — `standard`; escalate for canonical-Memory authority/approval/privacy changes
- WEB-ADMIN-01 / #382 — `standard`
- PA1-CONV-01 / #393 — `critical`
- PA1-INT-01 / #394 — `critical`

Mechanical follow-up work may be de-escalated to `economy` after the architecture/root cause is settled.

### Mandatory escalation

Escalate the current work to `critical` when any of these becomes true:

- a shared contract must change;
- a child needs a file outside its declared ownership;
- OAuth, credentials, tokens, authentication, authorization or approval semantics change;
- private owner data may cross a new boundary;
- an external write/effect is introduced or changed;
- replay, idempotency, restart or unknown-effect recovery becomes material;
- two child contracts conflict;
- a cross-worktree integration failure has no obvious local cause;
- CI repeatedly fails without a confident root cause;
- a security or architecture review finding is raised;
- fixing the issue would require weakening an existing invariant or test;
- the worker cannot establish the root cause with high confidence.

Escalation does not widen issue authority. If the fix requires shared ownership or broader scope, update the owning issue/contract first or defer the shared change to #393/#394.

### Review-driven routing

Use review findings as routing signals:

- mechanical/local finding -> `economy` or `standard`;
- ordinary behavioral/product finding -> `standard`;
- security, authorization, privacy, OAuth, recovery, architecture, or cross-contract finding -> `critical`.

After a critical architectural/root-cause decision is settled, repetitive follow-up may return to a cheaper profile.



## Verification budget

PA1 applies the repository-wide [Goal Execution Contract](goal-execution-contract.en.md) verification budget to every child PR.

- Use targeted tests during implementation and remediation.
- Push a coherent review-ready checkpoint rather than each micro-fix.
- Run required full validation and request independent review on a stable head.
- Batch compatible findings from one review pass before another full-suite/re-review cycle. Any post-review PA1 commit must be covered by the applicable independent review on the consolidated final head before merge.
- The normal soft budget is one review-ready broad cycle plus one consolidated remediation broad cycle when needed. A third or later broad cycle must record the new reason that makes it necessary.
- Do not request re-review for an unchanged head, duplicate a running review, or poll CI/review repeatedly without a decision point.
- Required exact-head CI/review and security/authority escalation remain mandatory; this budget reduces redundant cycles and never weakens evidence.

For PA1 specifically, a `critical` worker should broaden testing early for auth/OAuth, privacy, shared-contract, external-effect, replay/idempotency/recovery, or cross-worktree risk, but must still batch findings and avoid repeated stable-head churn.

## Owner-only operating gates

An owner-only action such as entering a credential, completing OAuth consent, pairing a live Telegram bot, or observing a real launchd/Homebrew effect is an **operating-validation gate**, not a reason to stop safe PA1 development early.

When a child reaches such a gate, it must first complete every safe development activity that does not require the owner action, including where applicable:

- contracts, adapters and injected transports;
- positive and negative tests;
- replay, idempotency, restart and recovery behavior;
- Telegram/web integration;
- PR, CI and independent review;
- synthetic/service/integration E2E;
- documentation and owner runbook steps.

The unavailable live step is recorded as `owner_validation_pending`. That state does not block unrelated dependency-satisfied PA1 work and does not by itself prevent a child from reaching development completion when its issue contract explicitly permits live operating evidence to remain pending.

Development completion and operating validation are separate evidence dimensions. Fixture/mock/injected-transport success must never be described as live-provider success.

### Continue-before-stopping rule

The PA1 coordinator must continue other safe dependency-satisfied work after an owner-only gate is identified. It may stop the whole program early only when the missing owner action genuinely prevents all remaining safe implementation/integration work and no other dependency-safe work remains.

Do not repeatedly ask the owner for the same unavailable live action while safe implementation remains.

### Batched owner validation

PA1-INT-01 / #394 owns the consolidated owner-validation checklist. Whenever practical, defer owner-only operating checks until development integration is otherwise complete, then present one minimal checklist instead of interrupting the owner separately for each child.

Expected PA1 live checks, when applicable, include:

- Telegram bot token/pairing and one live request/result;
- Gmail OAuth and one bounded read/search;
- Calendar OAuth and bounded read/create/update/cancel smoke;
- Homebrew/launchd/background start/restart observation;
- any other exact PA1 live effect that cannot be proven in CI.

Each item remains `owner_validation_pending` until actually observed. Unknown/unrun live operation is never converted into success merely because development tests passed.

## Evidence classes

Keep these distinct:

1. contract/static evidence;
2. injected-transport/unit evidence;
3. service/integration fixture evidence;
4. installed Homebrew/launchd smoke evidence;
5. live owner Telegram/Gmail/Calendar/provider evidence.

A lower class never silently proves a higher class. Real Gmail/Calendar credentials and private data are not required for development completion unless the active issue explicitly changes that boundary.

## Existing issues and non-blockers

- #314 and its completed children are the local file-workspace baseline; PA1 validates/reuses them.
- #358 is completed historical USE-01 work, not the current selector.
- #363 remains broader outcome-evaluator follow-up. PA1 uses task-specific acceptance and does not wait for the whole benchmark.
- #364 remains broader private-data hardening. A concrete PA1 enabled-path defect must be fixed by its owning PA1 child, but the entire issue is not an automatic program dependency.
- #359/#360 and #333/#335-#346 remain separate programs.
- #383/PR #384 remain longer-horizon personal-assistant design and are not PA1 runtime prerequisites.
- #381 is superseded as the broad planning discussion by finite #386 while its historical discussion remains preserved.

## Owner activation prompt

After this preparation is merged, the intended single-thread prompt is:

```text
Execute EPIC-PA1 / #386 from the current main delivery plan.

Use #386 and docs/pa1-parallel-delivery.en.md as the orchestration contract.
Create and coordinate only dependency-satisfied enumerated child branches/worktrees.
Parallelize only the declared parallel-safe wave and preserve exclusive file ownership.
Open one PR per child, require the declared validation/review evidence, and use #393/#394 for shared integration.
Do not start a second heartbeat, use live credentials, perform external account actions, or select work outside EPIC-PA1.
Continue through the finite PA1 program until completion or a real external/integration gate requires a truthful handoff.
```

This activates one top-level program. It is not blanket permission for future issues.

## Completion

The contract is satisfied only when #394 can map #386 J1–J8 to current merged evidence and required CI/review, with live owner operations separately labelled.
