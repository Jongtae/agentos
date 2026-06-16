# Calendar Read-only Capability Contract

Status: Fixture-backed contract with runtime status surface

Calendar is an everyday-work capability candidate, but Phase 2 must start with
read-only behavior. The public contract is intentionally narrower than a live
calendar integration:

- read upcoming events
- search events by title, description, location, or attendees
- summarize matching events
- store user-visible records when used through the runtime loop

Calendar must not create, update, delete, invite, cancel, or otherwise mutate an
event without a later explicit confirmation flow and live adapter design.

## Local-first Boundary

The first implementation is fixture-backed so contributors can test behavior
without Google/Microsoft credentials. Fixture mode must report:

- `real_calendar_credentials_used: false`
- `oauth_required: false`
- `proof.read_only: true`
- `proof.mutation_executed: false`

Live OAuth, if added later, must keep secrets outside shared user data and must
not claim VM or account proof unless the run is observed.

## Runtime Contract

Calendar prompts should classify to:

- intent: `calendar_readonly`
- capability: `calendar_readonly`

The runtime response should include a short event summary and should write a
user-owned record. If a user asks for a mutating action such as deleting,
creating, cancelling, or inviting, the result must be blocked or clarified.

## Fixture Proof

`scripts/smoke_phase2_calendar_fixture.sh` verifies the fixture contract.
`scripts/smoke_phase2_run_cli.sh` verifies that the Phase 2 CLI can route a
calendar prompt through the same user-owned record and activity surfaces as the
other everyday-work capabilities.

`phase2-run --message "status"` attaches `agentos-calendar-readonly-status.v1`
so operators can see fixture readiness, permission level, live OAuth blockers,
and mutation non-claims before any real Calendar adapter is promoted.
