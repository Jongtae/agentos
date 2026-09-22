# Delivery tracks

Active work is executed only from a goal-ready issue and active delivery-plan entry under the [Goal Execution Contract](docs/goal-execution-contract.en.md). Status tables are trackers, not authority to activate reserved work.

## Execution governance

| Work unit | Issue | Current boundary |
| --- | --- | --- |
| GOV-EXEC-01: verification budget and stable-head review | [#408](https://github.com/Jongtae/personal-agentos/issues/408) | Complete on merge after exact-head CI/review. Keeps required CI/review gates while using focused tests during implementation, coherent checkpoint pushes, batched review remediation, a soft two-broad-cycle expectation, and no duplicate review/polling. |

## Completed — reuse-first infrastructure migration

| Work unit | Issue | Current boundary |
| --- | --- | --- |
| GOV-REUSE-01: reuse-first engineering governance | [#412](https://github.com/Jongtae/personal-agentos/issues/412) | Merged via PR #414. Adds Constitution clause C15 (Adopt → Adapt → Build) and the Existing Solutions Review to `AGENTS.md` and the Development Constitution. Governance only; binds every contributor and coding tool. |
| GOV-REUSE-ACT-01: activate a non-overlapping tranche | [#419](https://github.com/Jongtae/personal-agentos/issues/419) | Merged via PR #421. Paused EPIC-PA1, activated EPIC-REUSE-01 for R1/R2/R4/R7/R8 only, and registered the PA1-overlapping substeps under dependency-blocked #420. |
| GOV-REUSE-PAR-01: bounded parallelism | [#424](https://github.com/Jongtae/personal-agentos/issues/424) | Merged via PR #425. At most two open EPIC-REUSE-01 children with disjoint ownership. |
| EPIC-REUSE-01: replace custom infrastructure with maintained implementations | [#418](https://github.com/Jongtae/personal-agentos/issues/418) | Complete on merge after exact-head CI and independent review. Activated tranche closed, Two Adopt, one Adapt, two evidence-backed Build-retained, one relocation. Static and local automated-suite evidence only; no live provider, Kubernetes, launchd or Homebrew operation was observed. |
| R1a: Gmail MIME header parsing | [#422](https://github.com/Jongtae/personal-agentos/issues/422) | **Adapt** — stdlib `email.headerregistry`. The audit's `format=RAW` premise was wrong: Gmail already decomposes the tree, so the custom code was header-parameter parsing, not a MIME parser. |
| R1b: Google OAuth/PKCE mechanics | [#427](https://github.com/Jongtae/personal-agentos/issues/427) | **Adopt** — `oauthlib` for the code verifier/challenge and authorization URL. `google-auth` rejected on recorded grounds. Drive scope check tightened. |
| R2: MCP protocol version | [#426](https://github.com/Jongtae/personal-agentos/issues/426) | **Adopt** — `mcp-types` official registry replaces the hardcoded version. Envelope models deliberately not adopted; the reason is recorded in both bridge module docstrings. |
| R4: Codex/Claude execution adapters | [#433](https://github.com/Jongtae/personal-agentos/issues/433) | **Build retained** — both official SDKs measured against the contract and rejected: each spawns the engine with `os.environ.copy()` and lets callers only *add* variables, so neither can express the closed env allowlist; neither enforces a per-turn wall-clock kill; and the Codex SDK speaks the persistent `app-server` protocol rather than the one-shot `exec` this adapter depends on. |
| R7: public search/page extraction | [#430](https://github.com/Jongtae/personal-agentos/issues/430) | **Build retained** — the audit's candidates have weaker defaults than the hand-written control on the SSRF/private-egress boundary. |
| R8: legacy and development-runtime cleanup | [#435](https://github.com/Jongtae/personal-agentos/issues/435) | Four modules relocated and **none deleted**; three of them left the installed package (`scripts/e2e.py` was already outside it). Seven kept. Four of eleven were reclassified from "supported" after independent review rejected circular reachability evidence. |
| REUSE-TRANSPORT-01: provider, Telegram and HTTP transport | [#420](https://github.com/Jongtae/personal-agentos/issues/420) | Deferred, dependency-blocked. R3/R5/R6 need the transport/policy seam that PA1-CONV-01 and PA1-INT-01 own. Not activated by #418's completion. |

EPIC-REUSE-01 closed its activated tranche without selecting a successor. R1 closed on R1a and R1b only: **R1c was never created or executed** and is dispositioned to [#440](https://github.com/Jongtae/personal-agentos/issues/440), which also carries the open `google_drive.py` scope defect [#432](https://github.com/Jongtae/personal-agentos/issues/432). [#420](https://github.com/Jongtae/personal-agentos/issues/420), #440, #432, [#437](https://github.com/Jongtae/personal-agentos/issues/437) and [#438](https://github.com/Jongtae/personal-agentos/issues/438) are registered dispositions and recorded follow-ups, not an execution queue. EPIC-PA1 was reactivated on 2026-09-22 by owner direction, recorded in [GOV-PA1-04 / #443](https://github.com/Jongtae/personal-agentos/issues/443) — not by #418's completion, which selected no successor. #393 and #394 both merged on 2026-09-22; no EPIC-PA1 substep remains, and that does not activate a successor ([GOV-PA1-05 / #453](https://github.com/Jongtae/personal-agentos/issues/453)).

## Prepared — PA1 first Telegram personal-assistant completion

| Work unit | Issue | Current boundary |
| --- | --- | --- |
| GOV-PA1-01: parallel program preparation | [#385](https://github.com/Jongtae/personal-agentos/issues/385) | Preparation branch/PR only; issue graph, source-plan selector and ownership rules. No product implementation or external operation. |
| GOV-PA1-03: owner-only operating gate batching | [#399](https://github.com/Jongtae/personal-agentos/issues/399) | Complete on merge of PR #400 after current CI/review: owner-only live actions remain `owner_validation_pending` while safe development continues; #394 batches the final live checklist. No live operation is claimed. |
| EPIC-PA1: first Telegram personal-assistant completion | [#386](https://github.com/Jongtae/personal-agentos/issues/386) | **Active** since 2026-09-22 by owner direction ([#443](https://github.com/Jongtae/personal-agentos/issues/443)), after being paused for the EPIC-REUSE-01 tranche by [#419](https://github.com/Jongtae/personal-agentos/issues/419). All nine children are merged and recorded in the ledger (#387, #388, #389, #390, #391, #392, #382, #393, and [#394](https://github.com/Jongtae/personal-agentos/issues/394) via PR #451, merge `04e3dc1`), coordinated under [the PA1 contract](docs/pa1-parallel-delivery.en.md). **No enumerated substep remains.** **Not development-complete**: J1 and J4 are unmet and J5 is partial for implementation reasons, and no PA1-containing release artifact exists. **Development-complete** as of 2026-09-22 ([GOV-PA1-06 / #463](https://github.com/Jongtae/personal-agentos/issues/463)). All nine substeps plus four follow-on merges are in: J1 release traceability ([#455](https://github.com/Jongtae/personal-agentos/issues/455)), J5 research wiring ([#458](https://github.com/Jongtae/personal-agentos/issues/458)), J4 Calendar ([#450](https://github.com/Jongtae/personal-agentos/issues/450)) and the Gmail data plane ([#457](https://github.com/Jongtae/personal-agentos/issues/457)). **No journey is live-validated.** Everything remaining is owner-live operating validation — a release action and a PA1-containing artifact, Google OAuth for Gmail and Calendar, a real Telegram bot, and a Homebrew install with a machine reboot. Recorded limitations carried forward: J5's inventory discrimination is 1/10 ([#459](https://github.com/Jongtae/personal-agentos/issues/459)), J4's natural-language create *intent* has no executing worker branch so prose asks for detail rather than drafting, and the refusal messages name one of several provenance sources ([#448](https://github.com/Jongtae/personal-agentos/issues/448)). Three claims previously recorded here were wrong and are corrected in #463: a release artifact did exist, J5 was not blocked on an owner decision, and J4's blocker was not prose extraction. Goal-ready is not execution — selection still needs an explicit `active` transition. J1–J8 are **not** met and are not claimed; owner-only live checks stay `owner_validation_pending`, batched at #394. |
| PA1-FDN-01 | [#387](https://github.com/Jongtae/personal-agentos/issues/387) | Wave 0 serialized connector/resume/ownership seam. |
| PA1 Wave 1 | [#388](https://github.com/Jongtae/personal-agentos/issues/388), [#389](https://github.com/Jongtae/personal-agentos/issues/389), [#390](https://github.com/Jongtae/personal-agentos/issues/390), [#391](https://github.com/Jongtae/personal-agentos/issues/391), [#392](https://github.com/Jongtae/personal-agentos/issues/392), [#382](https://github.com/Jongtae/personal-agentos/issues/382) | Parallel-safe only after #387; disjoint owned files, no integration-owned shared edits. |
| PA1-CONV-01 | [#393](https://github.com/Jongtae/personal-agentos/issues/393) | Wave 2 central Telegram capability handoff and exactly-once resume after connector contracts stabilize. |
| PA1-INT-01 | [#394](https://github.com/Jongtae/personal-agentos/issues/394) | Merged via PR #451 (`04e3dc1`), with J1/J3/J4/J5 completed afterwards in #455/#458/#450/#457. Wired the connector handoff, which was inert in the shipped deployment, added the `agentos service`/`gmail-config` commands and the Gmail OAuth callback, and closed eight private-egress leaks found during integration. Three independent review passes; two returned CHANGES-REQUIRED. Known limitations carried out: `list_roots` taints a whole Work, a document job in the history window closes `weather`/`web_search`/`public_page_read` for that conversation, and refusal messages name only one of six provenance sources (#448). |

PA1 reuses the completed file-workspace baseline rather than rebuilding it. #363/#364/#383 remain separate follow-up/design records and are not automatic PA1 blockers; concrete PA1 defects still belong to the relevant child. No second heartbeat, live credential use, purchasing/booking/payment, marketplace work or multi-principal runtime is authorized by preparation.

## Current — useful default agents and observable owner control

| Work unit | Issue | Current boundary |
| --- | --- | --- |
| GOV-USE-01: product, control, usefulness and backlog alignment | [#357](https://github.com/Jongtae/personal-agentos/issues/357) | Complete only on merge of PR #361 after required CI and independent review. Documentation/governance/static evaluation specification, not product runtime or measured model quality. |
| USE-01: useful research, file artifacts and continuity | [#358](https://github.com/Jongtae/personal-agentos/issues/358) | Development closeout recorded from merged [PR #362](https://github.com/Jongtae/personal-agentos/pull/362) and the closed issue. Deterministic evaluator is 72/72; live provider quality remains `not_run/pending_owner_operation`. #358 did not select a successor; EPIC-PA1 is separately prepared by #385. |
| OBS-01: observed progress, redacted receipts and owner controls | [#359](https://github.com/Jongtae/personal-agentos/issues/359) | Planned/inactive; uses current Work evidence and does not become a prerequisite cycle for USE-01. |
| AGENT-UX-01: useful install/run/revoke/remove/replacement | [#360](https://github.com/Jongtae/personal-agentos/issues/360) | Planned/inactive; consumes existing package/security/runtime/SDK implementation, not a second installer. |

Read [Owner Control](docs/owner-control-contract.en.md), [Default Agent Usefulness](docs/default-agent-usefulness.en.md) and [USE-01 readiness](docs/use-01-goal-readiness.en.md). Build the minimum evaluator before baseline, freeze the rubric before tuning, and grade actual useful outputs plus denied unauthorized effects. The 24-case seed/static checks are not an executed model benchmark. Development completion and live-quality promotion are separate; unrun live evaluation stays pending.

#335–#346 remain inactive. Their original unfinished update/rollback/event/SDK scope is preserved; #340/#341/#342 are foundations for #360, not dependent on that downstream integration. No new heartbeat, package execution, credentials or external actions are authorized by this tracker. Historical status below retains its original scope and dates.

## Complete on merge — Agent Distribution Platform foundation

| Work unit | Issue | Status |
| --- | --- | --- |
| D-AP-01: Core Primitives + AgentPackage v0.1 | [#334](https://github.com/Jongtae/personal-agentos/issues/334) | Complete on merge of PR #350 after current schema/fixture validation, required CI, and independent schema, authority, and convergence review. This is a contract and machine-verification slice only: no package execution, installation, Registry/Marketplace, credential, connector, Ruflo, or live external operation is implemented or claimed. |

## Owner dogfood vertical slice

| Work unit | Issue | Status |
| --- | --- | --- |
| DOGFOOD-01: owner-usable local browser, provider, file workspace, and restart path | [#351](https://github.com/Jongtae/personal-agentos/issues/351) | Complete on merge of PR #354 with deterministic local HTTP/worker evidence and independent authority/convergence review; live-provider/browser operation remains owner-controlled and is not claimed by repository tests. |

DOGFOOD-01 selected no successor at its historical closeout. The current preparation above selects EPIC-PA1 as goal-ready only; no product successor is executing. Issues #335–#346 remain planned and require separate explicit owner activation.

## Deferred — Product information and policy site

| Work unit | Issue | Status |
| --- | --- | --- |
| SITE-01: static product, installation, privacy, and terms site | [#313](https://github.com/Jongtae/personal-agentos/issues/313) | Closed as not planned by owner priority decision. PR #327's static bilingual pages and manual-only Pages workflow are preserved; remaining public deployment is deferred, not completed. Operator identity, support contact, effective date, hosting/domain choice and any Google verification require a new explicit owner decision. No active successor is selected. |

## Completed — File-and-folder personal workspace program

| Work unit | Issue | Status |
| --- | --- | --- |
| FILE-WS-A-01: product criteria and plan alignment | [#318](https://github.com/Jongtae/personal-agentos/issues/318) | Complete (PR #317 merged). |
| FILE-WS-B-01: first integrated file experience | [#315](https://github.com/Jongtae/personal-agentos/issues/315) | Complete (PR #320 merged). |
| FILE-WS-C-01: validation, review, and closeout | [#316](https://github.com/Jongtae/personal-agentos/issues/316) | Complete after the merged #320 evidence audit, independent reviews, required CI, and this closeout record. |

Drive #308/#310/#312 are closed/deferred optional connector work, not predecessors of FILE-WS. Merged PR #311 preserves its bounded local implementation but does not claim live Drive, OAuth, or Telegram operation. #313's remaining product/policy-site publication is owner-deferred; its existing source is preserved.

## Completed repository maintenance

| Work unit | Issue | Branch | Status |
| --- | --- | --- | --- |
| CI-01: GitHub Actions validation audit | [#303](https://github.com/Jongtae/personal-agentos/issues/303) | `codex/actions-ci-audit` | complete (PR #304 merged; required `validate` passed) |
| AUTO-01: state-driven GitHub handoff loop | [#321](https://github.com/Jongtae/personal-agentos/issues/321) | `codex/321-state-handoff-loop` | complete (PR #322 merged; fixture-backed queue/receipt recovery only—no live scheduler or GitHub worker operation is claimed) |
| DRIVE-TG-01: Telegram-to-browser Drive OAuth contract | [#306](https://github.com/Jongtae/personal-agentos/issues/306) | `codex/306-drive-telegram-web-oauth` | complete on merge of PR #307; mock-validated only—no provider login, credential, token, Drive, or external operating connection is claimed. |
| SCN-D-01: first live-use scenario contract | [#301](https://github.com/Jongtae/personal-agentos/issues/301) | `codex/scn-01-live-use-scenarios` | complete design; SCN-I-01 remains reserved until a separately goal-ready implementation issue is activated. |
| STRUCT-01-WU-01: 구조 확정과 이동 명세 | [#285](https://github.com/Jongtae/personal-agentos/issues/285) | `codex/struct-01-repo-structure` | complete |
| STRUCT-01-WU-02: 문서·산출물 정리 | [#286](https://github.com/Jongtae/personal-agentos/issues/286) | `codex/struct-01-workunit-02-docifacts` | complete |
| STRUCT-01-WU-03: 제품 패키지 정리 | [#287](https://github.com/Jongtae/personal-agentos/issues/287) | `codex/struct-01-workunit-03-product-packages` | complete (PR #288 merged) |
| STRUCT-01-WU-04: 도구·배포·테스트 정리 | [#291](https://github.com/Jongtae/personal-agentos/issues/291) | `codex/struct-01-workunit-04-tool-deployment-tests` | complete (PR #292 merged) |
| STRUCT-01-WU-05: 독립 검토와 최종 마감 | [#295](https://github.com/Jongtae/personal-agentos/issues/295) | `codex/struct-01-final-closeout` | complete (PR #296 merged) |

## Closed top-level program

| Goal | Issue | Status |
| --- | --- | --- |
| TOP | [#265](https://github.com/Jongtae/personal-agentos/issues/265) | Development complete on immutable candidate `53912eeb1357ced37031234b1e5376f024dd0a96` and main `validate` run `34204797899`; development closeout #282; no active successor. OWNER-01 remains separate operating work; LEGACY-01 resolved by #279 (historical only). |

## First milestone consolidation

[#282](https://github.com/Jongtae/personal-agentos/issues/282) merged the report in [PR #283](https://github.com/Jongtae/personal-agentos/pull/283) (`0025148e7ab30bd27c4b1ca761b3ba9702b0e0f8`, required validate `34213401518` success). See the [2026-09-08 first milestone report](docs/first-milestone-report.ko.md), full issue/PR/branch inventory, independent review, and evidence-based administrative cleanup. OP-03 [#280](https://github.com/Jongtae/personal-agentos/issues/280) / PR #281 remains unfinished; passing CI is not acceptance completion. Four dirty worktrees and that unmerged branch are preserved.

## Maintained baseline

| Track | Goal | Status |
| --- | --- | --- |
| v1 / M0–M6 | Self-hosted personal runtime, documents, continuity, manifests, and v1 acceptance | Complete baseline through 1.0.3 |
| v1 / M7 | Telegram task-card polish and release gate | Frozen maintenance; it does not block Hub v2 |

## Completed repository maintenance

| Issue | Goal | Status |
| --- | --- | --- |
| [#170](https://github.com/Jongtae/personal-agentos/issues/170) | Localize README navigation and prevent direct integration-branch changes | Complete; merged in #171 |
| [#172](https://github.com/Jongtae/personal-agentos/issues/172) | Position AgentOS as an owner-controlled personal AI control plane and record the next proposed Hub v2 outcome | Complete; merged in #173, documentation only |
| [#174](https://github.com/Jongtae/personal-agentos/issues/174) | Add bilingual personal-assistant vision and Master Plan hierarchy | Complete; merged in #175, activated MP1 documentation and reserved MP2 |
| [#226](https://github.com/Jongtae/personal-agentos/issues/226) | Record a reserved MP2 candidate for conversation-first settings and a Chrome Settings-like local companion | Complete; documentation only |
| [D-MP2-01 / #230](https://github.com/Jongtae/personal-agentos/issues/230) | Define the conversation-first settings and Chrome Settings-like companion contract before implementation | Complete; merged in #231 with automated documentation validation |
| [#232](https://github.com/Jongtae/personal-agentos/issues/232) | Reconcile owner-local delivery state with documented merged UX/MP1/D-MP2-01 work | Complete; merged in #233; its former next action is historical |
| [I-MP2-01 / #234](https://github.com/Jongtae/personal-agentos/issues/234) | Implement conversation-first settings lifecycle through the shared policy boundary | Complete; merged in #235 with automated mock-contract validation only |
| [#236](https://github.com/Jongtae/personal-agentos/issues/236) | Reconcile the merged I-MP2-01 closeout in owner-local delivery state | Complete; merged in #237; its superseded next action is historical |
| [#238](https://github.com/Jongtae/personal-agentos/issues/238) | Adopt autonomous MP2 delivery-cycle governance | Complete; merged in #239; its MP2-specific selection rule is superseded by TOP |
| [D-MP2-02 / #240](https://github.com/Jongtae/personal-agentos/issues/240) | Define reviewed capability discovery and recommendation before any install authority | Complete; merged in #241 |
| [I-MP2-02 / #242](https://github.com/Jongtae/personal-agentos/issues/242) | Implement owner-local read-only reviewed capability recommendations | Complete; merged in #243 |
| [D-MP2-03 / #244](https://github.com/Jongtae/personal-agentos/issues/244) | Define owner-local Personal Space knowledge retrieval before any external sharing | Complete; merged in #245 |
| [#246](https://github.com/Jongtae/personal-agentos/issues/246) | Enforce Master Plan design-to-implementation traceability | Complete; merged in #247; design completion cannot satisfy a capability or Master Plan development-complete claim |
| [#254](https://github.com/Jongtae/personal-agentos/issues/254) | Stabilize subscription-engine Telegram memory summaries | Complete; merged in #255 with CI `validate` required for `main`; fixture evidence only, no live engine/provider claim |
| [#257](https://github.com/Jongtae/personal-agentos/issues/257) | Prepare owner-approved operating deployment | Historical; merged in #258, but its `v1.0.4` candidate is unsupported and replaced by TOP-01 validation |
| [OP-02 / #260](https://github.com/Jongtae/personal-agentos/issues/260) | Correct the unsupported OP-01 candidate and prepare isolated subscription execution | Complete; merged in #261 as immutable commit `18538eabc00a20de64f4c5f5a6ac004aeda2469e`; fixture/CI evidence only, with provider allowlist, image build, official login, and one owner operating deployment explicitly deferred |
| [GOV-01 / #168](https://github.com/Jongtae/personal-agentos/issues/168) | Permanently align autonomous active-goal execution and evidence-only completion | Complete; merged in #263 as `d92a61693d557db80ff8378e5b6c46cca46b0e98`; controller and heartbeat now fail closed outside one explicit goal, with automated governance evidence only |
| [I-MP2-03 / #250](https://github.com/Jongtae/personal-agentos/issues/250) | Implement owner-local Personal Space knowledge retrieval | Complete; merged in #251 with fixture-backed automated evidence only; no external index, provider, credential, sharing, or operating deployment |
| [MP1-D-01 / #176](https://github.com/Jongtae/personal-agentos/issues/176) | Define the Personal Space memory, source, evidence, sharing, and I-01 acceptance contract | Complete; merged in #177, design only and no runtime behavior change |
| [MP1-I-01 / #179](https://github.com/Jongtae/personal-agentos/issues/179) | Deliver Personal Space and the single-assistant UX | Complete; merged in #180 with owner-attested live acceptance |
| [MP1-D-02 / #182](https://github.com/Jongtae/personal-agentos/issues/182) | Define reviewed capability lifecycle | Complete; merged in #183, design only |
| [MP1-I-02 / #184](https://github.com/Jongtae/personal-agentos/issues/184) | Deliver reviewed capability registry | Complete; merged in #185 with automated validation |
| [MP1-D-03 / #188](https://github.com/Jongtae/personal-agentos/issues/188) | Define Google Drive read-only connector contract | Complete; merged in #189, design only |
| [MP1-I-03 / #190](https://github.com/Jongtae/personal-agentos/issues/190) | Deliver mock-validated Google Drive read-only connector | Complete; merged in #191 without live provider configuration |
| [MP1-D-04 / #198](https://github.com/Jongtae/personal-agentos/issues/198) | Define compatibility A2A delegation contract | Complete; merged in #199, design only |
| [MP1-I-04 / #200](https://github.com/Jongtae/personal-agentos/issues/200) | Deliver compatibility A2A delegation | Complete; merged in #201 with mock validation |
| [MP1-D-05 / #202](https://github.com/Jongtae/personal-agentos/issues/202) | Define Calendar create-event approval contract | Complete; merged in #203, design only |
| [MP1-I-05 / #204](https://github.com/Jongtae/personal-agentos/issues/204) | Deliver Calendar create-only approval flow | Complete; merged in #205 with mock validation |
| [MP1-D-06 / #206](https://github.com/Jongtae/personal-agentos/issues/206) | Define integrated ReAct release contract | Complete; merged in #207, design only |
| [MP1-I-06 / #208](https://github.com/Jongtae/personal-agentos/issues/208) | Release Personal Assistant Core | Complete; merged in #209 with automated integrated acceptance |
| [#192](https://github.com/Jongtae/personal-agentos/issues/192) | Adopt contract-first, mock-driven, CI-gated delivery governance | Complete; merged in #193, documentation and verification policy only |

## Historical: MP1 remediation

The original MP1 D/I iterations remain merged historical work. [#214](https://github.com/Jongtae/personal-agentos/issues/214) recorded the remediation: R-01 ReAct orchestration, R-02 A2A completion, R-03 Calendar completion, R-04 Drive completion, and R-05 end-to-end release acceptance have now merged in order. MP1 is development complete on mock-contract evidence; operating-mode configuration remains separate.

| [MP1-R-01 / #216](https://github.com/Jongtae/personal-agentos/issues/216) | Deliver policy-owned ReAct orchestration, lifecycle invocation gate, redacted evidence, deterministic recovery, and shared HTTP/Telegram entry point | Complete; merged in #217 with automated mock validation |
| [MP1-R-02 / #218](https://github.com/Jongtae/personal-agentos/issues/218) | Complete A2A Card, progress, timeout, cancellation, artifact, minimum-context, and portable-evidence contracts through the orchestrator | Complete; merged in #219 with automated mock validation |
| [MP1-R-03 / #220](https://github.com/Jongtae/personal-agentos/issues/220) | Complete Calendar owner-bound draft, approval, create, failure-state, and portable-evidence contracts through the orchestrator | Complete; merged in #221 with automated mock validation |
| [MP1-R-04 / #222](https://github.com/Jongtae/personal-agentos/issues/222) | Complete Drive selected-excerpt approval, re-auth, lifecycle recovery, and portable-evidence contracts through the orchestrator | Complete; merged in #223 with automated mock validation |
| [MP1-R-05 / #224](https://github.com/Jongtae/personal-agentos/issues/224) | Verify the full new owner-local Personal Space, Drive, A2A, Calendar, lifecycle, fallback, and export/restore journey through the service/orchestrator | Complete; merged in #225 with automated mock validation |

## Historical: Personal AgentOS v1 release delivery

| Iteration | Goal | Status |
| --- | --- | --- |
| [V1-02 / #137](https://github.com/Jongtae/personal-agentos/issues/137) | Telegram daily-work task cards, approvals, cancellation, and truthful recovery | Historical implementation record; it is not an active delivery selector |
| [V1-03 / #138](https://github.com/Jongtae/personal-agentos/issues/138) | Opt-in local documents and context in Telegram work with source evidence and external-sharing approval | Historical implementation record; it is not an active delivery selector |
| [V1-04 / #139](https://github.com/Jongtae/personal-agentos/issues/139) | Docker Compose VPS health, update, backup/restore, and Telegram continuity boundaries | Historical implementation record; it is not an active delivery selector |

## Historical: AgentOS Hub v2

| Milestone | Goal | Issue | Status |
| --- | --- | --- | --- |
| M0 | Record Hub v2 product basis and delivery sequence | [#103](https://github.com/Jongtae/personal-agentos/issues/103) | Historical tracker; top-level inventory is authoritative |
| M1 | Connect subscription engines without API-key setup | [#104](https://github.com/Jongtae/personal-agentos/issues/104) | Complete on fixture evidence |
| M1.5 | Isolate each personal AgentOS runtime from the Mac host | [#109](https://github.com/Jongtae/personal-agentos/issues/109) | Complete on fixture evidence; operating verification remains TOP-01 |
| M2 | Run subscription engines through AgentOS-owned tools | [#105](https://github.com/Jongtae/personal-agentos/issues/105) | Complete on fixture evidence |
| M3 | Deliver first work through an owner-created BotFather personal bot | [#106](https://github.com/Jongtae/personal-agentos/issues/106) | Complete on fixture evidence; live token pairing is owner operating work |
| M4 | Build an opt-in local context inbox | [#107](https://github.com/Jongtae/personal-agentos/issues/107) | Complete on fixture evidence |
| M5 | Provide trusted assistants and portable personal state | [#108](https://github.com/Jongtae/personal-agentos/issues/108) | Complete on fixture evidence |

The Hub v2 Epic is [#102](https://github.com/Jongtae/personal-agentos/issues/102). Its still-open GitHub state is an administrative reconciliation item, not an active delivery selector. The top-level inventory and active delivery plan select work; historical v1 records remain in the ledger.

## Historical: AgentOS UX v1.1

The [UX v1.1 epic](https://github.com/Jongtae/personal-agentos/issues/149) records the delivered minimalist personal-agent DM: [UX-01](https://github.com/Jongtae/personal-agentos/issues/150) through [UX-05](https://github.com/Jongtae/personal-agentos/issues/154) cover DM home, opt-in workspaces, Telegram continuity, safety/recovery language, context selection, and release acceptance. Its still-open GitHub epic is an administrative reconciliation item, not work to restart. See [the UX product basis](docs/ux-v1.1-personal-agent-dm.ko.md).

## Historical: Telegram Conversation UX v1.2

[UX-06 / #162](https://github.com/Jongtae/personal-agentos/issues/162) is delivered historical work. It makes the paired Telegram chat a deliberate assistant conversation: a concise acknowledgement, progress only when needed, one readable terminal answer, optional detail, and private owner-bound actions with truthful recovery.

### UX-06 — Telegram conversation bubbles

[#162](https://github.com/Jongtae/personal-agentos/issues/162) is complete. Each Telegram request now uses one status-card sequence and one terminal answer bubble; long answers use a larger readable preview and direct the owner to local web history. Automated root-suite coverage passed, and the deployed Telegram desktop flow was observed to edit the card to completion and show one terminal answer without a generic completion duplicate.
