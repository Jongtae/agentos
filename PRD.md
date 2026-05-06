# AgentOS Product Requirements

Status: Current

## Vision

AgentOS is an AI-native operating system prototype where the primary user interaction is a managed agent runtime, not a traditional desktop application stack.

The product direction is:

```text
Human intent
-> AgentOS runtime
-> OS-native capabilities
-> narrated execution
-> result or recovery
```

## Phase 1 Status

Phase 1 is complete as a public prototype.

It proves:

- AgentOS can boot into a terminal-first operator surface.
- A bundled local LLM path can provide baseline interaction.
- Runtime and capability surfaces are exposed through `agentos-kernelctl`.
- Telegram setup/reply experiments can connect external conversation to AgentOS work.
- Intent dispatch and activity events provide the substrate for operator-visible execution.
- Local ISO build/remaster paths can package the prototype for VM experimentation.

It does not claim:

- production-ready Telegram automation
- polished consumer setup
- full installer/distribution readiness
- verified boot or hardware attestation
- full app ecosystem replacement

## Product Requirements

### Runtime-first operation

AgentOS must keep the managed agent runtime as the default path. Visual or appliance-like polish only counts when it strengthens runtime reachability, supervision, continuity, capability ownership, or proof.

### Secret-free public image

Public source and public images must not contain personal credentials. LLM keys and Telegram tokens are runtime configuration.

### Operator-visible work

AgentOS should narrate its work in human-readable form:

- request received
- intent understood
- capability started
- capability completed or failed
- reply sent or recovery suggested

### Native capability ownership

Common work should move toward OS-native capability surfaces before relying on app-mediated automation. Browser and external app automation remain fallback paths, not the default product identity.

### Local-first user ownership

AgentOS should keep user records, generated artifacts, exported logs, diagnostics, and retrieval-ready work history under user-owned local storage by default. External services and hosted providers are explicit adapters, not hidden defaults.

Secrets and provider credentials must be separated from shared user data.

## Phase 2 Requirements

Phase 2 should make the prototype feel coherent as a local-first Codex runtime loop:

- golden runtime loop acceptance before broad implementation
- Docker developer/demo runtime preview without reframing Docker as the product target
- user-owned runtime data boundary for shared records, artifacts, logs, diagnostics, and acceptance outputs
- prompt intent classification contract before capability dispatch
- guided setup state for local LLM, Telegram, and explicit external adapters
- bounded everyday-work capabilities including AgentOS status/recovery, workspace files, web/search, and Gmail read/search/summarize/draft
- activity feed and records output reliability
- lifecycle controls for restart, reboot, shutdown, and recovery
- friendly errors instead of raw JSON/parser traces
- acceptance-driven demo flow for common requests

## Validation

Prototype validation should include:

- targeted unit tests and smoke checks
- secret/artifact hygiene checks
- ISO asset/build contract checks
- runtime setup and operator TUI smoke checks
- cleanup of temp and build artifacts before closeout

## References

- `README.md`
- `TASKS.md`
- `docs/index.md`
- `docs/next-roadmap.md`
- `docs/acceptance/phase2-golden-runtime-loop.md`
- `docs/roadmap/phase2-local-first-runtime-loop.md`
- `docs/reference/phase1-agentos-prototype-closeout-v1.md`
- `AGENTS.md`
