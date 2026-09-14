# D-AP-01 independent convergence review

## Scope and result

Independent read-only schema/compatibility, security/authority, and final
convergence reviews examined D-AP-01 against GitHub issue #334, base commit
`7411048909c3479bd867d0674ac5eb4e64ad5a83`, the canonical governance and
architecture documents, the v0.1 schemas, fixtures, verifier, and tests.

Final reviewed implementation commit: `94f997b72083874f07c8ecd3e9435264494bdb60`.

Result: **approved for PR**. No unresolved blocker, High, or Medium finding
remains. This is independent design/schema/repository evidence, not live
package, runtime, Registry, or Marketplace operating evidence.

## Resolved findings

The initial reviews found fail-open gaps for current Owner/Capability/Runtime
state, Context expiry and recipient binding, MemoryCandidate disposition,
Event subscriptions, worker-output lineage, timestamp syntax, and optional Work
transition lists. A later GitHub review found four P1 gaps in delegated Grant
ancestor state, complete Grant lineage, subscribed Event authority, and Memory
decision binding. Independent follow-up also found that Event type/background
scope had to be explicit in both Work and Grant. Remediation now ensures:

- the latest owner, capability, runtime, and Context revision governs current
  execution while historical exact references remain attributable;
- expired/deleted Context and expired/misdirected ContextSnapshot records cannot
  be used, and snapshots require Work-effective Grants;
- package/runtime lineage for Artifact, Evidence, and MemoryCandidate matches
  the referenced Work;
- MemoryCandidate acceptance/rejection requires sealed, candidate-bound Memory
  decision Evidence, reciprocal accepted Memory linkage, and the same exact
  decision on the resulting canonical Memory;
- package Event delivery matches a declared subscription and an exact current
  active Work whose package/runtime, actions, Event/background scope, complete
  scope, and budget are covered by one current effective Grant;
- Runtime quarantine, Grant revocation/expiry (including every delegated
  ancestor), and inactive owner/capability state override stale references;
- every Grant lineage edge is checked even if the example transition catalog is
  empty, so terminal revocation/expiry cannot be followed by reactivation;
- Work authority-bearing request fields remain invariant across complete record
  lineage even if an example transition list is omitted;
- strict UTC RFC 3339 timestamps, closed objects, exact detached digests, local
  schema resolution, and negative-case rule identity are enforced.

## Requirement-to-evidence audit

| #334 acceptance criterion | Current evidence |
| --- | --- |
| Ten Core Primitive schemas and normative semantics | `schemas/v0.1/{owner,context,memory,artifact,capability,runtime,grant,work,event,evidence}.schema.json`; canonical specification sections for every primitive. |
| AgentPackage manifest contract | `schemas/v0.1/agent-package.schema.json` and positive package fixture. |
| Shared identity/version/provenance/reference semantics | `common.schema.json`; exact record revisions and scoped package/runtime/content digests; offline graph rules `REF-*`, `LINK-*`, and `OWNER-*`. |
| Positive and fail-closed negative fixtures | 25 positive documents and 58 declared negative mutations spanning schema and semantic authority failures. |
| English canonical and Korean companion | `core-primitives-agentpackage-v0.1.en.md`; Korean companion explicitly defers normative authority to English. |
| Lifecycle/state transitions and install/Grant separation | Normative lifecycle sections; manifest constants; complete Work lineage checks; `installationCreatesGrant: false` and negative fixtures. |
| ContextSnapshot/MemoryCandidate boundary | Dedicated closed schemas plus current Context, recipient, Grant, candidate-decision, and canonical-authority checks. |
| Versioning/compatibility/migration | Canonical compatibility/migration section; exact `schemaVersion: 0.1`; unknown-field/version rejection; copy/validate/commit rule. |
| CI validation | `validate.yml` installs the schema-validation extra and runs `verify_agentpackage_v01.py` before the full test suite. PR CI must still pass before merge. |
| Existing regression suite | Local final evidence: 322 pytest tests plus 52 subtests; 287 unittest tests using `PYTHONPATH=src`; all passed. |
| Independent review | Three read-only reviewer roles; final schema approval and post-P1 authority/convergence approvals; no unresolved blocker, High, or Medium finding. |
| Historical D-MP2-02 scope | Historical contract unchanged; canonical v0.1 spec explicitly rejects automatic migration or retrospective authority expansion. |
| Evidence boundary | Spec, verifier, fixtures, and this review state that no runtime/install/Registry/Marketplace/live operation was observed. |
| Tracker/roadmap/ledger and GitHub closeout | Reconciled as complete-on-merge with no active successor; current required CI, merge, and issue closure remain final external gates. |

## Validation observed

- `python3 scripts/verify_agentpackage_v01.py`: 14 schemas, 25 positive
  fixtures, 58 negative fixtures.
- `python3 scripts/verify_master_plan_docs.py`: passed.
- `python3 scripts/verify_src_layout.py`: passed.
- root/package delivery-plan equality: passed.
- ledger JSON parsing and `git diff --check`: passed.
- `PYTHONPATH=src python3 -m pytest -q tests`: 322 passed, 52 subtests.
- `PYTHONPATH=src python3 -m unittest discover -s tests -q`: 287 passed.

The post-P1 authority reviewer independently passed the verifier and focused
suite. The convergence reviewer passed 11 adversarial/control probes covering
ancestor revocation/expiry, omitted Grant transitions, denied and authorized
Event delivery, and matched/mismatched Memory decisions, then passed a clean
full pytest rerun. The four GitHub review threads were answered and resolved
only after commit `94f997b` and these independent approvals.

An unqualified local unittest run in one review process initially imported an
editable `personal_agent` from another checkout. Re-running with this
repository's `src` selected passed. GitHub CI installs the current checkout
before testing.

## Delegation record

The primary agent requested `gpt-6-astra` with `max` reasoning for the bounded
schema/compatibility reviewer, security/authority reviewer, schema implementer,
and convergence reviewer. Task-creation receipts accepted those requests. The
runtime did not expose model/reasoning telemetry to the reviewers, so the
requested settings are recorded without claiming independently observed backend
identity. Reviewer file ownership was none; reviews were read-only. The schema
implementer exclusively owned `schemas/v0.1/**`,
`scripts/verify_agentpackage_v01.py`, and
`tests/test_agentpackage_v01_schemas.py` during its bounded implementation
phase; the primary agent later resolved review findings after interrupting that
task.

## Remaining completion gates

This review approves the implementation for PR. D-AP-01 is not complete until
the issue-linked PR has current required CI, is merged, issue #334 is closed,
and TASKS/roadmap/ledger state is reconciled. No successor is authorized by this
approval.
