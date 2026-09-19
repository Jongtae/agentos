# Personal AgentOS roadmap

Use the [Goal Execution Contract](goal-execution-contract.en.md): the canonical delivery plan and a goal-ready issue select work; vision, list order and planned issues never activate execution themselves.

**Personal AgentOS = Personal AI Kernel + Agent Distribution Platform.** It must do useful work before the marketplace is large, while preserving observable and revocable owner authority. See [architecture](personal-agentos-architecture.en.md), [Owner Control](owner-control-contract.en.md), [Default Agent Usefulness](default-agent-usefulness.en.md) and [platform foundation](agent-distribution-platform-foundation.en.md).

## Current delivery status

| Work | Status and evidence boundary |
| --- | --- |
| GOV-USE-01 / [#357](https://github.com/Jongtae/personal-agentos/issues/357) | Complete only upon PR #361 merge after required CI and independent review. Product/docs/governance/static evaluation specification; no runtime feature, model-quality result or live operation. |
| USE-01 / [#358](https://github.com/Jongtae/personal-agentos/issues/358) | Sole owner-selected next goal, conditional on #361 merge. `owner-activated-goal-ready`, not `active`; later explicit owner Goal invocation starts implementation. [Execution readiness](use-01-goal-readiness.en.md). |
| OBS-01 / [#359](https://github.com/Jongtae/personal-agentos/issues/359) | Planned/inactive: actual progress, redacted tool/action receipts and owner controls on current Work paths. Coordinate with USE-01 without a circular prerequisite. |
| AGENT-UX-01 / [#360](https://github.com/Jongtae/personal-agentos/issues/360) | Planned/inactive: useful install → grant → run → inspect → revoke → denied retry → remove → restart → separately authorized replacement/reuse. Reuses #335/#337/#338/#340/#341/#342 rather than inventing a second installer. |

Preparation must not start product code, a second heartbeat, credentials, a provider call or package installation. #335–#346/#359/#360 remain inactive. USE-01 must stop after its own evidence-based closeout without choosing a successor.

## First implementation priority: useful defaults

USE-01 improves the current native tool loop and file workspace for three journeys: public research to a decision-ready brief, approved documents to substantive ordinary-file artifacts, and follow-up correction/restart reuse. It need not wait for the full package epic, public Registry, Marketplace, Ruflo or more agents.

Build the minimal evaluator/fixtures/graders **before** baseline collection; freeze the rubric before product tuning. Then measure failures, add bounded public-page reading with explicit SSRF/DNS/redirect/private-egress defenses, and improve actual source-grounded outcomes. Search snippets are not full-page, inventory or checkout evidence. No cart/hold/login/booking/payment/message action is part of this goal.

The 24-case seed is a specification, not an executed benchmark. All cases have three clean-state trials in the declared mode, with real outcome/state checks and held-out paraphrases. Simulated responses can validate deterministic paths, not model quality. The proposed live promotion target is at least 20/24 successful trials per eight-case family, plus no unauthorized effects or private leaks in declared negatives. Missing owner-authorized credentials/scope/budget leaves `live_quality: not_run/pending_owner_operation`; deterministic development may close truthfully without claiming the live gate passed. Latency, interventions and available usage/cost are measured, not invented.

## Preserved platform program

[#333](https://github.com/Jongtae/personal-agentos/issues/333) remains planned, not an automatic queue. The outcome-first priority overlay changes emphasis, not the unfinished scope or evidence dependencies below.

### Phase A — foundation contracts

| Work | Issue | Scope |
| --- | --- | --- |
| D-AP-01 | [#334](https://github.com/Jongtae/personal-agentos/issues/334) | Development-complete in PR #350: v0.1 contracts, 14 schemas, 25 positive/58 negative fixtures and independent review; no package runtime/install/Registry/Marketplace proof. |
| D-AP-02 | [#335](https://github.com/Jongtae/personal-agentos/issues/335) | Planned trust/permission/install/update/rollback/uninstall and six owner-control rights. |
| D-MEM-01 | [#336](https://github.com/Jongtae/personal-agentos/issues/336) | Planned Context/Memory/Candidate semantics, useful continuity, revoked/deleted sources and explicit retained/remote copy limits. |
| D-SBX-01 | [#337](https://github.com/Jongtae/personal-agentos/issues/337) | Planned sandbox/supply-chain/broker enforcement design; a specification alone is not working isolation. |
| D-RT-01 | [#338](https://github.com/Jongtae/personal-agentos/issues/338) | Planned common Runtime/Work/Grant/Evidence and observed-versus-requested receipt semantics. |
| D-REG-01 | [#339](https://github.com/Jongtae/personal-agentos/issues/339) | Planned Registry identity/integrity versus Marketplace discovery/commerce. |

Reconcile #335/#337's interface before dependent implementation. #336 applies wherever Memory is used. Keep original D-AP-01 evidence and historical D-MP2-02 read-only authority unchanged.

### Phase B — local package platform

| Work | Issue | Scope |
| --- | --- | --- |
| I-AP-01 | [#340](https://github.com/Jongtae/personal-agentos/issues/340) | Planned local manager and validator, install-disabled, real granted/denied fixture behavior, update/rollback/uninstall/restart. #341/#342/#360 are downstream consumers, not prerequisites of this manager. |
| I-EVT-01 | [#341](https://github.com/Jongtae/personal-agentos/issues/341) | Planned manual bounded Work first, then declared Event integration, cancellation/revocation/idempotent recovery. |
| I-SDK-01 | [#342](https://github.com/Jongtae/personal-agentos/issues/342) | Planned public authoring/validation/pack/install path and one useful Files reference first; General/Research/Coding/MCP examples remain required subsequent scope. |

Few reference agents is acceptable, weak supported functions are not. Useful allowed output and actual denied unauthorized behavior must both be evidenced. One happy-path substep cannot close the original full lifecycle/Event/SDK issue. #360 then integrates the implemented contracts and replacement journey; downstream consumers never become reverse dependencies of their foundations.

### Phase C — ecosystem bootstrap

[#343](https://github.com/Jongtae/personal-agentos/issues/343) wraps compatible official/licensed MCP and selected OpenAI/Codex/Claude formats with the same authority boundary. [#344](https://github.com/Jongtae/personal-agentos/issues/344) is an optional bounded Ruflo Runtime Adapter. The full phase retains both scopes; neither is a prerequisite to useful defaults or the first Files app. No universal compatibility or live operation is claimed.

### Phase D — Registry ready

[#345](https://github.com/Jongtae/personal-agentos/issues/345) is planned local/open exact-release identity/trust/advisory resolution. Registry does not contain owner Context/Memory/Work or grant execution authority. No public Marketplace launch or commercial catalogue is delivered.

### Phase E — future acquisition autonomy

[#346](https://github.com/Jongtae/personal-agentos/issues/346) defines L1–L5 acquisition policy. L4/L5 auto-install is outside the first MVP and independent of action authority. It cannot bypass identity/MFA/CAPTCHA, terms or owner consent.

## Current usable baseline and evidence

FILE-WORKSPACE-01 / #314/#315/#316 completed through PR #320 and PR #324: owner-approved read-only references, managed results, original/derived/draft/final provenance, separate rebuildable indexes and durable Work/approval/evidence/recovery/auth, and restart/reuse. Evidence is deterministic-model/temp-local-file integration, not a universal personal-folder or external-provider claim.

DOGFOOD-01 / #351 completed through PRs #354–#356: documented Mac/browser/direct-provider/file/result/restart steps and simulated-provider real HTTP/temp-file acceptance. Actual live provider and real owner browser quality remain separate observations. The old no-successor closeout is historical; #357 now prepares only USE-01 without executing it. [Current owner instructions](../QUICKSTART.md) remain usable while platform work is planned.

D-AP-01 / #334 completed in PR #350 supplies normative contracts and schema/fixture verification, not installation, Runtime/Registry/Marketplace, credentials or Ruflo operation. Tests/static cases must not be described as live capability or benchmark success.

## Deferred and historical work — preserved

The entire pre-GOV-USE roadmap is retained **byte-for-byte** in [the 2026-09-14 roadmap history](roadmap.history-2026-09-14.md), Git blob `25d87bbcc3c7667da640815f1f6d2c559d2a6a12`. Its dated/historical entries remain evidence of their original scope, not current execution selectors. This split avoids rewriting previous evidence while making the present priority readable.

Important preserved boundaries:

- SITE-01 / #313 remains owner-deferred/not-planned; PR #327 source and manual Pages workflow are retained. No deployment, domain/DNS, operator identity/policy date or Google verification is authorized here.
- Optional Drive #308/#310/#312 remains closed/deferred; PR #311 retains bounded connector code without a new live OAuth/Drive/Telegram claim. DRIVE-TG-01 #306/PR307 remains mock-validated scope.
- SCN-D-01 #301 is completed design only; SCN-I-01 remains reserved. No KakaoTalk sending or other external action is enabled.
- TOP completion candidate `53912eeb1357ced37031234b1e5376f024dd0a96`/main validate `34204797899`, first milestone #282/#283, and STRUCT-01 #285/#286/#288/#292/#295/#296 remain historical evidence. OP-03 #280/#281 is unfinished, not overwritten by this roadmap.
- CI-01 #303/#304 and AUTO-01 #321/#322 are completed repository infrastructure, not proof of live runtime/heartbeat operation.
- UX/M0–M5/MP1/MP2, stabilization and operating-preparation histories remain in the preserved document and append-only ledger. D-MP2-02 stays owner-local read-only recommendation; schema successors never retroactively made it an installer.

No data migration, new runtime/credential/permission, automation, deployment or historical test result is introduced by this roadmap update.
