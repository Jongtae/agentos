# DOGFOOD-01 Goal Readiness Record

## Status

Preparation record for GitHub issues #351 and #352.

DOGFOOD-01 is the owner-selected next product goal, but product implementation must not start until the activation-preparation change merges. The existing delivery heartbeat remains intentionally inactive until the owner invokes Codex Goal mode for #351.

## Owner outcome

The owner can run Personal AgentOS locally on a Mac, open the browser UI, connect one existing supported AI provider, chat, grant one local reference folder, complete one useful file-backed task, save the result into an owner-managed workspace, restart AgentOS, and find/reuse the prior result.

This is an operating-usability vertical slice. It is not an Agent Distribution Platform implementation and does not activate #335–#346.

## Required delivery-plan transition

The activation-preparation PR must make these state changes and no broader product change:

- add iteration `DOGFOOD-01`;
- milestone: `Owner Dogfood Vertical Slice`;
- issue: `351`;
- kind: `operating-usability`;
- activation status: `owner-activated-goal-ready`;
- dependency: `D-AP-01`;
- preserve D-AP-01 as completed historical evidence;
- keep SITE-01 owner-deferred;
- keep #335–#346 inactive;
- set `next_goal.id` to `DOGFOOD-01`;
- set `next_goal.status` to `owner-activated-goal-ready`, **not** `active`;
- state explicitly that the later owner invocation of Codex Goal mode is the execution delegation;
- keep both delivery-plan copies byte-identical.

Recommended iteration validation:

- `python3 scripts/verify_master_plan_docs.py`
- `python3 scripts/verify_src_layout.py`
- `cmp -s delivery-plan.yaml src/personal_agent/delivery-plan.yaml`
- `python3 -m pytest -q tests`
- `python3 -m unittest discover -s tests -q`

## Heartbeat invariant

Goal readiness and the repository heartbeat are separate states.

Before Goal-mode invocation:

- `next_goal.id == DOGFOOD-01`;
- `next_goal.status == owner-activated-goal-ready`;
- `DOGFOOD-01.activation_status == owner-activated-goal-ready`;
- `DeliveryPlan.select(...)` returns no work because `next_goal.status != active`.

The activation-preparation regression test should replace the old assumption that D-AP-01 closeout permanently implies `next_goal.id == null`. It must instead prove that an owner-selected dogfood target can be recorded without causing automatic controller execution.

## Implementation authority

Once the owner explicitly invokes Goal mode for #351, DOGFOOD-01 may change only what is necessary to complete the journey defined in #351. Reuse existing browser, provider, file-workspace and persistence paths where possible.

Do not silently widen:

- filesystem scope;
- host shell access;
- network destinations beyond the selected existing model-provider path;
- secret/credential exposure;
- external-recipient authority;
- package/runtime authority;
- background autonomy.

## Evidence boundary

Completion evidence must distinguish:

1. deterministic/unit/fixture evidence;
2. temporary local-file integration evidence;
3. repository CI/review evidence;
4. owner local operating observation;
5. real external-provider observation, only when actually exercised.

A configured provider screen, mock response, fixture or CI pass is not proof of a live provider call.

## Stop rule

After DOGFOOD-01 completes, stop. Do not activate #335–#346 or any other successor without a new explicit owner decision.
