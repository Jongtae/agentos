# AgentOS Tasks

Status: Current
Owner: Autonomous Codex implementation loop

## Active Execution State

Current parent branch:

- `main`

Current public milestone:

- **Phase 1 closed** — AgentOS OS-native agent runtime prototype

Current task:

- `[P289-20] Phase 1 public prototype closeout and docs cleanup`

Runtime impact statement:

- This task closes Phase 1 truthfully as a public prototype, removes misleading active-task wording, and makes the repository understandable to outside readers without overstating product readiness.

## Phase 1 Closeout Truth

Phase 1 proves:

- AgentOS can boot into a terminal-first operator surface.
- A bundled local Ollama path can provide a baseline local LLM.
- AgentOS exposes runtime/capability surfaces through `agentos-kernelctl`.
- Telegram setup/reply experiments exist and are integrated with the OS-native workflow substrate.
- Intent dispatch and activity events establish the direction for “AgentOS narrates its work.”
- ISO build/remaster scripts exist for local ARM64 VM experimentation.

Phase 1 does not claim:

- production-ready Telegram automation
- polished first-run setup
- always-on receiver reliability
- user-friendly lifecycle/recovery flows
- verified boot or attestation
- public installer distribution
- broad app ecosystem support

## Current Public Artifacts

Keep in Git:

- source code
- scripts
- docs
- reference contracts
- runbooks
- lifecycle ledger
- `.env.example`
- `LICENSE`

Do not commit:

- `build-output/`
- generated ISOs
- remaster workdirs
- runtime `workspaces/*/artifacts/`
- `.env`
- personal tokens or API keys
- `.DS_Store`

## Phase 2 Recommended Work

Phase 2 should productize the loop that Phase 1 exposed:

```text
boot AgentOS
-> configure LLM and Telegram
-> receive a request
-> classify intent
-> run the correct capability
-> narrate the work in the operator TUI
-> reply or fail with clear recovery guidance
```

Recommended Phase 2 tasks:

- Productized first-run setup for LLM and Telegram.
- Always-on Telegram receiver/reply loop with clear TUI status.
- Setup completion feedback in the setup page, TUI, and Telegram reply.
- TUI scrollback, activity feed, and mode switching stabilization.
- Lifecycle menu for restarting AgentOS services, rebooting, shutting down, and recovering.
- Friendly error recovery that hides raw JSON/parser traces by default.
- Acceptance-driven golden demo: `/start`, greeting, status, web search, workspace request, and failure recovery.

## Validation Standards

Before closing a task:

- run targeted tests or smokes relevant to the change
- commit meaningful slices
- close the issue only after the completion commit exists
- merge into the correct parent branch
- delete completed child branches when safe
- run cleanup:

```bash
python3 scripts/cleanup_temp_artifacts.py --delete --json
python3 scripts/cleanup_build_artifacts.py --delete --json
```

## Source Companions

- `README.md`
- `PRD.md`
- `AGENTS.md`
- `.codex/context.md`
- `docs/index.md`
- `docs/next-roadmap.md`
