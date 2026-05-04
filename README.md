# AgentOS

**A bootable, headless-first OS prototype with an agent-managed post-boot runtime.**

AgentOS explores what an operating system looks like when the default post-boot
interface is not a desktop full of apps, but a managed agent runtime.

Boot the image, reach the AgentOS operator surface, configure a local or online
LLM path, and experiment with requests entering through TTY, Telegram, and
runtime command surfaces. The prototype routes intent, runs local tools, replies
when configured, and leaves proof/log artifacts behind.

This is a **public prototype**, not a production AI OS distribution.

## What Is AgentOS?

AgentOS is an experimental OS-native agent runtime. It is built around one
question:

> What if the operating system boots into an agent operator surface instead of a
> traditional desktop?

Modern operating systems still assume a human manually opens apps, copies data
between them, and coordinates the workflow. AgentOS experiments with a different
default: after boot, an agent runtime becomes the operator surface and
coordinates capabilities such as status, workspace inspection, web access, LLM
setup, Telegram setup, and proof logging.

The intended demo is the bootable image. Running `python3 src/main.py` from the
repo is a developer shortcut for exercising some of the same runtime surfaces
without booting the OS image.

## Demo Idea

The small proof loop looks like this:

```text
Boot a tiny AgentOS VM
-> reach the terminal-first AgentOS operator surface
-> configure LLM / Telegram runtime settings
-> send a request through TTY or Telegram
-> classify the request intent
-> run the matching capability or tool
-> reply and record proof/log events
```

Example requests for the prototype:

```text
status
search AgentOS roadmap and summarize it
workspace 파일 목록 보여줘
```

Telegram and web-based setup paths can carry UTF-8 text. Direct multilingual TTY
input polish is still a Phase 2/i18n usability target.

## What Works Now

Phase 1 proves a narrow but real OS-native loop:

- Bootable AgentOS ISO prototype for local VM experimentation.
- Headless-first, terminal operator surface on boot.
- Full-screen Bubble Tea/Lip Gloss operator TUI.
- Agent and shell modes:
  - Agent mode: talk to AgentOS.
  - Shell mode: run Linux commands directly.
  - `% <command>`: run one Linux command from agent mode.
- Runtime readiness display for LLM, Telegram, Web, workspace, IP, and state.
- Bundled local Ollama path with `smollm2:135m-instruct-q5_K_M` as the tiny baseline model.
- LLM setup surface for local Ollama or OpenAI/Codex-style provider configuration.
- OpenAI/Codex path is pinned to `gpt-4o-mini` in the prototype.
- Telegram setup page and QR-oriented setup flow.
- Telegram receive/reply experiments when configured.
- Intent dispatch for greetings, status, search-style requests, and workspace-oriented requests.
- Human-readable activity feed hooks.
- Proof/log artifacts under the workspace, including `artifacts/os_events.jsonl`.
- `agentos-kernelctl` command surfaces for status, guided operator, workflow status, setup, activity, and intent dispatch.

## Quick Start

Booting the ISO shows the actual AgentOS concept; running from the repo is the
fastest developer shortcut.

### Concept Demo: Boot The OS Image

Build a local ISO:

```bash
git clone git@github.com:Jongtae/agentos.git
cd agentos
./scripts/build_latest_agentos_iso.sh
```

Generated images are written under:

```text
build-output/release/
```

For Apple Silicon local testing, use the ARM64 image and a Linux VM in UTM:

1. Install [UTM](https://mac.getutm.app/).
2. Create a Linux VM using ARM64 virtualization.
3. Attach the generated AgentOS ARM64 ISO.
4. Boot the VM.
5. Expect the AgentOS terminal operator surface.

Expected boot flow:

```text
Boot
-> AgentOS TTY/operator surface
-> managed agent runtime
-> LLM / Telegram / Web readiness
-> AgentOS prompt and command shortcuts
```

Notes:

- ISO build/remaster work may require host tooling and elevated permissions.
- Generated ISOs, `build-output/`, runtime workspaces, and artifacts are ignored by Git.
- Do not bake personal API keys or Telegram tokens into an ISO.

### Developer Shortcut: Run From Repo

Use this path when you want to inspect or develop the runtime without booting a
VM:

```bash
git clone git@github.com:Jongtae/agentos.git
cd agentos
cp .env.example .env
python3 src/main.py --doctor
python3 src/main.py --no-tui
```

Inspect the same runtime surfaces directly:

```bash
./scripts/agentos-kernelctl status --json
./scripts/agentos-kernelctl guided-operator --workspace ./workspaces/default --json
./scripts/agentos-kernelctl workflow-status --workspace ./workspaces/default --json
./scripts/agentos-kernelctl activity-feed --workspace ./workspaces/default --json
```

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
Tools and surfaces
  - LLM provider status
  - workspace/files
  - web access
  - Telegram setup/reply
  - proof/activity log
  |
  v
Reply + proof log
```

Important entrypoints:

- `cmd/agentos-operator-tui/` - full-screen terminal operator frontend
- `scripts/agentos-kernelctl` - main runtime command surface
- `scripts/kernel_intent_dispatch.py` - intent dispatch surface
- `scripts/kernel_activity_feed.py` - activity feed surface
- `scripts/kernel_llm_setup.py` - LLM setup surface
- `scripts/kernel_telegram_setup.py` - Telegram setup surface
- `src/kernel/event_fabric/` - event/proof substrate

## Commands / Operator Surface

Inside the AgentOS TUI:

```text
/help              show examples and shortcuts
/status            show human-readable runtime status
/mode agent        talk to AgentOS normally
/mode shell        type Linux commands directly
/setup llm         open the LLM setup page / QR flow
/engine ollama     force bundled local Ollama
/engine codex      select OpenAI/Codex path using gpt-4o-mini
/setup telegram    open the Telegram setup page / QR flow
/test telegram     manual Telegram drain/fallback receive-send check
/power             show restart/reboot/shutdown options
/clear             clear the visible activity area
% <command>        run one Linux command from agent mode
```

The TUI is the product-facing surface. Raw Python commands are mostly developer
shortcuts.

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

The current proof surfaces are prototype-grade. Phase 2 will make the activity
feed more reliable, more readable, and more central to the operator UI.

## Roadmap

Phase 1 is closed as a public prototype.

Near-term Phase 2 focus:

- productized first-run setup
- reliable always-on Telegram receiver/reply loop
- clearer setup completion feedback
- richer operator activity narration
- lifecycle controls for restart, reboot, shutdown, and service recovery
- friendlier error recovery
- acceptance-driven demo flow
- i18n usability, including better direct TTY multilingual input

Future tracks:

- broader app/message adapters
- stronger local models
- installer distribution
- verified boot, attestation, updater hardening
- production credential/security model

## Limitations

AgentOS is not yet:

- a production desktop OS
- a secure multi-user OS
- a Linux, macOS, or ChromeOS replacement
- a fully autonomous OS
- a polished consumer installer
- a production Telegram automation platform

Known prototype limitations:

- GUI is not the primary interface.
- Telegram support exists, but the product-grade always-on loop is Phase 2 work.
- Setup UX still needs polish for non-technical users.
- Direct TTY multilingual input is not yet a polished experience.
- Credential handling is secret-free in the repo, but the production runtime security model is still evolving.
- Gmail, Drive, Calendar, and broader app adapters are future work unless explicitly implemented in a branch.

## Security And Secrets

AgentOS keeps public code and public images secret-free.

Never commit:

- `.env`
- Telegram bot tokens
- OpenAI or other provider API keys
- generated ISO artifacts
- runtime workspace artifacts containing local state
- real conversation logs

Runtime setup should write user-provided secrets to local runtime env files, not
to committed artifacts.

Common runtime variables:

```bash
OPENAI_API_KEY=...
AGENTOS_TELEGRAM_BOT_TOKEN=...
AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS=...
```

## Contributing

Useful early contribution areas:

- TUI usability and activity feed presentation
- command router and intent dispatch rules
- workspace/file tools
- web-access reliability
- i18n and Korean/English examples
- VM boot testing across UTM/QEMU platforms
- docs and reproducible demo scripts

See `AGENTS.md` for the repository workflow.

## License

MIT. See `LICENSE`.
