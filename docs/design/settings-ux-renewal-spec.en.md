# Application settings UX specification — UX-SPEC-02

## 1. Status, authority and outcome

- Specification issue: [#766](https://github.com/Jongtae/agentos/issues/766).
- Owner request, 2026-09-28: document UI/UX improvements and how to implement them.
- Evidence class: design specification based on owner feedback, two supplied screenshots, and source inspection at `00ccf640e69208c7d911469e7521bda5b54392c4`.
- English is canonical; [Korean companion](settings-ux-renewal-spec.ko.md) presents the same decisions for owner review.
- This delivery changes documentation and a standalone design prototype only; production application files are unchanged. The owner activated the four implementation units on 2026-09-28 in #780 after reviewing the prototype; delivery-plan.yaml selects their execution order. Previously merged work remains historical evidence, not proof that this specification is implemented.

**Outcome:** the owner can understand the current configuration, make the intended change, and return to work without reading execution internals or assembling the AI workflow.

Adopt the [Presence contract](../presence-experience-contract.en.md), [product architecture](../personal-agentos-architecture.en.md) and [C16](../development-constitution.en.md#c16-ai-is-the-engine-agentos-orchestrates-it-does-not-implement-requests). The selected AI performs work; Judgment AI orchestrates worker/model choice and evaluates results; AgentOS preserves owner state, authority, secrets, budgets and evidence. This specification removes presentation obstacles to using that arrangement. It adds no task-specific automation.

The owner-local web remains a management application. Preserve the current conversation channel, task history and exact retained-item links. The long-term personal secretary, memory, Attention and collaboration direction does not authorize new runtime features here. “Codex/Claude application quality” is the owner's reference for compactness and predictable interaction, not a claim of feature or accessibility parity.

## 2. Evidence and problem inventory

The owner screenshots show an older title (`AI 연결`) and large outlined provider cards. Inspected main already has `AI 설정`, an `AI` tab and flatter chooser rows. Screenshot build identity is unknown; do not report every screenshot defect as a reproduced defect in current main. The local URL refused connection during the preceding inspection. No authenticated interaction or live product visual pass is claimed. The later standalone prototype is separately identified design evidence.

| ID / priority | Evidence and current source location | User cost | Required correction |
| --- | --- | --- | --- |
| P1 / high | `src/personal_agent/web/app.js:417`, `mainAiView`; subscription branches can say `현재 사용 중` while their description says login was not checked | Selection looks like verified health or active execution | Show configuration identity and verification as distinct facts; reserve execution wording for observed Work |
| P2 / high | `app.js:395`, `renderExecutionConnection`; raw `execution.limitation` and CLI versions are joined into the normal isolation row | The most technical paragraph dominates the settings screen | Keep the short access implication visible; disclose raw limitations and versions |
| P3 / high | `app.js:469`, `chooserRow`; route selection, model input, Claude token form, API replacement/removal and capability paragraphs share each route | Choosing an AI requires scanning unrelated account operations | Compact fixed-order list plus one explicitly opened account editor |
| P4 / medium | `app.js:390`, Judgment row; primary label limits the role to conversation interpretation | Owner gets an incomplete mental model of Judgment AI | Use `판단 AI`; explain orchestration concisely and preserve legacy entry points |
| P5 / medium | `app.js:425`, `mainAiView`; verification, model note, destination and capability text form one description | Facts have equal weight and no scanning hierarchy | Separate labelled model/destination metadata, verification state, capability summary and details |
| P6 / medium | Screenshot 2 shows a tall mixed form and a footer near clipped content; current `.dialog-body`/`.dialog-actions` in `style.css:504–531` need stateful visual acceptance | Important options or actions may become hard to reach | One bounded scroll region; footer in a separate layout row; test with expanded editor and zoom |
| P7 / medium | Screenshot 1 has stacked headings and long introductory copy; current `index.html` and `renderExecutionConnection` supply multiple explanatory layers | Settings feels like documentation | One page title, quiet group labels, persistent item titles and short contextual explanation |
| P8 / process | Prior merge/issue closeout did not settle the owner's visible concerns; screenshots and source are not the same identified build | Completed code can be mistaken for a delivered experience | Capture build-matched screens and interaction evidence; distinguish implementation, local delivery and owner acceptance |

Line numbers are inspection anchors, not stable APIs. Symbols and element IDs in section 10 are the implementation anchors. This inventory is an expert/source review, not a measured usability study. Do not publish the owner's screenshots, paths, accounts or credentials as public evidence; use synthetic data for reproducible examples.

## 3. Existing Solutions Review

**Decision: Adapt the existing presentation layer; Adopt native HTML and established interaction guidance.** No new component framework or runtime dependency is selected.

| Candidate / search evidence | Fit and decision |
| --- | --- |
| `settingsRow`, `settingsAction`, `settingsDisclosure`, `rememberFocus`, `restoreFocus`; existing `:root` tokens | Adapt existing row/disclosure/focus composition. Avoid a second settings component system |
| `mainAiView`, `judgmentView`, `effectiveJudgmentText`, `mainAiRoutes`, `MAIN_AI_GROUPS` | Adapt existing projections and fixed ordering. Keep canonical route resolution on the server |
| `chooserRow`, `chooserKeyForm`, `claudeTokenForm`, `openAiChooser`, `renderAiChooser`, `applyAiChoice`, `renderDecisionRoute` | Recompose existing forms/actions in contextual panels; preserve their transports and secret boundaries |
| `docs/design/ui-quality-01.md`, Presence settings contract, local web `AGENTS.md` | Reuse application typography, state/action grammar, two destinations, management role and history semantics |
| Native `dialog.showModal()`, `details/summary`, labelled radio inputs, `fieldset/legend`, CSS grid/flex, `Intl` | Adopt browser semantics; no build step, SDK, network call or licence-bearing runtime package added |
| WAI-ARIA APG dialog/radio patterns; WCAG reflow/target guidance | Interaction and accessibility reference, not evidence that the app already conforms |
| Radix Primitives | Considered accessible React components. MIT; official repository non-archived, maintained by WorkOS, last pushed `2026-08-08T16:39:51Z` when inspected; official package release page checked. Not selected: current UI is plain JS with native controls and no demonstrated missing contract requiring a React integration. No version installed or supply-chain safety claim made |

Searches included `rg` for the named symbols, settings/chooser selectors, UI test names and the linked contracts; `main_ai.py::status/activate` was read to distinguish saved credentials from the effective configuration. The pinned repository `frontend-design` and `web-interface-guidelines` checklists were applied to the proposal. Their decorative website suggestions yield to the owner's application brief.

AgentOS-owned authority and canonical state stay outside all presentation helpers. Reusing browser APIs avoids adding a dependency trust surface; it does not justify weakening content escaping, secret handling or server validation. Existing repository contributions remain AGPL-3.0-only. Radix's MIT licence is compatible in principle, but compatibility alone is not a reason to adopt it. No copied external implementation is required.

## 4. Information architecture and visual grammar

Preserve the current conceptual destinations: `작업 현황`, `설정`. Following the owner’s macOS Settings reference, expose them in one sidebar: Activity, then a Settings group containing its panes. Do not add a second settings navigation column, an in-content logo, provider emblem, or repeated Settings heading. The browser/window title may still identify AgentOS. Preserve settings routes: `#settings/ai`, files, external connections and privacy. Use `AI`, `파일 · 저장`, `외부 연결`, `개인정보 · 진단` as the settings navigation labels.

| Surface | Default content | On demand |
| --- | --- | --- |
| Work/activity | Request, substantive result, meaningful pending action or failure | Observed steps, redacted technical receipts |
| AI | Default AI, configured model, verification, Judgment AI relationship, material limitation | Change chooser, account editor, Judgment AI settings, execution details |
| Files/storage | Reference folders and output destination with explicit access meaning | Existing folder editor, path details, optional projects |
| External connections | Named service, observed connection state, next action | Credentials, session management, scope and disconnect consequences |
| Privacy/diagnostics | Existing collection/sharing settings and retained-data controls | Technical activity and developer details |

No new navigation destination, global chat composer, dashboard, marketplace, onboarding checklist or account-management subsystem is proposed. Existing optional projects and retained-item access stay reachable.

Visual targets are project choices, not standards:

- Reuse system fonts, the 14px base, existing 12/13/14/16/19/23 scale and 4/8/12/16/24/32 spacing. Do not shrink text to fit long diagnostics.
- Adapt the existing neutral palette: white content canvas, quiet gray sidebar and `#f7f8fa` grouped rows, existing ink/muted tokens and action blue `#1f3d6d`. The owner’s system-settings reference motivates restrained grouping; do not imitate OS window buttons or add decorative branding.
- Use one sidebar and one content pane. Item labels align left; current values and controls align right. Keep the useful settings pane around 720–840 CSS px. Show one title for the selected pane.
- Normal rows align item, current value and action. Main AI and Judgment AI are independent peer groups. Following the Main AI is a configuration option, not a parent/child role hierarchy; Judgment AI orchestrates the workers. Use quiet grouped rows with separators. Normal verification is plain text; reserve stronger state emphasis for meaningful exceptions.
- Desktop controls retain the 36px default height. Touch layouts target 44px hit areas without making every input visually oversized. Selected radio state and keyboard focus have different treatments; only the actual focused control needs a focus ring.
- Common-path labels and descriptions should fit in one or two lines at the desktop target. This is a copy budget, never a rule to truncate errors, destinations or essential access implications.

## 5. AI overview and terminology

The content title is `AI`; `AI 설정` remains a descriptive name for the destination, not a second visible heading. Stable row titles are `기본 AI` and `판단 AI`; empty/error states do not replace them. `AI 연결 안 됨` is not a global description of this page. Use connection language only for an actual connection check or service connection.

Illustrative synthetic wireframe, not a screenshot or a claim about the owner's configuration:

```text
AI

기본 AI                              Codex · 구독  [변경]
모델                                         CLI 기본값
로그인                                확인됨  [상태 확인]
전송 대상                                       OpenAI
사용 가능한 도구                         웹 검색, 브라우저

판단 AI                            기본 AI 따라가기 [설정]
모델                                <확인된 AI·모델명>
상태                                            확인됨
요청에 맞는 AI와 도구를 고르고 결과를 확인합니다.

파일 접근 범위                  작업 폴더 밖 접근 가능 [변경]
AI 도구가 작업 폴더 밖의 파일을 읽을 수 있습니다.

› 기술 정보
```

The value of the `기본 AI` row (or explicit `기본으로 설정됨` where needed for disambiguation) describes `main_ai.current`, not every Work's worker. A redundant selected badge is unnecessary in the default overview. C16 orchestration can choose another eligible worker; actual Work details own the observed execution identity. Do not advertise all tasks as running through the default route.

The default page has no general setup tutorial. When nothing is selected, the `기본 AI` row shows `선택된 AI 없음`, one short instruction and `AI 선택`. Optional unused providers do not create global warnings. An attention state for the selected route remains visible with its repair action.

With no Main AI, do not mark Judgment AI as waiting if an independently configured/effective route still exists. Project its own observed state.

Judgment AI help: `요청에 맞는 AI와 도구를 고르고 결과를 확인합니다.` Keep its configured mode and actual effective route distinguishable. Show `기본 AI 따라가기` only as the preference when its effective state is still fallback/checking; show the actual fallback/destination alongside that preference. Preserve the existing `대화 해석` navigation/help association where relied upon; changing the short visible heading does not authorize semantic routing changes.

`상태 확인` is an explicit check, not a monitoring subscription. Put the last check time in details unless freshness or a failure makes it relevant to the decision. An unknown runtime model stays `CLI 기본값` or `모델 확인 안 됨`; never substitute a plausible model name.

## 6. State projection contract

Configuration, authentication/verification and execution are separate dimensions. These are view projections of existing API fields, not new stored lifecycle states. A selected item may need attention. Use text with colour; neutral selection must not masquerade as a green health check.

| Existing evidence | Owner-visible wording / action | Forbidden implication |
| --- | --- | --- |
| No `main_ai.current` | `선택된 AI 없음`; `AI 선택` | Global system failure |
| Recognized `main_ai.current` | `기본으로 설정됨`; `변경` | Currently executing or qualified for every task |
| Subscription `installed=false` | `설치 확인 필요`; show existing installation/login guidance in its editor | Automatically install or switch engines |
| `login.state=signed-in` | `로그인 확인됨`; optional last checked time | A model task succeeded |
| `signed-out` | `로그인 필요`; `로그인 설정` | Token storage is authentication |
| `unchecked`, `unknown`, `token-saved` | Respectively `로그인 확인 전`, `로그인 상태 확인 필요`, `토큰 저장됨 · 로그인 확인 전` | `사용 가능` inferred from selection |
| `sidecar` | `실행 환경에서 인증 관리` | A fresh local login probe ran |
| API `key.saved=true`, not verified | `키 저장됨 · 연결 확인 전` | Ready or selected |
| API `key.pending=true` | `새 키 적용 전`; explain old active configuration remains until successful application | New stored key already active |
| Current API `last_check.state=ok`, `model_ready=true`, matching active configuration | `연결 확인됨` | Live performance or every tool verified |
| Failed/stale/missing verification or selected route missing from list | `확인 필요` with specific available reason and repair; retain configured identity | Automatic fallback or guessed healthy state |
| Judgment `effective.state=checking` | `판단 AI 확인 중`; existing cancellation when offered | Whole AI setup failed or already switched |
| Judgment `effective.state=fallback` | `대체 AI 사용 설정` plus actual model/destination and reason | Preference to follow equals effective use |
| Judgment `active`, `off`, `attention` | `확인됨`, `사용 안 함`, `확인 필요`, tied to actual effective data | A completed Work or hidden fallback |
| State endpoint unreachable | `상태를 불러오지 못했습니다`; mark retained values as last known | Assert the AI/provider itself is disconnected |

Evidence precedence: material failure/unknown freshness must remain visible; next show verification; keep configuration identity throughout. Older successful checks must not erase a newer explicit failure or pending credential replacement. `last_check` describes the current route; `route.check` is the candidate's recorded check. Do not apply one route's evidence to another. If the current response cannot establish matching identity/freshness, show the honest unverified state instead of adding a backend field for this UI iteration.

Capability summaries use existing `agency.search/browser` data. Present availability as capability exposure, not a proven completed search/browser task. Keep material restrictions visible beside the selected candidate; put repeated implementation notes in details. Do not promise available browser tools in unsupported profiles/platforms.

## 7. Change chooser and account editing

One native modal owns the change flow. Provider rows are stable: subscription `Codex`, `Claude Code`; API `OpenAI`, `Anthropic`, `OpenRouter`, subject to the existing response. Do not sort by readiness, selected state or perceived quality.

```text
기본 AI 변경

구독
  (●) Codex          로그인 확인됨       현재 기본 AI
  ( ) Claude Code    로그인 확인 전       [로그인 설정]
API
  ( ) OpenAI         키 저장됨            [계정 설정]
  ( ) Anthropic      키 없음              [키 입력]
  ( ) OpenRouter     키 없음              [계정 설정]

선택한 AI의 모델     [CLI 기본값                  ]
전송 대상           OpenAI
판단 AI             기본 AI를 따르며 별도 확인 예정
선택한 AI의 제한     <해당할 때 짧게 표시>

                                    [취소] [확인하고 사용]
```

This is a layout example. Readiness/eligibility still comes from current contracts; an ineligible radio stays disabled and its setup action stays operable. Display a reason, not an unexplained grey control.

### Selection and models

- Radio/label area changes only the draft selection. Row account actions never select the row through event bubbling. Use semantic labels and buttons instead of a clickable generic container as the only selection mechanism.
- Show one model editor below the list for the draft route. Reuse cached model suggestions when present; no model-list fetch on page entry or selection. Keep manual entry where the existing provider contract allows it; do not fabricate an available-model catalogue.
- For CLI defaults, show `CLI 기본값` and a short explanation that the actual model is determined at execution. Move config-file mechanics to details. Respect `model_selectable=false`; disclose any model-clearing consequence before applying exactly as the existing API requires.
- Footer names the transmission destination and Judgment AI consequence before application. A separately configured Judgment AI remains explicitly separate. A follow-mode check is asynchronous and can retain an observed fallback; do not promise an immediate successful switch.

### Account setup

- A per-row `계정 설정`, `로그인 설정` or `키 입력` button opens one account panel directly below that row. At most one account editor is expanded; no nested modal. Keep the provider name and an explicit panel close/cancel action.
- Move key replacement/removal and Claude token management into that panel. Saved credentials display presence/date, never their value. Keep OpenRouter's existing connect/resume action within its panel.
- Preserve unfinished input and focus across normal refresh. Before switching away from a dirty credential panel, offer an inline discard/cancel choice; never silently lose the input. Do not persist secret drafts in local storage, URLs, logs or screenshots.
- `키 저장` and token save are immediate, explicit credential operations. Their success does not activate an AI. Say `키를 저장했습니다. 기본 AI는 아직 바뀌지 않았습니다.` The outer `취소` cancels the route draft; it does not undo previously completed credential changes, and the success message must make that scope clear.
- Deletion stays a separate explicit confirmation with its existing consequence. Removing a credential never silently selects a different AI. Disconnection, credential deletion and retained-data deletion keep their different meanings.

### Apply, failure and dismissal

- `확인하고 사용` reuses the existing activation request and validation; disable duplicate submits while pending. Selection or credential save alone cannot invoke activation.
- On failed activation, retain the effective configuration, chosen draft, editable model and an actionable inline error. Focus the error or relevant field without losing the user's place. Unknown errors have a plain summary and existing redacted details.
- On Main AI success, show the updated Main AI even if Judgment AI remains checking/fallback/attention. Report the two outcomes separately. Retain existing follow qualification and cancellation controls.
- `Escape`/cancel closes an idle modal and returns focus to its opener. Dirty drafts use one inline discard decision in the same modal. Completed saves are not reversed. During activation, a dismiss action is labelled `닫기`, with notice that the request continues; do not describe dismissal as cancelling a server mutation. The resulting state/notice must still appear after refresh. A late response must not overwrite a newer draft in a reopened dialog; associate completion with its originating UI request.
- Use the existing backend outcome to settle uncertainty after a lost response. Do not issue a duplicate mutation as a visual retry, or claim failure means the server could not have applied a change.

## 8. Execution environment, help and other settings

The owner-facing row is `파일 접근 범위`, visible when applicable. Map `trusted-local` to `작업 폴더 밖 접근 가능`, verified `strict-isolated` to `작업 폴더로 제한`, stale verification to `격리 다시 확인 필요`, and unknown profile to `접근 범위 확인 필요`. Raw profile names belong in technical details. These labels describe observed access conditions, not a security endorsement or blanket unrestricted file permission. A short truthful consequence is mandatory even with details collapsed: trusted-local AI tools may read host files outside the managed work folder. Strict isolation and stale/unknown verification have distinct summaries; blocked execution and its recovery action stay visible.

`변경` expands profile choices within the same page using current isolation actions. Exact versions, probe output and raw `limitation` go in `기술 정보`. Choosing a trust profile continues to require its existing verification and explicit action. Hiding the profile's effect or relaxing isolation to simplify setup is outside scope.

Prefer short inline help or a native disclosure for multi-sentence explanations. A tooltip is optional for a short definition only: it must work with keyboard focus, be dismissible and have a touch-accessible equivalent. Never put required login instructions, transmission destinations, permission consequences, validation errors or interactive controls only in a hover tooltip. The APG tooltip pattern is still marked work in progress; it is not a reason to build a custom tooltip subsystem.

Apply the row grammar to existing settings without replacing their workflows:

| Existing area | Change to presentation | Preserve |
| --- | --- | --- |
| Files/storage | Distinct reference-folder and output-folder rows; summarize read/write meaning before opening editor | Scope, original files, existing picker/path fallback, unsaved folder draft, optional projects |
| Telegram | Current pairing/connection first, token entry only on setup/change | Pairing, local secret handling, pending steps and disconnect confirmation |
| Google connections | Service name, observed status and one management entry; show revocation uncertainty | Existing preview/confirmation, local disconnect versus remote revocation semantics |
| Search providers | Availability and opt-in/key state, credential actions on demand | Model chooses the search path; key storage alone does not guarantee success |
| Browser sessions | Platform availability and saved site sessions; contextual login action | Existing login limitation, session/credential boundary, deletion scope |
| Privacy/current context | Visible collection/sharing switch and short scope/retention statement | Collection, retention, approvals and deletion rules; temporary context versus Memory |
| Diagnostics | Collapsed activity/developer details after ordinary controls | Redaction, discoverability, observed events and retained evidence |
| Work/activity | Regression audit for result-first presentation and consistent status wording | Current chronology, typed relations, exact items, failures and unknown effects |

Work/activity receives only consistency fixes demonstrated by the audit. This plan does not add a new conversational surface or rewrite history presentation.

## 9. Responsive, accessibility and localization contract

- Desktop modal target: existing 640px width with viewport margins. Use a header/body/footer grid, one scrollable body with `min-height:0`, and a footer outside its scrolling content. No fixed overlay covering the last field. At 620px and below use the existing full-height dialog pattern with dynamic viewport units and safe-area padding.
- At desktop reference size 1280×800, the configured AI summary and change action are visible without scrolling. The five-row chooser's collapsed route list and footer are visible at default zoom; expanded account details may scroll.
- At 390×844 and 320 CSS px width, no page-level horizontal scrolling, clipped action label or inaccessible control. At 200% zoom and an effective 320px width, wrap/reflow rather than shrink. Test short landscape height and the virtual keyboard before claiming mobile completion.
- Use labelled native radios, associated helper/error text and a titled native modal. Preserve keyboard entry, arrow selection, Tab traversal and return focus. Existing settings tabs keep their arrow/Home/End behavior and URL state.
- Errors are textual and associated with their fields. Use a restrained polite status region for async feedback; polling must not repeatedly announce unchanged state. Honour reduced motion; no decorative entrance animation is required.
- Keep visible focus unobscured. Verify text/control contrast against the applicable WCAG criteria; this specification is not a conformance certification. Project touch targets are 44px; the WCAG 2.2 minimum target guidance is 24 CSS px subject to its stated exceptions.
- Preserve the existing language picker as a visible sidebar-footer preference (responsive top-row placement is allowed). Keep `language-select`, `welcome-language`, `data-language-select`, `LANGUAGES`, `storedLanguage`, `setLanguage`, `translateStatic`, and the existing `agentos-language` persistence/default behavior. Keep authenticated logout reachable when applicable. Choosing a simpler shell must not remove existing preferences or auth actions.
- Ship changed copy in Korean, English, Japanese and Chinese together using existing dictionaries. Preserve placeholders, provider/model identifiers and locale-aware dates. Use long localized strings in layout evidence. No change to the current default-language policy.

## 10. Implementation mapping and protected contracts

| Change | Existing implementation to adapt | Boundary |
| --- | --- | --- |
| AI state projection | `app.js`: `mainAiView`, `judgmentView`, `effectiveJudgmentText`, `mainAiRoutes` | Derive only from existing `main_ai`, `decision_route`, `model_ready`, subscription execution data |
| Overview composition | `renderExecutionConnection`, `settingsRow`, `settingsDisclosure`; `index.html` AI panel | Split long text into view metadata/disclosures; preserve item and feedback IDs |
| Chooser and one account panel | `openAiChooser`, `chooserRow`, `renderAiChooser`, `chooserKeyForm`, `claudeTokenForm`, `aiChoice`, `aiKeyEditing`, `aiKeyRemoving`, `aiModelDraft` | Local draft/panel state only; no parallel persisted configuration |
| Apply/check/recovery | `applyAiChoice`, `checkMainAi`, `followMainAi`, `cancelJudgmentCheck`, `openJudgmentChooser`, `renderDecisionRoute` | Retain existing validation and async outcome semantics |
| Focus/polling | `rememberFocus`, `restoreFocus`, `focusKey`, `refresh` and existing fingerprints/dirty guards | Refresh must not rebuild an active editor and lose input/caret/disclosure state |
| Other settings | `renderFileWorkspace`/`paintFileWorkspace`, `renderTelegram`, `renderConnectors`, `renderSearchProviders`, `renderBrowser`, `renderContext`, `renderCurrentContext`, `renderDiagnostics` | Recompose existing controls only; preserved server mutations |
| Layout/copy | `style.css` tokens, `.settings-*`, `.ai-route-*`, `.chooser-*`, `.dialog-*`; existing I18N dictionaries in `app.js` | Consolidate affected rules rather than stacking contradictory overrides |

Existing endpoints include `/api/main-ai/check`, `/api/main-ai/activate`, `/api/main-ai/key`, `/api/subscription-engines/login-status`, `/api/subscription-engines/isolation` and `/api/decision-route/activate`. Keep their request/response meanings, secret mediation, pending-key semantics, model restrictions and failure behavior. Preserve the existing Claude token and OpenRouter transports as well; no new endpoint is implied.

`main_ai.py`, `decision_routes.py`, runtime orchestration and authority enforcement are read-only references for this plan. Missing backend support is a recorded limitation and separately scoped issue, not permission to manufacture a positive status in JS. Opening Settings, choosing a radio, expanding details and navigation must invoke no model, CLI login probe, qualification job or external provider request. Existing local state refresh remains allowed.

## 11. Acceptance and evidence

Each criterion requires an artifact at the implementation revision, not merely an issue marked closed. Fixture evidence is sufficient to verify UI state/interaction; it never proves live provider operation.

| ID | Observable acceptance | Required evidence |
| --- | --- | --- |
| A01 | Configured and unconfigured overview keep stable titles; current route/model/action are immediately identifiable | Desktop screenshots of both synthetic states; source-to-screen build identification |
| A02 | Every state row in section 6 projects without false healthy/active claims | Focused table-driven projection checks, including unknown login, pending key, failed check and unavailable route |
| A03 | Five provider rows keep fixed ordering; at most one account editor; only one selected-model field | Screenshot plus route selection/setup walkthrough |
| A04 | Opening/selection performs no activation or provider probe; save and activation remain separate | Request-spy interaction evidence using injected transports |
| A05 | Failed activation keeps prior configuration; Main AI success with Judgment AI checking/fallback is represented honestly | Existing server regression cases plus UI response fixtures |
| A06 | Input, caret, model draft, selection, disclosure and error survive refresh; stale completion does not alter a new draft | Browser walkthrough with refresh and delayed responses |
| A07 | Cancel/close/discard and credential save/delete have the stated different consequences | Keyboard/pointer walkthrough; no real secrets or credential mutation |
| A08 | Access implications and blocking isolation errors remain visible; long technical evidence is available on demand | Trusted-local, strict, stale and unknown screenshots; unchanged isolation regressions |
| A09 | Dialog/tab/radio keyboard behavior, focus restoration, labels and errors are accessible; all four language choices remain reachable and the production language preference survives reload | Keyboard walkthrough, accessibility-tree inspection; no blanket certification claim |
| A10 | No clipped fields/actions or horizontal page overflow across required sizes/locales | Matched desktop/mobile/zoom/short-height screenshots, keyboard check |
| A11 | Other settings retain data/action distinctions and existing Work/history access | Targeted walkthrough for changed surfaces and existing relevant regressions |
| A12 | UI rollback and local deployed revision are identifiable; all required CI passes on the merge candidate | PR checks, commit/revert boundary, local startup/static-asset provenance when operated |

Reuse `tests/test_settings_ui.py`, `tests/test_ui_quality.py` and `tests/test_main_ai_routes.py`; inspect their cases before adding tests. Extend behavior-level coverage for genuinely new interactions/state mappings. Do not add tests that merely count CSS declarations or freeze incidental markup. Use injected transports, fake states and temporary stores. No routine paid/live model check or full Cartesian browser/provider matrix. Run affected checks during development and the repository's required CI on a stable head; broaden on a concrete failure or shared-contract concern.

Public evidence uses synthetic configuration and redacted data. Preserve owner screenshots outside the repository. A prototype is design evidence; the running application is local UI evidence; provider authentication and real external work are separate evidence classes.

## 12. Owner-activated implementation units and order

Owner activation #780 selects this finite sequence (#781–#784). Each unit needs a branch from fresh main, exclusive shared frontend ownership, and its own acceptance mapping; its predecessor must merge first. Specification delivery alone did not activate them.

| Order | Proposed unit | Deliverable / acceptance | Dependencies and ownership |
| --- | --- | --- | --- |
| 1 | UX-PREF-01: truthful AI overview | Sections 5–6 and isolation summary; A01, A02, A08 | Own AI projection/composition, affected copy and focused tests |
| 2 | UX-PREF-02: compact change flow | Section 7, account/model panel and explicit save/apply; A03–A07 | After 1; exclusive ownership of chooser/form functions and shared UI files |
| 3 | UX-PREF-03: consistent settings rows | Section 8, changed surface by surface; A11 | After shared AI grammar settles; preserve file/connection/privacy semantics |
| 4 | UX-PREF-04: integrated visual acceptance | Cross-surface layout, locale, keyboard and viewport acceptance; A09, A10, A12 | Integrate 1–3; fix demonstrated defects and reconcile changed wording in Presence/local web guidance |

Responsive, accessibility and interaction checks are part of every unit; unit 4 is integrated convergence, not permission to postpone basic accessibility. A unit is small enough to review/revert when its state rules, screen composition and regression evidence can be assessed together. Split unit 3 by pane if its diff becomes difficult to review.

This specification proposes presentation refinements to the older `AI 연결`, `판단 AI (대화 해석)` and `현재 사용 중` wording. In the implementation unit that changes a label, update the corresponding current guidance in Presence/local web instructions and UI design notes; retain historical records as history. Unit 4 audits this consistency rather than leaving contradictory instructions until closeout. None of these terminology changes modifies the two AI roles or their server contracts.

Parallel work is useful for read-only fixture inventory, copy/accessibility review or acceptance preparation. Do not run competing writers on `app.js`, `style.css`, `index.html` or the same UI tests. If delegation is used, record exclusive file ownership and requested/accepted/observed model settings. Inspect GitHub and refresh main before each unit, including any still-active overlapping work; issue #708's old mention is not proof of present ownership.

## 13. Delivery, rollout and rollback

Specification acceptance means the two documents and plan entry are reviewable and required checks pass. It does not mean any screenshot defect is fixed. The documentation issue closes only for those deliverables and the separately requested design prototype. The owner subsequently requested: no logo, one system-settings-style sidebar, independent AI roles, plain file-access wording and restored language selection. Those decisions are included here; the earlier subordinate-card wording is superseded for this proposal only.

For implementation, retain the existing backend and persistence formats. Commit each coherent unit separately. Before local acceptance, identify the served checkout/revision and static assets, then reload the existing route. If a long-running process serves old assets, restart only the intended app instance through its normal mechanism and preserve owner data. A stale screenshot is neither implementation evidence nor a reason to dismiss the user's observation. Keep build identifiers in development evidence rather than adding repository workflow controls to the product.

Rollback an implemented unit by reverting its UI commit/PR through the normal branch/check workflow, accounting for later dependent UI changes. There is no proposed data migration. Reverting UI cannot restore a credential the owner deleted or reverse a completed external operation; retain those existing consequence/confirmation contracts. Recheck the rendered revision after rollback.

Report three distinct facts at closeout: what implementation merged; which build/state was actually observed in the local application; whether the owner accepted the experience. No merge, green check or static mockup substitutes for the last two.

## 14. References and interpretation

Checked 2026-09-28. External guidance supports the interaction choices; dimensions, copy and work units above are AgentOS design decisions.

- [NN/g — Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/): defer infrequent options while keeping necessary decisions discoverable. Applied to account/technical panels; not a justification to hide material access effects.
- [WAI-ARIA APG — Modal Dialog](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/): modal focus and keyboard expectations.
- [WAI-ARIA APG — Radio Group](https://www.w3.org/WAI/ARIA/apg/patterns/radio/): single selection and keyboard behavior; prefer native inputs.
- [WAI-ARIA APG — Tooltip](https://www.w3.org/WAI/ARIA/apg/patterns/tooltip/): limited explanatory use; its work-in-progress status is explicit.
- [WHATWG — Interactive elements](https://html.spec.whatwg.org/multipage/interactive-elements.html): native dialog and disclosure semantics.
- [WCAG 2.2 — Reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html) and [Target Size (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html): reference criteria; project targets above do not establish full WCAG conformance.
- [Radix introduction](https://www.radix-ui.com/primitives/docs/overview/introduction), [repository](https://github.com/radix-ui/primitives), [releases](https://github.com/radix-ui/primitives/releases), [MIT licence](https://github.com/radix-ui/primitives/blob/main/LICENSE): considered candidate, not adopted.
- Repository review aids: [frontend-design](../../.claude/skills/frontend-design/SKILL.md) and [pinned web-interface-guidelines](../../.claude/skills/web-interface-guidelines/SKILL.md).

## 15. Interactive prototype and observed design evidence

Open [the self-contained prototype](settings-ux-renewal-preview.html). The preview toolbar selects configured/unconfigured/login-needed/checking/fallback examples. The sidebar selects existing settings panes and the language control demonstrates Korean, English, Japanese and Simplified Chinese. The AI chooser demonstrates fixed ordering and one account panel. Credential inputs are readonly sample values. No API transport, credentials, external request, storage write or production file is used; CSP blocks connections and form submissions. Language changes here are in memory only and do not touch the real app's preference.

The prototype illustrates layout and selected interactions; it does not implement the production verification/activation/cancellation pipeline, full credential lifecycle, dirty-state recovery, or all locale strings in sample feedback. Sidebar screens use fictional folder/session values. Product acceptance A01–A12 remains future work.

Captured design states: [overview](settings-ux-renewal-preview/overview.png), [chooser](settings-ux-renewal-preview/chooser.png), [account panel](settings-ux-renewal-preview/account.png), [mobile](settings-ux-renewal-preview/mobile.png). These are prototype screenshots, not shipped UI screenshots. Browser observations cover these layouts, language selection, sidebar changes, modal Escape/focus return, and 320px reflow. They do not establish full accessibility or production conformance.
