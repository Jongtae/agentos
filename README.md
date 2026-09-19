# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

**A personal AI environment you install, own, and control — built to do useful work.**

Personal AgentOS is a local-first, owner-installed personal AI operating environment for one person. Its intended experience is simple: ask for an outcome, use your chosen models and approved material, keep useful results, and install or replace agents without surrendering your memory, permissions or work history.

> **Personal AgentOS = Personal AI Kernel + Open Agent Distribution Platform**

The platform must earn trust by doing useful work within observable, enforceable boundaries. Control without usefulness is not the product. A small initial bundle is acceptable; deliberately weak basic functions are not.

## What exists today — and what is planned

| Status | Scope and evidence |
| --- | --- |
| Existing product code | Local browser setup/chat, model-provider adapters, bounded tools, notes, approved folders and managed file results. Exact supported operating paths are in [QUICKSTART](QUICKSTART.md). |
| File-workspace development complete | #314, PR #320 and PR #324: scoped file use, original preservation, saved results and restart/reuse, supported by deterministic/temporary-local-file evidence. |
| v0.1 contract complete | #334 / PR #350: Core Primitive and AgentPackage schemas, semantic validation and fixtures. This is not package execution or installation. |
| DOGFOOD-01 development complete | #351 / PRs #354–#356: simulated-provider HTTP/file/restart acceptance and operating instructions. Real-provider/browser use remains separately observed owner acceptance. |
| Planned useful default-agent work | [USE-01 #358](https://github.com/Jongtae/personal-agentos/issues/358): better research, file artifacts and continuity with measured outcome quality. |
| Planned control/app experience | [OBS-01 #359](https://github.com/Jongtae/personal-agentos/issues/359), [AGENT-UX-01 #360](https://github.com/Jongtae/personal-agentos/issues/360) and the uncompleted children of #333: receipts, install/use/revoke/remove and ecosystem expansion. |

There is no claim of current arbitrary third-party AgentPackage execution, public Registry/Marketplace, universal agent compatibility or autonomous purchasing. Legacy declaration-only plugins are not the planned executable AgentPackage system. Historical live acceptance remains limited to its recorded prompts, versions and provider conditions.

## Useful from the beginning

The next product targets are three complete journeys, not a collection of disconnected demos:

- **Research → decision:** compare public options using appropriate source evidence, distinguish known facts from missing inventory/fees, and produce a useful decision brief without buying anything.
- **My files → artifact:** understand approved documents, reconcile facts and save a useful result as an ordinary file without changing the originals.
- **Follow-up → continuity:** accept corrections, find previous work and reuse results after restart without rebuilding the owner's context every time.

Current public search returns snippets; it is not full-page or checkout verification. The [usefulness plan](docs/default-agent-usefulness.en.md) identifies this concrete gap and defines a 24-case synthetic evaluation seed. Static test success is not a model-performance result. Model quality, result substance, latency, cost and owner effort must be measured on the actual supported path.

Start with a capable default assistant and reliable shared tools; add specialists when they improve measured outcomes. Strong cloud models and local models are both compatible with the direction, subject to explicit data-destination choices. More agents, a larger framework or a marketplace do not substitute for good basic functionality.

## Control the environment, not just the conversation

The [owner-control contract](docs/owner-control-contract.en.md) defines six rights to implement and verify:

1. Inspect package source, publisher, version, execution mode and requested authority.
2. Choose the documents, memories and accounts each agent can use.
3. See where task information will be sent.
4. Limit actions separately from connecting or installing.
5. Stop work and revoke authority, with honest in-flight uncertainty.
6. Remove/replace agents while retaining owner artifacts, accepted Memory and appropriate evidence.

Controls must be enforced by the capability/runtime boundary, not just by telling a model to behave. Progress must reflect observed Work/tool events. Relevant redacted parameters, destinations, approval decisions and results should be inspectable; hidden reasoning, secrets and raw system prompts are not required.

Local installation is not the same as local processing. A local package using an external model sends approved context to that provider. A remote-agent connector does not make the remote service locally controlled. Disconnecting, revoking access, removing an agent and deleting retained information are different operations. Already transmitted data or completed external effects cannot be promised away by a local stop button.

## Architecture and application model

| Layer | Responsibility |
| --- | --- |
| Owner plane | Owner identity/policy, Context/Memory authority, data/workspace, Grants, approvals, Work/Event, Artifacts, Evidence and recovery |
| Capability plane | Typed tools/connectors and bounded runtime interfaces |
| Distribution plane | AgentPackage, Package Manager, Registry, trust metadata and Marketplace/discovery |
| Worker plane | Replaceable models, Codex/Claude Code, local/API workers and optional delegated runtimes such as Ruflo |
| Experience plane | Conversation, useful results, inspectable progress, approval/control and future agent discovery |

The kernel is **agent-independent**; the product and ecosystem can be **agent-centric**. Core primitives remain:

`Owner · Context · Memory · Artifact · Capability · Runtime · Grant · Work · Event · Evidence`

Agents request authority; AgentOS policy and the owner decide it. Models, agents, registries and marketplaces must not become the source of truth for canonical owner state.

The AgentPackage lifecycle distinguishes:

`downloaded != installed != enabled != connected != authorized-for-action`

Installation defaults to disabled and never creates a Grant. Updates that expand data, actions, destinations, memory or background behavior require fresh authority. Third-party durable-memory output is a MemoryCandidate by default. Removal revokes package authority while preserving owner-owned outputs and retained evidence according to policy.

A Registry resolves exact identity/version/digest/compatibility/advisories. A Marketplace supports discovery, ranking, reviews and possible commerce; popularity never overrides security policy. Package identity/signatures are not guarantees of behavior. Private owner Context is not marketplace search data.

See the canonical [architecture](docs/personal-agentos-architecture.en.md), [PRD](PRD.md), [platform foundation](docs/agent-distribution-platform-foundation.en.md) and [roadmap](docs/roadmap.md).

## Bootstrap the ecosystem

First prove one useful Files reference package and a public authoring path, then expand. Bundled and outside agents must use the same public contracts with no hidden first-party privilege. Compatibility adapters for MCP and selected skill/plugin formats are planned only where formats, licenses and authority can be mapped. Ruflo is an optional future worker adapter, not the kernel or a required dependency.

The first app experience to prove is: inspect → install disabled → grant → useful work → inspect receipt → revoke → denied retry → remove → restart → authorized replacement/reuse. A public store and payments are not prerequisites.

## Try the current baseline

```sh
brew install jongtae/agentos/agentos
agentos start
```

Homebrew is a developer/self-host path and may differ from current main. Follow [QUICKSTART](QUICKSTART.md) for the supported setup and a dedicated test-folder task; do not treat planned package features as commands that already exist. For the documented file-workspace test use a supported direct model-provider path, not a subscription engine.

## Portability and limits

```sh
scripts/agentos-backup.py DATA ARCHIVE
scripts/agentos-restore.py ARCHIVE EMPTY_DATA
```

Supported owner state and reviewed declarations can be exported/restored with integrity checks. Provider credentials, sessions, local-folder grants, engine/model selections and Telegram pairing are excluded from this portable archive; explicitly claim and reconnect the destination. This is distinct from backing up an entire private data directory, which may contain secrets.

Local-first does not mean local-only or automatically safe. Host security, package isolation, data already transmitted and remote-provider retention have limits. Supported cancellation/recovery must distinguish confirmed and unknown outcomes.

## Development governance

This is **not a coding harness, swarm framework, host kernel or replacement for macOS/Linux**. GitHub/Codex delivery automation builds Personal AgentOS; it is not the end-user product.

Follow [AGENTS.md](AGENTS.md), the [Development Constitution](docs/development-constitution.en.md) and [Goal Execution Contract](docs/goal-execution-contract.en.md): issue → bounded branch → implementation → validation → independent review → merge/closeout. Spec-driven patterns are development aids, not runtime dependencies.

Planned issues are not an automatic execution queue. GOV-USE-01 aligns requirements/backlog only; #358–#360 and uncompleted #333 children remain inactive until separately selected. A product completion claim must include useful outcome evidence and relevant denial/recovery evidence, not only schemas, file counts or green CI.
