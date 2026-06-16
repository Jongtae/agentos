# Public Preview Operations

Status: Phase 2 operational contract

## Purpose

This checklist defines what AgentOS public preview runs may prove without
credentials or a VM, what requires explicit tester input, and what must remain a
non-claim until observed.

The goal is to make the Docker/local preview useful without pretending it proves
boot ownership, live external adapters, or release readiness.

## Public Preview Contract

The public preview path is:

```text
README quickstart
-> Docker or local runtime
-> prompt intake
-> intent classification
-> bounded capability result
-> activity/proof output
-> user-owned record or clear recovery
```

Docker remains a developer/demo runtime preview. It is not the product target,
the OS boot proof, or a release-quality installer.

## Automated Local Proof

Before a public preview update is promoted, automation should prove:

- `docker compose up` or the equivalent runtime preview path is documented.
- `agentos-kernelctl phase2-run --message "status"` returns a structured result.
- workspace, web/search, record lookup, lifecycle recovery, Gmail fixture, and
  Calendar fixture paths keep destructive actions blocked.
- activity feed and user-owned records are written for completed or blocked work.
- browser fallback, live Gmail, live Calendar, live Telegram, updater, and VM/ISO
  proof fields do not claim unobserved external execution.
- temp and build artifact cleanup policy passes.

## Manual Proof Blockers

The following are blockers until a tester records observed evidence:

- live Gmail OAuth read/search/draft proof
- live Calendar OAuth read-only proof
- live Telegram receiver proof
- live browser fallback proof
- VM/ISO boot, reboot, recovery, and managed runtime rejoin proof
- live updater, rollback, and recovery proof
- release artifact signing or distribution proof

Missing blocker evidence should not stop safe local mock or fixture smokes. It
should be recorded as blocked, not silently treated as passed.

## Non-Claims

A public preview update must not claim:

- production operating system readiness
- production Telegram automation reliability
- live Gmail, Calendar, browser, or updater execution without observed proof
- boot ownership or recovery convergence from Docker-only evidence
- ISO freshness without an observed ISO/VM run
- credential safety beyond the documented secret-free repo and local secret paths

## Promotion Gate

A preview update can be promoted when:

- README, TASKS, and roadmap point to the same preview path and current blockers.
- targeted runtime smokes pass.
- public preview operations smoke passes.
- cleanup policy reports no stale temp or build artifacts.
- PR notes state which proof is automated, which proof is blocked, and which
  unobserved proof is explicitly not claimed.

If any manual proof blocker is required for the change, the update may still
land only when the blocker is named with a recovery action and no unobserved
proof is claimed.

## Exit Condition

The public preview operations epic is complete when this checklist is linked
from the docs index, smoke-tested, and used by the automation loop to decide
whether a preview change is promotable, blocked, or outside the current proof
boundary.
