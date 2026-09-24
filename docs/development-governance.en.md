# Development Governance — Contract-First Delivery

## Purpose

AgentOS uses contract-first delivery with automated quality gates. It is designed to keep development fast, repeatable, and independent of a person manually exercising every feature or third-party service on every change.

## Incremental delivery

Follow [Incremental Delivery and Merge Handoff](incremental-delivery.en.md). Ship small useful increments; fix concrete defects in enabled behavior without turning each PR into an unbounded hardening program. Explicitly transfer deferred criteria to linked follow-ups; never relabel a known defect fixed or a partial checkpoint as the whole goal.

Implementation verification, GitHub integration and actual owner operation have separate states. External review/check/permission waits produce a bounded `integration_pending` receipt when safe work is exhausted, not an invented implementation failure, repeated preparation cycle, or false completion. Required checks still apply; independent review applies only when the Development Constitution's material security/authority escalation criteria are met. Native auto-merge is optional and disabled auto-merge does not rule out normal merge. Neither this document nor the helper changes native repository settings.

## Execution status ownership

GitHub Issues, Pull Requests, merge state, and required Checks are authoritative for execution status. Planning and governance artifacts such as `delivery-plan.yaml`, `TASKS.md`, `docs/roadmap.md`, and ledgers express selected goals, sequencing, dependencies, authority, acceptance, durable decisions, and historical evidence; they are not a second database of GitHub status.

Do not create a follow-up commit or pull request solely to mirror an Issue/PR transition, merge SHA, or Check result into those files. Update them when their own plan or decision content changes—for example scope, ordering, dependency, authority, acceptance, milestone, activation, re-scope, blocker/disposition, or next-goal selection—or when an active contract explicitly requires substantive evidence that GitHub-native state cannot represent. Existing historical closeout rows remain valid historical evidence and need not be normalized.

## Method

The governance combines four complementary practices:

1. **Contract-first development.** Every capability defines its user outcome, boundary, inputs, outputs, failure states, data classification, and non-goals before implementation.
2. **Consumer-driven contract testing.** An AgentOS adapter is tested against versioned fixtures and test doubles that represent the precise external request/response contract it consumes.
3. **Test-pyramid automation.** Most coverage is focused unit and component testing; a smaller set verifies local integration and end-to-end product flows. UI or manual broad-stack testing is never the default release gate.
4. **Continuous-integration quality gates.** Every pull request runs deterministic formatting, canonical-document existence, local-link, contract-fixture, and relevant automated tests before it can merge. Historical translations must link to their English canonical source; translation parity is not a merge gate.
5. **Reuse-first implementation selection.** Before non-trivial implementation introduces or replaces a component, abstraction, integration, dependency, or framework, the Existing Solutions Review starts with reusable AgentOS code already in the repository, then standard/platform facilities, official/reference implementations, and mature maintained OSS. Custom Build is the final option and requires a documented contract mismatch.

## Development completion rule

The [Goal Execution Contract](goal-execution-contract.en.md) defines how an active plan/issue becomes an executable goal, how it remains active or becomes blocked, and the audit required before completion.

A development increment is implementation-verified when its issue and pull request record:

- a documented contract and threat/data-boundary decision;
- versioned success, denial, timeout, malformed-response, and recovery fixtures where applicable;
- automated tests that exercise the product code against those fixtures or mocks;
- required repository checks passing in CI; and
- known limitations and the exact distinction between mock evidence and operating evidence.

Full iteration completion additionally requires normal merge, the required exact-PR-head validation, any substantive plan/governance update required because the plan itself changed, and an independent review artifact only when the change crosses the Development Constitution's material security/authority escalation boundary. GitHub-native execution status does not require tracker/roadmap/ledger mirroring. Final completion alone is not a review trigger. A successful merge does not require re-running the same heavy suite on `main`; `main` receives a fast merged-tree integrity pass, while scheduled/manual full validation is the repository-wide backstop. An integration-pending session handoff is not full iteration completion. No person is required to perform a routine manual acceptance test, log in to a third-party provider, or create a provider token to complete a development iteration. Human review remains an escalation for material product/security boundary changes, not a recurring test gate.

## External integrations and agents

MCP servers, A2A peers, runtimes, OAuth providers, and external action APIs are implemented behind AgentOS-owned adapters. Their development contracts must state allowed scopes, request and response schemas, timeouts, cancellation, idempotency, redaction, approval behavior, error mapping, and disconnect/recovery behavior.

Development uses local mock peers and fixtures only. It never requires live credentials, a live URL, a real provider account, or a real action. A mock must reject undeclared requests so an adapter cannot accidentally grow an unreviewed dependency.

## Operating-mode deployment

Production operating-mode deployment remains separately owner-authorized under its active deployment contract. The owner may also explicitly select a narrow experimental local smoke test before the entire long-term roadmap is complete. Such a test declares the exact revision, fresh data scope, provider/destination and budget approval; it is not production deployment, blanket private-data permission or retroactive acceptance of all capabilities. See [the early-access runbook](early-access-smoke.en.md).

The deployed runtime must use automated startup and health checks, fail closed on missing or invalid configuration, redact secrets from evidence, and retain a machine-readable deployment report. An operating connection may be described as configured only when its automated health check succeeds. Mock evidence remains labelled as development evidence and never as proof that the external service is live.

## Governance controls

- One GitHub issue, `codex/` branch, focused commits, and a PR are required for every iteration.
- CI blocks merge on failed automated gates; it does not wait for a person to carry out a routine live test. The always-required `validate` check may use path-sensitive depth: Markdown/assets-only changes use fast structural/governance checks, while any runtime, test, schema, build, workflow, executable governance-data, or otherwise non-document-only change must pass the full suite before merge.
- Every PR must carry a structured Existing Solutions Review. For non-trivial implementation this records internal repository candidates and search evidence before external candidates and the final Adopt / Adapt / Build decision. `N/A` is allowed only with a concrete reason that no new component, abstraction, integration, dependency, or framework is introduced. The required `validate` check rejects a missing or incomplete record.
- A contract change requires its fixture and mock suite to change in the same PR.
- New scopes, external writes, credentials, data classes, or recovery semantics require a contract and threat-model update before implementation.
- Tests must be deterministic, hermetic where possible, and safe to run without personal data or external credentials.
- A capability is described as *development-complete* only after its full declared development contract, merge, required CI, and requirement-to-evidence audit. Planning documents are updated only for substantive plan/decision changes, not to duplicate GitHub execution status. It is described as *operating-configured* only after the relevant automated health check succeeds. Use narrower implementation-verified or experimental-checkpoint labels where appropriate.

## Non-goals

This policy does not claim that mocks prove vendor availability, account entitlement, network reachability, or real-world provider behavior. It also does not allow undocumented external calls, arbitrary runtime installation, or bypassing approval and local-first data boundaries.
