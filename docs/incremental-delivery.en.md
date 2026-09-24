# Incremental Delivery and Merge Handoff

Owner-authorized by DELIVERY-01 #365. This is development workflow, not an AgentOS
runtime feature, new heartbeat, GitHub policy bypass, or permission to use private data.
It supplements the [Goal Execution Contract](goal-execution-contract.en.md).

## Ship a useful increment, not an unlimited audit

Use small, runnable PRs. For each increment, state the supported user journey,
concrete acceptance tests, enabled data/action scope, and named deferred issues.
Do not add a framework or expand an already agreed goal to satisfy a speculative concern.
Do not silently lower existing acceptance: an owner-approved checkpoint transfers
unfinished criteria explicitly and preserves the original claims and review findings.
A deferred defect is not fixed. A merged experimental checkpoint is not production-ready.

For currently enabled paths, reproducible loss of data, unauthorized transmission,
wrong persistent state, broken promised output, and false pass claims are ship findings.
Prefer a minimal correction or disable the unfinished optional path. Do not block all
usefulness on broad benchmarks or hardening of unenabled features. Review actual changed
paths and evidence. A new concrete defect still deserves a response; this is not a
numeric limit on review or permission to suppress findings.

## Record three independent dimensions

These are issue/PR handoff fields, not new runtime Work states or heartbeat activation values.

| Dimension | Examples | Meaning |
| --- | --- | --- |
| Implementation | in_progress, implementation_verified | The declared increment works with exact test evidence. Does not certify review or deployment. |
| Integration | review_pending, integration_pending, merged, main_verified | GitHub reviews/policies and incorporation into main are independently observable. |
| Operating evidence | not_run, owner_validation_pending, observed | Actual owner/browser/provider operation, with its exact data and budget scope. |

A work session can end with a useful handoff while integration is pending. It must NOT
mark the full goal complete, close its issue, label a predecessor complete, activate a
successor, or advertise operating capability on that basis. Full goal completion still
requires the active issue's agreed scope, merged evidence, required CI and a current
requirement-to-evidence audit. Planning/governance documents need updates only when their
own plan or decision content changed; they do not need a second status transition merely
to mirror GitHub. Keep a checkpoint parent open when remaining criteria or explicit owner acceptance remain.

## Preflight once, then use the ordinary route

1. Refresh the exact PR head, base, draft/conflict status, required checks and actual review
   state. `mergeable` alone means no text conflict, not permission to merge. A running
   review is not a failed implementation. A check being non-required is not a waiver of
   its substantive findings. Do not infer inaccessible branch rules.
2. Use the read-only helper: `python3 scripts/pr_preflight.py --pr <number>`.
   Exit zero means a diagnostic was produced, NOT a passing CI gate or approval.
   It does not evaluate code, enumerate every protection rule, resolve conversations,
   poll, merge, or mutate repository settings. Unknown and skipped results need inspection.
3. Fix actual failures/conflicts. Request an independent review once for a stable head and
   scope only when the Development Constitution's material security/authority escalation
   criteria apply; otherwise proceed with required CI and evidence without a review gate.
   Resolve only addressed or explicitly triaged threads with evidence. Never impersonate
   another reviewer or treat self-review as independence.
4. When any risk-triggered review and GitHub requirements are satisfied, attempt one normal
   merge pinned to the validated full head SHA. No `--admin`, force push, false check, approval dismissal,
   protection removal, or settings mutation to work around refusal.
5. Native auto-merge is optional. When already enabled and this exact PR is authorized,
   it may be used under all normal gates. When disabled, skip it: ordinary merge still
   exists. Do not repeatedly request disabled auto-merge or install a replacement bot.
6. If an attempt fails, retain the exact error/category, refresh once, and choose a
   recovery specific to the state. A changed head requires new validation; a missing
   risk-triggered approval needs a reviewer; a permission failure needs an authorized actor. Do not
   call all three 'repository policy' without evidence.

If no safe in-scope work remains and the rest is external, write an `integration_pending`
receipt and stop the session. Do not wait through three identical Goal turns, spin a
polling loop, rewrite the goal, or fabricate completion. Recheck only on a meaningful
change or the owner's resumed request. This exception supersedes the generic three-turn
blocked rule for integration-only waits; genuine implementation blockers retain that rule.
No background monitoring is implied by a receipt. An independent enumerated substep may
continue only if the already-approved program allows it and its dependencies are satisfied.

## Required handoff receipt

Record: goal/issue/PR; exact head and base; supported increment; implementation state;
validation command/run links; review findings and disposition when review occurred; integration state;
exact unavailable gate/permission; next responsible actor and one resume action;
deferred issue links; smoke/run instructions; actual operating evidence or not_run.
No credentials, raw personal payloads, promises to monitor, or unsupported success claims.
After normal merge, verify main at the returned merge SHA. Close only genuinely completed
scope. GitHub Issues, Pull Requests, merge state, and required Checks are authoritative for
execution status: do not create a follow-up commit or PR solely to copy `merged`, `closed`,
a merge SHA, or a Check result into `delivery-plan.yaml`, `TASKS.md`, `docs/roadmap.md`, or
a ledger. Update those artifacts only when scope, order, dependencies, authority,
acceptance, milestone, activation, re-scope, blocker/disposition, next-goal selection, or
another substantive plan/evidence decision changed. If policy access is denied, state that
limitation rather than changing credentials.

## Repository setting note

At inspection for #365: main metadata named `validate` as required, native auto-merge was
false, and detailed protection reads returned 403 for the connected integration. These
are observations, not a complete policy audit. This change does not edit native settings.
The owner may separately enable Settings -> General -> Pull Requests -> Allow auto-merge;
that enables a convenience, not permission to bypass required reviews/checks and is not necessary
for the ordinary merge path. Recheck current settings instead of assuming this snapshot.

Primary references: [GitHub required checks](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks)
and [GitHub auto-merge](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/automatically-merging-a-pull-request).
