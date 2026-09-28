# UX-PREF-06 configuration summary evidence

Issue #809. Production HTML/CSS/JS served by the local synthetic fixture at port 18789. This is frontend implementation evidence, not an observation of owner accounts, available model names or live AI execution. The example model names are synthetic values supplied for the owner's requested hierarchy.

## Requirement audit

| Acceptance | Evidence |
| --- | --- |
| Main AI provider and model together | First `ai-summary` row uses `mainAiView` configured title/model; main effort is labelled CLI default or not separately configured, because the Main route has no persisted effort field. No invented medium. |
| Judgment model, effort and relationship together | Effective transport/model plus matching active engine/provider and effort. Follow describes shared subscription/account and a separately selected judgment model. Missing/stale/mismatched values do not imply successful following. |
| Effective fallback remains truthful | Focused tests and fallback screenshot show the fallback model without the previous Codex engine or low effort. Checking, off, explicit, missing effort and stale routes have focused regressions. |
| Preserve settings behavior | Existing status, destination, agency restrictions and action handlers retained; no API, persistence, model selection or authority changes. Existing chooser and draft regressions included. |
| Four locales and narrow width | Browser walkthrough checks all four locales at 1280×800 and 320×740, with document width equal to viewport width. Zero mutating API requests. |
| Delivery and rollback | Required exact-head checks and merge evidence live on the PR. Revert this presentation commit through normal PR/check workflow; no data migration or owner-state change. |

## Validation

- `python3 -m pytest -q tests/test_settings_ui.py tests/test_ui_quality.py tests/test_ai_connection_routes_ui.py`: **40 passed**.
- JavaScript syntax, whitespace, canonical documentation and execution specification checks passed.
- Browser result: ko/en/ja/zh-CN each document width 320; mutations 0.
- No provider login, model call or actual owner configuration was changed. Owner-local application at port 18787 is not claimed updated by this fixture evidence.

## Served asset identity

Compared byte-for-byte to the checkout after the final implementation change:

- `index.html`: `8ed6828ec581167db12fc6368cf7d1b110bd36e8fa2c8b886c39946e838256e2`
- `app.js`: `5ad7c7f6023ee3ec73b66493dc621a419f121a7d7b49716573acc38d484df47c`
- `style.css`: `0916ec7daf9d5218c5c9f961113862ffec81bbf0fcb966a33635e85ae210348c`

## Captures and reproduction

- Desktop: [Korean](809-ko.png), [English](809-en.png), [Japanese](809-ja.png), [Chinese](809-zh-CN.png).
- Narrow: [Korean](809-ko-mobile.png), [English](809-en-mobile.png), [Japanese](809-ja-mobile.png), [Chinese](809-zh-CN-mobile.png).
- [Fallback](809-fallback.png).

Start `python3 tests/web_management_browser_fixture.py --port 18789` and run [809-browser.js](809-browser.js) through Playwright CLI run-code. Use only the synthetic fixture, never owner data. It intercepts local read models and rejects/counts mutations. Captures are written to `output/playwright`.
