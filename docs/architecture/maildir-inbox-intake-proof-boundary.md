# Maildir Inbox Intake Proof Boundary

Status: Local user-owned proof boundary, not production mailbox sync

AgentOS should grow the broader app/inbox ecosystem through OS-native,
user-owned substrate capabilities before expanding browser automation or
external app mediation. Maildir is the next safe inbox proof surface because it
can be tested locally, read without OAuth, and normalized through the same inbox
records and workflow paths as fixture-backed proof.

This boundary does not claim production mailbox sync or external mailbox
mutation support. It defines a safe proof shape for a user-provided local
Maildir path.

## Proof Goal

Maildir inbox intake proves that AgentOS can:

- read from an explicitly selected user-owned local Maildir path
- preserve message identity, thread identity, sender/recipient metadata, body
  previews, and attachment metadata
- normalize Maildir messages into the inbox intake substrate
- run proof baseline and inbox workflow surfaces without external credentials
- keep source data under user-controlled local storage
- avoid send, delete, archive, mark-read, label, folder, or calendar mutations

## Route Contract

| Route | Source kind | Permission | Proof claim |
| --- | --- | --- | --- |
| native inbox fixture | fixture | local read | deterministic substrate proof |
| Maildir intake | maildir | local read | local user-owned path proof after explicit path selection |
| external inbox adapters | Gmail, Calendar, later providers | external read | blocked until credentials and observed proof exist |

Maildir intake is not a browser or app automation path. It is a local adapter
surface selected only when the user points AgentOS at a workspace-relative
Maildir path.

## Required Runtime Signals

A valid Maildir proof must preserve:

- `source_kind: maildir`
- `path_kind: adapter`
- `inbox_adapter_required: true`
- `inbox_execution_ready: true`
- `message_thread_correlated: true`
- `attachment_visibility_ok: true`
- `proof.adapter_kind: maildir`
- `proof.ok: true`

Missing paths, invalid Maildir layout, unreadable messages, or malformed input
must produce blocked or deferred recovery guidance, not a live inbox claim.

## Secret And Data Boundary

Maildir proof must not require OAuth credentials, provider tokens, refresh
tokens, browser sessions, or app automation. Proof artifacts may include
redacted message metadata and body previews, but should not claim full mailbox
retention, compliance behavior, or provider synchronization.

The selected Maildir path is user-owned local state. It may be included as a
workspace-relative source reference in proof, but secrets and private host paths
must not be committed to the public repository.

## Mutation Non-Claims

Maildir intake does not allow AgentOS to:

- send messages
- delete messages
- archive messages
- move folders or labels
- mark messages read or unread
- mutate external calendars
- synchronize with a provider mailbox

Those actions require a later confirmation model, explicit permission
declarations, activity language, rollback/recovery behavior, and observed proof.

## Promotion Gate

The Maildir path can support later broader inbox/app work only when a future
issue names:

- the user-owned source path and redaction behavior
- the exact read/search/summarize/draft workflow being promoted
- the observed proof record to attach
- the recovery path for missing or invalid Maildir layout
- the explicit non-claims for mutation and production sync

Until then, AgentOS may claim local Maildir intake proof, not full app ecosystem
replacement.
