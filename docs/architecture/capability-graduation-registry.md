# Capability Graduation Registry

Status: Phase 2 completion epic active

## Purpose

AgentOS should not grow into a collection of browser macros and external app
scripts. Repeated browser fallback, inbox/app, calendar, web, and external
adapter patterns should graduate into OS-native capabilities when they become
common, bounded, and testable.

This registry defines how AgentOS decides whether a repeated access pattern is:

- already covered by an internal capability
- allowed as temporary fallback
- blocked by missing credential or external state
- ready to become a first-class AgentOS capability candidate

## Graduation Criteria

A pattern can become a capability candidate when all of these are true:

- the user goal is recurring and narrow enough to name
- the required permission level is known
- the data boundary is local-first or explicitly adapter-backed
- destructive actions are blocked or require confirmation
- activity and user-owned records can be produced
- fixture or mock proof can run without live credentials
- live proof blockers are explicit before any claim is promoted

## Registry Contract

The seed machine-readable registry is
`docs/architecture/capability-graduation-registry.json`.

Each candidate records:

- `candidate_id`
- `source_pattern`
- `target_capability`
- `current_route`
- `graduation_stage`
- `permission_level`
- `data_boundary`
- `safe_mock_available`
- `live_proof_required`
- `blockers`
- `exit_condition`

## Seed Candidates

| Candidate | Source pattern | Target capability | Current route |
| --- | --- | --- | --- |
| `calendar_readonly_live` | repeated calendar read/search requests | read-only Calendar adapter | fixture-backed contract |
| `gmail_readonly_live` | repeated Gmail read/search/summarize/draft requests | read-only Gmail adapter | fixture and manual OAuth acceptance |
| `web_research_brief` | repeated web/search summary requests | internal research brief capability | web summary with browser fallback contract |
| `browser_fallback_observed` | repeated interactive browser fallback requests | bounded browser acceptance capability | blocked until observed user-approved run |
| `maildir_inbox_intake` | local inbox-like file/mail workflows | Maildir/user-owned inbox intake | native inbox fixture boundary |

## Non-Claims

This registry does not claim:

- production app ecosystem replacement
- live browser automation proof
- live Gmail or Calendar OAuth proof
- send/delete/archive mutations
- credential storage readiness for new adapters
- VM/ISO or hardware proof

## Exit Condition

The capability graduation registry epic is complete when:

- the registry document and JSON seed candidates exist
- a smoke verifies candidate shape, blockers, README/TASKS/roadmap/docs links,
  and golden runner inclusion
- future broader app ecosystem work can choose a candidate and open a focused
  task before expanding browser or external app mediation

