# PA1 Parallel Delivery Contract

## Status

This is the execution contract for [EPIC-PA1 / #386](https://github.com/Jongtae/personal-agentos/issues/386), prepared by [GOV-PA1-01 / #385](https://github.com/Jongtae/personal-agentos/issues/385).

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
- accepted/observed execution setting when available;
- targeted and full validation actually run;
- implementation state;
- PR/head SHA;
- review state/findings;
- operating evidence state.

Do not record secrets, private owner payloads, raw mail/calendar contents, hidden reasoning, or credentials.

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
