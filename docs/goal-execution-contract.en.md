# Goal Execution Contract

## Purpose

This contract makes an active AgentOS work item executable as an agent goal. A goal is not a restatement of a document title: it is a bounded commitment with an authoritative source, allowed authority, observable evidence, and a truthful terminal condition.

Use this contract for every new active design, implementation, release, remediation, operating-mode deployment, or documentation iteration. Historical records remain historical; vision documents and reserved proposals are inputs, not executable goals.

## Incremental delivery and session handoff

Follow [Incremental Delivery and Merge Handoff](incremental-delivery.en.md) for owner-authorized small increments. Record implementation, integration and operating evidence separately. `implementation_verified`, `review_pending`, `integration_pending`, `merged` and `owner_validation_pending` are handoff descriptions, not new product Work states or permission to activate the heartbeat.

A pending review/check, repository merge permission, or disabled native auto-merge is not by itself failed implementation. Refresh actual gates, attempt the ordinary SHA-pinned merge only when appropriate, and use the read-only `scripts/pr_preflight.py` helper for diagnosis. Never bypass protection or invent approval. Disabled auto-merge does not prevent ordinary merge.

When only an external integration step remains, finish safe in-scope work, record the exact gate, reviewed head, tests, unresolved findings, next actor and resume command, and end the session with `integration_pending`. Do not wait for three identical Goal turns, start another preparation cycle, poll indefinitely, or claim full completion. This narrow integration-wait rule takes precedence over the generic blocked rule below. Required review, actual findings, merged evidence and truthful full-goal closeout remain mandatory. An owner-approved experimental checkpoint must preserve and explicitly transfer deferred criteria; it is not a production or private-data approval.

## Goal-ready record

Before activating a goal, its issue and source plan must identify all of the following.

| Field | Required meaning |
| --- | --- |
| Objective | One user-visible outcome, including the scope that must be true at completion. A top-level objective may name finite, ordered substeps. |
| Source of truth | The issue, active `delivery-plan.yaml` iteration, and governing contract documents. The active delivery plan decides order. |
| State and predecessors | `active` work has satisfied dependencies. `reserved`, `proposed`, archived, and blocked work is not silently activated. |
| Allowed authority | Files, runtime boundaries, repositories, and external systems the goal may change. Read-only inspection is allowed; new credentials, external actions, or scope expansion require an explicit contract. |
| Non-goals | Adjacent work deliberately excluded so the agent cannot substitute an easier or broader result. |
| Work units | Small ordered deliverables, each with its own observable result. Design work fixes contracts before dependent implementation begins. |
| Evidence | Exact automated checks, fixtures, review artifacts, and—only for operating mode—deployment health evidence. Mock and operating evidence are named separately. |
| Delegation record | For each delegated work unit: exclusive file ownership, requested model/reasoning, tool-accepted setting when available, observed result, and the reason the delegation is independent. |
| Independent review | A required review artifact for relevant security, recovery, external-boundary, and final-completion work. It is not a routine owner manual-test gate. |
| Completion rule | A current requirement-to-evidence audit proving every promised artifact, state transition, and check, including merged artifacts, required CI, and tracker/roadmap/ledger closeout. |
| Blocked rule | The concrete external condition that prevents progress, recovery attempts already made, and the next authority or state change required. Integration-only waits use the bounded handoff above. |

## Execution lifecycle

1. Inspect the current repository, issue, branch, plan, and prior evidence; do not rely only on prior conversation.
2. Derive a checklist from the goal-ready record. Preserve every explicit requirement and dependency.
3. Create the required issue and `codex/` branch before changing implementation or documentation. Keep commits intentional and scoped.
4. Complete the ordered work units. After each material change, test the relevant contract before moving on. Use delegation only with the recorded model, ownership, and review boundaries.
5. Run the declared complete validation set, including plan/doc parity, local-link, ledger, and full-suite checks when the source plan requires them.
6. Create a PR that distinguishes automated evidence from operating evidence, merge it, close the issue, and update `TASKS.md`, `docs/roadmap.md`, and the ledger together. If only external integration is pending, preserve a resumable handoff instead; do not falsely close the issue.
7. Perform the completion audit. Only then report the full goal complete.

## Autonomous delivery-cycle delegation

For a cycle explicitly delegated by the owner, the Agent does not wait for owner review after every small work unit. It may continue the explicitly active, goal-ready iteration, or the finite ordered substeps of an explicitly active top-level goal, through design → implementation → automated validation → PR merge → closeout.

This delegation is not authority for automatic installation, permission escalation, or an operating-mode transition. The Agent may create an issue and `codex/` branch only for an already enumerated, dependency-satisfied substep of the active top-level goal. It must not select an unlisted successor, start a new feature, or reactivate a reserved proposal. It must stop before credential or OAuth configuration, a new external connection/endpoint, permission or scope expansion, a consequential external action, expansion of a personal-data boundary, a security/governance boundary change, or Master Plan cycle completion unless that exact action is explicitly authorized in the active goal-ready record. If a next selection would be needed, it reports candidates and evidence instead of starting implementation.

## Delegation and independent review

The active issue records model-routed delegation only where it makes work independently reviewable. The default requested roles are Astra medium for the primary worker, Terra low or medium for independent exploration/document inspection, Sol medium for bounded implementation, and Astra high for security/recovery/final-completion review. These are role labels, not claims that a requested model was available. The record distinguishes requested, accepted, and observed settings and assigns files so two implementers do not edit the same file concurrently.

An independent review artifact is required before completion when a goal changes security, recovery, an external boundary, automation/authority controls, or its completion claim. The reviewer checks the current diff and evidence, names unresolved findings, and does not substitute a fake product success or routine owner manual test.

The single existing delivery automation reads this contract and may resume only the named active goal after checking issue, branch, plan, contract, and task state. It may advance only to an already enumerated substep, must not create another automation, and must not run concurrently with an already active task. It remains paused when there is no active top-level goal and after top-level closeout; retries require a meaningful changed condition.


## Verification budget and stable-head review

The goal lifecycle preserves required evidence while avoiding validation churn that consumes more execution context than the change itself.

### Implementation and remediation loop

1. During implementation, run the smallest focused tests that exercise the changed contract.
2. Keep related edits/remediation local to the worktree until they form a coherent checkpoint; do not push every micro-fix merely to ask CI or a reviewer the same question again.
3. When the work is review-ready, push a stable head and run the declared complete validation set required by the source plan.
4. Request independent review only on that stable head.
5. Collect all known compatible findings from the review pass and remediate them together. Use focused tests while fixing them.
6. If the remediation materially changes the reviewed behavior, run the required exact-head full validation and re-review once on the consolidated remediation head before merge.

### Soft verification budget

For a normal review-ready work unit, the expected broad cycle budget is:

- **cycle 1:** stable-head full validation + required independent review;
- **cycle 2:** one consolidated full validation + re-review after material review findings, when needed.

A third or later full-suite/re-review cycle is permitted when correctness requires it; it is not a bypassable hard limit. Before triggering that cycle, record why another broad pass is necessary, such as a newly discovered security/authority defect, changed shared contract, flaky or unknown root cause, or material cross-worktree conflict. Repeated broad cycles without a new reason are a signal to stop micro-fixing, establish the root cause, and batch remediation.

### No redundant gate work

- Do not request review again for an unchanged head.
- Do not request duplicate review while the current review is running.
- Do not repeatedly poll CI/review when no decision depends on a new state transition.
- Do not run the full suite after every narrow mechanical edit solely for reassurance; run focused tests, batch compatible changes, then use the required exact-head full gate.
- Automatic CI triggered by a push is still authoritative evidence; reduce avoidable trigger frequency by pushing coherent checkpoints, not by disabling required workflows.
- Never skip, weaken, relabel, or bypass tests, branch protection, exact-head validation, or independent review to save context/compute.

Broader validation may be run earlier whenever security, authentication/OAuth, privacy, external effects, shared contracts, replay/idempotency/recovery, or uncertain root cause makes narrow testing insufficient.

## Terminal-state discipline

- A goal is **complete** only when a current requirement-to-evidence audit proves every completion item, merged artifact, required CI result, and tracker/roadmap/ledger closeout. A top-level goal additionally proves every enumerated substep and requirement is complete, owner-setting-only, or separately decision-required. Intent, a partial fixture, a closed issue, an unmerged branch, or a narrow test cannot prove a broader claim.
- A goal remains **active** while a safe next action exists, even if work is difficult or incomplete.
- A goal is **blocked** only after the same concrete external blocker has recurred across three goal turns and no meaningful safe progress remains. The report must name the blocker, evidence, and the smallest required next input. Integration-only waits instead end the current session with the exact `integration_pending` receipt; they do not require repeated identical turns.
- A goal never treats a routine owner manual test, real credential, or live provider as a development blocker. Those belong to the separately documented operating-mode deployment unless the active goal explicitly authorizes it.

## Design–implementation traceability

A completed design contract is evidence that an interface and acceptance boundary were specified; it is not evidence that the capability exists. Every Master Plan design entry must name its dependent implementation entry and English canonical contract. That implementation must link back to the design, declare automated evidence, and remain inactive until a goal-ready issue authorizes it.

The delivery-plan verifier rejects a design without this mapping. It also rejects a Master Plan or capability `development_complete` claim unless every declared implementation is documented complete with its mapped automated evidence. `design_complete`, `in_progress`, and `requires-goal-ready-issue` are intentionally narrower states and must never be rendered as a user-facing capability completion or operating claim.

## Document routing

| Document kind | Goal behavior |
| --- | --- |
| Vision | Supplies direction and non-goals; never activates work by itself. |
| Master Plan | Supplies phases, completion criteria, and design/implementation ordering. Its active iteration must still be selected in the delivery plan. |
| Active delivery plan | Selects the next executable iteration and its declared validation commands. |
| Design contract | Becomes a design goal only when its predecessor is complete; it must define the dependent implementation's contracts and fixtures. |
| Issue | Carries the goal-ready record and PR closeout evidence. |
| Reserved/proposed proposal | Records a candidate and missing promotion evidence; it cannot create implementation work until promoted explicitly. |
| Operating-mode runbook | Is executable only after development completion and only with its explicit owner-controlled configuration authority; an experimental owner-smoke exception requires its own explicit scope and is not production deployment. |

## Goal prompt template

Use this template when activating a goal:

```text
Execute <iteration ID and user outcome> from <authoritative issue and delivery-plan entry>.

Preserve the stated predecessors, non-goals, data/permission boundaries, and operating-mode separation. Work only within the documented authority. Implement the ordered work units, then run every declared validation and perform a requirement-by-requirement completion audit against current repository and PR state.

Do not mark the full goal complete until the issue, branch, PR merge, required CI, requirement-to-evidence audit, tracker/roadmap/ledger closeout, and all stated evidence are current. Continue only this active goal; do not select a successor. Treat live credentials, real providers, and manual owner validation as out of scope unless this specific goal explicitly authorizes operating-mode work. For integration-only waits, follow incremental-delivery.en.md: diagnose once, finish safe work, and preserve an integration_pending receipt and one resume action without bypass or repeated unchanged polling. Other external implementation blockers use the three-turn blocked rule.
```

## Required final report

The final report names the supported increment, implementation state, integration state, operating evidence, PR/issue, exact validation evidence, data/security effect, known limits, and any remaining owner action. It must not claim an external capability is live when only mock-contract evidence exists, or describe a pending integration as merged/full-goal completion.
