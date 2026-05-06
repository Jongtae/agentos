# AgentOS Tasks

Status: Current
Owner: Autonomous Codex implementation loop

## Active Execution State

Current parent branch:

- `main`

Current public milestone:

- **Phase 2 opened** — Local-first Codex runtime loop

Current task:

- `[P2-16] Add lifecycle recovery acceptance surface`

Runtime impact statement:

- This task gives Phase 2 a truthful lifecycle/recovery acceptance surface so restart/rejoin-style requests can be planned, confirmed, and blocked without pretending destructive controls ran.

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

Phase 2 should productize the local-first runtime loop that Phase 1 exposed:

```text
local or booted AgentOS runtime
-> configure local-first runtime adapters
-> receive a user prompt
-> classify intent
-> run a bounded capability
-> narrate progress
-> store user-visible records
-> reply or fail with clear recovery guidance
```

Recommended Phase 2 tasks:

- Golden runtime loop acceptance.
- Docker developer/demo runtime preview boundary.
- User-owned runtime data boundary for shared records, outputs, logs, diagnostics, and acceptance artifacts.
- Intent classification contract and eval set.
- Productized first-run setup state model.
- Gmail read/search/summarize/draft capability boundary.
- Activity feed, records output, lifecycle controls, and recovery.
- Acceptance-driven golden demo: `/start`, greeting, status, web search, workspace request, Gmail draft, and failure recovery.

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
- repo-local private context when present
- `docs/index.md`
- `docs/next-roadmap.md`
- `docs/architecture/docker-runtime-preview-boundary.md`
- `docs/architecture/intent-classification-contract.md`
- `docs/architecture/user-owned-runtime-data-boundary.md`
- `docs/acceptance/phase2-golden-runtime-loop.md`
- `docs/acceptance/phase2-intent-eval.json`
- `docs/roadmap/phase2-local-first-runtime-loop.md`
