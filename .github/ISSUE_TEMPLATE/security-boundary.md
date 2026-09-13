---
name: Security / authority boundary
about: Threat-model and harden a Personal AgentOS trust, permission, sandbox, or external-action boundary
labels: ""
---

## User outcome

What owner capability becomes safer, more inspectable, or more recoverable?

## State / activation

Planned, active, blocked, or review-only? Name the active delivery-plan entry and explicit owner activation when executable. **Creating this issue does not activate it.**

## Constitution / architecture boundary

Relevant Development Constitution principles, architecture contracts, and predecessor evidence:

## Assets and trust boundaries

Owner data/state, package/runtime, filesystem, network, secrets, connectors, Registry/Marketplace, external recipients and human gates involved:

## Threat actors / abuse cases

Consider at minimum where relevant:

- prompt/instruction injection;
- malicious or compromised AgentPackage/runtime;
- confused deputy / excessive agency;
- Grant/capability escalation;
- cross-package or cross-capability leakage;
- secret exfiltration/log leakage;
- Memory poisoning/provenance spoofing;
- malicious update/dependency substitution/typosquatting;
- replay/stale approval or duplicated consequential action;
- background persistence and Event abuse;
- Registry/Marketplace misinformation or publisher takeover.

## Authority model

Exactly which actions/resources/destinations are allowed, denied, approval-gated, or impossible? Who may request escalation and who alone may grant it?

## Isolation / containment

Sandbox, filesystem/process/network boundaries, capability tokens/broker, secret mediation, quarantine/kill switch, rate/budget limits and failure containment:

## Update / revocation / recovery

Permission diff, signature/provenance re-evaluation, advisory/revocation, rollback, disable/quarantine, uninstall, restart and preservation of owner Artifacts/Evidence:

## Acceptance criteria

- [ ]

## Negative test matrix

List deterministic attacks/violations that must fail closed and the observable evidence for each.

## Non-goals

## Evidence / independent review

Required static/schema/fixture/local/live evidence classes, independent reviewer role, and claims explicitly not proven by this work:

## Branch

`codex/<issue>-<slug>`
