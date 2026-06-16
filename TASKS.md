# AgentOS Tasks

Status: Current
Owner: Autonomous Codex implementation loop

## Active Execution State

Current parent branch:

- `main`

Current public milestone:

- **Docker-first AgentOS runtime preview** — public try path for the local-first runtime loop

Current task:

- `[P2-76] Define Calendar live adapter candidate boundary`

Runtime impact statement:

- This task defines the Calendar live read-only adapter candidate boundary so AgentOS can graduate repeated Calendar read/search/summarize requests toward an OS-native read-only adapter while preserving fixture/live separation, secret isolation, observed-proof requirements, and mutation blockers.

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
- `phase2-run` should expose permission level, outcome, recovery, and secret-redaction proof in JSON output and user-owned records.
- Capability permission declarations should be backed by `docs/architecture/capability-permission-registry.json`.
- The capability permission boundary epic is closed for this Phase 2 slice; future loops should return to the roadmap before selecting the next epic.
- The updater hardening epic is closed for this Phase 2 slice; future updater work should require an observed VM/live-updater proof issue before claiming reboot, rollback, or ISO behavior.
- The first updater hardening slice is `agentos-phase2-updater-state.v1`, which records ready, blocked, rollback-needed, and recovery-suggested states without running destructive updater actions.
- `phase2-run` lifecycle recovery should surface updater state artifacts for update, rollback, restart, and recovery prompts while keeping live updater and VM/ISO proof blocked until observed.
- The browser fallback capability boundary epic is closed for this Phase 2 slice; future browser fallback work should return to the roadmap and open a new task only when it adds observed fallback proof or graduates a repeated pattern into an internal AgentOS capability.
- The first browser fallback slice is `agentos-phase2-browser-fallback-contract.v1`, which classifies internal capability, allowed fallback, blocked external state, and capability graduation paths without launching a browser.
- `phase2-run` web/search requests should attach the browser fallback contract artifact and keep live browser proof unclaimed unless a separate observed browser acceptance run exists.
- The public preview operations epic is closed for this Phase 2 slice; future preview work should return to the roadmap and open a new task only when it adds observed proof, release packaging, or a new promotion decision surface.
- The first public preview operations slice is `docs/operations/public-preview-operations.md`, smoke-tested by `scripts/smoke_public_preview_operations.sh`.
- The public preview operations smoke is included in the Phase 2 golden demo runner so preview promotion gates remain part of practical local/Docker-safe proof.
- The distribution packaging proof boundary epic is closed for this Phase 2 slice; future distribution work should require real release artifacts, signing/checksum publication, or observed VM/ISO proof before claiming release readiness.
- The first distribution packaging slice is `docs/operations/distribution-packaging-proof-boundary.md`, smoke-tested by `scripts/smoke_distribution_packaging_boundary.sh`.
- Release manifest/checksum preflight is covered by `scripts/release_manifest_checksum_preflight.py` and `scripts/smoke_release_manifest_checksum_preflight.sh` without publishing or signing artifacts.
- The release manifest/checksum preflight smoke is included in the Phase 2 golden demo runner so packaging non-claims remain part of practical local/Docker-safe proof.
- The inbox capability ownership boundary epic is closed for this Phase 2 slice; future inbox work should require live read-only OAuth proof, observed Maildir/user data proof, or a later confirmed external mutation model before claiming broader inbox ecosystem support.
- The first inbox ownership slice is `docs/architecture/inbox-capability-ownership-boundary.md`, smoke-tested by `scripts/smoke_inbox_capability_ownership_boundary.sh`.
- The inbox ownership boundary smoke is included in the Phase 2 golden demo runner so inbox capability ownership remains part of practical local/Docker-safe proof.
- `phase2-run --message "status"` attaches the inbox routing/ownership contract artifact so inbox capability ownership is visible in the user-testable runtime status proof.
- The verified boot and attestation proof boundary epic is closed for this Phase 2 slice; future verified boot work should require observed VM or hardware evidence before claiming Secure Boot, TPM measured boot, PCR/event-log, IMA, or hardware attestation proof.
- The first verified boot slice is `docs/architecture/verified-boot-attestation-proof-boundary.md`, smoke-tested by `scripts/smoke_verified_boot_attestation_boundary.sh`.
- `phase2-run --message "status"` attaches the verified boot/attestation non-claim artifact so boot-chain trust proof remains visibly separate from local runtime proof.
- The observed proof intake and blocker handoff epic is closed for this Phase 2 slice; future observed-proof work should require actual sanitized observed records or a new proof promotion task before claiming live credential, VM/ISO, release, browser, or boot-chain proof.
- The first observed proof intake slice is `docs/architecture/observed-proof-intake-boundary.md`, smoke-tested by `scripts/smoke_observed_proof_intake_boundary.sh`.
- Observed proof intake must keep secrets out of repo/workspace records, require sanitized evidence before proof promotion, and preserve explicit blockers for live credentials, VM/ISO, release, browser, and boot-chain proof.
- Observed proof records now use `docs/architecture/observed-proof-intake-schema.json` and can be checked with `scripts/observed_proof_intake_validate.py`; `scripts/smoke_observed_proof_intake_validator.sh` covers valid, blocked, and secret-term rejection behavior.
- `phase2-run --message "status"` attaches `agentos-observed-proof-intake-status.v1` so observed proof intake readiness and missing observed-record blockers are visible in the user-testable runtime status output.
- The capability graduation registry epic is closed for this Phase 2 slice; future broader app/inbox work should choose a candidate from `docs/architecture/capability-graduation-registry.json` before expanding browser or external app mediation.
- Capability graduation must prefer internal AgentOS capabilities, keep browser/external app mediation non-default, preserve permission/data boundaries, and require observed proof before live claims.
- The Calendar read-only live adapter readiness epic is closed for this Phase 2 slice; future Calendar work should require explicit live OAuth adapter design, tester credentials, or a confirmed mutation model before claiming more than fixture-backed readiness.
- The Gmail read-only live readiness epic is closed for this Phase 2 slice; future Gmail work should require explicit tester OAuth credentials, observed read-only proof, or a later confirmed mutation model before claiming more than setup readiness.
- The VM/ISO observed proof status epic is closed for this Phase 2 slice; future VM/ISO work should require a real observed VM run, sanitized evidence, or a new release/boot proof promotion task before claiming boot, reboot/recovery, managed runtime rejoin, ISO freshness, or VM signoff.
- The Calendar live read-only acceptance epic is closed for this Phase 2 slice; future Calendar live work should require real tester OAuth evidence, a live read-only adapter run, or a new proof promotion task before claiming live account proof or Calendar mutations.
- The Calendar live adapter candidate epic is active; its first slice defines and smoke-tests the read-only live adapter boundary while preserving live OAuth, observed account proof, and create/update/delete/invite/cancel mutation blockers.

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
- `docs/architecture/capability-permission-registry.json`
- `docs/architecture/capability-graduation-registry.md`
- `docs/architecture/capability-graduation-registry.json`
- `docs/architecture/user-owned-runtime-data-boundary.md`
- `docs/architecture/verified-boot-attestation-proof-boundary.md`
- `docs/architecture/observed-proof-intake-boundary.md`
- `docs/architecture/observed-proof-intake-schema.json`
- `docs/acceptance/phase2-golden-runtime-loop.md`
- `docs/acceptance/docker-runtime-preview.md`
- `docs/acceptance/phase2-intent-eval.json`
- `docs/roadmap/phase2-local-first-runtime-loop.md`
- `docs/reference/phase2-local-first-runtime-loop-closeout-v1.md`
- `.agents/roadmap-direction-judge.md`
- `docs/architecture/calendar-readonly-capability-contract.md`
- `docs/architecture/calendar-live-adapter-candidate-boundary.md`
- `docs/architecture/inbox-capability-ownership-boundary.md`
- `docs/architecture/browser-fallback-capability-boundary.md`
- `docs/architecture/updater-hardening-state-contract.md`
- `docs/acceptance/vm-iso-proof-preflight.md`
- `docs/acceptance/gmail-live-readonly-acceptance.md`
- `docs/acceptance/calendar-live-readonly-acceptance.md`
