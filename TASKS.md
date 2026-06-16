# AgentOS Tasks

Status: Current
Owner: Autonomous Codex implementation loop

## Active Execution State

Current parent branch:

- `main`

Current public milestone:

- **Docker-first AgentOS runtime preview** — public try path for the local-first runtime loop

Current task:

- `[P2-34] Enforce capability permission outcomes in Phase 2 smokes`

Runtime impact statement:

- This task makes Phase 2 capability results carry smoke-verified permission levels, blocked outcomes, recovery hints, and secret-redaction proof before live adapter expansion.

Current autonomous completion loop:

- A Codex heartbeat automation runs every 15 minutes against this thread.
- Each pass starts from the repo startup order, compares README, PRD, TASKS, roadmap, and GitHub milestone/issue state, runs the roadmap direction judge, and decides whether to continue an epic, create a missing milestone-backed epic, or defer because a blocker requires user/external input.
- Every epic must declare a completion goal, roadmap milestone alignment, validation plan, and exit condition before implementation work proceeds.
- When the direction judge finds no safe task candidate, it should inspect uncovered completion tracks and propose the next missing epic candidate before falling back to lightweight status checks.
- Created epic candidates must be registered in the roadmap state before the loop chooses the next task, so repeated passes do not create duplicate epics.
- Roadmap changes that require product or architecture judgment should be backed by primary or credible external research before they become milestone, epic, or exit-condition updates.
- A direction verdict of `accept_with_risk` means the loop may finish lightweight validation, but should not repeat heavy smoke-only passes when no safe forward-progress candidate exists.
- A direction verdict of `reject` means autonomous apply work should stop and hand off or open a repair issue before continuing.
- ISO smoke is limited to at most once per calendar day unless ISO/build code changed or the user explicitly requests it.
- Live Gmail OAuth and observed VM/ISO proof remain explicit blockers until a tester provides credentials or a VM run can be observed and recorded.

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

- Docker preview is promoted as the primary public try path at `http://localhost:8787`.
- Gmail setup is exposed through `agentos-kernelctl gmail-setup --serve-http`; live Gmail remains read-only and requires explicit user OAuth credentials.
- Phase 2 closeout is recorded in `docs/reference/phase2-local-first-runtime-loop-closeout-v1.md`.
- Practical local/Docker-safe proof is aggregated by `scripts/smoke_phase2_golden_demo.sh`.
- A 15-minute roadmap-governed completion loop is active as an operational loop that compares source-of-truth docs, GitHub work state, and roadmap milestones before deciding whether to create or continue an epic.
- Roadmap direction judging is part of that loop so stable Phase 2 validation can promote the next safe completion task instead of becoming the whole product motion.
- Calendar read-only now has a fixture-backed contract and smoke path; live Calendar OAuth remains future work until explicit credentials and adapter design exist.
- VM/ISO proof now has a preflight smoke and blocker contract; observed boot, reboot/recovery, and managed runtime rejoin still require a real VM run before signoff.
- Gmail live read-only proof now has a manual acceptance pack and blocker capture; automated smokes still avoid real user credentials.
- VM/ISO proof remains an explicit blocker until a VM run is observed and recorded.
- Capability result smokes now enforce permission levels and blocked outcomes for safe local reads, missing external setup, and destructive unsupported requests.

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
- `docs/architecture/capability-permission-boundary.md`
- `docs/architecture/user-owned-runtime-data-boundary.md`
- `docs/acceptance/phase2-golden-runtime-loop.md`
- `docs/acceptance/docker-runtime-preview.md`
- `docs/acceptance/phase2-intent-eval.json`
- `docs/roadmap/phase2-local-first-runtime-loop.md`
- `docs/reference/phase2-local-first-runtime-loop-closeout-v1.md`
- `.agents/roadmap-direction-judge.md`
- `docs/architecture/calendar-readonly-capability-contract.md`
- `docs/acceptance/vm-iso-proof-preflight.md`
- `docs/acceptance/gmail-live-readonly-acceptance.md`
