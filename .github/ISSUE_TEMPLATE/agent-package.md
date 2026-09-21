---
name: AgentPackage change
about: Design or implement an AgentPackage, Package Manager, Registry, or package lifecycle change
labels: ""
---

## User outcome

What can the owner safely do after this work that they cannot do now?

## State / activation

Planned, active, blocked, or review-only? Name the active delivery-plan entry and explicit owner activation when executable. **Creating this issue does not activate it.**

## Constitution / spec

Relevant Development Constitution principles, architecture/foundation docs, parent epic, and predecessor contracts:

## Package identity / compatibility

Package/schema/API identifiers, publisher/version/digest expectations, supported AgentOS/runtime versions:

## Requested capabilities and authority

- capabilities/actions:
- filesystem/data scopes:
- network destinations:
- secrets/connectors:
- Memory read selectors / MemoryCandidate writes:
- Event/background subscriptions:
- time/cost/resource budgets:
- consequential actions requiring approval:

## Lifecycle

Describe expected behavior for:

`inspect → verify → stage → health-check → installed-disabled → grant/connect/enable → run → update/rollback → disable/quarantine → uninstall`

## Trust / supply-chain model

Publisher identity, signature/integrity, provenance/SBOM, behavioural/conformance checks, advisories/revocation/quarantine, and what each signal does not prove:

## Threat model / negative cases

At minimum consider malicious package, permission expansion, secret exfiltration, undeclared egress, memory poisoning, prompt injection, dependency substitution, malicious update, confused deputy, replay/stale approval and package removal/recovery.


## Existing solutions review (Adopt / Adapt / Build)

Required when this work materially implements or replaces commodity infrastructure. Otherwise write `N/A`.

- problem/boundary:
- official SDK/reference/standard candidates:
- mature open-source candidates:
- maintenance/security/supply-chain fit:
- licence fit:
- runtime/deployment/compatibility fit:
- decision: `Adopt / Adapt / Build`
- why rejected candidates are insufficient:
- AgentOS-owned policy/authority boundary kept outside the dependency:

## Acceptance criteria

- [ ]

## Non-goals

## Dependencies

## Validation / evidence plan

Positive cases, fail-closed negative cases, restart/recovery/idempotency, current CI, independent review and exact evidence class expected at completion:

## Historical authority / migration

Prior contracts/evidence that remain historically accurate and must not be retroactively widened:

## Branch

`codex/<issue>-<slug>`
