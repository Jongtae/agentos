# Personal AgentOS Architecture

## Status and purpose

This document is the canonical product-architecture definition for Personal AgentOS. It defines the intended product boundary, the meaning of the word **OS**, and the authority relationship between the personal AI kernel, installable AgentPackages, distribution services, and replaceable execution runtimes.

It is not a claim that every layer described here is already shipped or live-operated. Current support is determined by merged implementation, the [roadmap](roadmap.md), and named acceptance evidence.

## Product identity

**Personal AgentOS is a local-first, owner-installed personal AI operating environment for one person.**

The long-term architecture thesis is:

> **Personal AgentOS = Owner-authoritative Personal AI Kernel + Open Agent Distribution Platform**

The analogy is the personal computer and personal operating system: one owner should have a durable AI environment that remains theirs across conversations, tasks, tools, agents, packages, and model changes. Personal AgentOS owns the persistent personal state and policy. AI models, coding agents, packages, connectors, and multi-agent frameworks are replaceable workers/capabilities inside that environment.

Personal AgentOS is not a replacement for macOS or Linux, and it is not a host kernel, hypervisor, or general-purpose operating system. The host OS still owns hardware, processes, devices, and ordinary application execution. Personal AgentOS is the persistent AI layer running on an owner-controlled host or isolated owner runtime.

It is also **not a coding harness or agent-swarm framework**. Coding automation and multi-agent orchestration can be capabilities or runtimes that run through Personal AgentOS, but they do not define the product.

## Architecture thesis

The key design choice is to separate:

1. **owner-authoritative state and policy** that must survive any one agent/runtime;
2. **installable package/distribution metadata** that describes capabilities but does not grant authority;
3. **replaceable workers/runtimes** that perform bounded Work;
4. **experience surfaces** that let the owner converse, approve, inspect, discover, and operate the system.

The kernel is **agent-independent**. The product and marketplace may be **agent-centric**.

```text
                              OWNER
                                |
                    conversation / work / approval
                                |
+-------------------------------------------------------------------+
|                         PERSONAL AGENTOS                           |
|                                                                   |
|  Owner plane                                                      |
|  - identity and policy                                            |
|  - personal Context and Memory authority                          |
|  - owner data and managed workspace                               |
|  - Grants and approvals                                           |
|  - Work/Event state, Artifact, Evidence, recovery and audit       |
|                                                                   |
|  Capability plane                                                 |
|  - tools and connectors                                           |
|  - capability registry                                            |
|  - Runtime Adapter boundary                                       |
|                                                                   |
|  Distribution plane                                               |
|  - AgentPackage / Package Manager                                 |
|  - Registry: identity/version/digest/trust/advisories             |
|  - Marketplace/Discovery: search/ranking/reviews/commerce         |
|  - compatibility import/adapters                                  |
|                                                                   |
|  Experience plane                                                 |
|  - local conversation UI                                          |
|  - Telegram / companion where supported                           |
|  - package inspect/install/permission/discovery surfaces          |
+--------------------------------+----------------------------------+
                                 |
                         bounded Work contract
                                 |
           +---------------------+-----------------------+
           |                     |                       |
         Codex              Claude Code               Ruflo /
        worker                worker                other/local
           |                     |                       |
         tools                 tools                  nested agents
```

The important ownership rule is that everything above the worker boundary remains authoritative when a worker changes. A model, coding agent, AgentPackage, Registry, Marketplace, or orchestration framework must not become the source of truth for canonical owner Memory, Grants, Work transitions, approval history, recoverable Work state, or retained Evidence.

## Kernel primitives

Personal AgentOS defines ten owner-level semantic primitives. Concrete schema/version work is owned by [D-AP-01 / #334](https://github.com/Jongtae/personal-agentos/issues/334); this architecture defines their responsibility boundaries.

### Owner

The human principal whose Personal AgentOS state is being protected. Owner identity, policies, devices/runtime claims, preferences and trust settings are not delegated to a package or marketplace.

### Context

Task-scoped, attributable information assembled for a specific Work item. Context is ephemeral/bounded by default and must not be confused with durable Memory.

### Memory

Durable owner knowledge with source/provenance, confidence, sensitivity, retention/expiry, supersession and deletion semantics. Third-party packages do not directly own or mutate canonical Memory by default.

### Artifact

A durable result of Work—document, code, image, spreadsheet, structured data, draft, report, etc.—with provenance and ownership independent of the package/runtime that produced it.

### Capability

A typed ability that AgentOS policy can reason about, independent of one package/runtime implementation. Examples include web research, file reading, spreadsheet creation, calendar drafting, code editing or message sending.

### Runtime

A replaceable execution environment/adapter that performs bounded Work: model provider, Codex, Claude Code, local model, script/API executor, human-mediated executor, or delegated framework such as Ruflo.

### Grant

Explicit authority over a resource/action/scope/destination/time/budget. Grants are issued by AgentOS policy/owner, not by the requesting package or runtime.

### Work

Durable execution lifecycle containing goal, package/capability/runtime identity, ContextSnapshot, effective Grants, approvals, checkpoints, Artifacts, Evidence, budgets, result and recovery state.

### Event

Typed trigger such as user action, schedule, file change, connector notification or system event. An Event may cause policy evaluation and Work creation; the Event itself does not grant consequential action authority.

### Evidence

Retained record of what ran, which exact package/runtime revision was used, what context/grants/tools/destinations were involved, what changed, and whether validation/approval occurred. Evidence must distinguish mock/fixture/local/external operating observations.

## AgentPackage

An **AgentPackage** is the installable product unit presented to the user as an agent/app/capability bundle. It is not a privileged authority domain and is not another OS.

The manifest is expected to declare, in a machine-verifiable form:

- package ID, publisher, version and compatible AgentOS API;
- capabilities/actions and runtime/model requirements;
- filesystem/data scopes and network destinations;
- secret/connector references without embedding raw credentials;
- Memory read policy and write-candidate policy;
- Event/background subscriptions;
- time/cost/resource budgets;
- consequential-action approval requirements;
- Artifact inputs/outputs;
- dependencies and sandbox profile;
- health check and migration behavior;
- install/update/rollback/remove expectations;
- licence, provenance, digest/signature/SBOM metadata where supported.

The package describes *requested potential authority*. Effective authority exists only after AgentOS resolves current policy and Grants for a specific Work item.

## Package lifecycle and authority

The lifecycle is staged by design:

```text
discovered
  -> inspected
  -> verified
  -> staged
  -> health_checked
  -> installed_disabled
  -> enabled/connected as separately allowed
  -> running only under Work-scoped Grants
  -> updated or rolled_back
  -> disabled/quarantined
  -> uninstalled
```

The following are separate states and must never be collapsed:

`downloaded != installed != enabled != connected != authorized-for-action`

Installing a package never creates or widens a Grant. Connecting a credential never authorizes every action that credential can technically perform. Event subscription never authorizes the triggered action. Trust tier never overrides per-action authority.

An update that expands permissions, data scope, external destinations, Memory behavior, background/Event behavior, budgets, dependencies or consequential actions requires a fresh policy/owner decision before the new authority becomes effective.

Failed health checks must not activate a package. Failed updates must preserve or restore a known-good state where the package lifecycle supports rollback. Package disable/quarantine/uninstall must revoke package-scoped active authority while preserving owner-owned Artifacts and retained Evidence according to policy.

## Context and Memory boundary for third-party packages

A Work item receives a **ContextSnapshot** assembled by AgentOS from owner-authorized sources. The package/runtime receives only the bounded context required for that Work.

Complete conversations do not automatically become permanent Memory. A third-party package may return a **MemoryCandidate** with source, confidence, sensitivity, expiry/retention and supersession information. AgentOS policy/owner decides whether it becomes canonical Memory.

Package-local/runtime-local memory may exist as an implementation detail when declared, but it is subordinate to the package boundary, cannot silently become owner Memory, and must be removable/exportable according to lifecycle policy.

## Capability and Runtime contract

Capabilities and runtimes are intentionally decoupled. The same capability may have multiple runtimes; one runtime may expose multiple capabilities.

The common semantic boundary should support, at minimum:

- capability list/describe/prepare/invoke/cancel/health;
- Work create/get/lease/checkpoint/report/transition;
- Grant evaluate/list-effective/request-escalation;
- Evidence append/seal/query-redacted;
- bounded ContextSnapshot input;
- deadline, cost/resource budget, cancellation and idempotency;
- Artifact/result/Evidence/MemoryCandidate output.

A runtime may request an escalation but cannot mint/widen its own Grant. It may append current Evidence but cannot rewrite sealed history. It may propose Memory but not directly own canonical Memory. Final Work completion is validated by AgentOS policy/evidence, not self-declared by the worker.

This allows simple APIs, Codex, Claude Code, local models, MCP-backed workers, human-mediated workers, and multi-agent frameworks to share one owner-authority model.

### Ruflo's place

Ruflo is a candidate **delegated Runtime Adapter**. Its internal swarm routing, agents and memory are package/runtime-local implementation details. Any durable Memory proposal returns through MemoryCandidate; nested agents/tools cannot exceed the parent Work Grant. Removing or swapping Ruflo must not remove owner state or rewrite Work/Evidence history.

## Distribution plane

### Package Manager

The local Package Manager owns the lifecycle of an exact AgentPackage revision: validate, verify, stage, health-check, install, enable/disable coordination, update, rollback, quarantine and uninstall. It cannot invent owner authority.

### Registry

The Registry is the identity/integrity metadata plane for packages. It may expose:

- publisher namespace/identity;
- immutable exact package version and digest;
- AgentOS API/runtime compatibility;
- signature/provenance/SBOM metadata;
- trust/evaluation metadata;
- advisories, revocation and quarantine;
- optional package-binary location.

Registry records must not contain private owner Context, Memory or Work content.

### Marketplace / discovery

Marketplace/discovery may offer search, recommendations, ranking, reviews, editorial curation, install-base metrics, evaluation summaries and future commercial metadata. Those signals are useful for discovery but are not security authority.

Popularity or ratings cannot override invalid signatures, revoked releases, package quarantine, current AgentOS policy or required owner approval. Raw private owner prompts/context should not be required for marketplace search; discovery should prefer structured/minimised capability metadata.

### Trust is multidimensional

Trust signals should remain separate rather than collapsing into one misleading badge:

- publisher identity;
- package signing/integrity;
- build provenance/SBOM;
- static policy/schema verification;
- behavioral conformance/evaluation;
- permissions/data-destination risk;
- update/incident/revocation history;
- user/expert reviews and install base;
- curator status.

A signed package can still be malicious or unsafe. A popular package can still require excessive authority. `Verified` must always state what was verified.

## Compatibility and ecosystem strategy

The Agent Distribution Platform should not wait for a brand-new native ecosystem before becoming useful. Existing ecosystems may be wrapped/imported when their metadata and authority can be mapped deterministically to AgentOS semantics.

Priority compatibility directions include MCP and selected official OpenAI/Codex and Claude skill/plugin formats. A foreign package is still subject to AgentOS manifest validation, Grants, sandbox/network policy, Evidence, update review and Memory boundaries. Foreign lifecycle hooks or hidden authority fail closed or are marked partially unsupported.

A2A-style delegated agents can be treated as external capabilities/runtimes under the same Work/Grant/Evidence model rather than as peers with implicit owner authority.

## Bootstrap/reference agents

Early Personal AgentOS may include a small number of bundled reference packages such as General Assistant, Files, Research and Coding. They are analogous to bootstrap/reference applications: enough to make the platform useful and demonstrate contracts while the ecosystem grows.

Bundled packages must use the same public Package/Runtime/Grant contracts as third-party packages. They must not receive hidden first-party privileges simply because they ship with the OS.

## Autonomous capability acquisition

Capability acquisition is a separate axis from action authority. A future staged model is:

- **L1** owner manually selects/installs;
- **L2** AgentOS recommends a candidate for an unmet capability;
- **L3** AgentOS creates an exact install plan and asks owner approval;
- **L4** trusted low-risk packages may install under standing policy while enable/grants remain separately governed;
- **L5** a package may request another capability through the kernel, never by bypassing package/policy controls.

The first Agent Distribution Platform MVP does not require L4/L5. Automatic acquisition must never silently accept new external data destinations, permission expansion, legal/vendor terms, payments or human-only identity/MFA/CAPTCHA gates.

## Durable state versus replaceable workers

Personal AgentOS should keep these concepts durable and owner-controlled where implemented:

- Owner identity/policy, Grants and connection references;
- explicit personal Context/Memory records;
- owner material, managed-workspace results, Artifacts and provenance;
- Work/Event state, approvals, Evidence, recovery and audit;
- package declarations and exact installed-version records;
- capability/runtime bindings and policy boundaries.

The following remain replaceable behind explicit boundaries:

- reasoning/model providers;
- Codex, Claude Code, local model or another execution runtime;
- Ruflo or another multi-agent framework;
- connectors, specialist agents and AgentPackages;
- Registry/Marketplace implementations;
- conversation and companion interfaces.

Engine/package replacement must not require reconstructing the owner's AI life from prompt history.

## Services are above the owner plane

A personal AI OS can expose services such as file knowledge, research, coding, communication, scheduling or other automations. These capabilities use the same owner state, Grant, Work/Event, Artifact and Evidence model; they are not separate owners of personal data.

The repository's current first usable slice is the **file-and-folder personal workspace**. That slice proves an important OS property: approved material and reusable results survive individual conversations and restarts while remaining inside explicit data boundaries. Future packages/services must reuse the same ownership model instead of creating isolated agent silos.

## Product runtime versus development harness

This repository also contains machinery used to build Personal AgentOS: GitHub issues, issue-linked branches, pull requests, CI, the Goal Execution Contract, development Constitution, and a state-driven implementer/reviewer handoff loop. Those mechanisms are **repository development infrastructure**.

The development process may adapt ideas from GitHub Spec Kit (constitution/spec/plan/tasks/converge), BuilderMethods Agent OS (relevant standards/context injection), and Open AgentOS-style explicit states/authority/receipts. Those are development-governance patterns, not Personal AgentOS runtime dependencies.

They must not be confused with the end-user runtime. Their presence proves how this repository is developed; it does not make GitHub, a Codex development loop, or a software-delivery harness part of the personal AI OS product contract.

## Current implementation boundary

The file-and-folder workspace program [#314](https://github.com/Jongtae/personal-agentos/issues/314) is complete. The first integrated implementation merged in [PR #320](https://github.com/Jongtae/personal-agentos/pull/320), and the program closeout merged in [PR #324](https://github.com/Jongtae/personal-agentos/pull/324).

Current evidence covers the scoped local-file flow with deterministic adapters and temporary local folders: read-only reference grants, scoped managed-workspace writes, original/derived provenance, reuse after restart, and separation of rebuildable indexes from durable work state. It does **not** by itself prove live operation of an external model, Telegram, Google Drive/OAuth, a recurring scheduler, personal folders, AgentPackage installation, Registry, Marketplace, Ruflo, or autonomous capability acquisition.

The Agent Distribution Platform epic [#333](https://github.com/Jongtae/personal-agentos/issues/333) and child issues are planned successors. Creating or documenting them does not activate implementation. Historical capability-discovery contract D-MP2-02 remains historical/read-only authority; future distribution work extends it through successor contracts instead of retroactively widening it.

Optional Drive work and the public information-site publication remain deferred from the core path unless separately reactivated by the owner.

## Design invariants

1. **One owner, one durable personal state.** Personal state belongs to the owner-controlled AgentOS runtime, not to an external model, package, Registry or Marketplace.
2. **Kernel is agent-independent.** Product presentation may center agents, but kernel semantics are Owner/Context/Memory/Artifact/Capability/Runtime/Grant/Work/Event/Evidence.
3. **Install is not authorization.** Download/install/enable/connect/action authority are distinct states.
4. **Local-first does not mean local-only.** External engines/services/packages may be used, but every transmission is a separate policy boundary and must be described truthfully.
5. **Minimum authority.** Packages, tools, connectors, runtimes and nested agents receive only Work-scoped authority required for the task.
6. **Consequential actions require explicit authority.** External sends, payments, destructive file/account changes, privilege expansion or new data destinations cannot be inferred from install/read access/conversation intent.
7. **Memory remains owner-authoritative.** Third-party packages propose MemoryCandidates; they do not silently create permanent owner Memory.
8. **Recoverable long-running Work.** Work state and Evidence survive a model turn, supported process restart, package update, worker replacement or rollback without duplicating consequential effects.
9. **Exact revisions and provenance.** Package/runtime/version/digest and relevant supply-chain metadata are attributable in Evidence.
10. **Trust is not a single badge.** Identity, integrity, provenance, behavioral evaluation, popularity, permissions risk and incidents remain distinguishable.
11. **Portable owner state.** Owner state can move between supported runtimes without turning credentials, provider sessions, package caches or marketplace accounts into the durable identity.
12. **Evidence before capability claims.** A design, mock, fixture, issue, package listing, signature or development harness is not evidence of live external operation.
