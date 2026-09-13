# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

**Personal AgentOS is a local-first, owner-installed personal AI operating environment for one person.**

Just as a personal computer gives one owner a durable computing environment, Personal AgentOS is intended to give one owner a durable AI environment that survives individual conversations, tasks, tools, and model changes. It runs on an owner-controlled Mac/runtime and keeps the owner's policy, personal context, workspace, permissions, approvals, work state, evidence, and recovery under an AgentOS-owned boundary.

Codex, Claude Code, GPT-class models, local models, tools, and specialist agents are workers or capabilities that AgentOS may use. They are not the owner of the personal state. Changing an execution engine should not discard the owner's memory/context records, permissions, approval history, recoverable work, or evidence.

**This is not a coding harness or an agent-swarm framework.** Coding automation can be one service inside Personal AgentOS, and this repository uses substantial GitHub/Codex delivery automation to build the product, but that development harness is not the product itself. Personal AgentOS is also not a replacement for macOS/Linux, a kernel, or a hypervisor; it is the persistent personal-AI layer above an owner-controlled host/runtime.

## Product model

The long-term architecture separates durable owner state from replaceable workers:

| Layer | Responsibility |
| --- | --- |
| **Owner plane** | Identity/policy, personal context and memory boundaries, owner data/workspace, permissions, approvals, work state, evidence, recovery |
| **Capability plane** | Tools, connectors, assistants, specialist capabilities, runtime/engine registry |
| **Worker plane** | Bounded Codex, Claude Code, model-provider, or local-runtime execution |
| **Experience plane** | Conversation and work through supported local, Telegram, or companion interfaces |

The canonical architecture is [Personal AgentOS Architecture](docs/personal-agentos-architecture.en.md). It distinguishes intended architecture from shipped evidence and explains why the word **OS** refers to the persistent owner-level AI environment rather than a host operating-system replacement.

## Current implemented baseline

The first usable slice is the **file-and-folder personal workspace**. The finite [#314 program](https://github.com/Jongtae/personal-agentos/issues/314) is complete: its integrated file-workspace implementation merged in [PR #320](https://github.com/Jongtae/personal-agentos/pull/320), and validation/closeout merged in [PR #324](https://github.com/Jongtae/personal-agentos/pull/324).

That flow preserves owner originals, uses approved reference folders as read-only by default, writes new results only inside an owner-granted managed workspace, keeps original/derived/draft/final provenance distinct, separates rebuildable search indexes from durable work/approval/evidence/recovery/authentication state, and can find/reuse saved results after restart.

The evidence boundary matters: the completed file-workspace program is backed by automated deterministic-model and temporary local-file evidence. It does **not** by itself claim live operation of an external model, Telegram, Google Drive/OAuth, a recurring scheduler, or personal folders. Optional Drive work and public-site publication are currently deferred from the core path. The [roadmap](docs/roadmap.md) is the status source for shipped, historical, deferred, and proposed work.

## Owner control and trust boundary

- The owner chooses which folders, services, tools, assistants, and runtimes are connected.
- Connected reference folders are read-only by default; managed-workspace writes stay inside explicit owner scope.
- Originals remain distinct from extracted text, summaries, drafts, and final records.
- Search indexes are rebuildable and separate from durable task, approval, evidence, recovery, and authentication state.
- External AI, messenger, agent, and recipient transmission is a separate policy boundary from local storage.
- Consequential actions such as external sending or destructive/account changes require explicit authority.
- Work state and evidence are retained where supported for cancellation, retry, recovery, export, and restore.

Local-first does not mean "nothing ever leaves the device." When the owner selects an external AI engine, messenger, connector, or recipient, approved task context may be transmitted under that capability's policy. AgentOS must make that boundary explicit rather than hiding it behind the word local.

## Portability

Owner state can move between local runtimes with:

```sh
scripts/agentos-backup.py DATA ARCHIVE
scripts/agentos-restore.py ARCHIVE EMPTY_DATA
```

The archive is integrity-checked and carries durable owner state such as memory records, work evidence, and reviewed assistant declarations. It does not carry provider credentials, sessions, local-folder grants, engine/model selections, or Telegram pairing; the destination runtime must be explicitly claimed and reconnected.

## Development installation

```sh
brew install jongtae/agentos/agentos
agentos start
```

The Homebrew path remains for developers and self-hosters while consumer installation is refined.

## Development governance

Repository delivery follows issue-linked branches, pull requests, required validation, and the [Goal Execution Contract](docs/goal-execution-contract.en.md). The repository also contains a state-driven implementer/reviewer handoff loop. Those are **development infrastructure for building Personal AgentOS**, not an end-user AgentOS service or proof of live autonomous operation.

Read [AGENTS.md](AGENTS.md), [PRD.md](PRD.md), [TASKS.md](TASKS.md), and the [roadmap](docs/roadmap.md) before implementation.
