# Personal AgentOS — Personal AI operating environment

## Product identity

Personal AgentOS is a local-first, owner-installed personal AI operating environment for one person. It is the durable layer that retains owner policy, personal context, workspace state, permissions, approvals, work state, evidence, recovery, and capability/runtime boundaries across individual conversations and execution-engine changes.

The word **OS** describes this persistent owner-level AI environment. Personal AgentOS does not replace macOS/Linux and is not a kernel or hypervisor. Codex, Claude Code, model providers, local models, connectors, and specialist agents are bounded workers/capabilities behind AgentOS-owned policy and state.

Repository delivery automation is not the product. GitHub issues, branches, pull requests, CI, Goal Execution Contract processing, and the implementer/reviewer handoff loop are development infrastructure used to build Personal AgentOS.

See the canonical [Personal AgentOS Architecture](docs/personal-agentos-architecture.en.md).

## Product outcome

An owner has one persistent AI environment that can use explicitly approved personal material and capabilities without making any single model session the source of truth. The owner can entrust material, ask for outcomes in conversation/work, preserve reusable results, understand what was used or sent, approve consequential actions, and recover durable work state across restarts where the current capability supports it.

## Current release slice: file-and-folder personal workspace

The first usable product slice is owner-controlled files and folders. The owner entrusts material from approved locations. AgentOS preserves originals, finds and understands material in conversation/work, saves reusable outputs as ordinary files, and retains work policy, approvals, evidence, and recovery across restarts and engine changes.

This finite workspace program is complete in #314/#315/#316, with the integrated implementation in PR #320 and closeout in PR #324. Current acceptance evidence is deterministic/local-file evidence, not a claim of live external-model, Telegram, Drive/OAuth, scheduler, or personal-folder operation.

## Primary user

A person who wants a durable personal AI environment they control, rather than repeatedly rebuilding context and permissions inside separate chat sessions or vendor-specific agents. The current first-flow target is a non-developer Mac user working with their own files and folders.

## Core platform responsibilities

- Keep durable owner state separate from replaceable AI workers.
- Maintain explicit personal-context and memory boundaries rather than treating all conversation as automatic permanent memory.
- Preserve owner material and managed-workspace results with provenance.
- Enforce grants, tool boundaries, approvals, and external-transmission policy.
- Track work state, evidence, recovery, and audit information required by supported capabilities.
- Register and invoke tools, connectors, assistants, and execution runtimes through bounded interfaces.
- Allow owner state to remain portable without treating provider credentials or sessions as the owner's durable identity.

## Current file-workspace capabilities

- Connected owner reference folders, read-only by default, searched/read only within approved scope.
- An AgentOS-managed workspace that writes new material and results only within owner-granted scope.
- Conversation paths for requests, source evidence, explicit approvals, recovery, and reuse after restart.
- Original/derived/draft/final provenance, rebuildable search indexes, and durable task/approval/evidence/recovery/auth state kept distinct.
- Bounded execution engines and optional connectors/delegation; AgentOS retains policy and personal state.

## Boundaries

Included in the current file-workspace slice: local Mac runtime; owner-approved file/folder connection; read-only reference material; managed-workspace result files; conversation work; explicit approval; provenance; durable recovery; and export/restore without connection secrets.

Excluded from the current slice: automatic full-conversation memory, arbitrary shell or broad home-folder access, original overwrite/deletion or bulk moves without separate authority, automatic cloud sync, central OAuth/authentication, persistent relay-content storage, unapproved external transmission, and destructive migration. OCR, transcription, video analysis, advanced large-library search, cloud-only import, and material-bundle delegation remain follow-up work unless separately implemented and evidenced.

Coding, research, communication, scheduling, and other services may be added above the same owner-state and permission model. Their presence must not create separate personal-data silos or redefine Personal AgentOS as a tool-specific harness.

## Success measures

- An owner can save a meeting note or summary as TXT/MD from approved material and find/reuse it after app restart in another conversation.
- AgentOS preserves originals, prevents traversal/out-of-grant access, and records source/result relationships.
- Search indexes can be rebuilt without losing task, approval, evidence, recovery, or authentication state.
- External AI, messenger, agent, and recipient transmission remains separately controlled and evidence distinguishes mock, local-file, and operating observations.
- Replacing an execution engine does not redefine or silently discard the durable owner state AgentOS is responsible for.
