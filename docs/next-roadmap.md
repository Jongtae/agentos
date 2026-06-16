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

## Autonomous Completion Loop

The recurring completion loop should protect the current runtime proof and also
move AgentOS toward completion. It runs every 15 minutes and starts by comparing
README, PRD, TASKS, this roadmap, and GitHub issue/milestone state before
choosing work.

- keep validating only when no safe forward-progress task exists
- create or continue a milestone-backed epic when the roadmap has a real gap
- open the next small issue for a safe completion track inside that epic
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
- `docs/roadmap/phase2-local-first-runtime-loop.md`
- `docs/reference/phase1-agentos-prototype-closeout-v1.md`
- `docs/reference/phase2-local-first-runtime-loop-closeout-v1.md`
