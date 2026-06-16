# AgentOS Next Roadmap

Status: Phase 2 closeout recorded

## Phase 1 Closed

Phase 1 is closed as:

> AgentOS OS-native agent runtime prototype

Phase 1 established the shape of AgentOS:

- terminal-first operator surface
- bundled local LLM baseline
- `agentos-kernelctl` capability and proof surfaces
- Telegram setup/reply experiments
- intent-aware dispatch direction
- activity-feed substrate for “AgentOS narrates its work”
- local ARM64 ISO build and VM experimentation path

Phase 1 is not a production-ready operating system release. It is the proof that the OS-native agent runtime direction is worth productizing.

## Phase 2 Goal

Phase 2 should turn the prototype into a local-first Codex runtime loop:

```text
local or booted AgentOS runtime
-> configure local-first runtime adapters
-> receive a user prompt
-> classify intent
-> run a bounded capability
-> narrate progress
-> store user-visible records
-> reply or recover clearly
```

The detailed Phase 2 roadmap is tracked in
`docs/roadmap/phase2-local-first-runtime-loop.md`.

## Phase 2 Priority Work

1. **Golden runtime loop acceptance**
   - Define the repeatable proof before broad implementation.
   - Cover setup, prompt intake, intent classification, capability dispatch, activity narration, records, reply, and recovery.
   - Detailed acceptance is tracked in `docs/acceptance/phase2-golden-runtime-loop.md`.

2. **Docker runtime preview**
   - Docker should be a developer/demo runtime preview, not the product target.
   - It should prove the runtime loop without claiming boot, installer, VM recovery, or ISO freshness proof.

3. **User-owned runtime data**
   - Shared folders and bind mounts should expose user-owned records, outputs, logs, diagnostics, and acceptance artifacts.
   - Secrets must stay outside plaintext shared user data.

4. **Intent classification contract**
   - Prompt intent classification should be a runtime contract before capability dispatch.
   - Low-confidence, destructive, external-send, or lifecycle-changing requests should require clarification or confirmation.

5. **Everyday work capabilities**
   - Prove bounded AgentOS status/recovery, workspace files, web/search, and Gmail read/search/summarize/draft flows.
   - Calendar should begin read-only if it fits the Phase 2 slice.

6. **Activity feed, records, and recovery**
   - Every request should show received, classified, running, completed, replied, or failed.
   - Raw JSON and parser traces should be hidden behind logs.
   - Records/retrieval should be framed as a searchable user-owned work archive, not a complete second brain.

## Later Tracks

- live Gmail OAuth read/search/draft observed proof after manual acceptance pack
- VM/ISO observed proof for boot, recovery, and managed Codex session rejoin after preflight
- calendar read-only live adapter candidate after fixture-backed contract
- verified boot and hardware attestation
- updater hardening
- broader app/inbox ecosystem
- richer browser fallback
- distribution packaging
- public preview operations

## Active Completion Epics

- No active completion epic is currently open. The next automation pass should
  re-check this roadmap, the open GitHub issue state, and the Later Tracks
  before creating a new milestone-backed epic.

## Completed Completion Epics

- `verified-boot-attestation-proof-boundary-epic` — [EPIC: Verified boot and attestation proof boundary](https://github.com/Jongtae/agentos/issues/125)
  - Milestone: Phase 2: Local-first Codex runtime loop
  - Completion goal: define the AgentOS verified boot and attestation proof boundary so Secure Boot, TPM measured boot, event logs, PCR evidence, and Linux runtime integrity signals become explicit future proof surfaces without falsely claiming hardware-backed trust today.
  - Exit condition: completed by `docs/architecture/verified-boot-attestation-proof-boundary.md`, `scripts/smoke_verified_boot_attestation_boundary.sh`, golden runner integration through `scripts/phase2_golden_demo_runner.py`, and `phase2-run --message "status"` attaching `agentos-verified-boot-attestation-nonclaim.v1` while keeping Secure Boot, TPM measured boot, PCR/event-log, IMA, and hardware attestation proof unclaimed.
  - Closed issue: #125.
  - Completed tasks: P2-58, P2-59, and P2-60.
  - Residual blocker: real Secure Boot, TPM measured boot, PCR/event-log, Linux IMA, and hardware-backed attestation proof remain unclaimed until observed VM or hardware evidence exists.
  - Advances: runtime proof truthfulness, OS-native runtime defaults, recovery, capability ownership.

- `inbox-capability-ownership-boundary-epic` — [EPIC: Inbox capability ownership boundary](https://github.com/Jongtae/agentos/issues/116)
  - Milestone: Phase 2: Local-first Codex runtime loop
  - Completion goal: define the inbox capability ownership boundary so Gmail, Calendar, Maildir, fixture, and future inbox-like adapters converge through an OS-native, read-first, user-owned intake substrate.
  - Exit condition: completed by `docs/architecture/inbox-capability-ownership-boundary.md`, `scripts/smoke_inbox_capability_ownership_boundary.sh`, golden runner integration through `scripts/phase2_golden_demo_runner.py`, and `phase2-run --message "status"` attaching the inbox routing/ownership contract artifact while keeping live inbox OAuth and mutation proof unclaimed.
  - Closed issue: #116.
  - Completed tasks: P2-54, P2-55, P2-56, and P2-57.
  - Residual blocker: live Gmail, Calendar, and broader inbox OAuth proof remain unclaimed until explicit tester credentials and observed read-only runs exist; external send/delete/archive mutations remain blocked until a later confirmation model exists.
  - Advances: capability ownership, mediation cost reduction, OS-native runtime defaults, runtime proof truthfulness.

- `distribution-packaging-proof-boundary-epic` — [EPIC: Distribution packaging proof boundary](https://github.com/Jongtae/agentos/issues/107)
  - Milestone: Phase 2: Local-first Codex runtime loop
  - Completion goal: define the distribution packaging proof boundary for safe local checks, release artifact requirements, signing/checksum expectations, VM/ISO blockers, and explicit non-claims.
  - Exit condition: completed by `docs/operations/distribution-packaging-proof-boundary.md`, `scripts/smoke_distribution_packaging_boundary.sh`, `scripts/release_manifest_checksum_preflight.py`, `scripts/smoke_release_manifest_checksum_preflight.sh`, and golden runner integration through `scripts/phase2_golden_demo_runner.py`.
  - Closed issue: #107.
  - Completed tasks: P2-50, P2-51, and P2-52.
  - Residual blocker: real release artifacts, signing/checksum publication, installer readiness, and observed VM/ISO proof remain unclaimed until maintainers provide artifacts and a VM run is observed.
  - Advances: runtime proof truthfulness, distribution packaging, OS-native runtime defaults.

- `public-preview-operations-epic` — [EPIC: Public preview operations](https://github.com/Jongtae/agentos/issues/100)
  - Milestone: Phase 2: Local-first Codex runtime loop
  - Completion goal: define the public preview operating contract for Docker/local runtime testing, manual proof blockers, release non-claims, and safe preview promotion.
  - Exit condition: completed by `docs/operations/public-preview-operations.md`, `scripts/smoke_public_preview_operations.sh`, and golden runner integration through `scripts/phase2_golden_demo_runner.py`.
  - Closed issue: #100.
  - Completed tasks: P2-47 and P2-48.
  - Residual blocker: live Gmail, Calendar, Telegram, browser, updater, VM/ISO, and release distribution proof remain unclaimed until observed with explicit tester input or release evidence.
  - Advances: runtime proof truthfulness, public preview operations, mediation cost reduction, OS-native runtime defaults.

- `browser-fallback-capability-boundary-epic` — [EPIC: Browser fallback capability boundary](https://github.com/Jongtae/agentos/issues/89)
  - Milestone: Phase 2: Local-first Codex runtime loop
  - Completion goal: define when browser automation is allowed as a fallback and how AgentOS moves common web/app access patterns toward internal, OS-native capabilities.
  - Exit condition: completed by the documented and smoke-tested `agentos-phase2-browser-fallback-contract.v1`, plus `phase2-run` integration that records browser fallback artifacts while keeping live browser proof unclaimed.
  - Closed issue: #89.
  - Completed tasks: P2-43 and P2-45.
  - Residual blocker: observed live browser fallback proof remains unclaimed until a separate user-approved browser acceptance run exists; repeated web/app patterns should graduate into internal capabilities before broad browser dependence.
  - Advances: mediation cost reduction, capability ownership, OS-native runtime defaults, runtime proof truthfulness.

- `capability-permission-boundary-epic` — [EPIC: Capability permission boundary](https://github.com/Jongtae/agentos/issues/66)
  - Milestone: Phase 2: Local-first Codex runtime loop
  - Completion goal: define how AgentOS declares, approves, denies, narrates, and records OS-native capability access before expanding live adapters.
  - Exit condition: completed by contract docs, public registry, smoke-enforced outcomes, `phase2-run` output, and user-owned records across P2-33 through P2-36.
  - Closed issue: #66.
  - Advances: capability ownership, OS-native runtime defaults, runtime proof truthfulness.

- `updater-hardening-epic` — [EPIC: Updater hardening](https://github.com/Jongtae/agentos/issues/80)
  - Milestone: Phase 2: Local-first Codex runtime loop
  - Completion goal: define the updater hardening path that preserves managed runtime continuity and truthful rollback/recovery proof.
  - Exit condition: completed by `agentos-phase2-updater-state.v1`, focused updater state smoke, `phase2-run` lifecycle integration, and explicit live-updater/VM proof blockers across P2-39 through P2-40.
  - Closed issue: #80.
  - Residual blocker: live updater, reboot, rollback, and VM/ISO proof remain unclaimed until an observed VM/live-updater acceptance run records them.
  - Advances: OS-native runtime defaults, recovery, runtime proof truthfulness.

## Autonomous Completion Loop

The recurring completion loop should protect the current runtime proof and also
move AgentOS toward completion. It runs every 15 minutes and starts by comparing
README, PRD, TASKS, this roadmap, and GitHub issue/milestone state before
choosing work.

- keep validating only when no safe forward-progress task exists
- create or continue a milestone-backed epic when the roadmap has a real gap
- open the next small issue for a safe completion track inside that epic
- when no safe task candidate exists, promote an uncovered Later Track or
  README completion track into a missing-epic candidate before falling back to
  status-only validation
- record an explicit blocker when the next proof needs credentials, a VM, or
  external state
- hand off when the loop is misaligned with the runtime-first product direction

Every epic must define:

- the milestone it advances
- the completion goal
- the validation plan
- the exit condition
- the rule for deciding whether to continue follow-up work or return to the
  roadmap for the next epic

If roadmap changes require product or architecture judgment, the loop should
research primary or credible external sources, summarize the evidence, and
translate that evidence into milestone, epic, and exit-condition changes before
implementation begins.

Heavy smoke checks should not become the product motion. ISO smoke is limited
to at most once per calendar day unless ISO/build code changed or a maintainer
explicitly requests it.

The direction judge must not claim live Gmail OAuth or VM/ISO proof unless those
runs are actually observed.

## Current Source Of Truth

- `README.md`
- `PRD.md`
- `TASKS.md`
- repo-local private context when present
- `docs/index.md`
- `docs/acceptance/phase2-golden-runtime-loop.md`
- `docs/acceptance/docker-runtime-preview.md`
- `docs/roadmap/phase2-local-first-runtime-loop.md`
- `docs/reference/phase1-agentos-prototype-closeout-v1.md`
- `docs/reference/phase2-local-first-runtime-loop-closeout-v1.md`
