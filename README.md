# AgentOS

[English](README.md) | [한국어](README.ko.md) | [日本語](README.ja.md) | [中文](README.zh.md)

**A bootable, headless-first OS prototype where the post-boot interface is an agent runtime.**

AgentOS explores a different OS default: instead of opening apps manually after
boot, you enter an operator surface that can receive requests, route intent, run
tools, reply, and leave proof logs.

```text
Boot VM
  -> AgentOS operator TUI
  -> LLM / Telegram / Web readiness
  -> request from TTY or Telegram
  -> intent routing
  -> tool execution
  -> reply + proof log
```

This is a **public prototype**, not a production AI OS distribution.

## Demo Idea

Boot the ISO, reach the AgentOS TUI, then try a request such as:

```text
status
search AgentOS roadmap and summarize it
workspace 파일 목록 보여줘
```

The core proof is small but concrete:

- an external or local request enters the runtime
- AgentOS classifies the intent
- a runtime capability runs
- the operator gets a reply
- proof/activity events are written under the workspace

## What Works Now

- Bootable ARM64 VM prototype for local experimentation.
- Terminal-first AgentOS operator TUI.
- Agent and shell modes for talking to AgentOS or running Linux commands.
- Bundled local Ollama baseline with `smollm2:135m-instruct-q5_K_M`.
- LLM and Telegram setup surfaces.
- Intent routing for greetings, status, search, and workspace-oriented requests.
- Activity/proof log hooks such as `artifacts/os_events.jsonl`.

## Quick Start

Booting the ISO shows the actual AgentOS concept. Running from the repo is the
fastest developer shortcut.

### Concept Demo: Boot The OS Image

```bash
git clone git@github.com:Jongtae/agentos.git
cd agentos
./scripts/build_latest_agentos_iso.sh
```

Then boot the generated ARM64 ISO in a Linux VM, such as UTM on Apple Silicon.

Expected boot flow:

```text
Boot
-> AgentOS TTY/operator surface
-> managed agent runtime
-> LLM / Telegram / Web readiness
-> AgentOS prompt and command shortcuts
```

Generated ISOs, `build-output/`, runtime workspaces, and artifacts are ignored
by Git. Do not bake personal API keys or Telegram tokens into an ISO.

For details, see [Getting Started](docs/getting-started.md).

### Developer Shortcut: Run From Repo

```bash
git clone git@github.com:Jongtae/agentos.git
cd agentos
cp .env.example .env
python3 src/main.py --doctor
python3 src/main.py --no-tui
```

You can also exercise runtime surfaces directly:

```bash
./scripts/agentos-kernelctl status --json
./scripts/agentos-kernelctl phase2-run --message "status"
./scripts/agentos-kernelctl phase2-run --message "draft a reply to my Gmail roadmap email"
./scripts/agentos-kernelctl gmail-setup --serve-http --host 0.0.0.0 --display-host <vm-ip>
./scripts/agentos-kernelctl gmail-status --json
./scripts/agentos-kernelctl gmail-read --query "roadmap" --json
./scripts/agentos-kernelctl phase2-run --gmail-live --message "summarize my latest Gmail roadmap email"
./scripts/agentos-kernelctl guided-operator --workspace ./workspaces/default --json
./scripts/agentos-kernelctl workflow-status --workspace ./workspaces/default --json
./scripts/agentos-kernelctl activity-feed --workspace ./workspaces/default --json
```

The Phase 2 CLI loop is local-first and safe to try without credentials. Gmail
uses fixture data by default. Live Gmail is read-only, uses Google's Desktop
OAuth flow, stores credentials at `~/.agentos/secrets/gmail/credentials.json`
and tokens at `~/.agentos/secrets/gmail/token.json`, and never writes secrets
to records, workspace artifacts, Docker bind records, or Git-tracked files.
Send, delete, archive, and Gmail draft mutation remain blocked.

## Operator Surface

Inside the AgentOS TUI:

```text
/status          show runtime status
/mode agent      talk to AgentOS
/mode shell      run Linux commands directly
/setup llm       configure the LLM path
/setup telegram  configure Telegram
/power           restart/reboot/shutdown menu
% <command>      run one Linux command from agent mode
```

See [Operator Surface](docs/operator-surface.md) for the fuller command map.

## Architecture

```text
Bootable OS image
  |
  v
AgentOS runtime
  |
  v
TTY / Telegram / setup page input
  |
  v
Command router / intent dispatcher
  |
  v
Tools: LLM, status, workspace, web, Telegram, proof log
  |
  v
Reply + proof log
```

See [Runtime Overview](docs/architecture/runtime-overview.md) for more detail.

## Roadmap

Phase 1 closed as a public prototype. Phase 2 focuses on:

- productized first-run setup
- reliable always-on Telegram receiver/reply loop
- clearer setup completion feedback
- richer operator activity narration
- lifecycle controls and friendlier recovery
- acceptance-driven demo flow

See [Next Roadmap](docs/next-roadmap.md).

## Limitations

AgentOS is not yet:

- a production desktop OS
- a secure multi-user OS
- a Linux, macOS, or ChromeOS replacement
- a polished consumer installer
- a production Telegram automation platform

GUI is not the primary interface. Credential handling is secret-free in the
repo, but the production runtime security model is still evolving.

## Security

Never commit:

- `.env`
- Telegram bot tokens
- OpenAI or other provider API keys
- generated ISO artifacts
- runtime workspace artifacts containing local state
- real conversation logs

See [Security Notes](docs/security.md).

## Contributing

Good early contribution areas:

- TUI usability and activity feed presentation
- command router and intent dispatch rules
- workspace/file tools
- web-access reliability
- i18n and Korean/English examples
- VM boot testing across UTM/QEMU

See [Contributing](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md).

## License

MIT. See [LICENSE](LICENSE).
