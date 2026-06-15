# AgentOS Tasks

Status: Current
Owner: Autonomous Codex implementation loop

## Active Execution State

Current parent branch:

- `main`

Current public milestone:

- **Phase 2 testable runtime loop** — Local-first Codex runtime loop

Current task:

- `[P2-29] Add Gmail live read-only manual acceptance pack`

Runtime impact statement:

- This task advances the next safe completion candidate from the roadmap direction judge by adding a Gmail live read-only manual acceptance pack that separates mock/blocker proof from real user-observed OAuth proof without exposing secrets.

Current autonomous hardening loop:

- A Codex heartbeat automation runs every five minutes against this thread.
- Each pass starts from the repo startup order, checks the active issue/branch state, runs the roadmap direction judge, runs high-signal Phase 2 and setup smokes, cleans temp/build artifacts, and opens the next small lifecycle issue when it finds either an actionable regression/state drift or a safe forward-progress candidate after stable repetition.
- A direction verdict of `accept_with_risk` means the loop may finish the current validation pass, but the next autonomous issue should move a project-completion track forward when that can be done without live credentials or unobserved VM proof.
- A direction verdict of `reject` means autonomous apply work should stop and hand off or open a repair issue before continuing.
- Recent manual passes confirmed Telegram setup/live receiver, terminal QR rendering, Gmail setup page, Phase 2 CLI, Gmail live-blocked recovery, golden demo, workflow status, ISO build smoke coverage, and cleanup policy before refreshing this task status.

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

- Gmail setup is exposed through `agentos-kernelctl gmail-setup --serve-http`; live Gmail remains read-only and requires explicit user OAuth credentials.
- Phase 2 closeout is recorded in `docs/reference/phase2-local-first-runtime-loop-closeout-v1.md`.
- Practical local/Docker-safe proof is aggregated by `scripts/smoke_phase2_golden_demo.sh`.
- Five-minute hardening is active as an operational loop that repeatedly validates Telegram setup/live receive, Gmail setup/live-blocked recovery, Phase 2 runtime CLI, golden demo, workflow status, ISO build smoke, and cleanup policy.
- Roadmap direction judging is part of that loop so stable Phase 2 validation can promote the next safe completion task instead of becoming the whole product motion.
- Calendar read-only now has a fixture-backed contract and smoke path; live Calendar OAuth remains future work until explicit credentials and adapter design exist.
- VM/ISO proof now has a preflight smoke and blocker contract; observed boot, reboot/recovery, and managed runtime rejoin still require a real VM run before signoff.
- Gmail live read-only proof now has a manual acceptance pack and blocker capture; automated smokes still avoid real user credentials.
- VM/ISO proof remains an explicit blocker until a VM run is observed and recorded.

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
- `docs/reference/phase2-local-first-runtime-loop-closeout-v1.md`
- `.agents/roadmap-direction-judge.md`
- `docs/architecture/calendar-readonly-capability-contract.md`
- `docs/acceptance/vm-iso-proof-preflight.md`
- `docs/acceptance/gmail-live-readonly-acceptance.md`
