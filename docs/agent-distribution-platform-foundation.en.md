# Agent Distribution Platform Foundation

## Status

This is the canonical **foundation and migration plan** for the planned Agent Distribution Platform program. It translates the current Personal AgentOS architecture into a staged body of future design and implementation work.

It is not a shipped-capability claim and does not activate any child issue. The executable work selector remains the Goal Execution Contract plus an explicitly owner-activated, goal-ready delivery-plan entry.

Parent epic: [EPIC-ADP-01 / #333](https://github.com/Jongtae/personal-agentos/issues/333).

## Thesis

> **Personal AgentOS = Personal AI Kernel + Agent Distribution Platform**

The kernel owns the durable personal state and authority model. The distribution platform makes third-party AgentPackages discoverable/installable while remaining subordinate to that kernel.

The platform should enable a future in which the quality of the Personal AgentOS experience is not limited by bundled agents. Bundled agents are bootstrap/reference applications. The durable value is the owner's environment plus an open ecosystem of capabilities that can be changed without rebuilding the owner's AI life.

## Authority boundary

The kernel remains authoritative for:

- Owner identity and policy;
- canonical Context/Memory semantics;
- Artifact ownership/provenance;
- Capability and Runtime registration;
- effective Grants and approvals;
- Work/Event lifecycle;
- retained Evidence, recovery and audit.

A package, runtime, Registry or Marketplace may request, describe or recommend authority. It cannot grant itself authority.

## Distribution components

### AgentPackage

Installable unit. Describes package identity, capabilities, runtimes, permissions/data scope, egress, secrets/connector references, memory policy, events/background behavior, budgets, approvals, artifacts, dependencies, sandbox, health, lifecycle, provenance and integrity metadata.

### Package Manager

Owner-local lifecycle mechanism. Validates and verifies exact revisions, stages them, performs health checks, records package state, coordinates enable/disable, applies update permission diffs, rolls back failures, quarantines unsafe revisions and uninstalls package-owned state while preserving owner artifacts/evidence.

### Registry

Package identity and release metadata authority. Resolves publisher/package/version/digest, compatibility, trust metadata, advisories/revocation/quarantine and optional package locations. It must not contain owner Context/Memory/Work content.

### Marketplace / Discovery

Search, recommendation, ranking, curation, reviews and future commerce. Marketplace signals help the owner find packages but do not grant execution authority and do not override kernel security policy.

### Trust / Verification

Trust is a set of evidence classes rather than a single badge: publisher identity, signature/integrity, build provenance/SBOM, static manifest checks, behavioral conformance/evals, permission risk, update history, incidents/revocation, user/expert reviews and curator status.

## Lifecycle

```text
discover
  -> inspect
  -> resolve exact version/digest
  -> verify integrity/trust metadata
  -> stage in isolated package area
  -> preflight + health check
  -> installed-disabled
  -> optional connection/credential setup
  -> owner/policy Grant + enable
  -> Work-scoped execution
  -> update with permission/data/egress diff
  -> rollback on failure
  -> disable/quarantine
  -> uninstall
```

The following are explicitly distinct:

`downloaded != installed != enabled != connected != authorized-for-action`

## Security invariants

1. Package install cannot create a Grant.
2. Runtime/package cannot mint or widen authority.
3. Package update cannot inherit old approval when authority requirements changed.
4. Exact package/runtime revision is attributable in Evidence.
5. External destinations are explicit policy data, not hidden implementation detail.
6. Secret references are mediated; raw secrets are not package metadata/evidence.
7. Third-party durable Memory writes are candidate-only by default.
8. Nested agents/tools inherit a subset of the parent Work authority.
9. Registry/Marketplace content is untrusted input, not executable policy.
10. Signature/provenance proves identity/integrity, not behavioral safety.
11. Quarantine/revocation overrides popularity/recommendation.
12. Owner Artifacts and retained Evidence survive package removal as policy requires.

## Development-framework adoption

### GitHub Spec Kit — adapt, do not depend

Adopt the discipline:

`Constitution -> Specify -> Plan -> Tasks -> Implement -> Converge`

Personal AgentOS extends it with explicit authority/threat modeling and evidence:

`Constitution -> Spec -> Authority/Threat Model -> Plan -> Tasks -> Implement -> Verify -> Converge`

Do not make Spec Kit a product runtime dependency.

### BuilderMethods Agent OS — adapt context/standards discipline

Use relevant-context/standards injection ideas for development so a worker receives only applicable product/security contracts. Do not make that framework the authority for personal Memory or package state.

### Open AgentOS-style governance — adapt explicit state and authority

Use explicit workflow states, role separation, live authority checks and receipts for repository development. GitHub workflow state is not the end-user Personal AgentOS Work state.

### Ruflo — optional Runtime Adapter

Treat Ruflo as one delegated execution implementation behind the common Runtime contract. Ruflo swarm state/memory is package-local/runtime-local and subordinate to AgentOS owner state.

### MCP / A2A / foreign skills — compatibility protocols

Treat these as ways to describe/connect/import capabilities, not as sources of owner authority. Unsupported/ambiguous foreign authority fails closed.

## Bootstrap strategy

A platform cannot wait for a large native ecosystem before being useful. The initial distribution may ship a small number of public-contract reference packages:

- General Assistant — basic conversation/work delegation;
- Files — local file/workspace operations under explicit Grants;
- Research — web/document research and attributable report artifacts;
- Coding — bounded project coding, testing and PR preparation.

They are reference/bootstrapping applications, not privileged kernel modules and not a claim of best-in-class agent quality.

Cold-start mitigation should prioritize deterministic wrappers/importers for existing ecosystems where official metadata and licensing permit it. MCP is a strong early compatibility target; selected OpenAI/Codex and Claude skills/plugins are subsequent targets. Imported packages receive the same Package Manager, Grant, sandbox, Memory and Evidence rules as native packages.

## Phased roadmap

### Phase A — Foundation contracts

- [#334](https://github.com/Jongtae/personal-agentos/issues/334) D-AP-01 — Core Primitives + AgentPackage v0.1.
- [#335](https://github.com/Jongtae/personal-agentos/issues/335) D-AP-02 — package trust/permission/lifecycle.
- [#336](https://github.com/Jongtae/personal-agentos/issues/336) D-MEM-01 — third-party Context/Memory semantics.
- [#337](https://github.com/Jongtae/personal-agentos/issues/337) D-SBX-01 — sandbox/supply-chain/capability broker.
- [#338](https://github.com/Jongtae/personal-agentos/issues/338) D-RT-01 — common Runtime Adapter.
- [#339](https://github.com/Jongtae/personal-agentos/issues/339) D-REG-01 — Registry/Marketplace separation.

**Exit condition:** schemas/contracts can be reviewed independently of one runtime/framework and negative cases are specified. No package execution is required for design completion.

### Phase B — Local package platform

- [#340](https://github.com/Jongtae/personal-agentos/issues/340) I-AP-01 — local validator + Package Manager.
- [#341](https://github.com/Jongtae/personal-agentos/issues/341) I-EVT-01 — Work/Event integration.
- [#342](https://github.com/Jongtae/personal-agentos/issues/342) I-SDK-01 — SDK/CLI/reference packages.

**Exit condition:** a deterministic locally signed fixture package can be validated, staged, installed-disabled, explicitly granted/enabled, executed under bounded Work, updated/rolled back and uninstalled with restart/recovery and evidence tests.

### Phase C — Ecosystem ready

- [#343](https://github.com/Jongtae/personal-agentos/issues/343) I-ECO-01 — MCP/OpenAI-Codex/Claude compatibility import.
- [#344](https://github.com/Jongtae/personal-agentos/issues/344) I-RT-RUFLO-01 — bounded Ruflo Runtime Adapter.

**Exit condition:** at least one foreign ecosystem representation and one sophisticated delegated runtime operate through the same AgentOS authority/evidence contracts in deterministic/local validation.

### Phase D — Registry ready

- [#345](https://github.com/Jongtae/personal-agentos/issues/345) I-REG-01 — local/open Registry + trust metadata.

**Exit condition:** exact package release resolution/trust/advisory metadata is demonstrable without sending private owner data to the Registry and without allowing Registry lookup to install/enable a package by itself.

### Phase E — Autonomous acquisition design

- [#346](https://github.com/Jongtae/personal-agentos/issues/346) D-AUTO-01 — acquisition levels L1-L5.

The first platform MVP does **not** require L4/L5 automatic installation. Owner-visible install plans and safe package lifecycle precede autonomy.

## Historical migration rule

Existing closed/deferred work is evidence, not raw material to rewrite.

The historical D-MP2-02 capability-discovery contract defined reviewed, read-only local recommendation and explicitly excluded marketplace/download/install/activation. It remains historical authority for that work. Agent Distribution Platform contracts are successors; they do not retroactively expand what D-MP2-02 implemented or proved.

Likewise, completed file-workspace evidence, deferred Drive work, repository handoff automation and deferred SITE-01 remain in their existing evidence classes/status.

## Do not implement yet

Until the corresponding child contract is goal-ready and activated, do not:

- launch a public Registry/Marketplace;
- add payments, revenue share or developer commerce;
- download/execute arbitrary third-party packages;
- give packages broad host shell/network/home-folder access;
- allow packages to write canonical Memory directly;
- automatically accept credentials/OAuth/legal/vendor terms;
- implement L4/L5 capability acquisition;
- adopt Ruflo or another framework as kernel authority;
- turn package popularity/rating into a permission decision;
- create a second conflicting workflow authority or scheduler.

## Evidence rule

A design, manifest, issue, package listing, signature, unit test or fixture proves only its own evidence class. Live external capability/package/registry/marketplace operation is claimed only when that exact operating path is configured and observed under current acceptance criteria.
