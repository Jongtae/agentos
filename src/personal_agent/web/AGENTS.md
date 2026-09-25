# Local web contribution guidance

Read the root AGENTS.md and [Local Web Management Contract](../../../docs/web-management-contract.en.md) before changing this directory. Implementation work is tracked in #382 (WEB-ADMIN-01). These instructions record product direction, not an automatic task or runtime capability.

## Product boundary

- The default local web is an AgentOS management utility, not another messenger. Telegram is the current conversation channel; AgentOS remains channel-independent and owns history, work, memory, results and authority.
- Default destinations: 작업 현황, 설정 (#562 removed the generic 내 기록 browser; exact retained items open at `#item/<kind>/<id>` from the turn that recorded them or from the Settings pane that manages that type, chosen from typed Work data only). Settings: AI 연결, 파일 · 저장, 외부 연결, 개인정보 · 진단. One stable navigation and one visible pane; no below-chat expansion, duplicate menus or global transcript/composer by default.
- Projects are optional secondary grouping. Preserve project access and data; do not force a project/setup flow. No dashboard hero, mascot, model shop, permanent checklist, tip/support panel or empty agent marketplace.
- Preserve existing Telegram delivery, chat APIs, stored conversations, drafts, files, records and grants. Removing a visible chat view is not deletion or permission to break the execution backend.
- Task detail shows actual result/required action first, then observed events and optional redacted execution details. Original request context is task-scoped and explicitly expanded. Do not copy all Telegram messages or repository CI/heartbeat into product task progress.
- Show actual route-specific execution connections, not a single misleading API-only status. Preserve exact-draft test/apply and the working connection on failed/stale tests. No invented readiness/model identity or provider calls on page entry.
- Keep record types/actions distinct and preserve input, caret, search results, confirmations, selection and detail across polling/navigation. Help is brief and contextual; connected services show state/manage before credential forms.

## Delivery and review

Reuse current vanilla frontend and real backend contracts. #382 W0 reconciles the goal-ready delivery entry before implementation; this instruction file itself activates nothing. Coordinate the overlapping #372 / PR #373 settings branch. Do not run #381 or unrelated backlog items.

For component, form, accessibility and copy review of changed UI, apply the pinned checklists in [`.claude/skills/web-interface-guidelines/`](../../../.claude/skills/web-interface-guidelines/SKILL.md) and [`.claude/skills/frontend-design/`](../../../.claude/skills/frontend-design/SKILL.md) (any tool; provenance in [`.claude/skills/README.md`](../../../.claude/skills/README.md)). They are development aids subordinate to this file and the Presence Experience Contract.

Use browser-task evidence plus existing backend/channel regressions. Replace obsolete chat-presentation assertions only with coverage preserving history/API/Telegram semantics. Prototype images and canned status data are not working behavior. Keep owner screenshots, credentials and private payloads out of public evidence.

Ship small verified increments under existing repository checks. Review changed UX and actual authority deltas, not the entire security roadmap. Use the existing integration_pending handoff for external merge waits; never bypass protection, invent approval, poll unchanged state repeatedly or claim an unmerged implementation is complete.
