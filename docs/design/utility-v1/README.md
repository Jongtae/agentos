# AgentOS Utility UI — proposal v1

Status: design proposal, awaiting owner visual approval. Tracking issue: #379. Baseline inspected: `c6a78466ea82cfc90d79d434c733ccab37339039`; related diagnosis: #371. This proposal does not authorize product implementation or replace existing runtime/governance contracts.

## Product character

An installed personal utility, even when delivered through a browser. Users open it to operate their AI, inspect a request, locate a result, or change a setting, then return to their work. It is not an AI subscription website, dashboard, promotional onboarding page, or model shop.

No mascot, hero banner, feature advertising, recommendation carousel, pricing, statistics tiles, daily-tip panel, support widget, or obligatory setup checklist. Do not replace these with a dark developer console. The target is quiet, precise and readable.

## Review the proposal

Open `prototype.html` with `utility.css` and `utility.js` in the same directory. It has no dependencies, remote fonts, network calls, provider integration, filesystem access or persistent storage. All records, statuses, times and model names are synthetic. The key field is read-only intentionally. This is a browser interaction prototype, NOT working AgentOS.

Review five routes: `#ai`, `#tasks`, `#files`, `#records`, and the model-change dialog opened from `#ai`. The other routes demonstrate navigation and contextual help; they are not complete feature specifications.

The prototype source is the visual reference. This README and the actual product authority contracts take precedence over incidental sample behavior. Generated illustrations are mood references, never exact component/code specifications. Screenshots in the companion design bundle are rendered from the prototype; no private user screenshots or live credentials are committed.

## Navigation and content

One stable sidebar contains everyday destinations: 대화, 작업 현황, 내 기록, 프로젝트. Below a quiet 환경설정 group label are AI 연결, 파일 · 저장, 외부 연결, 개인정보 · 진단. Selecting any destination REPLACES the main pane. Never append management sections under chat. No duplicate top navigation, nested Connections system, or tab that merely scrolls to another section.

On desktop, the sidebar is about 194 px; the main utility window is about 1100 × 776 px. These are visual reference dimensions, not a mandate for a fixed viewport. On narrow screens, a menu reveals the same destinations and selection closes it. The active pane owns its scroll; dialogs must fit the viewport. Preserve browser back/forward, active destination, draft input, search, selected task, expanded detail and appropriate scroll/focus.

The decorative desktop titlebar belongs only to the presentation. Do not duplicate native window controls inside a normal browser tab. No desktop wrapper is required.

Each screen has a compact title, one-line purpose, task controls, and at most a short contextual hint. Longer explanations are disclosure text near the relevant action. Empty/error states explain the next useful action. Do not repeat a page-length glossary, security promise or setup guide on every page. Folder setup is OPTIONAL until the task needs files; do not block plain chat on file configuration.

## AI connection contract

The primary object is the selected EXECUTION CONNECTION: subscription CLI, direct provider, or local model. A selected Codex CLI must not coexist with a top-level message saying no AI is connected. A provider/model configured for a different route must not be displayed as the engine that will handle the next request.

Show connection type, selected name, readiness evidence and its timestamp when known. A self-attested login is not a measured successful call; an undisclosed model is "모델 정보 미제공", not an invented model name. Distinguish selected connection, working readiness, configured model and observed model.

Change flow: open draft -> edit -> test exact draft -> apply on success. Maintain the previous working connection until successful apply. Test failure leaves it intact. Changing provider, endpoint, model or key after testing invalidates the test; stale asynchronous responses cannot re-enable apply. A server should bind its verification to the exact draft, not merely trust a front-end disabled button.

Keys never transfer silently to a changed destination. Local/CLI routes do not demand an API key. Explicit test actions may contact a provider in the real product; disclose this next to the action. Do not collect real keys in this prototype.

The dialog's success/failure selector is a PROTOTYPE CONTROL and must not enter production. The mock CLI uses one generic example; actual implementation must reflect supported CLI authentication/readiness rather than treating a text field as proof of login. Reuse current working endpoints and adapt the smallest missing read model.

## Task monitor contract

Desktop: request list and selected request detail. Main status, observed connection/model, selected source references, timestamped event timeline, optional redacted tool detail and actual result links. No KPI dashboard or guessed percentage.

Differentiate observed completion, in-flight activity and planned steps. Show "다음 실행 정보는 아직 없습니다" when no new event is available, rather than fabricate analysis steps. A last successful read does not prove a later synthesis or write. Missing model identity remains unknown.

Bind everything by job/work ID; never mix events, approvals or results from adjacent tasks. Preserve details and scroll during polling. Repository CI/heartbeat is not user-request progress and must not appear in this monitor.

Only expose supported controls. Production stop handling must distinguish requested, confirmed, interrupted and externally unknown outcomes. The prototype's instant local stop toggle is only visual state demonstration, not cancellation implementation. Do not claim rollback. Unsupported controls are omitted or explained, never faked.

## Records, files and project language

내 기록 uses one searchable list with filters for 메모, 기억, 결과, 임시 자료. Identify each item by title/preview, type, source and time as available. Show type-specific guidance only after choosing that filter. Backend types remain separate. Inspect before delete; deletion must clearly specify its scope and never implicitly remove the original file, every record, or shared results. The prototype removes only an in-memory sample row.

참고 폴더 means input files. 결과 저장 폴더 means output files. 프로젝트 means related conversations/results, not a filesystem path. Present one owner-facing folder model without destructive consolidation of legacy storage. Existing authority and approval invalidation continue to apply.

외부 연결 is optional. 개인정보 · 진단 holds secondary retention and diagnostic information, not daily notes. Do not expose unsupported edit/delete/install controls to make the layout appear finished.

## Visual rules

Neutral off-white sidebar, white pane, thin separators, restrained blue for selection/actions. Use familiar outline icons, aligned label/value rows, 6–8 px control radii and a compact hierarchy. No saturated full-width CTA when it is merely another way to connect a provider. Select controls/list rows, not provider product cards. System fonts only; no bundled font files.

Use comfortable utility density, not unreadably small typography. The supplied fixed screenshots are a visual starting point. Product implementation must check actual-size text, 200% zoom, keyboard/focus/dialog behavior and adequate touch hit areas on narrow screens; do not copy a small presentation caption into an essential form label. Aim for at least 44 px touch hit areas without forcing oversized desktop controls. Status cannot depend on color alone.

## Implementation slices after owner approval

1. Navigation shell and stable local draft state. Preserve existing working APIs, record definitions and stored data. Do not restore older commits.
2. AI connection summary plus test/apply state accuracy across direct and CLI routes.
3. Request monitor, records list, and consistent reference/output/project terms.
4. Contextual copy, empty/error states and narrow-screen/keyboard fit.

Reuse vanilla HTML/CSS/JS. No new UI framework, telemetry service, governance rewrite, package platform or permissions expansion. Each slice may ship independently under current repository gates. Missing optional runtime capability is a labelled follow-up, not an invitation to build a new backend platform.

## Product acceptance (not satisfied by this prototype)

- Opening a destination displays only that pane; browser history and mobile navigation behave predictably.
- Editing a model/search/toggle, waiting through multiple real polling cycles and navigating away/back preserves intended draft state and focus.
- API and CLI status accurately identify the next execution route. Test the exact new draft; failed/stale tests never replace the current working connection.
- Each selected task shows its own real source/tool/result events; unsupported actions/telemetry are not invented.
- A note can be inspected and removed in its supported scope without opening diagnostics; folder and project setup are distinct.
- Browser evidence at desktop and 390 px includes empty, ready, editing, testing, failure, approval-needed and completed states. Check keyboard, Escape, dialog focus, long names, loading and 200% zoom.

## Evidence of this proposal

Nine offline Chromium interaction checks passed: mock exact-draft test does not change current connection; draft edits invalidate prior test; apply updates the mock state; failed test preserves it; navigation replaces pane; record query survives navigation/idle; task selection and stop state demonstrate; 390 px view has no page-level horizontal overflow; no JavaScript page errors observed. These checks injected the authored HTML/CSS/JS into a blank browser document because local URL navigation was unavailable. No runtime polling, actual API, native host, live model quality, user study, end-to-end AgentOS acceptance or independent expert review was performed.

The deliverable is a visual direction and executable interaction reference. The real app must continue to use real state and its tested backend contracts.
