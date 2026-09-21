# Personal AgentOS — Claude Code thin bootstrap

@AGENTS.md
@docs/development-constitution.en.md

The imported files are the canonical repository execution contract and Development Constitution. This file is intentionally short: it is a Claude Code compatibility/bootstrap entrypoint, not an independent source of policy. Apply the canonical **Reuse first: Adopt → Adapt → Build** and Existing Solutions Review rules from those files rather than restating them here.

1. Read `AGENTS.md` before broad repository or GitHub inspection.
2. Follow `docs/goal-execution-contract.en.md` and the active program contract referenced by the delivery plan.
3. For EPIC-PA1 / #386, read the execution cursor comment marked `<!-- agentos-execution-cursor:v1 -->` first.
4. Verify only the cursor's current main SHA, governing contract SHAs, and referenced PR/head/state needed for the next action.
5. Read only that issue/PR and its actionable evidence. Do not reread every PA1 issue, PR, CI history, review thread or tracker while the cursor remains consistent.
6. Perform full reconciliation only for the anomaly triggers in `docs/execution-cursor.en.md`.
7. Follow the repository verification budget: targeted tests while editing, batched remediation, coherent checkpoint pushes, stable-head CI/review, no duplicate review/polling.
8. After a meaningful state transition, update the same #386 cursor comment and increment its generation. Do not append a new cursor history comment.
9. The cursor is a cache, never authority. Current GitHub/repository evidence wins on conflict.
10. If any tool-specific instruction conflicts with `AGENTS.md` or the Development Constitution, canonical repository governance wins.
11. Do not duplicate canonical governance in this file.
