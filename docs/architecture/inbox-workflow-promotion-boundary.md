# Inbox Workflow Promotion Boundary

Status: Phase 2 active promotion gate

AgentOS should grow broader app and inbox support by promoting narrow,
repeatable workflows into OS-native capabilities before expanding browser
automation or external app mediation. This boundary defines how a workflow
candidate moves from local fixture, Maildir, Gmail, Calendar, or browser
fallback proof toward a first-class AgentOS inbox capability.

## Promotion Goal

A broader app or inbox workflow may be promoted only when it can be named,
bounded, permissioned, recorded, and validated without hiding external-state
requirements.

The first safe promotion shape is read-first:

- receive or read an inbox-like item
- normalize it into the inbox substrate
- summarize, triage, or prepare a draft
- write user-owned records and activity narration
- block mutation unless a later confirmation model exists

This keeps AgentOS centered on runtime ownership instead of becoming a set of
browser or app macros.

## Candidate Sources

Promotion candidates must come from
`docs/architecture/capability-graduation-registry.json`.

Safe source classes are:

| Source class | Current proof | Promotion rule |
| --- | --- | --- |
| fixture inbox | deterministic local fixture | may validate schema and workflow behavior |
| Maildir | user-owned local path boundary | may promote local read workflow after explicit path selection |
| Gmail read-only | fixture/manual acceptance | blocked until live OAuth observed proof exists |
| Calendar read-only | fixture/manual acceptance | blocked until live OAuth observed proof exists |
| browser fallback | contract/manual acceptance | blocked until user-approved observed browser proof exists |

## Required Promotion Record

Every promoted workflow task must declare:

- selected registry `candidate_id`
- source class and permission level
- exact user workflow being promoted
- expected user-owned record fields
- activity and recovery language
- fixture or mock validation plan
- live proof blocker or observed proof record
- explicit mutation, sync, retention, compliance, and browser-default
  non-claims

## Exit Gate

A task may claim a broader inbox/app workflow only when:

- the candidate exists in the capability graduation registry
- the permission level is no stronger than the selected proof path allows
- fixture, mock, or local proof can run without live credentials
- blocked live-proof paths name the missing evidence
- records and activity are user-visible and redacted
- send, delete, archive, mark-read, move, calendar mutation, and external app
  automation remain blocked unless a later issue adds confirmation and observed
  proof

## Non-Claims

This boundary does not claim:

- production app ecosystem replacement
- full mailbox sync
- retention or compliance behavior
- live Gmail or Calendar OAuth proof
- real user Maildir proof without an observed user-provided path
- browser automation as the default runtime path
- external send/delete/archive or calendar mutations

## Exit Condition

This slice is complete when the promotion boundary, smoke test, docs index,
golden runner, README, TASKS, and roadmap state make broader app/inbox work
choose a capability candidate and preserve the blocker truth before claiming
new live or mutation behavior.
