# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

**Personal AgentOS is a local-first, owner-installed personal AI operating environment for one person.**

Its long-term product thesis is:

> **Personal AgentOS = Personal AI Kernel + Agent Distribution Platform**

Just as a personal computer gives one owner a durable computing environment, Personal AgentOS is intended to give one owner a durable AI environment that survives individual conversations, tasks, tools, agents, and model changes. It runs on an owner-controlled host/runtime and keeps the owner's policy, personal context, workspace, permissions, approvals, work state, evidence, and recovery under an AgentOS-owned boundary.

The kernel is intentionally **agent-independent**. Codex, Claude Code, GPT-class models, local models, tools, MCP servers, specialist agents, and multi-agent runtimes such as Ruflo may be used as replaceable workers or capabilities. They are not the owner of personal state and cannot become the authority for canonical memory, grants, work transitions, or evidence history.

The product experience can still be **agent-centric**. A useful third-party agent should be discoverable, inspectable, installable, permissioned, runnable, updatable, rollbackable, disableable, and removable like an application—without taking ownership of the user's AI environment.

**This is not a coding harness or an agent-swarm framework.** Coding automation can be one service inside Personal AgentOS, and this repository uses GitHub/Codex delivery automation to build the product, but that development harness is not the end-user product. Personal AgentOS is also not a replacement for macOS/Linux, a kernel, or a hypervisor; it is the persistent personal-AI layer above an owner-controlled host/runtime.

## Product model

The architecture separates durable owner state, distribution, and replaceable workers:

| Layer | Responsibility |
| --- | --- |
| **Owner plane** | Identity/policy, personal context and memory boundaries, owner data/workspace, permissions, approvals, work state, evidence, recovery |
| **Capability plane** | Tools, connectors, assistants, specialist capabilities, runtime/engine registry |
| **Distribution plane** | AgentPackage, Package Manager, Registry, trust metadata, discovery/Marketplace boundaries |
| **Worker plane** | Bounded Codex, Claude Code, model-provider, local-runtime, Ruflo, or other execution |
| **Experience plane** | Conversation and work through supported local, Telegram, companion, and future package-discovery interfaces |

The canonical architecture is [Personal AgentOS Architecture](docs/personal-agentos-architecture.en.md). The platform foundation and planned delivery sequence are in [Agent Distribution Platform Foundation](docs/agent-distribution-platform-foundation.en.md) and [#333](https://github.com/Jongtae/personal-agentos/issues/333).

### Kernel primitives

Personal AgentOS treats these as owner-level primitives rather than agent-specific implementation details:

`Owner · Context · Memory · Artifact · Capability · Runtime · Grant · Work · Event · Evidence`

The Agent Distribution Platform adds package/distribution concepts around those primitives:

`AgentPackage · Package Manager · Registry · Marketplace/Discovery · Trust/Verification`

The important rule is that distribution metadata and worker runtimes remain subordinate to kernel authority.

## Agent application model

An AgentPackage is the installable product unit. Its manifest is expected to declare identity/version, compatible AgentOS API, capabilities/actions, runtime requirements, permissions and data scope, network destinations, secret references, memory policy, events/background behavior, budgets, approval requirements, artifacts, dependencies, sandbox profile, health checks, provenance/signing and removal/update behavior.

Installation is deliberately separated from authority:

`discovered → inspected → verified → installed-disabled → granted/enabled → running → updated/rolled back → disabled → uninstalled`

**Downloaded, installed, enabled, connected, and authorized-for-action are different states.** Installing a package never implicitly creates or widens a Grant. A package update that expands permissions, external destinations, memory behavior, or background authority requires a new policy/owner decision.

Registry and Marketplace are also different responsibilities. A Registry resolves publisher/package identity, immutable versions/digests, compatibility, trust metadata, advisories and revocation. A Marketplace/discovery layer may search, rank, review or commercialize packages, but popularity and ratings do not grant execution authority and do not override security policy.

## Bootstrap strategy

The first Personal AgentOS distribution does not need the world's best bundled agents. Like early operating systems, it can ship a small set of bootstrap/reference packages—such as General, Files, Research, and Coding—to prove the application model and provide a usable baseline.

Those reference agents must use the same public package/runtime/permission contracts as third-party agents. They do not receive hidden first-party privileges. The long-term product value should come from the owner-controlled kernel plus a healthy ecosystem of independently developed capabilities.

To avoid an empty-marketplace problem, Personal AgentOS plans compatibility adapters for existing ecosystems such as MCP and selected OpenAI/Codex and Claude skills/plugins. Ruflo is planned as an optional delegated Runtime Adapter, not as the AgentOS kernel or personal-memory authority.

## Current implemented baseline

The first usable slice is the **file-and-folder personal workspace**. The finite [#314 program](https://github.com/Jongtae/personal-agentos/issues/314) is complete: its integrated file-workspace implementation merged in [PR #320](https://github.com/Jongtae/personal-agentos/pull/320), and validation/closeout merged in [PR #324](https://github.com/Jongtae/personal-agentos/pull/324).

That flow preserves owner originals, uses approved reference folders as read-only by default, writes new results only inside an owner-granted managed workspace, keeps original/derived/draft/final provenance distinct, separates rebuildable search indexes from durable work/approval/evidence/recovery/authentication state, and can find/reuse saved results after restart.

The evidence boundary matters: the completed file-workspace program is backed by automated deterministic-model and temporary local-file evidence. It does **not** by itself claim live operation of an external model, Telegram, Google Drive/OAuth, a recurring scheduler, personal folders, AgentPackage installation, Registry operation, or Marketplace operation.

The Agent Distribution Platform work in [#333](https://github.com/Jongtae/personal-agentos/issues/333) and its child issues is **planned**, not activated merely because the issues exist. The [roadmap](docs/roadmap.md) remains the status source for shipped, historical, deferred, proposed, and active work.

## Owner control and trust boundary

- The owner chooses which folders, services, tools, agents, packages, and runtimes are connected.
- Connected reference folders are read-only by default; managed-workspace writes stay inside explicit owner scope.
- Originals remain distinct from extracted text, summaries, drafts, and final records.
- Search indexes are rebuildable and separate from durable task, approval, evidence, recovery, and authentication state.
- Third-party packages do not directly mutate canonical owner Memory by default; they propose bounded memory candidates under AgentOS policy.
- External AI, messenger, agent, package, runtime, and recipient transmission is a separate policy boundary from local storage.
- Consequential actions such as external sending, payments, privilege expansion, or destructive/account changes require explicit authority.
- Work state and evidence are retained where supported for cancellation, retry, recovery, export, restore, and later audit.
- Package signatures/provenance establish identity and integrity; they are not a guarantee of behavioral safety.

Local-first does not mean "nothing ever leaves the device." When the owner selects an external AI engine, connector, package, runtime, messenger, or recipient, approved task context may be transmitted under that capability's policy. AgentOS must make that boundary explicit rather than hiding it behind the word local.

## Portability

Owner state can move between local runtimes with:

```sh
scripts/agentos-backup.py DATA ARCHIVE
scripts/agentos-restore.py ARCHIVE EMPTY_DATA
```

The archive is integrity-checked and carries durable owner state such as memory records, work evidence, and reviewed assistant/package declarations where supported. It does not carry provider credentials, sessions, local-folder grants, engine/model selections, or Telegram pairing; the destination runtime must be explicitly claimed and reconnected.

## Development installation

```sh
brew install jongtae/agentos/agentos
agentos start
```

The Homebrew path remains for developers and self-hosters while consumer installation is refined.

## Development governance

Repository delivery follows the [Development Constitution](docs/development-constitution.en.md), issue-linked branches, pull requests, required validation, and the [Goal Execution Contract](docs/goal-execution-contract.en.md). The development process adapts useful ideas from Spec-Driven Development and explicit state/authority governance, while keeping those frameworks out of the Personal AgentOS runtime dependency boundary.

The intended sequence is:

`Constitution → Spec → Authority/Threat Model → Plan → Tasks → Implement → Verify → Converge`

Repository automation, implementer/reviewer handoff, and CI are **development infrastructure for building Personal AgentOS**, not an end-user AgentOS service or proof of live autonomous operation.

Read [AGENTS.md](AGENTS.md), [PRD.md](PRD.md), [TASKS.md](TASKS.md), and the [roadmap](docs/roadmap.md) before implementation.
