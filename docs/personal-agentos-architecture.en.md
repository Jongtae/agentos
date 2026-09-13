# Personal AgentOS Architecture

## Status and purpose

This document is the canonical product-architecture definition for Personal AgentOS. It defines the intended product boundary and the meaning of the word **OS**. It is not a claim that every layer described here is already shipped or live-operated. Current support is determined by merged implementation, the [roadmap](roadmap.md), and named acceptance evidence.

## Product identity

**Personal AgentOS is a local-first, owner-installed personal AI operating environment for one person.**

The analogy is the personal computer and personal operating system: one owner should have a durable AI environment that remains theirs across conversations, tasks, tools, and model changes. Personal AgentOS owns the persistent personal state and policy. AI models and coding agents are replaceable workers inside that environment.

Personal AgentOS is not a replacement for macOS or Linux, and it is not a kernel, hypervisor, or general-purpose host operating system. The host OS still owns hardware, processes, devices, and ordinary application execution. Personal AgentOS is the persistent AI layer running on an owner-controlled host or isolated owner runtime.

It is also **not a coding harness or agent-swarm framework**. Coding automation can be one service that runs through Personal AgentOS, but software-development orchestration is not the product definition.

## Logical architecture

```text
                         OWNER
                           |
                 conversation / work
                           |
+-----------------------------------------------------------+
|                    PERSONAL AGENTOS                       |
|                                                           |
|  Owner plane                                              |
|  - identity and policy                                    |
|  - personal context and memory boundaries                 |
|  - owner data and managed workspace                       |
|  - permissions and approvals                              |
|  - work state, evidence, recovery, and audit              |
|                                                           |
|  Capability plane                                         |
|  - tools and connectors                                   |
|  - assistants and specialist capabilities                |
|  - runtime/engine registry                                |
|                                                           |
|  Experience plane                                         |
|  - local conversation UI                                  |
|  - Telegram / companion interfaces where supported        |
+-------------------------------+---------------------------+
                                |
                      bounded task/context
                                |
                  +-------------+-------------+
                  |             |             |
               Codex       Claude Code    other/local
               worker         worker        runtimes
```

The important ownership rule is that the box above the worker boundary remains authoritative when a worker changes. A model or coding agent must not become the source of truth for the owner's memory, permissions, approval history, recoverable work state, or evidence.

## Durable state versus replaceable workers

Personal AgentOS should keep these concepts durable and owner-controlled where implemented:

- identity, policy, grants, and connection state;
- explicit personal context and memory records;
- owner material, managed-workspace results, and provenance;
- task/work state, approvals, evidence, recovery, and audit records;
- capability declarations and the boundaries under which they may run.

The following should remain replaceable behind explicit boundaries:

- reasoning/model providers;
- Codex, Claude Code, or another execution runtime;
- connectors and specialist agents;
- conversation and companion interfaces.

Engine replacement must not require reconstructing the owner's AI life from prompt history.

## Services are above the owner plane

A personal AI OS can eventually expose services such as file knowledge, research, coding, communication, scheduling, or other automations. These are capabilities that use the same owner state and permission model; they are not separate owners of personal data.

The repository's current first usable slice is the **file-and-folder personal workspace**. That slice proves an important OS property: approved material and reusable results survive individual conversations and restarts while remaining inside explicit data boundaries. Future services must reuse the same ownership model instead of creating isolated agent silos.

## Product runtime versus development harness

This repository also contains machinery used to build Personal AgentOS: GitHub issues, issue-linked branches, pull requests, CI, the Goal Execution Contract, and a state-driven implementer/reviewer handoff loop. Those mechanisms are **repository development infrastructure**.

They must not be confused with the end-user Personal AgentOS runtime. Their presence proves how this repository is developed; it does not make GitHub, a Codex development loop, or a software-delivery harness part of the personal AI OS product contract.

Likewise, specification frameworks, multi-agent orchestrators, and coding-agent harnesses may provide useful implementation ideas or optional components, but Personal AgentOS remains the owner-level environment that decides what state, permissions, evidence, and capabilities survive any one agent or framework.

## Current implementation boundary

The file-and-folder workspace program [#314](https://github.com/Jongtae/personal-agentos/issues/314) is complete. The first integrated implementation merged in [PR #320](https://github.com/Jongtae/personal-agentos/pull/320), and the program closeout merged in [PR #324](https://github.com/Jongtae/personal-agentos/pull/324).

Current evidence covers the scoped local-file flow with deterministic adapters and temporary local folders: read-only reference grants, scoped managed-workspace writes, original/derived provenance, reuse after restart, and separation of rebuildable indexes from durable work state. It does **not** by itself prove live operation of an external model, Telegram, Google Drive/OAuth, a recurring scheduler, or personal folders.

Optional Drive work and the public information-site publication are currently deferred from the core path. No product successor is activated merely by this architecture document.

## Design rules

1. **One owner, one durable personal state.** Personal state belongs to the owner-controlled AgentOS runtime, not to an external model session.
2. **Local-first does not mean local-only.** External engines and services may be used, but every transmission is a separate policy boundary and must be described truthfully.
3. **Minimum authority.** Folder grants, tools, connectors, and workers receive only the scope required for the task.
4. **Consequential actions require explicit authority.** External sends, destructive file/account changes, payments, or privilege expansion must not be inferred from read access or conversation intent alone.
5. **Recoverable long-running work.** Work state and evidence should survive a model turn, process restart, or worker replacement where the current capability supports it.
6. **Portable owner state.** The architecture should allow owner state to move between supported runtimes without turning credentials or provider sessions into the durable identity.
7. **Evidence before capability claims.** A design, mock, fixture, or development harness is not evidence of live external operation.
