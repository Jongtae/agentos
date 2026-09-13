# Personal AgentOS — Personal AI operating environment

## Product identity

Personal AgentOS is a local-first, owner-installed personal AI operating environment for one person.

Its long-term product contract is:

> **Personal AgentOS = Personal AI Kernel + Agent Distribution Platform**

The kernel is the durable owner-authoritative layer that retains policy, personal context and memory boundaries, owner material/workspace, permissions, approvals, work state, artifacts, evidence, recovery, events, and capability/runtime boundaries across individual conversations and execution-engine changes.

The distribution platform lets the owner discover, inspect, verify, install, grant, enable, execute, update, roll back, disable, and remove third-party AgentPackages without surrendering that durable state.

The word **OS** describes this persistent owner-level AI environment. Personal AgentOS does not replace macOS/Linux and is not a host kernel or hypervisor. Codex, Claude Code, model providers, local models, MCP servers, connectors, specialist agents, and multi-agent frameworks are bounded workers/capabilities behind AgentOS-owned policy and state.

Repository delivery automation is not the product. GitHub issues, branches, pull requests, CI, Goal Execution Contract processing, and the implementer/reviewer handoff loop are development infrastructure used to build Personal AgentOS.

See the canonical [Personal AgentOS Architecture](docs/personal-agentos-architecture.en.md) and the planned [Agent Distribution Platform Foundation](docs/agent-distribution-platform-foundation.en.md).

## Product outcome

An owner has one persistent AI environment that can use explicitly approved personal material and installable capabilities without making any single model session, package, runtime, or marketplace the source of truth.

The owner can:

- entrust material and durable preferences to AgentOS-owned state;
- ask for outcomes in conversation/work rather than manually orchestrating integrations;
- install and replace agents/capabilities while preserving owner state;
- understand what data, tools, destinations, models, and packages a Work item used;
- approve consequential authority separately from package installation;
- preserve reusable Artifacts and Evidence;
- recover durable Work across supported restarts;
- export/restore owner state independently of provider credentials or package-local state.

## Kernel primitives

The core product semantics are agent-independent:

- **Owner** — identity, policies, devices/runtime claims, preferences and trust settings.
- **Context** — task-scoped, attributable information assembled for Work; not canonical durable Memory.
- **Memory** — explicit/derived durable owner knowledge with provenance, confidence, sensitivity, retention and supersession semantics.
- **Artifact** — durable user-visible or machine-usable result with provenance.
- **Capability** — a typed ability exposed through AgentOS policy, independent of one implementation.
- **Runtime** — a replaceable execution environment/adapter that performs bounded Work.
- **Grant** — explicit authority over resource/action/scope/destination, issued by AgentOS policy/owner rather than by a package.
- **Work** — durable goal/task lifecycle with context, runtime, grants, checkpoints, artifacts, approvals, evidence and recovery.
- **Event** — typed trigger that may cause policy evaluation/Work creation but does not grant action authority.
- **Evidence** — append-only/retained record of what ran, with which package/runtime/context/grants/tools/destinations and what changed.

The Agent Distribution Platform adds:

- **AgentPackage** — installable unit describing capabilities, runtime requirements and requested authority.
- **Package Manager** — local lifecycle manager for verify/install/health/enable/update/rollback/uninstall.
- **Registry** — package identity/version/digest/compatibility/trust/advisory authority.
- **Marketplace/Discovery** — search/ranking/review/commercial metadata; never execution authority.
- **Trust/Verification** — publisher identity, signatures, provenance, scanning, conformance/evaluation, incidents and revocation metadata kept as distinct signals.

## AgentPackage product contract

An AgentPackage is analogous to an application package, not a privileged mini-OS. The manifest is expected to declare at least:

- stable package ID, publisher, version and AgentOS API compatibility;
- capabilities/actions and Runtime requirements;
- model/provider compatibility where relevant;
- filesystem/data scope and external network destinations;
- secret references/connector requirements without embedding raw credentials;
- Memory read selectors and write-candidate policy;
- Event/background subscriptions;
- time/cost/resource budgets;
- consequential-action approval requirements;
- produced/consumed Artifact types;
- dependencies and sandbox profile;
- health check, install/update/rollback/remove behavior;
- licence, provenance, digest/signature/SBOM metadata where supported.

The lifecycle is deliberately staged:

`discover → inspect → verify → stage → health-check → installed-disabled → grant/connect/enable → run → update/rollback → disable → uninstall`

`downloaded != installed != enabled != connected != authorized-for-action`.

Installation never implicitly creates a Grant. Package updates that expand permissions, data scope, external destinations, Memory behavior, Event/background subscriptions, cost/resource authority, or consequential actions require fresh policy/owner review.

Third-party packages do not directly mutate canonical owner Memory by default. They return attributable MemoryCandidates that AgentOS policy/owner may accept, reject, expire or supersede.

## Registry and Marketplace boundaries

The **Registry** is responsible for publisher/package identity, immutable exact releases/digests, compatible AgentOS/runtime metadata, signatures/provenance, security advisories, revocation/quarantine and trust metadata.

The **Marketplace/Discovery** layer may expose search, ranking, editorial curation, reviews, evaluation summaries and future commercial metadata. Popularity, stars, install counts, recommendations or payments never grant runtime authority and never override quarantine, signature, policy or permission enforcement.

Owner Context/Memory/Work content is not Registry/Marketplace state. Capability discovery should use structured/minimised search metadata rather than sending raw private owner prompts or personal context to a marketplace.

## Runtime/worker model

The kernel is agent-independent while the product can be agent-centric. A Runtime may be Codex, Claude Code, a model provider, a local model, an MCP-backed worker, a script/API, a human-mediated worker, or a delegated framework such as Ruflo.

All such workers must remain behind a common semantic boundary: receive Work-scoped Context and effective Grants, perform bounded execution, return Artifacts/Evidence/MemoryCandidates, and respect cancellation/deadline/budget. They do not mint Grants, rewrite sealed Evidence, directly own canonical Memory, or determine final Work completion.

Ruflo is therefore a possible delegated Runtime Adapter, not the AgentOS kernel, memory authority, or mandatory orchestration layer.

## Ecosystem/bootstrap strategy

The first distribution may include a small number of bootstrap/reference agents such as General Assistant, Files, Research, and Coding. Their purpose is to make the OS useful and prove the public application model, not to be permanently best-in-class.

Bundled/reference agents use the same AgentPackage/Runtime/Grant contracts as third-party packages and receive no hidden first-party privilege.

To mitigate ecosystem cold start, Personal AgentOS plans compatibility import/wrapping for existing ecosystems where official formats and licensing allow it, beginning with MCP and selected OpenAI/Codex and Claude skill/plugin metadata. Imported packages receive no security exemption and must map all authority into AgentOS semantics or fail closed/declare partial support.

## Current release slice: file-and-folder personal workspace

The first usable implemented product slice is owner-controlled files and folders. The owner entrusts material from approved locations. AgentOS preserves originals, finds and understands material in conversation/work, saves reusable outputs as ordinary files, and retains work policy, approvals, evidence, and recovery across restarts and engine changes.

This finite workspace program is complete in #314/#315/#316, with the integrated implementation in PR #320 and closeout in PR #324. Current acceptance evidence is deterministic/local-file evidence, not a claim of live external-model, Telegram, Drive/OAuth, scheduler, personal-folder, AgentPackage, Registry, or Marketplace operation.

## Primary user

A person who wants a durable personal AI environment they control, rather than repeatedly rebuilding context, permissions, agents, and integration state inside separate vendor sessions. The current first-flow target remains a non-developer Mac user working with their own files and folders.

A secondary long-term user is an AgentPackage developer who wants to publish a capability against a stable owner-state, permission, runtime and distribution contract rather than rebuilding those concerns inside every agent.

## Core platform responsibilities

- Keep durable owner state separate from replaceable agents, packages and runtimes.
- Maintain explicit Context/Memory semantics rather than treating all conversation as automatic permanent memory.
- Preserve owner material and managed-workspace results with provenance.
- Enforce Grants, tool boundaries, sandbox/network/data rules, approvals and external-transmission policy.
- Track Work/Event state, Artifacts, Evidence, recovery and audit information required by supported capabilities.
- Register and invoke tools, connectors, packages and runtimes through bounded interfaces.
- Verify/install/update/rollback/uninstall packages without silently widening authority.
- Allow owner state to remain portable without treating provider credentials, sessions, package caches or marketplace identity as the owner's durable identity.
- Keep distribution trust signals explicit and falsifiable: signed/verified/reviewed/curated are not synonyms for safe.

## Current file-workspace capabilities

- Connected owner reference folders, read-only by default, searched/read only within approved scope.
- An AgentOS-managed workspace that writes new material and results only within owner-granted scope.
- Conversation paths for requests, source evidence, explicit approvals, recovery, and reuse after restart.
- Original/derived/draft/final provenance, rebuildable search indexes, and durable task/approval/evidence/recovery/auth state kept distinct.
- Bounded execution engines and optional connectors/delegation; AgentOS retains policy and personal state.

## Planned Agent Distribution Platform program

[#333](https://github.com/Jongtae/personal-agentos/issues/333) is the planned epic. Creating these issues does not activate execution. Each child requires explicit owner activation and the normal Goal Execution Contract.

Foundation design: #334 Core Primitives/AgentPackage, #335 package trust/lifecycle, #336 Context/Memory, #337 sandbox/supply-chain, #338 Runtime Adapter, #339 Registry/Marketplace.

Local platform: #340 Package Manager, #341 Work/Event integration, #342 SDK/reference packages.

Ecosystem: #343 compatibility import, #344 Ruflo Runtime Adapter, #345 local/open Registry.

Future autonomy: #346 capability-acquisition policy. Level 4/5 automatic acquisition is explicitly outside the first platform MVP.

## Boundaries and non-goals

Included in the current file-workspace slice: local Mac runtime; owner-approved file/folder connection; read-only reference material; managed-workspace result files; conversation work; explicit approval; provenance; durable recovery; and export/restore without connection secrets.

Excluded from the current slice: public Agent Registry/Marketplace, live third-party package download/execution, automatic package installation, payment/commerce, arbitrary shell or broad home-folder access, original overwrite/deletion or bulk moves without separate authority, automatic cloud sync, central OAuth/authentication, persistent relay-content storage, unapproved external transmission, and destructive migration.

The planned distribution program must not claim a public store, live external package compatibility, behavioral security, or autonomous capability acquisition until those exact paths have current evidence.

## Success measures

### Current product slice

- An owner can save a meeting note or summary as TXT/MD from approved material and find/reuse it after app restart in another conversation.
- AgentOS preserves originals, prevents traversal/out-of-grant access, and records source/result relationships.
- Search indexes can be rebuilt without losing task, approval, evidence, recovery, or authentication state.
- External AI, messenger, agent, and recipient transmission remains separately controlled and evidence distinguishes mock, local-file, and operating observations.

### Platform readiness

- Replacing an execution engine or installed agent does not redefine or silently discard durable owner state.
- A package can be installed, enabled, updated, rolled back, disabled and removed without implicit Grant expansion.
- The owner can inspect requested permissions, data destinations, Memory behavior, background Events, costs and consequential actions before authority is issued.
- Package identity/integrity, behavioral conformance, publisher identity, popularity, incidents and curation remain distinct trust signals.
- Reference and third-party packages use the same public authority model.
- Existing ecosystems can be wrapped only where their authority can be mapped explicitly and safely into AgentOS semantics.
