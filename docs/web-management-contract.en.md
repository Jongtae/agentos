# Local Web Management Contract

Decision date: 2026-09-20. Design record: #379 / PR #380. Implementation: #382 (WEB-ADMIN-01). [Korean owner summary](web-management-contract.ko.md).

**Status: owner-selected product direction and implementation specification, not shipped behavior.** Recording this contract or merging its documentation does not start Codex, mark the implementation complete, or activate a scheduler. The implementation issue supplies the bounded work units, readiness alignment, validation and stop rule.

## 1. Product role

The owner uses Telegram to ask for work and receive useful answers. The local web is the utility used to manage AgentOS: inspect tasks and results, find retained records, and configure execution/data connections. It is not a second messenger and does not reproduce a global Telegram conversation by default.

AgentOS remains authoritative for history, Memory, Grants, Work, Artifacts and Evidence. Telegram is today's interaction adapter, not a dependency of the kernel's identity; later channels can share the same management tool. Removing the default web conversation view does not remove history, chat APIs, backend context, channel delivery, or existing user data.

## 2. Decision precedence

This decision supersedes the web-chat-first and mandatory top-level-project placement in the earlier utility-v1 prototype and generated mockups. Reuse compact styling, stable drafts, exact test/apply and task list/detail patterns, but do not copy obsolete navigation or fake demo states into production. The [historical design README](design/utility-v1/README.md) identifies the older reference.

Preserve improvements already on current main. #371 is a diagnostic reference, #374/#378 contain earlier UI work, and #372 / PR #373 must be inspected for overlapping settings changes before implementation. Do not reset the code to an old screenshot. #358 is closed at this recording; do not erase its evidence. #359/#363/#364 retain their distinct remaining scope. #381 is separate conversation-quality planning and remains inactive.

This is a successor presentation contract, not a relaxation of data/authority rules. Current root AGENTS.md, [Goal Execution Contract](goal-execution-contract.en.md), [Incremental Delivery](incremental-delivery.en.md) and [Owner Control Contract](owner-control-contract.en.md) continue to apply.

## 3. Information architecture

Default destinations:

- **작업 현황**: meaningful owner requests, status, results and observed execution.
- **내 기록**: searchable typed records and results.
- **설정**: AI 연결; 파일 · 저장; 외부 연결; 개인정보 · 진단.

Use one stable navigation and one visible destination. Selecting a destination replaces the content pane, not scrolls to another section under a conversation. Do not duplicate the same navigation in the content. Desktop may use a quiet sidebar; mobile uses destination/list/detail with a clear back action. Preserve appropriate URL history, selection, scroll, focus and unsaved drafts.

Projects remain optional grouping accessible through relevant work/records. Preserve their data and access; no compulsory project CTA, top-level project home or setup step. Add an independent agent-management destination only when real install/manage capabilities are separately delivered; no empty marketplace shell now.

Once initial configuration exists, open task status or the last management destination. A missing connection gets a small contextual setup action. File location setup is required only for a file-backed operation, not every first use. No hero, mascot, KPI dashboard, recommendations carousel, daily tips, support widget or permanent setup checklist.

## 4. Tasks are not messages

The default task list represents useful work, not every Telegram message. Connection commands such as /start and internal probes belong in connection activity/diagnostics; classification changes visibility, not retention. Reuse existing IDs and state rather than introducing a new authoritative task database.

Task detail order:

1. Request title and current state.
2. Actual result or the action the owner must take next.
3. Observed execution timeline and sources.
4. Expandable redacted execution details.

A completed text response is itself inspectable. An artifact needs an actual working result link/action. Do not show 'result available' with an empty Result heading. Keep failed, partial, interrupted and unknown outcomes distinct. Do not invent progress percentages, ETAs, intermediate steps or model identity. The repository's development heartbeat is not product-request progress.

'원래 요청 보기' reveals only the authorized context of the selected task on explicit expansion, not a default global transcript. Approve/cancel/recover are task-bound controls only where supported by real backend actions. Preserve approval, cancellation-requested versus confirmed, and external-uncertainty distinctions. This slice does not implement all of OBS-01.

## 5. Records and files

Records start with search, type filters, list and selected detail, not a glossary or policy form. Keep notes, durable memory, temporary context and artifacts distinct underneath. Labels, counts, previews and allowed actions must match their real type. Identify an item before removal; never send artifact deletion to a memory endpoint, ignore an error, or implicitly delete an original file.

Temporary collection/sharing controls live under their relevant settings. Record empty states explain what is absent without implying ordinary conversation history was lost. Example: '아직 따로 저장한 기록이 없습니다. 대화 이력과 저장한 기록은 구분됩니다.' This is copy guidance, not a change to retention.

Use **참고 폴더** for input and **결과 저장 폴더** for generated files. **프로젝트** is grouping, not a path. Present one understandable owner-facing folder configuration while preserving legacy stores/grants. Where old folder capabilities differ, identify the distinction rather than silently widening access or merging records.

## 6. Connections, states and guidance

The principal setting is the selected execution connection. Show actual backend precedence, not an assumed channel split: on the inspected implementation a selected subscription CLI takes precedence for both web and Telegram AI jobs, and editing/testing a direct API does not switch that selection. A selected CLI must not be labelled 'no AI connected' merely because a direct API provider is unset. If future supported routes genuinely differ, identify them independently rather than inventing a global model. Preserve the current route restrictions and show unsupported operations honestly.

Distinguish configuration, owner-attested login, verified readiness, and actually observed execution/model. Missing model information is '모델 정보 미제공', not a fabricated model. Local process execution does not prove local-only model processing. Data-location/sharing copy comes from the effective route and policy, not reassuring boilerplate.

Preserve **edit draft -> test that exact draft -> apply**. Failed/stale tests leave the working configuration intact; changed inputs invalidate prior verification. CLI and local models do not arbitrarily require API keys. Do not transfer an old key to a changed destination or perform paid calls merely by opening settings.

Connected services show their current status and a manage/change entry, not an empty credential form demanding reconnection. Put setup fields behind setup/change. Example help: '새 연결을 테스트하는 동안 기존 연결은 유지됩니다.' Do not imply the test is free or offline if it actually contacts a provider.

Content belongs beside the relevant action: brief label, necessary hint, inline error and recovery. Longer explanation is optional disclosure. Do not put a title/purpose/what-you-can-do/tip block on every screen. No unsupported edit/install/cancel buttons solely to fill space. Results may render safe links/lists/formatting, not arbitrary HTML or pages of raw encoded URLs.

Polling must not destroy draft input, caret/selection, search results, pending confirmation or expanded detail. Update only the relevant state; navigation does not discard owner work without an explicit discard decision. Visiting a pane must not itself create a model request or external action.

## 7. Bounded implementation and evidence

#382 owns three product increments: W1 management shell/removal of duplication; W2 task/result monitor; W3 records/settings/content alignment. W0 checks current source, overlap and readiness in that same issue, not another preparation project. The exact branch is `codex/382-web-management-utility`.

Readiness must exist in both the issue and source plan before explicit activation under the existing selection rules. If it is absent or incomplete, an invocation is limited to W0 preparation and must stop after normal validation/review/merge; it does not continue into W1-W3 in that same preparation invocation. If the dependency-satisfied ready record already exists, verify it and the owner's explicit activation before product work. Registering a ready entry does not select a goal, displace another goal or start a worker/heartbeat. Preserve plan parity and history.

Reuse current vanilla HTML/CSS/JS and backend contracts. Necessary read-model fixes are allowed; replacing the frontend framework, message infrastructure, storage system or authority model is not. Preserve Telegram ingestion/delivery, internal conversations and existing APIs. Changing obsolete UI assertions requires replacement backend/channel coverage, not wholesale removal of tests.

Issue #382 defines A1-A8 acceptance: destination replacement; preserved Telegram-origin task/result path; task-specific events/results; stable drafts/search through real polling/navigation; truthful CLI/API route states; typed record actions and data survival; contextual optional setup; and real browser evidence at desktop/mobile with synthetic fixtures. These are requirements, not passed tests.

Independent UX/convergence review is bounded to changed paths. Address actual enabled-path regressions; do not make an unrelated historical audit, a paid benchmark or a new design study a prerequisite. Run required CI and inspect the resulting browser. Ship small verified increments; never close the whole issue from shell-only evidence.

For external merge waits, use the existing integration_pending receipt: exact head, actual gate, tests/findings, next actor and one resume action. Do not claim completion, bypass protection or repeatedly poll unchanged state. A session handoff is not an automated retry mechanism.

## 8. Recording versus execution

This contract, source-plan readiness record and issue #382 make the work explicit and discoverable. They do not run a coding worker. The [Codex handoff](design/utility-v1/CODEX_PROMPT.txt) first checks already-recorded readiness and explicit owner activation. Missing readiness permits preparation only, followed by a stop and a separate owner activation action; it is not permission to implement first and reconcile governance afterward. No new automation or provider access is configured by this record.

Keep four facts separate in reports: decision recorded; task specified/ready; implementation executed; verified/merged. Documentation CI does not demonstrate that the owner's local web changed. Read the current checkout explicitly in an already-running Codex session rather than assuming it automatically noticed this new decision.

The original screenshots and conversations remain private input. Repository evidence uses synthetic examples only. The author's environment did not connect to the owner's local server; screenshot diagnosis and source inspection are not a live browser audit of the current installation.
