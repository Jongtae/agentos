# Delivery tracks

Active work is executed only from a goal-ready issue and active delivery-plan entry under the [Goal Execution Contract](docs/goal-execution-contract.en.md). Status tables are trackers, not authority to activate reserved work.

## Complete on merge — Agent Distribution Platform foundation

| Work unit | Issue | Status |
| --- | --- | --- |
| D-AP-01: Core Primitives + AgentPackage v0.1 | [#334](https://github.com/Jongtae/personal-agentos/issues/334) | Complete on merge of PR #350 after current schema/fixture validation, required CI, and independent schema, authority, and convergence review. This is a contract and machine-verification slice only: no package execution, installation, Registry/Marketplace, credential, connector, Ruflo, or live external operation is implemented or claimed. |

## Owner dogfood vertical slice

| DOGFOOD-01: owner-usable local browser, provider, file workspace, and restart path | [#351](https://github.com/Jongtae/personal-agentos/issues/351) | Complete on merge of PR #354 with deterministic local HTTP/worker evidence and independent authority/convergence review; live-provider/browser operation remains owner-controlled and is not claimed by repository tests. |

No successor is active. Issues #335–#346 remain planned and require separate explicit owner activation.

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
