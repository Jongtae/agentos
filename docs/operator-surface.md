# Operator Surface

The AgentOS TUI is the product-facing surface. Raw Python commands are mostly
developer shortcuts.

## Core Commands

Inside the AgentOS TUI:

```text
/help              show examples and shortcuts
/status            show human-readable runtime status
/mode agent        talk to AgentOS normally
/mode shell        type Linux commands directly
/setup llm         open the LLM setup page / QR flow
/engine ollama     force bundled local Ollama
/setup telegram    open the Telegram setup page / QR flow
/test telegram     manual Telegram drain/fallback receive-send check
/power             show restart/reboot/shutdown options
/clear             clear the visible activity area
% <command>        run one Linux command from agent mode
```

## Modes

Agent mode is for talking to AgentOS. Shell mode is for running Linux commands
directly.

Use `% <command>` when you want to run one Linux command without leaving agent
mode.

## Setup Surfaces

`/setup llm` and `/setup telegram` should guide the user through runtime setup
without committing secrets to the repo or ISO.

Secrets belong in local runtime configuration, not in source control, generated
artifacts, screenshots, or public proof logs.

## Proof Logs

AgentOS is proof-first. A request should leave a trace:

```text
request received
-> intent classified
-> capability started
-> capability completed or failed
-> reply sent or surfaced to the operator
```

Typical workspace paths:

```text
/home/ubuntu/agentos-ws/artifacts/os_events.jsonl
/home/ubuntu/agentos-ws/artifacts/
```

From a repo checkout:

```bash
./scripts/agentos-kernelctl activity-feed --workspace ./workspaces/default --json
```
