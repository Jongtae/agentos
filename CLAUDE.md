# Personal AgentOS — Claude Code thin bootstrap

@AGENTS.md
@docs/development-constitution.en.md

The imported files are the canonical repository execution contract and Development Constitution. This file is intentionally short: it is a Claude Code compatibility/bootstrap entrypoint, not an independent source of policy. Apply the canonical **Reuse first: Adopt → Adapt → Build** and Existing Solutions Review rules from those files rather than restating them here.

1. Read `AGENTS.md` before broad repository or GitHub inspection.
2. Follow `docs/goal-execution-contract.en.md` and the active program contract referenced by the delivery plan.
3. Read `next_goal` in `delivery-plan.yaml` before selecting anything. Only an explicit owner `active` transition authorises execution.
4. **If no top-level goal is active — `next_goal.id` is `null`, or its status is not `active` — no work is selected. Stop and report that.** Do not infer one from open issues, open PRs, trackers, a closed program's records, or this file. Open is not active: see *Autonomous goal execution* in `AGENTS.md`.
5. If a goal is active, follow `docs/goal-execution-contract.en.md` and that program's own contract, including whatever resume source that program defines. A program may define one; a completed program has none, and this file does not supply a substitute.
6. Follow the repository verification budget: targeted tests while editing, batched remediation, coherent checkpoint pushes, stable-head CI/review, no duplicate review/polling.
7. If any tool-specific instruction conflicts with `AGENTS.md` or the Development Constitution, canonical repository governance wins.
8. Do not duplicate canonical governance in this file.
