# D-AP-01 — Core Primitives and AgentPackage v0.1

## Status and authority

This is the canonical English specification for the Personal AgentOS v0.1 Core
Primitive and AgentPackage data contracts. It is a design and schema contract,
not a package manager, runtime, Registry, Marketplace, credential flow, or live
operation claim. The Korean companion is owner-facing explanatory material and
does not create a second normative source.

This specification is subordinate to the [Development Constitution](development-constitution.en.md),
the [Personal AgentOS Architecture](personal-agentos-architecture.en.md), and the
[Agent Distribution Platform Foundation](agent-distribution-platform-foundation.en.md).
GitHub issue #334 is its bounded delivery contract.

Normative terms **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, and **MAY** have
their ordinary RFC 2119 meanings.

## Outcome and non-goals

v0.1 freezes portable, framework-neutral contracts for Owner, Context, Memory,
Artifact, Capability, Runtime, Grant, Work, Event, Evidence, and AgentPackage.
AgentOS remains the authority for durable owner state, policy, approvals,
transitions, recovery, and sealed Evidence. Packages and runtimes are bounded
workers that may declare or request needs but cannot approve those needs.

This contract does not implement download, install, enable, connection,
execution, update, rollback, Registry, Marketplace, OAuth, credentials, Ruflo,
MCP/OpenAI/Claude import, or autonomous acquisition. It does not activate
#335–#346.

## Inventory and contract map

Before v0.1, runtime code and earlier contracts had useful but feature-specific
representations for Personal Space records, capabilities, approvals, jobs,
events, and evidence. They did not constitute a single portable AgentPackage
schema family. Historical D-MP2-02 defined only owner-local, read-only reviewed
recommendations and explicitly excluded download, installation, activation,
Grants, credentials, and execution. v0.1 extends the architecture prospectively
and does not reinterpret that historical evidence.

No source contradiction requiring authority expansion was found. Three concrete
legacy incompatibilities require an explicit non-migration boundary: the legacy
`PluginRegistry.install` model records an enabled host-action declaration; the
reviewed catalogue uses symbolic fixture digests that are not cryptographic
SHA-256 values; and the legacy `CapabilityRegistry` stores declared scope lists
alongside lifecycle configuration. None is a conforming v0.1 AgentPackage,
immutable digest, or effective Work-scoped Grant. Existing behavior and tests
remain historical implementation evidence and are not silently migrated or
relabeled by this design. A future mapping requires a separately activated,
reviewed implementation goal.

| Contract | AgentOS authority | Package/runtime participation | Durable/portable rule |
| --- | --- | --- | --- |
| Owner | identity and policy revision | receives opaque reference only | owner record excludes credentials and sessions |
| Context | selects and issues Work-scoped ContextSnapshot | consumes bounded snapshot | snapshot expires and is never canonical Memory |
| Memory | accepts/rejects canonical records and candidates | proposes MemoryCandidate only | candidate status is explicit; package-local memory is non-canonical |
| Artifact | owns state, provenance, retention, and recovery | produces declared output | exact Work/package/runtime lineage is retained |
| Capability | registers callable contract | package declares supplied actions | declaration never grants action authority |
| Runtime | registers and controls runtime state | executes bounded Work | runtime revision/digest is attributable and replaceable |
| Grant | issues, narrows, revokes, and evaluates | may request, never issue or widen | exact subject, Work, scopes, destination, and expiry are explicit |
| Work | owns lifecycle, leases, retry, cancellation, and completion | reports results/checkpoints | terminal state is validated by AgentOS |
| Event | orders and accepts lifecycle facts | emits permitted observations or requests subscriptions | an event cannot mutate authority by itself |
| Evidence | seals claims, observations, and evidence class | supplies observations | retained records identify exact revisions and cannot be rewritten |
| AgentPackage | validates manifest and compares requests to policy | declares identity, behavior, and requested authority | manifest is descriptive, never self-authorizing |

## Common envelope and references

Every v0.1 instance carries `schemaVersion: "0.1"`, a typed opaque `id`, and a
positive integer `revision` where it represents an AgentOS-owned record. IDs are
identifiers, not filesystem paths, URLs, secrets, or mutable display names.
Timestamps use RFC 3339 date-time values.

Security- or behavior-relevant cross-record links use an `ImmutableReference`:
`kind`, typed `id`, and at least one immutable selector (`revision` or
`digest`). Package-release and runtime-execution provenance MUST include both an
exact revision/version and a `sha256:` digest. Mutable tags such as `latest`,
ranges in exact-release positions, and a name without immutable selection are
invalid.

An object `revision` identifies an immutable AgentOS record revision. A
`contentDigest` hashes the referenced content bytes; a package/runtime `digest`
hashes the resolved release artifact bytes. These detached digests do not hash
the containing record and therefore do not create Work/Artifact/Evidence
reference cycles. v0.1 does not prescribe byte canonicalization for whole JSON
records and a conforming verifier MUST NOT pretend that an identifier-shaped
digest proves bytes it did not actually hash.

`Provenance` identifies the creating Work and, when a worker participated, the
exact package and runtime references plus source references. Omitting a worker
reference is allowed only when no package/runtime participated. Provenance does
not itself establish trust or authority.

All schema objects reject unknown fields. Extension data is permitted only in a
field explicitly defined for that purpose by a later compatible schema. A
consumer MUST reject an unknown required field, unknown enum member, unresolved
reference, invalid digest, or unsupported schema version; it MUST NOT guess.
Parsing also fails closed on duplicate JSON member names, `NaN`, infinity, and
other non-JSON values. Date-time and URI formats are assertions in the v0.1
verification profile rather than annotation-only hints.

## Core primitive semantics

### Owner

Owner is the local human principal and policy root. AgentOS creates and revises
the record. `authority` is always `agentos`; packages receive only a reference.
The record contains no password, token, provider session, or raw secret. A
suspended owner cannot acquire new effective authority.

### Context and ContextSnapshot

Context is represented at the worker boundary as a `ContextSnapshot` bound to
one Owner and one Work, with issue and expiry timestamps, classified items,
source/digest attribution, and explicit allowed uses. `canonicalMemory` is
always `false`. Possession of Context does not grant an action, filesystem,
network, secret, or Memory write. Expired or differently bound snapshots fail
closed. Full conversation history is not implied by a snapshot.

### Memory and MemoryCandidate

`MemoryRecord` is canonical only when its `authority` is `agentos` and
`canonical` is `true`. A package/runtime output uses `MemoryCandidate`, whose
`canonical` value is always `false`, whose status begins as `proposed`, and
whose exact Work/package/runtime provenance is required. Only AgentOS policy may
accept a candidate and create or revise a separate canonical MemoryRecord.
Acceptance never mutates the candidate into an owner-authoritative record.
Package/runtime-local state remains local and non-canonical even if durable.

### Artifact

Artifact is an owner-owned result or material record with content digest,
media/type metadata, lifecycle state, retention policy, and Provenance.
`original`, `derived`, `draft`, and `final` roles remain distinguishable.
Packages may produce declared artifacts but cannot transfer ownership, erase
retained Evidence, or overwrite an original merely by declaring an output.

### Capability

Capability is an AgentOS registration of a callable action contract. It binds a
stable capability ID to the exact package release that supplies it, the accepted
input/output schema references, consequential-action classification, requested
scope categories, and compatible runtime kinds. Registration is not enablement
or a Grant. Undeclared actions cannot be invoked.

### Runtime

Runtime is an AgentOS registration of a replaceable execution adapter and its
exact revision/digest. AgentOS owns registration state and health observations.
A runtime receives one Work, a ContextSnapshot, and the effective subset of
Grants. It cannot mint Grants, mutate canonical Memory, rewrite sealed Evidence,
or declare final Work completion. Nested workers receive no more than the
parent Work authority.

### Grant

Grant is the only v0.1 authority record. It is issued by AgentOS from an
attributable owner/policy decision and binds an exact subject to one Work,
allowed actions/resources/destinations, validity interval, and status. Empty or
ambiguous scope, wildcard network destination, raw filesystem breadth, secret
value, action not registered by the Capability, stale revision, or requested
scope wider than the Grant fails closed. A package manifest contains requests,
not Grants. Installation, enablement, connection, conversation intent, and an
Event cannot create or widen a Grant.

Schema constants such as `authority: "agentos"` and `issuedBy: "agentos"`
prove only structural conformance of a fixture. They do not authenticate an
issuer. A future implementation MUST establish origin and integrity inside the
owner-controlled trust boundary before treating a record as effective.

### Work

Work is the AgentOS-owned durable execution state. It binds Owner, Capability,
ContextSnapshot, exact package/runtime, effective Grant references, budgets,
deadline, idempotency key, attempts, lease/checkpoint metadata, and recovery.
AgentOS alone validates transitions:

```text
queued -> authorized -> running -> {succeeded | failed | cancelled | timed-out}
running -> paused -> running
failed/timed-out -> queued (only under bounded retry and idempotency policy)
```

No other transition is valid. A worker report is an observation; `succeeded`
requires AgentOS validation and Evidence. Cancellation/revocation stops further
authority. Retry MUST NOT duplicate a consequential effect.

### Event

Event is an immutable, ordered fact or request bound to Owner and normally Work.
It identifies emitter, sequence, type, classification, payload digest, and
Evidence when applicable. Package subscriptions are declarations reviewed by
AgentOS. An Event is neither a Grant nor proof that an action occurred.
Background delivery requires declared policy, a current Grant, and budget.

### Evidence

Evidence is an AgentOS-sealed record of a claim and attributable observations.
It names its evidence class: `normative-design`, `schema-static`,
`deterministic-fixture`, `repository-ci`, `local-operation`,
`authenticated-connection`, or `live-external-operation`. Stronger classes may
not be inferred from weaker ones. Exact Work/package/runtime provenance is
required when relevant. Packages may submit observations but cannot seal,
rewrite, downgrade, or delete retained Evidence.

## AgentPackage v0.1 manifest

The manifest is a closed, declarative object with these required groups:

- exact package/publisher identity, semantic version, release revision and
  SHA-256 digest;
- supported AgentOS schema/API compatibility, without mutable `latest` values;
- declared capabilities/actions and consequential-action classification;
- runtime kinds/API requirements and exact bundled runtime identity where used;
- requested owner-data categories, symbolic filesystem scopes, explicit network
  destinations, mediated secret/connector references, Context selectors, and
  MemoryCandidate behavior;
- Event/background subscriptions, budgets, and approval classes;
- produced Artifact declarations, exact dependencies, sandbox requirements,
  declarative health checks, and lifecycle/recovery behavior;
- publisher identity, signature metadata, source, build provenance, and SBOM
  digests as separate trust signals.

Raw secret values, shell commands, home-directory/root grants, wildcard hosts,
undeclared destinations, direct canonical-Memory writes, self-issued Grants,
implicit background operation, unpinned dependencies, and install-time
authorization are not representable as valid v0.1 manifests.

Identity/signature/provenance fields support attribution and integrity checking;
they do not prove behavioral safety. Popularity, rating, or Registry presence is
not an authority input.

## Package lifecycle contract

The lifecycle is descriptive in v0.1; no implementation is supplied:

```text
discovered -> downloaded -> verified -> staged -> installed-disabled
installed-disabled -> enabled
enabled -> connected (when a connector is required)
enabled/connected + current Work Grant -> authorized-for-action
enabled/connected -> disabled or quarantined
installed-disabled/disabled/quarantined -> uninstalled
```

`downloaded != installed != enabled != connected != authorized-for-action`.
Install defaults to `installed-disabled` and `installCreatesGrant` is always
false. Enablement does not imply connection; connection does not imply action
authority. Update is a new exact release evaluated against a permission,
data/egress, Memory/Event, dependency, budget, sandbox, approval, and
consequential-action diff. Any expansion needs a new decision. Failed health
checks never activate a release. Rollback selects a previously verified exact
revision and does not restore expired/revoked Grants. Disable, quarantine, and
uninstall revoke package-scoped active authority while owner Artifacts and
retained Evidence survive according to policy.

## Compatibility and migration

v0.1 uses JSON Schema Draft 2020-12 and stable `$id` values under
`https://personal-agentos.dev/schemas/v0.1/`. Schema and manifest
`schemaVersion` are exactly `0.1`.

- Patch-level documentation clarifications may tighten prose only when the
  accepted instance set and authority meaning do not change.
- A backward-compatible additive field requires a new schema version because
  v0.1 rejects unknown fields. A consumer supports it only after explicit
  opt-in; silently ignoring it is forbidden.
- Removing/renaming a field, widening authority meaning, changing defaults,
  changing enum semantics, or accepting a formerly invalid authority request is
  incompatible and requires a new minor/major schema family plus migration.
- Exact package dependencies use an exact semantic version and digest. AgentOS
  API compatibility uses bounded minimum/maximum versions; an unsupported or
  contradictory range is rejected.
- Migration is copy/validate/commit: retain the source record, produce a new
  revision with migration Provenance, validate every reference and invariant,
  and atomically select it only after success. Failure leaves the prior record
  authoritative and records Evidence. Migration cannot create a Grant, accept a
  MemoryCandidate, mark Work complete, or upgrade evidence class.
- Downgrade is unsupported unless a later contract defines a lossless mapping.
  Consumers must retain unknown newer records without executing them when safe,
  or quarantine them when retention cannot be guaranteed.

## Machine verification and evidence boundary

Schemas live in `schemas/v0.1/`; deterministic fixtures live below
`schemas/v0.1/fixtures/`. `scripts/verify_agentpackage_v01.py` validates all
schemas, requires every positive fixture to pass, and requires every negative
fixture to fail for its declared reason. Repository tests repeat those checks.

This produces normative-design, schema-static, deterministic-fixture, review,
and CI evidence only. It does not prove package download, installation,
execution, Registry/Marketplace service, external runtime connection, or live
operation.
