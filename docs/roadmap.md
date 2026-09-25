# Personal AgentOS roadmap

## Owner-selected execution integration — 2026-09-25

[AGENCY #600](https://github.com/Jongtae/agentos/issues/600) refines the active Presence program with actual supported goal execution. Follow the [execution contract](assistant-execution-contract.en.md) and [finite delivery/ownership](assistant-execution-delivery.en.md), reusing #597/#598. Baseline, broker parity, reviewed context composition, goal loop, recovery and real-model/installed-build qualification precede final claims. Older useful-default/platform order below is historical direction, not reactivation authority. No mandatory new framework or automatic acquisition is selected.

Use the [Goal Execution Contract](goal-execution-contract.en.md): the canonical delivery plan and a goal-ready issue select work; vision, list order and planned issues never activate execution themselves.

**Personal AgentOS = Personal AI Kernel + Agent Distribution Platform.** It must do useful work before the marketplace is large, while preserving observable and revocable owner authority. See [architecture](personal-agentos-architecture.en.md), [Owner Control](owner-control-contract.en.md), [Default Agent Usefulness](default-agent-usefulness.en.md) and [platform foundation](agent-distribution-platform-foundation.en.md).

## Current delivery status

| Work | Status and evidence boundary |
| --- | --- |
| GOV-EXEC-01 / [#408](https://github.com/Jongtae/agentos/issues/408) | Complete on merge after exact-head CI/review: repository-wide stable-head verification budget. Focused tests and batched remediation reduce redundant full-suite/re-review churn without weakening branch protection, exact-head validation, independent review, or security/authority escalation. |
| PRESENCE-01 / [#508](https://github.com/Jongtae/agentos/issues/508) | **Active top-level goal.** GitHub Issues/PRs/Checks are authoritative for completed execution. Completed foundations and follow-ups are regression inputs, not work to repeat. Completed since activation: #494, #506 (Google revoke split to [#588](https://github.com/Jongtae/agentos/issues/588), proposed), #505, #580, #559, #562, #447; #581 implementation merged (#591) but its owner live pass failed, so it is reopened. [#512](https://github.com/Jongtae/agentos/issues/512) first run merged (#596) with findings. Remaining (owner decisions 2026-09-25; up to two non-overlapping children at once): [#597](https://github.com/Jongtae/agentos/issues/597) ∥ [#598](https://github.com/Jongtae/agentos/issues/598) → re-run [#512](https://github.com/Jongtae/agentos/issues/512) + independent convergence review → [#513](https://github.com/Jongtae/agentos/issues/513). Non-blocking findings: [#594](https://github.com/Jongtae/agentos/issues/594) (proposed). #383/#437/#445 are outside the current Presence execution queue. |
| EPIC-FU1 / [#501](https://github.com/Jongtae/agentos/issues/501) | **Owner-paused on 2026-09-24** by GOV-PRESENCE-ACT-01 / [#523](https://github.com/Jongtae/agentos/issues/523): FU1-474/FU1-473/FU1-DEC-01 merged, #475/#482 not reopened, no closeout audit claimed. Originally owner-activated and goal-ready by GOV-FU1-01 / [#502](https://github.com/Jongtae/agentos/issues/502) (owner direction 2026-09-23). Removes the four P1 first-use dead ends found by TEST-FIRST-USER-01 / #472, one substep at a time: FU1-474 / #474 (complete on merge of #519) → FU1-473 / #473 (complete on merge of #520) → FU1-DEC-01 / #521 (owner direction 2026-09-24: FU1's semantic judgments become placeholder seams handed to IMPL-DECISION-01 #417) → FU1-475 / #475 → FU1-482 / #482. Reuses only connectors, grants, OAuth routes and approval APIs already on `main`; no new connector, scope, destination or live operation. Evidence class: automated synthetic/fixture only. Completion does not select a successor. |
| EPIC-REUSE-01 / [#418](https://github.com/Jongtae/agentos/issues/418) | Activated tranche (R1, R2, R4, R7, R8) complete. Commodity mechanics were reduced without reducing owner control: two Adopt (`oauthlib` PKCE, `mcp-types` protocol registry), one Adapt (stdlib `email` header parsing), two Build-retained on measured contract mismatch, and four development-only/historical modules relocated with none deleted, three of which left the installed package (`scripts/e2e.py` was already outside it). R1 closed on R1a and R1b only; R1c was never executed and is dispositioned to [#440](https://github.com/Jongtae/agentos/issues/440). Evidence is static analysis plus local automated suites and required CI; **no live provider, Kubernetes, launchd or Homebrew operation was observed**. No successor selected; EPIC-PA1 resumed separately by owner direction in #443, not by this completion. |
| REUSE-TRANSPORT-01 / [#420](https://github.com/Jongtae/agentos/issues/420) | Deferred/dependency-blocked: R3/R5/R6 provider, Telegram and HTTP transport replacement requires the transport/policy seam owned by PA1-CONV-01 / #393 and PA1-INT-01 / #394. #418's completion does not activate it. |
| GOV-PA1-01 / [#385](https://github.com/Jongtae/agentos/issues/385) | Preparation in PR branch: finite PA1 issue graph, parallel-worktree ownership and source-plan selector only; no runtime or external operation. |
| GOV-PA1-03 / [#399](https://github.com/Jongtae/agentos/issues/399) | Complete on merge of PR #400 after current CI/review: owner-only credentials/OAuth/live observations are operating-validation gates, not premature implementation blockers; safe PA1 development continues and #394 consolidates final `owner_validation_pending` checks. |
| EPIC-PA1 / [#386](https://github.com/Jongtae/agentos/issues/386) | **Closed out.** Development-complete on 2026-09-22 (GOV-PA1-06 / #463) and retired from the delivery plan by GOV-PA1-07 / #467, which moves `next_goal` to the no-active-goal contract so nothing in this program can be selected again. It was active from 2026-09-22 by explicit owner direction (GOV-PA1-04 / #443) and paused for the EPIC-REUSE-01 tranche by #419 before that; that history is preserved. All nine children merged and recorded in the ledger, PA1-INT-01 / #394 last via PR #451 (`04e3dc1`) — under [PA1 parallel delivery](pa1-parallel-delivery.en.md). **No enumerated substep remains, and that does not activate a successor** ([GOV-PA1-05 / #453](https://github.com/Jongtae/agentos/issues/453)). **Development-complete** as of 2026-09-22 (GOV-PA1-06 / #463). The earlier reading of this row — that J1 and J4 were unmet for implementation reasons — was superseded: both were engineering that had been misrecorded as blocked, and both landed (#455, #450). J1's artifact is traceable, J3 covers connection and retrieval, J4 is reachable as tools with an owner approve/apply surface, and J5 is wired with its discrimination measured and weak. **No journey has installed-smoke or live-owner evidence, and none is claimed.** What remains is entirely owner-live validation: a release action, Google OAuth for Gmail and Calendar, a real Telegram bot, and a Homebrew install with a reboot. Recorded limitations: J5 inventory discrimination 1/10 (#459), J4's natural-language create intent had no executing worker branch until [PA1-J4-02 / #465](https://github.com/Jongtae/agentos/issues/465) (literal-rule draft, exact preview, text approval; fixture evidence only), refusal messages name one of several provenance sources (#448). |
| GOV-USE-01 / [#357](https://github.com/Jongtae/agentos/issues/357) | Complete only upon PR #361 merge after required CI and independent review. Product/docs/governance/static evaluation specification; no runtime feature, model-quality result or live operation. |
| USE-01 / [#358](https://github.com/Jongtae/agentos/issues/358) | Development closeout recorded from merged [PR #362](https://github.com/Jongtae/agentos/pull/362) and the closed issue. Deterministic development evidence is 72/72; live provider quality remains `not_run/pending_owner_operation`. #358 did not select a successor; EPIC-PA1 is separately prepared by #385. |
| OBS-01 / [#359](https://github.com/Jongtae/agentos/issues/359) | Planned/inactive: actual progress, redacted tool/action receipts and owner controls on current Work paths. Coordinate with USE-01 without a circular prerequisite. |
| AGENT-UX-01 / [#360](https://github.com/Jongtae/agentos/issues/360) | Planned/inactive: useful install → grant → run → inspect → revoke → denied retry → remove → restart → separately authorized replacement/reuse. Reuses #335/#337/#338/#340/#341/#342 rather than inventing a second installer. |

Preparation must not start product code, a second heartbeat, credentials, a provider call or package installation. #335–#346/#359/#360 remain inactive. USE-01 must stop after its own evidence-based closeout without choosing a successor.

## First implementation priority: useful defaults

USE-01 improves the current native tool loop and file workspace for three journeys: public research to a decision-ready brief, approved documents to substantive ordinary-file artifacts, and follow-up correction/restart reuse. It need not wait for the full package epic, public Registry, Marketplace, Ruflo or more agents.

Build the minimal evaluator/fixtures/graders **before** baseline collection; freeze the rubric before product tuning. Then measure failures, add bounded public-page reading with explicit SSRF/DNS/redirect/private-egress defenses, and improve actual source-grounded outcomes. Search snippets are not full-page, inventory or checkout evidence. No cart/hold/login/booking/payment/message action is part of this goal.

The 24-case seed is a specification, not an executed benchmark. All cases have three clean-state trials in the declared mode, with real outcome/state checks and held-out paraphrases. Simulated responses can validate deterministic paths, not model quality. The proposed live promotion target is at least 20/24 successful trials per eight-case family, plus no unauthorized effects or private leaks in declared negatives. Missing owner-authorized credentials/scope/budget leaves `live_quality: not_run/pending_owner_operation`; deterministic development may close truthfully without claiming the live gate passed. Latency, interventions and available usage/cost are measured, not invented.

## Preserved platform program

[#333](https://github.com/Jongtae/agentos/issues/333) remains planned, not an automatic queue. The outcome-first priority overlay changes emphasis, not the unfinished scope or evidence dependencies below.

### Phase A — foundation contracts

| Work | Issue | Scope |
| --- | --- | --- |
| D-AP-01 | [#334](https://github.com/Jongtae/agentos/issues/334) | Development-complete in PR #350: v0.1 contracts, 14 schemas, 25 positive/58 negative fixtures and independent review; no package runtime/install/Registry/Marketplace proof. |
| D-AP-02 | [#335](https://github.com/Jongtae/agentos/issues/335) | Planned trust/permission/install/update/rollback/uninstall and six owner-control rights. |
| D-MEM-01 | [#336](https://github.com/Jongtae/agentos/issues/336) | Planned Context/Memory/Candidate semantics, useful continuity, revoked/deleted sources and explicit retained/remote copy limits. |
| D-SBX-01 | [#337](https://github.com/Jongtae/agentos/issues/337) | Planned sandbox/supply-chain/broker enforcement design; a specification alone is not working isolation. |
| D-RT-01 | [#338](https://github.com/Jongtae/agentos/issues/338) | Planned common Runtime/Work/Grant/Evidence and observed-versus-requested receipt semantics. |
| D-REG-01 | [#339](https://github.com/Jongtae/agentos/issues/339) | Planned Registry identity/integrity versus Marketplace discovery/commerce. |

Reconcile #335/#337's interface before dependent implementation. #336 applies wherever Memory is used. Keep original D-AP-01 evidence and historical D-MP2-02 read-only authority unchanged.

### Phase B — local package platform

| Work | Issue | Scope |
| --- | --- | --- |
| I-AP-01 | [#340](https://github.com/Jongtae/agentos/issues/340) | Planned local manager and validator, install-disabled, real granted/denied fixture behavior, update/rollback/uninstall/restart. #341/#342/#360 are downstream consumers, not prerequisites of this manager. |
| I-EVT-01 | [#341](https://github.com/Jongtae/agentos/issues/341) | Planned manual bounded Work first, then declared Event integration, cancellation/revocation/idempotent recovery. |
| I-SDK-01 | [#342](https://github.com/Jongtae/agentos/issues/342) | Planned public authoring/validation/pack/install path and one useful Files reference first; General/Research/Coding/MCP examples remain required subsequent scope. |

Few reference agents is acceptable, weak supported functions are not. Useful allowed output and actual denied unauthorized behavior must both be evidenced. One happy-path substep cannot close the original full lifecycle/Event/SDK issue. #360 then integrates the implemented contracts and replacement journey; downstream consumers never become reverse dependencies of their foundations.

### Phase C — ecosystem bootstrap

[#343](https://github.com/Jongtae/agentos/issues/343) wraps compatible official/licensed MCP and selected OpenAI/Codex/Claude formats with the same authority boundary. [#344](https://github.com/Jongtae/agentos/issues/344) is an optional bounded Ruflo Runtime Adapter. The full phase retains both scopes; neither is a prerequisite to useful defaults or the first Files app. No universal compatibility or live operation is claimed.

### Phase D — Registry ready

[#345](https://github.com/Jongtae/agentos/issues/345) is planned local/open exact-release identity/trust/advisory resolution. Registry does not contain owner Context/Memory/Work or grant execution authority. No public Marketplace launch or commercial catalogue is delivered.

### Phase E — future acquisition autonomy

[#346](https://github.com/Jongtae/agentos/issues/346) defines L1–L5 acquisition policy. L4/L5 auto-install is outside the first MVP and independent of action authority. It cannot bypass identity/MFA/CAPTCHA, terms or owner consent.

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
