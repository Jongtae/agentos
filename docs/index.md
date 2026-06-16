# AgentOS Docs

Use this page as the public documentation map for the Phase 1 prototype export.
This public repo intentionally keeps only the current product truth and a compact
Phase 1 closeout note. Historical ledgers, runtime artifacts, local VM logs, and
large build outputs are not included.

## Start Here

- `README.md` - public project overview and quickstart
- `docs/getting-started.md` - ISO boot and repo-local developer shortcut
- `docs/operator-surface.md` - TUI commands, modes, setup surfaces, and proof logs
- `PRD.md` - product requirements and Phase 1 truth
- `TASKS.md` - current execution state and next work
- `docs/next-roadmap.md` - Phase 2 roadmap
- `AGENTS.md` - issue-first workflow for agents and contributors

## Current Product Docs

- `docs/architecture/runtime-overview.md` - boot/runtime/input/intent/tool/proof overview
- `docs/architecture/docker-runtime-preview-boundary.md` - Docker developer/demo proof boundary
- `docs/architecture/intent-classification-contract.md` - Phase 2 prompt intent contract
- `docs/architecture/capability-permission-boundary.md` - capability approval, denial, record, and recovery boundary
- `docs/architecture/capability-permission-registry.json` - seed permission declarations for Phase 2 capabilities
- `docs/architecture/calendar-readonly-capability-contract.md` - read-only Calendar fixture capability boundary
- `docs/architecture/updater-hardening-state-contract.md` - updater, rollback, recovery, and runtime rejoin state proof boundary
- `docs/architecture/user-owned-runtime-data-boundary.md` - local-first user data ownership boundary
- `docs/acceptance/docker-runtime-preview.md` - Docker-first runtime preview acceptance
- `docs/acceptance/phase2-golden-runtime-loop.md` - Phase 2 golden runtime loop acceptance
- `docs/acceptance/phase2-intent-eval.json` - seed prompt intent eval set
- `docs/acceptance/vm-iso-proof-preflight.md` - VM/ISO proof preflight and blocker contract
- `docs/acceptance/gmail-live-readonly-acceptance.md` - live Gmail read-only manual proof and blocker capture
- `docs/roadmap/phase2-local-first-runtime-loop.md` - Phase 2 local-first runtime loop roadmap
- `docs/reference/phase1-agentos-prototype-closeout-v1.md` - Phase 1 closeout and Phase 2 handoff
- `docs/reference/phase2-local-first-runtime-loop-closeout-v1.md` - Phase 2 proof and blocker closeout
- `docs/reference/docker-runtime-preview-closeout-v1.md` - Docker-first runtime preview closeout
- `docs/security.md` - public repo secret and artifact hygiene notes

## Public Export Policy

This export is intentionally secret-free:

- no Telegram bot token
- no OpenAI or other provider API key
- no generated ISO
- no runtime workspace artifact dump
- no local VM conversation log
- no private host temp or remaster directory

If you need the full historical development record, keep it in a private
workspace and publish only reviewed, sanitized slices.
