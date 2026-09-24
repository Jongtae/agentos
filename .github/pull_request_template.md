## User outcome

## Runtime impact

## Goal / authority

Issue, active delivery-plan iteration, declared authority, dependencies, and non-goals:

## Constitution / specification alignment

Relevant [Development Constitution](../docs/development-constitution.en.md) principles, product spec/contract, and architecture decisions:

## What changed


## Existing solutions review (Adopt / Adapt / Build)

Required before non-trivial implementation that introduces or replaces a component, abstraction, integration, dependency, framework, or commodity infrastructure. Start with internal repository reuse. For a pure bug fix/data/content change that introduces none of those, set the decision to `N/A` and give a concrete reason.

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

## Authority / threat model

What owner data, Grants, packages/runtimes, filesystem scopes, network destinations, secrets, external recipients/actions, or human gates are involved?

## AgentPackage / runtime delta

Complete when package/runtime/distribution behavior changes; otherwise write `N/A`.

- exact package/runtime/schema revision or digest:
- permission / owner-data scope delta:
- external network / data-destination delta:
- Memory read / MemoryCandidate behavior delta:
- Event / background-subscription delta:
- secrets / connector delta:
- cost / time / resource-budget delta:
- consequential-action / approval delta:
- dependency / sandbox delta:

## Supply-chain / trust evidence

Complete when relevant; otherwise write `N/A`.

Publisher identity, signature/integrity, provenance/SBOM, static verification, behavioral/conformance evaluation, advisories/revocation/quarantine, and what each signal does **not** prove:

## Lifecycle / recovery impact

Install, staged health check, enable/disable, update, rollback, quarantine, uninstall, restart/recovery, and owner Artifact/Evidence preservation impact:

## README / localization impact

Complete when any public README or README visual changes; otherwise write `N/A`.

- canonical `README.md` changed:
- `README.ko.md`, `README.ja.md`, `README.zh-CN.md` updated for semantic/structural parity:
- illustrative product direction vs current supported slice remains explicit:
- embedded-text visuals are language-neutral or localized:
- `python3 scripts/verify_readme_localization.py`:

## Validation

Positive tests, negative authority/security tests, schema/conformance tests, recovery/idempotency tests, and repository-required validation:

## Evidence class / operating validation

Explicitly distinguish design, schema/static validation, mock/fixture, local deterministic operation, authenticated connection check, and live external operating observation. Do not claim a stronger class than observed.

## Evidence and completion audit

Map each acceptance criterion to merged artifacts, required CI, any risk-triggered review artifacts, and tracker/roadmap/ledger closeout. Do not treat a local test, signature, package manifest, closed issue, branch, or PR alone as completion.

## Independent review escalation

- material security/authority boundary changed: `yes / no`
- trigger, if yes: filesystem/network/secret/connector/runtime authority; OAuth/credential boundary; consequential-action approval; sandbox/isolation/privilege; private-data egress/recipient; package/supply-chain trust or install/update authority; canonical owner-state/authority ownership; weakened/removed safety invariant
- independent review required: `yes / no`
- review head / findings, if required:
- post-review remediation changed the triggering boundary or introduced a new trigger: `yes / no / N/A`
- re-review required: `yes / no / N/A`

Do not mark review required solely for final closeout, ordinary recovery that preserves authority semantics, UI/conversation/Settings work, non-authority bug fixes/refactors/docs, or tracker/ledger reconciliation. When review is required, state whether the reviewer was independent of the implementation role.

## Data and security impact

## Known limitations / follow-up

## Historical authority / migration

If this supersedes or extends a prior contract, identify it and explain why the old evidence remains historically accurate rather than being retroactively widened.

Closes #
