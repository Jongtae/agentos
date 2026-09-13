---
name: Runtime Adapter change
about: Design or implement a bounded execution Runtime Adapter
labels: ""
---

## User outcome

What capability becomes replaceable/portable through this runtime without moving owner state into the runtime?

## State / activation

Planned, active, blocked, or review-only? Name the active delivery-plan entry and explicit owner activation when executable. **Creating this issue does not activate it.**

## Constitution / spec

Relevant Development Constitution principles, D-RT/common-runtime contract, parent package contract, and predecessors:

## Runtime identity / revision

Runtime/framework/provider identity, exact revision/version where relevant, transport and compatibility assumptions:

## Work contract

Describe ContextSnapshot input, capability invocation, effective Grants, deadlines/budgets, cancellation, idempotency/checkpoints, Artifact/result output, Evidence, and MemoryCandidate output.

## Authority boundary

- What can this runtime read/write?
- Which AgentOS capabilities/tools can it invoke?
- Can it start nested agents/tools, and how are parent Work Grants projected?
- What authority can it request but never grant itself?
- What canonical state is explicitly forbidden from runtime ownership/mutation?

## Secrets / external destinations

Credentials, connector references, network destinations, redaction and evidence rules:

## Runtime-local state / memory

What may persist locally to this adapter/package, how it is isolated/exported/removed, and why it is not canonical owner Memory:

## Failure / recovery

Timeout, cancellation, crash/restart, duplicate/retry, partial external effect, quarantine/disable and runtime replacement behavior:

## Acceptance criteria

- [ ]

## Negative conformance cases

At minimum cover Grant widening, direct canonical-Memory mutation, sealed-Evidence rewrite, nested-worker escape, deadline/cancel failure, secret/log leakage and unsupported capability claims.

## Non-goals

## Validation / evidence plan

Deterministic fixtures first; state separately what live provider/runtime observation, if any, is actually required for completion.

## Branch

`codex/<issue>-<slug>`
