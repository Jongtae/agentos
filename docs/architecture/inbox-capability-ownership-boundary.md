# Inbox Capability Ownership Boundary

Status: Phase 2 boundary

## Purpose

AgentOS should treat inbox-like work as an OS-native capability family, not as a
collection of app automations. The runtime should be able to receive, normalize,
summarize, draft, record, and explain inbox work through a common substrate even
when the source is Gmail, Calendar, Maildir, a local fixture, or a later
read-only adapter.

This boundary keeps the default proof local-first and user-owned while making
live external adapters explicit.

## Owned Intake Paths

AgentOS-owned inbox intake starts with paths that can be tested without
credentials:

- native fixture intake through the workspace-owned inbox fixture
- Maildir intake when the user explicitly points AgentOS at a local Maildir
- normalized inbox intake records that carry source kind, message metadata,
  thread correlation, body preview, and attachment metadata
- activity and proof artifacts written under user-owned workspace/runtime data

These paths are sufficient for local proof of classification, triage,
summarization, draft preparation, activity narration, and record lookup.

## External Read-Only Adapters

Gmail, Calendar, and future inbox-like providers are explicit read-only adapters
until live proof is observed.

External adapters must:

- require explicit user setup and credentials
- keep credentials out of user-owned shared records and git-tracked files
- support read/search/summarize/draft preparation before mutation
- write only redacted proof, activity, and user-owned records by default
- return blocked recovery guidance when OAuth, network, or provider state is
  missing

Fixture-backed Gmail and Calendar proof must not be described as live OAuth
proof. Mock responses may validate schema and recovery behavior, but they do
not prove real mailbox or calendar access.

## Mutation Blockers

The Phase 2 inbox boundary blocks external mutations by default.

Blocked actions include:

- send
- delete
- archive
- mark read/unread
- move labels or folders
- create, modify, or delete external calendar events

These actions need a later confirmation model, permission declaration, activity
language, and observed live proof before they can be promoted beyond blocked or
draft-only behavior.

## User-Owned Records

Inbox capability output should remain searchable and manageable by the user.

Records should include:

- source kind, such as native fixture, Maildir, Gmail read-only, or Calendar
  read-only
- intent and capability name
- normalized message or event references
- summary and draft text when generated
- blockers and recovery guidance when live setup is missing
- redacted proof that avoids provider tokens, refresh tokens, and secret paths

The record layer may support retrieval and later memory-like workflows, but this
boundary does not claim a complete second brain.

## Activity And Recovery

Inbox requests should narrate:

- request received
- intent classified
- intake path selected
- capability started
- summary or draft prepared
- record written
- adapter blocked or recovery suggested

Raw provider errors, parser traces, and token paths should stay in logs or
redacted diagnostics, not in primary user-facing output.

## Non-Claims

This boundary does not claim:

- live Gmail OAuth proof unless a tester completes the read-only OAuth flow
- live Calendar OAuth proof unless a tester completes the read-only OAuth flow
- external send/delete/archive support
- browser or app automation as the default inbox path
- production mailbox sync, retention, or compliance behavior
- a complete app ecosystem replacement

## Exit Condition

This boundary is satisfied for the first Phase 2 slice when it is linked from
the source-of-truth docs and smoke-tested for native/local intake, explicit
read-only adapter blockers, mutation non-claims, user-owned records, and
activity/recovery expectations.
