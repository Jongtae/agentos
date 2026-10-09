# Contributing to Personal AgentOS

Thank you for looking. Personal AgentOS is a local-first personal AI assistant for one person. It keeps that person's memory, permissions, work records and files on their own machine, and it lets them use whichever AI they choose to do the work. Bug reports, ideas, docs fixes and code are all welcome.

This page is the short guide for people. The full execution contract, written mainly for AI coding agents working in this repository, is [`AGENTS.md`](../AGENTS.md). The durable engineering principles are in the [Development Constitution](../docs/development-constitution.en.md). When this page and those files disagree, those files win.

## Reporting a bug or suggesting an idea

Open an issue with the **Bug report** or **Idea** template. For a security problem, do **not** open a public issue. Follow [`SECURITY.md`](SECURITY.md).

## Setting up

You need macOS or Linux and Python 3.12 or newer.

```sh
git clone https://github.com/Jongtae/agentos.git
cd agentos
python3 -m venv .tools/uv
.tools/uv/bin/python -m pip install 'uv==0.11.33'
.tools/uv/bin/uv sync --locked --extra schema-validation --group dev --no-python-downloads
git config core.hooksPath .githooks   # blocks commits and pushes directly to main
```

Run the app from the checkout with `.venv/bin/agentos start`. [QUICKSTART.md](../docs/QUICKSTART.md) covers model, folder, mail, calendar and Telegram setup. The exact resolver/update boundary and currently claimed profiles are in [`docs/dependency-update-contract.en.md`](../docs/dependency-update-contract.en.md).

## Tests

- Check that the manifest and lock agree with `.tools/uv/bin/uv lock --check`.
- While you work, run the tests for what you changed, for example `.venv/bin/python -m pytest -q tests/test_owner_model_upkeep.py`.
- Before you ask for review, run the suite CI runs: `.venv/bin/python -m pytest -q tests`.
- Tests use injected model and tool transports, fake clocks and temporary stores. They make no live model calls and touch no real account.
- Tests that open a real macOS WebKit window or Keychain only run when you set `AGENTOS_REAL_BROWSER_TESTS=1`.

## How a change lands

1. **Issue first.** Describe the owner outcome, what changes at runtime, the acceptance criteria and the non-goals.
2. **A branch named after the issue**, for example `oss-ready-01-878`.
3. **Small commits**, then a pull request that fills in the [PR template](pull_request_template.md) and says which issue it closes.
4. The required `validate` check must pass. Feature work is squash-merged into `main`.

Which work is actively scheduled is decided by the maintainer in [`delivery-plan.yaml`](../delivery-plan.yaml). An open issue is not automatically in progress. Ask on the issue before starting something large.

## Rules that shape every change

**Reuse first: Adopt → Adapt → Build.** Before you add a component, dependency, protocol client, parser or other infrastructure, look for an existing piece in this repository, then the standard library, official SDKs and standards, then maintained open source. Say in the issue or PR which one you picked and why. See [C15](../docs/development-constitution.en.md#c15-reuse-first-adopt--adapt--build).

**Keep upstream changes reviewable.** Package manifests and reproducible resolution own package versions; pinned content keeps its immutable upstream revision and licence. An update PR records the upstream diff, affected real boundary, focused tests and rollback. A necessary local patch names its upstream base and the release or condition that lets the project remove it. The current relationship map and selected pilots are in [`docs/upstream-relationship-map.en.md`](../docs/upstream-relationship-map.en.md).

**The AI is the engine.** The owner's chosen AI (Codex, Claude Code, a local model, a model API) does the work. AgentOS code keeps owner state, permissions, secrets, payment approval and budgets, and it removes blockers that stop the AI. It never implements one specific kind of request, and it never branches on a named site, provider or task category. See [C16](../docs/development-constitution.en.md#c16-ai-is-the-engine-agentos-orchestrates-it-does-not-implement-requests).

**Truthful evidence.** A test, a mock, a local run and a live external run are different kinds of evidence. Never describe something as working live when only a test or fixture shows it.

## Licence

Personal AgentOS is licensed under [AGPL-3.0-only](../LICENSE). Contributions are accepted under the same licence (inbound = outbound), and there is no CLA. Do not add code or dependencies whose licence is incompatible with AGPL-3.0. Record the licence of any new dependency in the PR. The name and logo are covered by [TRADEMARKS.md](../docs/TRADEMARKS.md), not by the code licence.

## Language

Internal design documents and code are in English. Korean companion documents exist for the owner. The four public READMEs (`README.md`, `docs/i18n/README.ko.md`, `docs/i18n/README.ja.md`, `docs/i18n/README.zh-CN.md`) must change together. The app interface is Korean today.
