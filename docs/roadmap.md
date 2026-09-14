# Personal AgentOS roadmap

Use the [Goal Execution Contract](goal-execution-contract.en.md) with this tracker: the active delivery plan and a goal-ready issue select work; vision, roadmap order, historical entries, and planned/reserved issues do not activate themselves.

Personal AgentOS is a local-first, owner-installed personal AI operating environment. The long-term architecture is **Personal AI Kernel + Agent Distribution Platform**: AgentOS owns durable owner state and authority; packages, tools, models and delegated runtimes remain replaceable workers/capabilities. See the canonical [architecture](personal-agentos-architecture.en.md), [development constitution](development-constitution.en.md), and [Agent Distribution Platform foundation](agent-distribution-platform-foundation.en.md).

## Proposed — Agent Distribution Platform / EPIC-ADP-01

[#333](https://github.com/Jongtae/personal-agentos/issues/333) is the planned successor epic that turns the owner-authoritative kernel into an ecosystem-ready platform. **Creating these issues does not activate execution.** Each issue requires explicit owner activation, a goal-ready contract and the normal issue → branch → PR → validation/review lifecycle.

The platform keeps the kernel agent-independent while allowing the product/marketplace to present agents as installable applications. Core authority remains with Owner, Context, Memory, Artifact, Capability, Runtime registration, Grant, Work, Event and Evidence. Distribution adds AgentPackage, Package Manager, Registry, Marketplace/Discovery and Trust/Verification without giving those layers owner-state authority.

D-AP-01 / [#334](https://github.com/Jongtae/personal-agentos/issues/334) is complete on merge of [PR #350](https://github.com/Jongtae/personal-agentos/pull/350). It defines the canonical v0.1 contracts, schemas, deterministic fixtures, compatibility rules, and independent review evidence. This is specification and machine-verification evidence only; it does not implement or prove package execution, installation, a Registry/Marketplace, credentials, connectors, Ruflo, or live external operation. No successor is active, and #335–#346 remain planned until separate explicit owner activation.

Owner-authorized DOGFOOD-01 / [#351](https://github.com/Jongtae/personal-agentos/issues/351) is the current implementation goal on `dogfood/owner-usable-vertical-slice`. It closes only the smallest local browser → supported provider → explicit reference folder → managed result → restart/reuse path. Automated evidence uses a simulated provider and temporary folders; live provider operation remains a separate owner observation and is not claimed here. #335–#346 remain inactive.

### Phase A — foundation contracts

| Work | Issue | Planned outcome |
| --- | --- | --- |
| D-AP-01 | [#334](https://github.com/Jongtae/personal-agentos/issues/334) | Complete on merge of PR #350: Core primitives + AgentPackage v0.1 schemas/contracts |
| D-AP-02 | [#335](https://github.com/Jongtae/personal-agentos/issues/335) | package trust, permission and install/update/rollback/uninstall lifecycle |
| D-MEM-01 | [#336](https://github.com/Jongtae/personal-agentos/issues/336) | third-party Context/Memory and MemoryCandidate semantics |
| D-SBX-01 | [#337](https://github.com/Jongtae/personal-agentos/issues/337) | sandbox, capability broker, supply-chain and quarantine/revocation model |
| D-RT-01 | [#338](https://github.com/Jongtae/personal-agentos/issues/338) | common Runtime Adapter / Work / Grant / Evidence contract |
| D-REG-01 | [#339](https://github.com/Jongtae/personal-agentos/issues/339) | Registry identity/integrity plane separated from Marketplace/discovery |

### Phase B — local package platform

| Work | Issue | Planned outcome |
| --- | --- | --- |
| I-AP-01 | [#340](https://github.com/Jongtae/personal-agentos/issues/340) | local AgentPackage validator + Package Manager |
| I-EVT-01 | [#341](https://github.com/Jongtae/personal-agentos/issues/341) | installed-package Work/Event integration and restart/recovery |
| I-SDK-01 | [#342](https://github.com/Jongtae/personal-agentos/issues/342) | SDK/CLI + General/Files/Research/Coding reference packages |

### Phase C — ecosystem bootstrap

| Work | Issue | Planned outcome |
| --- | --- | --- |
| I-ECO-01 | [#343](https://github.com/Jongtae/personal-agentos/issues/343) | wrap/import compatible MCP and selected OpenAI/Codex/Claude ecosystems |
| I-RT-RUFLO-01 | [#344](https://github.com/Jongtae/personal-agentos/issues/344) | prove Ruflo as a bounded delegated Runtime Adapter, not kernel authority |

### Phase D — Registry ready

| Work | Issue | Planned outcome |
| --- | --- | --- |
| I-REG-01 | [#345](https://github.com/Jongtae/personal-agentos/issues/345) | local/open Registry with immutable releases, trust metadata and advisories |

### Phase E — future capability acquisition

[D-AUTO-01 / #346](https://github.com/Jongtae/personal-agentos/issues/346) defines L1–L5 acquisition policy from manual install through future bounded agent-requested capability acquisition. L4/L5 auto-install is **not** part of the first platform MVP. Package acquisition authority remains separate from action authority at every level.

Current product evidence does not include AgentPackage installation, a Registry/Marketplace, Ruflo integration or autonomous acquisition. The above is planned work only.

## Deferred — Product information and policy site

[#313](https://github.com/Jongtae/personal-agentos/issues/313) is closed as not planned by explicit owner priority decision. [PR #327](https://github.com/Jongtae/personal-agentos/pull/327) prepared bilingual static product, install, privacy, and terms pages plus a manually dispatched Pages workflow; these artifacts remain preserved and unchanged. Remaining public deployment is deferred, not completed, and is not a prerequisite for local-file work or optional Drive/OAuth development. The earlier publication-blocker observation in PR #328 remains historical evidence, not a live deployment claim. Reconsider publication only after a new explicit owner decision and current confirmation of operator identity, support contact, policy effective date, hosting/domain choice, and any required Google verification. No Pages dispatch, domain/DNS change, Google registration, or successor activation is authorized by this closeout.

## Completed — File-and-folder personal workspace

Owner-authorized [#314](https://github.com/Jongtae/personal-agentos/issues/314) completed its finite A → B → C program. AgentOS now treats owner files and folders as the material foundation and conversation/work as the experience: preserve originals, search and use approved material, save ordinary-file results, and reuse them after restart. A merged in PR #317; B merged in [PR #320](https://github.com/Jongtae/personal-agentos/pull/320); and C records the current requirement-to-evidence audit, two independent review artifacts, and the latest required CI. This completion is limited to automated deterministic-model and temporary local-file evidence; it does not claim external model, Telegram, Drive, scheduler, or personal-folder operation.

Connected reference folders are read-only by default; managed-workspace writes are scoped. Originals, derived material, drafts, final records, rebuildable indexes, and durable task/approval/evidence/recovery/auth state remain distinct. External AI, messenger, and agent transmission is separately controlled. This program does not implement OCR, transcription, video analysis, advanced large-library search, cloud-only import, material-bundle delegation, cloud sync, or destructive migration.

Drive #308/#310/#312 are closed/deferred optional connector work rather than first-flow predecessors. Merged PR #311 preserves a bounded local Drive Picker implementation, but no live Google OAuth, Drive, Telegram, credential, or operating observation is claimed. #313's remaining informational/policy-site publication is owner-deferred and does not block local file functionality.

## First milestone closeout — 2026-09-08

Owner-authorized [#282](https://github.com/Jongtae/personal-agentos/issues/282) consolidates the development baseline through merged PR #283 (`0025148e7ab30bd27c4b1ca761b3ba9702b0e0f8`, required validate `34213401518` success) in the [Korean report](first-milestone-report.ko.md). TOP remains development-complete, and #279 retains the legacy prototype as historical. OP-03 #280/#281 remains unfinished and preserved. Actual provider login, Telegram/OAuth activation, and operating deployment remain separate.

## Completed — GitHub Actions validation audit

[#303](https://github.com/Jongtae/personal-agentos/issues/303) audited all tracked workflows and found one required `validate` workflow. Merged [PR #304](https://github.com/Jongtae/personal-agentos/pull/304) retained its pull-request and `main` triggers while removing its redundant `unittest discover` invocation: the preceding full `pytest` suite already collects those tests. Required `validate` run `34222145626` passed. This is CI-only maintenance and changes no runtime, credential, provider, connection, or operating-deployment boundary.

## Completed — state-driven GitHub handoff loop

[#321](https://github.com/Jongtae/personal-agentos/issues/321) merged [PR #322](https://github.com/Jongtae/personal-agentos/pull/322), which adds a bounded, state-driven implementation/review handoff loop. It derives authority from the active delivery-plan item, protects claims and receipts through interrupted CI/review cycles, fails closed for unknown required checks and invalid worker factories, and preserves an owner merge decision. Required `validate` run `34474165551` passed. This is fixture-backed repository automation only: no recurring scheduler registration, live GitHub worker operation, credential change, automatic merge, or external deployment is claimed.

## Complete on merge — Telegram Drive web OAuth contract

Owner-authorized [DRIVE-TG-01 / #306](https://github.com/Jongtae/personal-agentos/issues/306) delivers a mock-validated Telegram-to-browser Google Drive OAuth handoff: owner binding, signed and expiring state, PKCE, encrypted owner-local token storage, explicit file selection, native Google Workspace export handling, redacted recovery messages, and Drive-request job pause/resume. It is not a live connection: no provider login, credential entry, token exchange, Drive access, or external operating deployment is claimed. A separately goal-ready operating iteration is required for local live testing.

## Complete design — First live-use scenarios

Owner-authorized [SCN-D-01 / #301](https://github.com/Jongtae/personal-agentos/issues/301) defines two first-use journeys before any new capability is implemented: (1) Telegram meeting preparation using owner-approved, attributable Drive context followed by separately approved Calendar draft creation; and (2) owner-supplied content translation or summarization followed by an exact KakaoTalk recipient/conversation preview and a separate one-time final-send approval. It is a design-only goal. KakaoTalk capability, credentials, connection, delivery, and live operating evidence are explicitly out of scope; a copy/export fallback is not a delivery claim. SCN-I-01 remains reserved until a separate goal-ready implementation issue is created and activated.

## M0 — Product basis and delivery sequence

[#103](https://github.com/Jongtae/personal-agentos/issues/103) records the current product contract, freezes legacy P7 work, and moves the delivery loop onto Hub v2.

## M1 — Subscription engine connection

[#104](https://github.com/Jongtae/personal-agentos/issues/104) delivers consumer onboarding that detects Codex or Claude Code, guides the owner to its official login, and records only owner-confirmed connection without API-key setup. It does not inspect credentials or run the engine; bounded execution follows in M2. Homebrew remains a developer path.

## M1.5 — Personal runtime isolation

[#109](https://github.com/Jongtae/personal-agentos/issues/109) creates the user-scoped OCI container or managed lightweight VM, dedicated volume, mediated read-only file boundary, and hosted Kubernetes translation. The consumer never operates Docker or Kubernetes directly. See [the isolation boundary](runtime-isolation.md).

## M2 — AgentOS-owned execution boundary

[#105](https://github.com/Jongtae/personal-agentos/issues/105) adds bounded execution adapters and AgentOS MCP tools inside the isolated owner runtime. A turn receives an empty temporary working directory, a fixed minimal environment, structured output handling, a timeout, and only the `list_notes`, `save_note`, and `web_search` AgentOS tool facade. Engines do not receive arbitrary host access, owner storage, credentials, document roots, or a route outside that runtime. Automated boundary coverage is complete; a real owner subscription turn still requires separately recorded live acceptance evidence.

## M3 — Personal Telegram bot and first work

**delivered.** [#106](https://github.com/Jongtae/personal-agentos/issues/106) uses an owner-created BotFather bot: the owner pastes its token once into authenticated local AgentOS, which validates it locally, creates a one-time private pairing link, and owns polling, recovery, and delivery. The token remains only in the local private connection store and is excluded from settings, logs, events, exports, and the redacted [live acceptance procedure](validation/h3-01-botfather-telegram-first-work.md).

## M4 — Personal context inbox

**delivered.** [#107](https://github.com/Jongtae/personal-agentos/issues/107) adds opt-in local clipboard/URL capture, sensitive-data filtering, retention, and per-assistant sharing policy.

## M5 — Trusted assistants and portability

**delivered.** [#108](https://github.com/Jongtae/personal-agentos/issues/108) exposes three official assistants and adds portable owner export/restore plus a managed-hosting migration design. The built-ins are researcher, reviewer, and planner; each is an explicit bounded, read-only role. `scripts/agentos-backup.py` exports owner state and reviewed plugin declarations only. It excludes connection secrets, login/session material, local folder grants, selected engines/models, and Telegram pairing; restoring requires a new local claim and explicit reconnection.

## Historical baseline

## Completed repository maintenance

[#170](https://github.com/Jongtae/personal-agentos/issues/170) adds Korean, Simplified Chinese, and Japanese README versions, with navigation between all supported languages. It also adds repository hooks and `main` branch protection to keep work on issue-linked pull-request branches.

The v1 runtime and 1.0.3 release are retained as documented maintenance history. P7 Telegram task-card acceptance and release work are frozen rather than treated as Hub v2 prerequisites.

The [V1-02 Telegram daily-work iteration](https://github.com/Jongtae/personal-agentos/issues/137) makes the existing paired-owner Telegram surface usable for routine natural-language requests: status-only task cards, progress, queued-only cancellation, document-sharing approval, and truthful restart or uncertain-delivery status. It does not replay interrupted work or uncertain Telegram sends.

The [V1-03 safe personal-context iteration](https://github.com/Jongtae/personal-agentos/issues/138) adds an explicit Telegram context attachment form. The owner selects opaque local inbox IDs with `/context ID[,ID] -- request`; AgentOS never selects or enumerates context from prose. Attached items remain local until a model-specific local sharing policy exists and, for an external model, the paired owner approves that exact queued job in Telegram. Results retain local source labels; cards, approvals, and progress controls do not reveal context content.

## Historical — AgentOS UX v1.1

The [UX v1.1 epic](https://github.com/Jongtae/personal-agentos/issues/149) records delivered historical iterations: [UX-01](https://github.com/Jongtae/personal-agentos/issues/150) moved the web home to a conversation-first surface, later work added saved results, Telegram continuity, recovery language, and redacted source labels. It is not an active delivery selector. Its still-open GitHub epic is an administrative reconciliation item, not evidence that its work should restart. The detailed historical product basis is in [UX v1.1 personal-agent DM](ux-v1.1-personal-agent-dm.ko.md).

## Historical — Telegram Conversation UX v1.2

[UX-06](https://github.com/Jongtae/personal-agentos/issues/162) is delivered historical work. It treats the Telegram bubble sequence as product UX: concise acknowledgement, only necessary progress, one scannable completion message, owner-requested detail, clearly distinct approval and recovery prompts, and safe idempotent owner-only controls.

### UX-06 implementation status

**Delivered.** [#162](https://github.com/Jongtae/personal-agentos/issues/162) records the owner-visible bubble contract in [UX-06 Telegram conversation](ux-06-telegram-conversation.ko.md). The implementation preserves one status card and one terminal answer bubble, keeps approval/recovery controls separate, and expands the readable long-result preview. The root suite passed and the deployed Telegram desktop flow was directly observed to edit a status card to completion followed by one terminal answer without a generic completion duplicate.

## Historical/development-complete — Master Plan 1 Personal Assistant Core

The owner closed UX-05 after deciding its remaining manual Telegram observations were disproportionate. This does not claim the waived checks passed. [Master Plan 1](master-plan-01-personal-assistant-core.en.md) is development complete on mock-contract evidence: R-01 through R-05 prove policy-owned ReAct orchestration, A2A, Calendar, Drive, and the new owner-local release journey. External credentials and real connections remain deferred to the owner-controlled operating-mode deployment. The repository-wide [contract-first development governance](development-governance.en.md) defines these gates.

MP2 is proposed for [conversation-first settings](master-plan-02-proposal.en.md). [D-MP2-01](d-mp2-01-conversation-settings-contract.en.md) and I-MP2-01 are complete on automated mock-contract evidence: conversation and the local companion share a policy-owned, redacted settings read and exact lifecycle preview/confirm boundary. This does not configure a credential, OAuth flow, provider connection, or live external capability.

The owner-local delivery state is reconciled and must not rerun merged UX, MP1, D-MP2-01, or I-MP2-01 work. Autonomous execution continues only an explicitly owner-activated, goal-ready iteration; it never selects the next MP2 friction, successor, or feature by itself.

D-MP2-02 selects reviewed capability discovery and recommendation as that bounded friction. It defines only an owner-local reviewed catalogue and read-only recommendation boundary; marketplace discovery, downloading, installation, activation, permission/scope grant, credentials, OAuth, external endpoints/actions, and operating deployment remain out of scope. It remains historical authority for that original scope. The Agent Distribution Platform epic #333 and successor contracts #334–#346 extend future package/distribution work without retroactively widening D-MP2-02.

I-MP2-02 delivers the fixture-backed owner-local catalogue and read-only recommendation model with deterministic ranking and HTTP/Telegram parity. It remains development-only mock-contract evidence and does not claim any live recommendation source, connector, installation, Registry or Marketplace.

D-MP2-03 defines transparent owner-local Personal Space retrieval with source evidence and a separate explicit sharing boundary. It excludes external indexing, cloud sync, provider/OAuth/credentials, automatic long-term memory, document ingestion, external action, and operating deployment. I-MP2-03 is complete in [#251](https://github.com/Jongtae/personal-agentos/pull/251) on fixture-backed automated evidence: the policy-owned owner-local read model provides deterministic source evidence/redaction, safe audit/export/recovery, and HTTP/paired-Telegram/local-companion parity. It does not claim an external index, provider, connection, credential, sharing, action, or operating deployment.

Design completion is not capability completion. Historical plans mechanically mapped every Master Plan design entry to its named implementation, bilingual contract, and automated-evidence declaration. A `development_complete` Master Plan claim remains limited to its recorded evidence and is not an external operating claim.

The owner-directed subscription-engine Telegram stabilization cycle is complete in [#255](https://github.com/Jongtae/personal-agentos/pull/255). It fixes the `/summarize` command-only engine input defect, verifies the bounded AgentOS MCP bridge/tool round trip and failure/restart/duplicate recovery with fixtures, and introduces the required `validate` CI check for `main`. The single heartbeat resumes only an owner-approved active goal; it cannot select a new feature or operating deployment. This is mock/fixture and CI evidence only; it does not claim a live engine, Telegram deployment, or provider connection.

The original owner-approved operating deployment preparation cycle [#258](https://github.com/Jongtae/personal-agentos/pull/258) is historical only: its `v1.0.4` candidate claim was incorrect. [OP-02 / #261](https://github.com/Jongtae/personal-agentos/pull/261) corrected isolation/recovery design. TOP-01 [#272](https://github.com/Jongtae/personal-agentos/pull/272) proved the credential-free Compose lifecycle, and TOP-02/TOP-03 [#277](https://github.com/Jongtae/personal-agentos/pull/277) repaired the configured isolated-Codex path and completion gate. The reproducible candidate is `53912eeb1357ced37031234b1e5376f024dd0a96`, with successful main `validate` run `34204797899`. It proves development/fixture and local Compose evidence only: provider allowlist, official login, provider reachability, Telegram activation, and an operating deployment remain explicit owner-mode steps.

The design-to-implementation traceability governance is complete in [#246](https://github.com/Jongtae/personal-agentos/issues/246) / [#247](https://github.com/Jongtae/personal-agentos/pull/247). It is documentation and delivery-controller governance only, backed by automated verification; it does not configure or operate any external service.

[GOV-01 / #263](https://github.com/Jongtae/personal-agentos/pull/263) permanently aligns the contribution rules, bilingual goal contract, templates, heartbeat instructions, and legacy delivery controller. Only a named active goal may resume; successor selection, automatic issue/branch/merge/release actions, duplicate scheduling, time-only retries, and evidence-free completion fail closed. This is governance and automated-test evidence only; it grants no product, provider, credential, or operating authority.

## Completed — STRUCT-01 repository structure

[WU-01](https://github.com/Jongtae/personal-agentos/issues/285), [WU-02](https://github.com/Jongtae/personal-agentos/issues/286), WU-03 through merged [PR #288](https://github.com/Jongtae/personal-agentos/pull/288), and WU-04 through merged [PR #292](https://github.com/Jongtae/personal-agentos/pull/292) are complete. The final STRUCT-01 requirement-to-evidence audit is complete in [WU-05 / #295](https://github.com/Jongtae/personal-agentos/issues/295) through merged [PR #296](https://github.com/Jongtae/personal-agentos/pull/296). This restructuring preserves existing CLI usage, persisted data format, approval boundaries, isolation boundaries, recovery behavior, the nested `agentos/` repository, and `.runtime/` owner data. Owner-controlled operating deployment remains separate and is not claimed here.
