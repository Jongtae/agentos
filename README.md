# AgentOS

AgentOS is an AI-native operating system prototype.

Instead of treating the agent as another app inside a traditional desktop, AgentOS explores a different default: the OS boots into a managed agent runtime, exposes local capabilities through kernel-style surfaces, and lets the operator talk to the system first.

Phase 1 proves the shape of that idea:

- bootable AgentOS ISO prototype
- terminal-first full-screen operator surface
- bundled local LLM path through Ollama
- setup surfaces for LLM and Telegram credentials
- Telegram request/reply experiments
- intent dispatch and human-readable activity events
- native document, web, inbox, and proof surfaces exposed through `agentos-kernelctl`

This repository is currently a **public prototype**, not a production distribution.

## Prototype Status

Phase 1 is closed as an OS-native agent runtime prototype.

What works today:

- AgentOS can boot into a terminal-first operator surface.
- A bundled local Ollama provider can run a tiny model for baseline interaction.
- `agentos-kernelctl` exposes runtime, capability, setup, and proof surfaces.
- Telegram setup/reply paths exist and are wired into the operator/runtime substrate.
- The operator TUI can show status, mode switching, shell escapes, and activity-oriented output.
- ISO remaster/build scripts exist for local ARM64 VM experimentation.

What is intentionally still Phase 2 work:

- setup UX is not yet polished enough for non-technical users
- Telegram receiving/replying needs a reliable always-on product loop
- lifecycle actions such as restart, reboot, shutdown, and recovery need a clearer product surface
- error recovery needs to be friendlier than current diagnostic output
- TUI history, activity narration, and setup completion feedback need product-quality refinement
- verified boot, attestation, updater hardening, and installer distribution are out of Phase 1 scope

## Quick Start

The fastest path is to run the prototype locally from the repo:

```bash
git clone git.com:Jongtae/agentos.git
cd agentos
cp .env.example .env
python3 src/main.py --doctor
python3 src/main.py --no-tui
```

For the operator/runtime surfaces:

```bash
./scripts/agentos-kernelctl status --json
./scripts/agentos-kernelctl guided-operator --workspace ./workspaces/default --json
./scripts/agentos-kernelctl workflow-status --workspace ./workspaces/default --json
```

## Build An ISO

Local ISO builds are supported for experimentation. Generated ISOs and remaster workdirs are intentionally ignored by Git.

```bash
./scripts/build_latest_agentos_iso.sh
```

Expected output is under:

```text
build-output/release/
```

Notes:

- Apple Silicon local VM testing should use the ARM64 ISO.
- The build/remaster path may require host tooling and, depending on the platform, elevated permissions.
- Do not commit generated ISOs, `build-output/`, or runtime artifacts.

## Run In UTM

For Apple Silicon:

1. Install [UTM](https://mac.getutm.app/).
2. Create a Linux VM using ARM64 virtualization.
3. Attach the generated AgentOS ARM64 ISO from `build-output/release/`.
4. Boot the VM.
5. Expect a terminal-first AgentOS operator surface.

The intended Phase 1 boot experience is:

```text
AgentOS TTY/operator surface
-> local LLM status
-> Telegram/LLM setup hints
-> AgentOS prompt and command shortcuts
```

## Configure LLM And Telegram

AgentOS keeps secrets out of the ISO and out of the repo.

Runtime setup should write user-provided secrets to local runtime env files, not to committed artifacts.

Common runtime variables:

```bash
OPENAI_API_KEY=...
AGENTOS_TELEGRAM_BOT_TOKEN=...
AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS=...
```

From inside AgentOS, use the operator surface or kernelctl setup commands:

```bash
agentos-kernelctl llm-setup --workspace /home/ubuntu/agentos-ws --json
agentos-kernelctl telegram-setup --workspace /home/ubuntu/agentos-ws --json
```

Telegram support is currently prototype-grade. Phase 2 will focus on making setup completion, always-on receiving, reply status, and recovery clear from the TUI.

## Architecture

AgentOS is organized around these ideas:

- **managed runtime first**: the visible OS surface exists to launch, supervise, and rejoin the agent runtime
- **capability substrate**: common actions such as document, web, inbox, and proof export are exposed as OS-native surfaces
- **intent dispatch**: requests should be understood before choosing a capability
- **activity narration**: the operator should see what the system received, understood, ran, and completed
- **secret-free images**: public ISOs should not bake personal credentials

Useful entrypoints:

- `src/` — runtime and kernel substrate code
- `scripts/agentos-kernelctl` — primary command surface
- `cmd/agentos-operator-tui/` — terminal operator frontend
- `docs/index.md` — documentation map
- `docs/reference/phase1-agentos-prototype-closeout-v1.md` — Phase 1 closeout truth

## Roadmap

Phase 1 is closed as a public prototype.

Phase 2 should productize the loop:

```text
boot AgentOS
-> configure LLM and Telegram with clear setup feedback
-> receive a user request
-> classify intent
-> run the right capability
-> narrate progress in the TUI
-> return a useful reply
-> recover clearly when something fails
```

Near-term Phase 2 focus:

- productized first-run setup
- always-on Telegram receiver/reply loop
- reliable operator activity feed
- lifecycle controls
- friendly error recovery
- acceptance-driven demo flow

## Security And Secrets

Never commit:

- `.env`
- Telegram bot tokens
- OpenAI or other provider API keys
- generated ISO artifacts
- runtime workspace artifacts containing local state

The repo ignores generated build and runtime paths by default.

## Contributing

See `AGENTS.md` for the repository workflow.

The short version:

- start from an issue
- create a matching branch
- commit meaningful slices
- validate before closeout
- merge back into the correct parent branch
- keep generated artifacts out of Git

## License

MIT. See `LICENSE`.
