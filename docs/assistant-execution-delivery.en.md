# Assistant execution: delivery, ownership and completion

Parent [#600](https://github.com/Jongtae/agentos/issues/600). Normative [execution contract](assistant-execution-contract.en.md). This is the 2026-09-25 owner-selected execution-integration refinement of PRESENCE-01, not a second coordinator. The two-child limit counts actively executing implementation worktrees, not backlog issue records.

## Finite work breakdown

| Order | Issue | Deliverable | Dependencies |
| --- | --- | --- | --- |
| G | #601 | Contract, plan/guidance convergence, manifest, executable evidence gate/tests; no product runtime edit | Owner request |
| Existing | #597 | Capability-need and explicit-memory semantics at the existing DecisionEngine seam | Existing foundation; new closeout criteria do not discard prior work |
| Existing | #598 | Partial/unknown/model truth and useful projection | #597 where shared files overlap; preserve original acceptance |
| 1 | #603 | Baseline failures, real entrypoint/bridge evidence and installed-build diagnostics | G; shared instrumentation waits for #597/#598 |
| 2 | #604 | One broker contract and actual native/MCP/isolated capability bindings | #603 |
| 3 | #605 | Reviewed source/destination-authorized public context composition | #604 |
| 4 | #606 | Existing goal loop, observations, alternatives and completion obligations | #605/#597 |
| 5 | #607 | Typed recovery, safe effects/retry/Stop/restart and transactional resume | #606/#598 |
| 6 | #608 | Real runner, protocol/model/owner qualification and enforced promotion/rollback | #607 and relevant #581 |
| Final | #512 | Rerun original A-J and cross-track integration on final candidate | #608/#598; fixture baselines may run earlier |
| Claims | #513 | All public README locales describe only qualified scope | #512/#608 |

#581 retains native Telegram and fixture/live discrepancy ownership. #595 is separately owner-directed Jev transport work, not a requirement to use one provider. Advertise that option only after actual qualification. Missing live credentials is an operating boundary, not permission for hidden provider substitution or stopping all safe development.

## Shared file discipline

`quickstart_service.py`, `conversation_handoff.py`, `agent_runtime.py`, `providers.py`, `bounded_execution.py` and `mcp_bridge.py` cannot have concurrent implicit owners. #597/#598 coordinate or serialize overlapping changes. New runtime children rebase after their predecessors merge. #601 owns planning/guidance/CI-gate files, not existing runtime fixes. Record intentional ownership transfer in both issues before edits.

Before each child, inspect main, PRs, issue scope and required checks; use the existing delivery lock; select only a dependency-satisfied enumerated child. Historical completion snapshots are not current GitHub status. Do not add a scheduler or reactivate retired programs. Planning changes record scope/order/authority, not every merge.

## Required closeout packet

Each behavioral child supplies requirement IDs and its actual production call path; baseline revision/configuration/profile; a baseline failing assertion and candidate result; opposing valid/denied cases; a meaningful mutation; content-addressed trace/JUnit artifacts; current CI and genuinely risk-triggered independent review; and explicit unmet criteria. Missing provider-reported model remains unknown.

A test that passes after its claimed live binding is removed is insufficient. Diagnostic work can retain failing baselines without claiming repair. A child cannot `Closes #600`, transfer unmet criteria into an unlabeled backlog, or promote `skip`/`xfail` to product success. Implementer self-check is not independent review.

## Executable checks

Offline specification/ownership and gate tests:

```sh
python3 scripts/verify_assistant_execution.py --check-spec
python3 -m pytest -q tests/test_assistant_execution_gate.py
python3 scripts/verify_master_plan_docs.py
python3 scripts/verify_src_layout.py
```

Evidence consistency on eventual #608 runner outputs:

```sh
python3 scripts/verify_assistant_execution.py \
  --evidence /path/to/redacted-run/report.json \
  --source-sha <independently-known-source-sha> \
  --artifact-sha256 <independently-known-built-artifact-digest>
```

The report uses content-addressed paths confined to its own artifact directory. JUnit results and matching trace assertions must agree; all required cells/trials are present. No all-green product report is committed. Absent/inconsistent evidence exits nonzero. This checker cannot authenticate arbitrary hand-authored files: #608 must bind trusted runner/CI provenance, reviews and owner attestation into the actual promotion command and demonstrate rejection.

## Plan adoption and operating authority

Repository-root `delivery-plan.yaml` is the only current plan. Its packaged copy was already retired at the audited baseline; older two-copy instructions must not restore repository governance into the product. The spec gate and src-layout gate reject that regression.

The root plan enumerates this finite track inside the existing Presence program. #600 is the integration/evidence parent, not a second active coordinator. Implementation proceeds through dependency-satisfied children after governance adoption, with independent security review for changed authority/egress/effect boundaries. It does not turn on new authority on an owner installation.

Before real-model evaluation, record provider/account, synthetic or selected data, destinations, requests/tokens or monetary ceiling, duration and retention. Before deployment/account mutation, use explicit owner operating authorization. New paths start disabled/unqualified and receive per-profile qualification. No new scheduled automation is created or activated here.

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

**Specification/gate infrastructure:** #601 merges with required checks and adversarial gate tests. No runtime-repair claim.

**Development integration:** runtime changes have useful-positive, authority-negative and actual transport evidence with current CI. Missing authorized live operation is pending, not fabricated.

**Product qualification:** #608 real-model and exact installed-owner gates pass, mandatory risk dispositions are resolved, #512 final regression covers the same integration and #513 states that measured scope. Only then may #600 close as productized.

A paragraph, regex, tool declaration or expected-failure test alone cannot cross these boundaries. Report the precise stage achieved instead of saying the assistant is now fixed.
