# Capability Permission Boundary

Status: Planned

AgentOS should treat every capability as an explicit runtime contract before it
touches user data, external services, lifecycle controls, or OS-native state.
This boundary keeps capability ownership local-first and makes approval,
denial, narration, and recovery visible to the user.

## Permission Levels

Phase 2 uses these public permission levels:

- `safe_read`
- `safe_write_user_owned`
- `external_read`
- `external_write_confirmed`
- `lifecycle_confirmed`
- `destructive_blocked`
- `unsupported`

## Capability Declaration

Every capability should declare:

- capability id
- intent names it may serve
- permission level
- user-owned record behavior
- secret requirements
- confirmation requirement
- blocked operations
- recovery hint when unavailable

Adapters may expose richer internal state, but public activity, records, and
acceptance output should use this shared declaration vocabulary.

## Default Rules

AgentOS may run without confirmation when a capability is:

- local
- non-destructive
- read-only or writes only to user-owned AgentOS records
- secret-free or already configured without exposing secret values

AgentOS must ask for confirmation or block when a capability is:

- external-send or mailbox-mutating
- destructive
- lifecycle-changing
- low-confidence or ambiguous
- missing required credentials
- outside the declared permission boundary

## Required Outcomes

Capability execution should produce one of these outcomes:

- `completed`
- `blocked_needs_setup`
- `blocked_needs_confirmation`
- `blocked_unsupported`
- `failed_recoverable`

Every non-completed outcome must include a recovery hint that is safe to show in
the operator surface, activity feed, JSON output, and user-owned records.

## Activity And Records

Every capability run should emit activity for:

- request received
- intent classified
- capability selected
- permission checked
- capability completed, blocked, or failed
- recovery suggested when needed

User-owned records may include capability id, permission level, outcome,
artifact paths, and recovery hints. They must not include plaintext secrets,
OAuth refresh tokens, provider credentials, or raw private adapter responses
unless the user explicitly exported those records.

## Phase 2 Capability Baseline

Initial Phase 2 declarations should cover:

- runtime status and setup help as `safe_read`
- workspace/file lookup as `safe_read`
- user-owned record creation as `safe_write_user_owned`
- web/search summary as `external_read`
- Gmail read/search/summarize as `external_read`
- Gmail draft-local-output as `safe_write_user_owned`
- Gmail send/delete/archive as `destructive_blocked` until a later confirmed
  live adapter exists
- Calendar read-only as `external_read`
- restart/reboot/shutdown as `lifecycle_confirmed`

## Acceptance

The boundary is acceptable when smokes or fixtures can show:

- a safe local read runs without confirmation
- a user-owned record write is recorded under the user data boundary
- a missing external credential returns `blocked_needs_setup`
- a destructive or external-send request is blocked or requires confirmation
- activity and records include permission level and recovery without leaking
  secrets

`scripts/smoke_phase2_capability_result.sh` is the seed executable check for
these outcomes.
