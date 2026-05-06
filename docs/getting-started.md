# Getting Started

AgentOS has two practical entry paths:

- Boot the ISO to see the actual OS-native concept.
- Run from the repo when developing or testing runtime surfaces quickly.

## Concept Demo: Boot The OS Image

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

## Developer Shortcut: Run From Repo

Use this path when you want to inspect or develop the runtime without booting a
VM:

```bash
git clone git@github.com:Jongtae/agentos.git
cd agentos
cp .env.example .env
python3 src/main.py --doctor
python3 src/main.py --no-tui
```

Inspect runtime surfaces directly:

```bash
./scripts/agentos-kernelctl status --json
./scripts/agentos-kernelctl phase2-run --message "status"
./scripts/agentos-kernelctl phase2-run --message "draft a reply to my Gmail roadmap email"
./scripts/agentos-kernelctl guided-operator --workspace ./workspaces/default --json
./scripts/agentos-kernelctl workflow-status --workspace ./workspaces/default --json
./scripts/agentos-kernelctl activity-feed --workspace ./workspaces/default --json
```

The Phase 2 CLI loop is local-first and safe to try without credentials. Gmail
uses fixture data by default; live Gmail OAuth and VM/ISO proof remain explicit
follow-up work.

The same loop is the Docker developer/demo default:

```bash
docker compose run --rm agent-os --prompt "status"
docker compose run --rm agent-os --prompt "draft a reply to my Gmail roadmap email"
```
