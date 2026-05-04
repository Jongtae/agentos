# AgentOS Next Roadmap

Status: Current

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

Phase 2 should turn the prototype into a coherent product loop:

```text
boot AgentOS
-> configure LLM and Telegram
-> receive a user request
-> understand intent
-> run the right capability
-> show progress in the TUI
-> reply or recover clearly
```

## Phase 2 Priority Work

1. **Productized first-run setup**
   - LLM setup and Telegram setup should feel like one guided flow.
   - Setup completion must be visible in the setup page, TUI, and runtime status.

2. **Always-on Telegram runtime**
   - Telegram should not require a manual “test” command for normal operation.
   - The TUI should show receiver state, last request, last reply, and failure reason.

3. **Operator activity feed**
   - Every request should show: received, understood, planned, running, completed, replied, or failed.
   - Raw JSON and parser traces should be hidden behind logs.

4. **Lifecycle and recovery**
   - Add clear controls for restarting AgentOS services, rebooting, shutting down, and recovery/rejoin.
   - Dangerous actions should require explicit commands.

5. **Golden demo acceptance**
   - A repeatable demo should cover `/start`, greeting, status, web search, workspace/file request, and a controlled failure path.

## Later Tracks

- verified boot and hardware attestation
- updater hardening
- broader app/inbox ecosystem
- richer browser fallback
- distribution packaging
- public preview operations

## Current Source Of Truth

- `README.md`
- `PRD.md`
- `TASKS.md`
- `.codex/context.md`
- `docs/index.md`
- `docs/reference/phase1-agentos-prototype-closeout-v1.md`
