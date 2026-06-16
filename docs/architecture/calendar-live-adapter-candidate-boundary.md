# Calendar Live Adapter Candidate Boundary

Status: Candidate contract, not live proof

The Calendar fixture, readiness status, and manual acceptance pack now define a
safe path toward live read-only Calendar access. The next boundary is the live
adapter candidate: a contract for a future OAuth-backed read-only adapter that
can be implemented without changing AgentOS into an app-mediated automation
shell or claiming unobserved account proof.

This document does not promote live Calendar proof. It defines the conditions a
future adapter must satisfy before proof can be promoted.

## Candidate Goal

The live adapter candidate should let AgentOS answer Calendar read/search and
summarize requests through an OS-native capability surface while keeping:

- fixture mode as the default automated proof path
- live OAuth as explicit tester-provided external state
- secrets outside shared user-owned records and repo files
- observed proof separate from local smoke proof
- all Calendar mutations blocked until a later confirmed mutation model exists

## Adapter Routes

| Route | Purpose | Proof claim |
| --- | --- | --- |
| `calendar_fixture` | Local deterministic read/search/summarize proof | Fixture-only, no real account access |
| `calendar_oauth_readonly_mock` | Synthetic live-shaped proof for acceptance pack tests | Mock-only, no real account access |
| `calendar_oauth_readonly` | Future tester-provided OAuth read-only adapter | Live read-only only after observed proof |

The runtime must continue to expose `calendar_fixture` as safe local proof. The
future live route must not replace fixture proof in automated CI or local golden
smokes unless explicit credentials and a sanitized observed proof record are
provided by a tester.

## OAuth Preconditions

A live Calendar adapter can be promoted only when all of these are true:

- OAuth credentials and tokens are supplied by the tester at runtime.
- Tokens are stored outside repo files, shared records, and generated acceptance
  artifacts.
- The adapter uses read-only Calendar scopes.
- A sanitized observed proof record is attached through the observed proof
  intake boundary.
- The acceptance pack validates both runtime status and read output.

Missing credentials, missing observed proof, or any secret-bearing artifact must
produce a blocker, not a partial live-proof claim.

## Runtime Proof Shape

A promoted live read-only run must preserve these fields:

- `adapter: calendar_oauth_readonly`
- `permission.level: external_read`
- `proof.read_only: true`
- `proof.live_calendar_oauth_completed: true`
- `proof.mutation_executed: false`
- `proof.secrets_redacted: true`

Fixture and mock routes must keep `proof.live_calendar_oauth_completed: false`
unless an observed tester run supplies a real live adapter output.

## Mutation Non-Claims

The live adapter candidate does not allow:

- creating events
- updating events
- deleting events
- inviting attendees
- cancelling events
- changing reminders, recurrence, locations, guests, or conference links

Requests for these actions must be blocked or routed to a future explicit
confirmation design. They must not be performed by a read-only adapter.

## Promotion Gate

The candidate may become an implementation task only after a future issue names:

- the target OAuth provider and read-only scope
- credential storage and redaction behavior
- the observed proof record to attach
- the exact non-mutating read/search/summarize commands to run
- the rollback behavior when credentials are missing or revoked

Until then, AgentOS may claim fixture-backed Calendar readiness and manual
acceptance-pack readiness, but not live Calendar account proof.
