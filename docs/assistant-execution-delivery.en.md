# Assistant execution: delivery, ownership and completion

Parent [#600](https://github.com/Jongtae/agentos/issues/600). Normative [execution contract](assistant-execution-contract.en.md). Cost/reuse amendment [#612](https://github.com/Jongtae/agentos/issues/612) is authoritative for verification depth. This is the 2026-09-25 owner-selected execution-integration refinement of PRESENCE-01, not a second coordinator. The two-child limit counts actively executing implementation worktrees, not backlog issue records.

## Finite work breakdown

| Order | Issue | Deliverable | Dependencies |
| --- | --- | --- | --- |
| G | #601 | Contract, plan/guidance convergence, manifest, executable evidence gate/tests; no product runtime edit | Owner request |
| Existing | #597 | Capability-need and explicit-memory semantics at the existing DecisionEngine seam | Existing foundation; new closeout criteria do not discard prior work |
| Existing | #598 | Partial/unknown/model truth and useful projection | #597 where shared files overlap; preserve original acceptance |
| 1 | #603 | Minimal known-defect reproductions and model-free build/route diagnostics | G; shared instrumentation waits for #597/#598 |
| 2 | #604 | One broker contract and actual native/MCP/isolated capability bindings | #603 |
| 3 | #605 | Reviewed source/destination-authorized public context composition | #604 |
| 4 | #606 | Existing goal loop, observations, alternatives and completion obligations | #605/#597 |
| 5 | #607 | Typed recovery, safe effects/retry/Stop/restart and transactional resume | #606/#598 |
| 6 | #608 | Existing unit/integration harness, accidental-request guard and optional scoped smoke | #607 and relevant #581 |
| Final | #512 | Rerun original A-J and cross-track integration on final candidate | #608/#598; fixture baselines may run earlier |
| Claims | #513 | All public README locales describe only qualified scope | #512/#608 |

#581 retains native Telegram and fixture/live discrepancy ownership. #595 is separately owner-directed Jev transport work, not a requirement to use one provider. Advertise that option only after actual qualification. Missing live credentials is an operating boundary, not permission for hidden provider substitution or stopping all safe development.

## Shared file discipline

`quickstart_service.py`, `conversation_handoff.py`, `agent_runtime.py`, `providers.py`, `bounded_execution.py` and `mcp_bridge.py` cannot have concurrent implicit owners. #597/#598 coordinate or serialize overlapping changes. New runtime children rebase after their predecessors merge. #601 owns planning/guidance/CI-gate files, not existing runtime fixes. Record intentional ownership transfer in both issues before edits.

Before each child, inspect main, PRs, issue scope and required checks; use the existing delivery lock; select only a dependency-satisfied enumerated child. Historical completion snapshots are not current GitHub status. Do not add a scheduler or reactivate retired programs. Planning changes record scope/order/authority, not every merge.

## Proportionate verification and concrete reuse

Default: changed-function unit tests with injected model/tool transports; a small model-free integration test only for a changed wire/broker/process/state boundary. Retain useful-positive and authority-negative cases. A fake model is valid for wiring tests, not proof of language competence. Do not mock away the boundary being tested.

Normal closeout is issue/changed behavior, focused tests, existing required CI and known limits. No per-child mandatory historical baseline run, mutation, content-addressed JUnit/trace packet, whole-project re-audit or live model trial. Mutations/counterexamples and independent review are reserved for actual risk, especially sole authority checks, idempotency and reachability. A relevant failing regression remains unresolved; optional unrun model checks are not development blockers.

Model checks are opt-in for affected model/prompt/tool-description changes, unexplained model-dependent behavior or a scoped public claim, with explicit data/destination/provider and request/token/cost/time budget. No all-case/all-route three-trial quota, universal 90% threshold or production per-answer judge. Repetition follows observed uncertainty. Installation identity can be checked without a model. Preserve the specific #581 reported client discrepancy and critical release conditions without adding unrelated model runs.

Reuse prior reviews such as #426. Name the internal symbol or SDK API, adapter glue and duplicate code removed/avoided. New contract nouns do not mandate new classes/stores. Before custom Build or wholesale replacement, use one bounded no-model compatibility test on the changed requirement/version. The execution contract contains the concrete internal/MCP/PydanticAI mapping; this amendment installs no framework.

Success reporting: command summary and affected tests. Failure reporting: failing IDs, assertion and bounded relevant diagnostic. Do not repeatedly feed passing transcripts or unchanged full logs to a model. Focused local iteration precedes one required stable-head CI run.

## Executable checks

```sh
python3 scripts/verify_assistant_execution.py --check-spec
python3 -m unittest discover -s tests -p test_assistant_execution_gate.py -q
python3 scripts/verify_master_plan_docs.py
python3 scripts/verify_src_layout.py
```

The first command is an offline manifest/ownership check, not a task-quality grade. The previous unused `--evidence` certificate interface and exhaustive-trial report parser are removed; use existing pytest/unittest/GitHub results. #608 must not grow a replacement certification platform. No live model, owner data or credential is used by these checks.

## Scope of the owner amendment

#612 changes verification/reuse, not the root plan's selected goal, finite task order, authority or runtime file ownership. The older root-plan model/installed-artifact qualification prose and historical numerical evaluation proposals are interpreted through this revised contract: scoped observed claims, not universal repeated trials or a live prerequisite for development closure. This explicit precedence avoids silently reactivating the retired #602 workload. Original security, useful outcomes and evidence honesty remain.

## Plan adoption and operating authority

Repository-root `delivery-plan.yaml` is the only current plan. Its packaged copy was already retired at the audited baseline; older two-copy instructions must not restore repository governance into the product. The spec gate and src-layout gate reject that regression.

The root plan enumerates this finite track inside the existing Presence program. #600 is the integration/evidence parent, not a second active coordinator. Implementation proceeds through dependency-satisfied children after governance adoption, with independent security review for changed authority/egress/effect boundaries. It does not turn on new authority on an owner installation.

Before real-model evaluation, record provider/account, synthetic or selected data, destinations, requests/tokens or monetary ceiling, duration and retention. Before deployment/account mutation, use explicit owner operating authorization. New paths retain existing safe rollout controls; verify the changed profile with no-model tests and only the scoped authorized smoke that its claim needs. No new scheduled automation is created or activated here.

## Production risk disposition

| Existing finding | Disposition |
| --- | --- |
| #594 items 1/2/3/4/5/6/9/11 | Applicable retry/atomicity/classification/secret/process/effect/item/resume work under #607; do not silently waive |
| #594 item 10 | Owner-local Host-boundary review under #608 before local handoff promotion; retain current restrictions |
| #594 items 7/8 | Trace retention/attribution disposition under #608; do not imply unlimited audit |
| #588 | Google-connected production profile needs effective disconnect/revoke or an explicit narrower product scope |
| #437/#445 | Keep bounded maintenance ownership; reuse mutation-test principles without historical whole-project re-audit |
| #383 and retired platform/usefulness programs | Historical/future only; no implicit activation |

## Completion stages

**Contract/infrastructure:** #601/#612 document the requirement and offline specification check; no runtime-repair claim.

**Development integration:** each actual runtime task meets its focused unit and needed boundary tests, required CI and risk-triggered review. #608 summarizes coverage with existing tools and an optional smoke procedure; it does not require a new evaluator.

**Operating claims:** only claim the specific model/client/build behavior actually observed. Missing live permission is recorded, not used to stop safe development or to invent success. #600 can close the agreed development integration once all runtime requirements pass; #512/#513 preserve any narrowly required operating condition and accurately label unobserved profiles. No blanket all-profile matrix is needed.
