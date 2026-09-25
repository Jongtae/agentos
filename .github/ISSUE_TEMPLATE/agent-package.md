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

Required when this issue proposes a new design, contract, architecture element, loop, component or framework adoption, and before non-trivial implementation that introduces or replaces a component, abstraction, integration, dependency, framework, or commodity infrastructure. Start with internal repository reuse. For a pure bug fix/data/content change that introduces none of those, set the decision to `N/A` and give a concrete reason.

- problem/boundary:
- internal repository candidates:
- search evidence (paths/symbols/docs checked):
- standard-library/platform candidates:
- official SDK/reference/standard candidates:
- mature open-source/framework candidates:
- maintenance/security/supply-chain fit:
- licence fit:
- runtime/deployment/compatibility fit:
- decision: `Adopt / Adapt / Build / N/A`
- why rejected candidates are insufficient:
- AgentOS-owned policy/authority boundary kept outside the dependency:
- N/A reason:

## Acceptance criteria

- [ ]

## Non-goals

## Dependencies

## Validation / evidence plan

Positive cases, fail-closed negative cases, restart/recovery/idempotency, current CI, exact evidence class, and independent review only when the Development Constitution's material security/authority escalation criteria apply:

## Historical authority / migration

Prior contracts/evidence that remain historically accurate and must not be retroactively widened:

## Branch

`codex/<issue>-<slug>`
