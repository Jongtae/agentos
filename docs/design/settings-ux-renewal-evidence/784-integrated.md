# UX-PREF-04 integrated acceptance

Issue #784, parent #780. This is production HTML/CSS/JS served from this checkout by `tests/web_management_browser_fixture.py`, with synthetic read models intercepted in a real Chromium browser. No owner credentials, live AI requests, provider login, or external account mutations were used. This is implementation/UI evidence, not live AI capability or owner acceptance.

## Requirement audit

| Acceptance | Evidence |
| --- | --- |
| A01 | Final configured and empty overview captures; stable Main AI/Judgment AI labels, current route and change action. |
| A02 | `test_settings_ui.py` and `test_ai_connection_routes_ui.py`: login/key/pending/failure/unknown state matrix. Finite numeric, strictly newer login evidence is required before superseding a failed check. |
| A03 | Fixed Codex/Claude Code/OpenAI/Anthropic/OpenRouter order, one contextual account editor and one selected-model editor in #782 and final chooser captures. |
| A04 | Final navigation/selection/locale walkthrough recorded zero mutating API requests. #782 separately records explicit key-save versus activation requests. |
| A05 | `test_main_ai_routes.py` and `test_decision_qualification_jobs.py`; #782 synthetic activation refusal retains dialog/model, successful Main AI activation reports Judgment separately. |
| A06 | #782 delayed-response and refresh browser walkthrough; #783 search/browser draft walkthrough; final Judgment DOM regressions retain actual inputs, caret and feedback, guard stale request completion, and disable retained controls when their capability contract changes. |
| A07 | Main AI Escape/cancel/dirty-discard and explicit secret operations covered in #782; Judgment close/reopen retains unfinished input, switching editor asks once before discard. |
| A08 | #781 isolation projection checks plus final known/unknown profile captures. Material access implication remains visible, technical evidence is disclosed; backend isolation is unchanged. |
| A09 | Four production language choices persist across reload. Authenticated logout and welcome-language remain reachable. Desktop tabs use Up/Down, mobile tabs Left/Right; Home/End, native radio arrows, Tab to footer, Escape and opener-focus return were exercised. Existing dictionaries/placeholder tests cover all four locales. |
| A10 | 1280×800 desktop, 390×844, 320×740, 640×400 and 844×390 real-browser viewports. Document width equals viewport width; modal footer remains within viewport. Four locales captured. 640×400 is the CSS reflow space of 1280×800 at 200%; it is not a claim of testing OS/browser zoom UI. No physical mobile virtual keyboard was available; mobile device/IME certification remains unclaimed. |
| A11 | #783 pane walkthrough, final substantive Work/result screenshot and exact retained Memory opening. `test_web_item_deep_links.py`, `test_truthful_terminal_result.py`, `test_ui_quality.py`, and `test_web_management_readiness.py` preserve typed records, truthful results, chronology and project/folder access. |
| A12 | Required exact-head CI and merge status are authoritative on the implementation PRs. Final served asset bytes were compared to this checkout; hashes below identify the capture revision. Each unit is independently revertible subject to later UI dependencies; no migration or backend change. |

## Scope and limitations

The owner-local application at port 18787 is not identified as updated by this evidence. Port 18789 serves the real implementation with synthetic state for repeatable inspection. The earlier standalone prototype at port 18788 is design evidence only. Owner acceptance of the final experience is still distinct from implementation completion.

The unit-1 screenshots are intermediate historical captures; their original evidence file's recorded hashes were updated after a wrapping adjustment. They must not be treated as exact final-source screenshots. The final captures here supersede them for build-matched layout evidence.

## Rollback

Revert the relevant implementation PR through the normal branch/check workflow, accounting for dependent later changes. UI rollback changes no stored data and cannot undo a credential deletion or completed external operation. Compare served assets again after rollback. No repository plan status mirror or scheduler goal change is needed.

## Validation results

- Focused settings/AI/Work/retained-item/backend regressions: **142 passed, 17 subtests passed**.
- Consolidated final async draft remediation: **38 focused tests passed** (decision UI, settings UI and UI quality).
- JavaScript syntax, diff whitespace, canonical documents and execution-spec verification passed.
- Sample token contrast ratios: body on white 17.46:1; muted text on grouped rows 5.39:1; selected/action white-on-blue 10.79:1; focus blue on white 5.01:1. These checks are not a WCAG conformance certification.

## Final served asset identity

Compared byte-for-byte to the running local fixture after the final source change:

- `index.html`: `8ed6828ec581167db12fc6368cf7d1b110bd36e8fa2c8b886c39946e838256e2`
- `app.js`: `782276d8504e0f955b55b7529f140e91448e0f48333da9d07b0a53c51d3ab448`
- `style.css`: `2547bdd6909c128f65ef6ca15270f30f178e5815fae26ea4a8557fa64c7ff4f8`

## Captures and reproduction

- Overview: [Korean](784-ko.png), [English](784-en.png), [Japanese](784-ja.png), [Chinese](784-zh-CN.png), [empty](784-empty.png).
- Main chooser: [Korean](784-ko-chooser.png), [English](784-en-chooser.png), [Japanese](784-ja-chooser.png), [Chinese](784-zh-CN-chooser.png).
- Reflow: [390×844](784-390x844.png), [320×740](784-320x740.png), [640×400](784-640x400.png), [844×390](784-844x390.png).
- States: [login unknown](784-unknown-login.png), [strict](784-strict.png), [stale](784-stale.png), [unknown access](784-unknown-access.png).
- Retained Judgment editor: [capture](784-judgment.png). Final browser assertion checks the focused input is within the scrolling body, above the separate footer.
- Existing surfaces: [substantive Work](784-work.png), [exact Memory item](784-item.png), [welcome languages](784-welcome.png).

Start only the synthetic fixture: `python3 tests/web_management_browser_fixture.py --port 18789`. In the Playwright CLI session, run the companion async scripts in this order: `784-judgment-browser.js`, `784-browser.js`, `784-states.js`, `784-records-browser.js`. They use synthetic input and local interceptors; do not repoint them at owner data. Captures are written to `output/playwright`. The Judgment walkthrough records one explicit intercepted credential save; the navigation/locale chooser walkthrough records zero mutations. Existing #782/#783 walkthroughs cover Main AI and other-settings mutation semantics.

## Consolidated review remediation

The #806 review identified an omitted saved-model field in the Judgment editor contract. Clean editors now rebase to the observed saved model while preserving field focus; dirty editors retain the original draft in a disabled fieldset until explicit reopening. The focused 38-test group passed after remediation, and the real-browser Judgment walkthrough exercised an independent saved-model change followed by a dirty draft conflict. All final captures were refreshed and served bytes compared again. This requires one post-remediation exact-head CI run; no authority boundary changed and no duplicate review was requested.
