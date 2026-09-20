# AgentOS Utility UI — historical prototype and current handoff

## Current decision: management-only local web (2026-09-20)

Read the [Local Web Management Contract](../../web-management-contract.en.md), [Korean summary](../../web-management-contract.ko.md), and implementation issue **#382 / WEB-ADMIN-01** before using any prototype in this folder. The design record remains #379 / PR #380.

The owner no longer wants the local web to continue conversations or mirror Telegram. Default destinations are **작업 현황 / 내 기록 / 설정**. Projects are optional secondary grouping. Telegram is the current conversation channel, while AgentOS retains history, memory, work, results and authority. This is a product decision and implementation specification, not already-shipped behavior or automatic Codex activation.

The new [CODEX_PROMPT.txt](CODEX_PROMPT.txt) replaces the earlier chat-first handoff. It directs a later owner-invoked coding session to the scoped issue, current main and the contract. Do not start a second preparation program, automatically activate #381 or silently merge overlapping settings PR #373.

## Historical visual study — not the current navigation specification

`prototype.html`, `utility.css`, and `utility.js` remain the original offline utility-v1 study. **Their conversation and top-level-project destinations are superseded.** Their synthetic model identities, instant stop behavior and simulated controls are not runtime capabilities. Opening this old prototype does not show the new management-only design.

The original full v1 brief is preserved at [the pre-supersession commit](https://github.com/Jongtae/personal-agentos/blob/30af263f10156ea572d2a39178cc7fecaa1a641e/docs/design/utility-v1/README.md). No original private owner screenshots or font files are stored here. The original prototype files are retained unchanged for comparison.

Patterns still useful when consistent with the new contract: compact neutral utility styling, aligned setting rows, one active pane, exact-draft test/apply, preserved form/search state and request list/detail. Rejected patterns: generic web composer/transcript as default, mandatory projects, marketing/dashboard panels and permanent onboarding.

## Evidence boundary

The prior proposal recorded nine offline Chromium interaction checks on synthetic state. Those are historical prototype checks, not new tests of the management-only contract, actual AgentOS polling, a real provider, a user study or current owner installation. This documentation update does not repeat or expand that evidence.

Implementation acceptance is A1-A8 in #382: actual navigation, task/results, route-state accuracy, draft survival, type-correct record actions, preserved Telegram/API/history and desktop/mobile browser evidence. Runtime code, private state, delivery-plan activation and provider configuration are not changed by this design record.
