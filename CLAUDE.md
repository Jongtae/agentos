# Personal AgentOS — Claude Code thin bootstrap

This file is intentionally short. Canonical repository governance lives elsewhere.

1. Read `AGENTS.md` before broad repository or GitHub inspection.
2. Follow `docs/goal-execution-contract.en.md` and the active program contract referenced by the delivery plan.
3. For EPIC-PA1 / #386, read the execution cursor comment marked `<!-- agentos-execution-cursor:v1 -->` first.
4. Verify only the cursor's current main SHA, governing contract SHAs, and referenced PR/head/state needed for the next action.
5. Read only that issue/PR and its actionable evidence. Do not reread every PA1 issue, PR, CI history, review thread or tracker while the cursor remains consistent.
6. Perform full reconciliation only for the anomaly triggers in `docs/execution-cursor.en.md`.
7. Follow the repository verification budget: targeted tests while editing, batched remediation, coherent checkpoint pushes, stable-head CI/review, no duplicate review/polling.
8. After a meaningful state transition, update the same #386 cursor comment and increment its generation. Do not append a new cursor history comment.
9. The cursor is a cache, never authority. Current GitHub/repository evidence wins on conflict.
10. Do not duplicate canonical governance in this file.
