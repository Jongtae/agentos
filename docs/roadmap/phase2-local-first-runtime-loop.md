# Phase 2 Local-First Runtime Loop

Status: Planned

## Goal

Phase 2 turns the Phase 1 prototype into a coherent Codex-native product loop:

```text
local or booted AgentOS runtime
-> configure local-first runtime adapters
-> receive a user prompt
-> classify intent
-> run a bounded capability
-> narrate progress
-> store user-visible records
-> reply or recover clearly
```

Phase 2 is not a reset of the Phase 1 MVP. It extends the public prototype
toward local-first capability ownership, lower mediation cost, and OS-native
defaults for Codex.

## Product Position

AgentOS should be local-first by default, user-owned by design, and explicit
before external sync or external execution.

Phase 2 work must preserve these boundaries:

- Docker is a developer and demo runtime preview, not the AgentOS product
  target.
- Shared folders and bind mounts are part of the user-owned runtime data
  boundary.
- User records, generated outputs, exported logs, acceptance artifacts, and
  diagnostics should be manageable by the user.
- Secrets, tokens, and provider credentials must not be stored as plaintext in
  shared user data.
- External adapters such as Gmail, Calendar, Telegram, browser, or hosted LLM
  APIs must be explicit at setup or execution time.

## Core Workstreams

### Golden Runtime Loop Acceptance

Define the repeatable proof for Phase 2 before broad implementation. The
acceptance loop should cover setup status, prompt intake, intent classification,
capability dispatch, activity narration, user-visible records, reply, and
friendly recovery.

The detailed acceptance contract is tracked in
`docs/acceptance/phase2-golden-runtime-loop.md`.

The initial acceptance set should include:

- `/start` or greeting
- runtime status
- workspace or file request
- web/search-like request
- controlled failure with recovery guidance
- activity feed assertions
- cleanup checks before closeout

### Docker Runtime Preview

Docker support should make the public project easier to try and easier to smoke
test. It should not claim to prove boot ownership, installer readiness,
reboot/rejoin behavior, kernel-level supervision, VM recovery, or ISO freshness.

The detailed boundary is tracked in
`docs/architecture/docker-runtime-preview-boundary.md`.

The Docker path should prove only the runtime preview surface: configuration
status, intent dispatch, activity events, bounded capability execution, records
output, and friendly failure behavior.

### User-Owned Runtime Data

AgentOS should separate user-owned data from AgentOS-managed state.

The detailed boundary is tracked in
`docs/architecture/user-owned-runtime-data-boundary.md`.

User-owned data includes:

- workspaces
- generated files and artifacts
- exported activity logs
- diagnostics bundles
- user-provided records and transcripts
- acceptance outputs

AgentOS-managed state includes:

- runtime sockets
- process state
- internal caches
- temp files
- service lock files

Secret-managed data includes:

- API keys
- Telegram tokens
- OAuth tokens
- sensitive chat or account identifiers when applicable

### Intent Classification

Intent classification is a core runtime contract, not a Telegram-specific
feature. User prompts must be classified before capability dispatch so AgentOS
can execute safely, narrate accurately, and recover clearly.

The detailed contract is tracked in
`docs/architecture/intent-classification-contract.md`, with the seed eval set in
`docs/acceptance/phase2-intent-eval.json`.

The Phase 2 contract should define at least:

- `greeting`
- `status`
- `setup_help`
- `workspace_file_request`
- `web_search_request`
- `gmail_read_or_draft`
- `record_lookup`
- `lifecycle_recovery`
- `unknown_or_unsupported`

Low-confidence, destructive, external-send, or lifecycle-changing requests
should stop for clarification or confirmation before execution.

### Everyday Work Capabilities

Phase 2 should prove a bounded everyday-work capability set:

- AgentOS status and recovery
- workspace files
- web/search context
- Gmail read, search, summarize, and draft
- Calendar read-only status if it fits the slice

Gmail should begin as read/search/draft-first. Sending, deleting, archiving, or
changing mailbox state requires explicit confirmation or a later phase.

### Records And Retrieval Substrate

Phase 2 should prepare for searchable work history without promising a full
second brain product.

AgentOS should treat user-provided records, transcripts, email-derived notes,
web research, workspace outputs, and generated summaries as user-owned runtime
records. Derived artifacts such as summaries, action items, tags, and indexes
must link back to their source records and remain rebuildable or removable.

The product language for Phase 2 should be:

> searchable user-owned work archive

not:

> complete second brain

## Recommended Issue Order

1. `[P2-02] Document Phase 2 local-first runtime roadmap`
2. `[P2-03] Define Phase 2 golden runtime loop acceptance`
3. `[P2-04] Define Docker runtime preview boundary`
4. `[P2-05] Define user-owned runtime data boundary`
5. `[P2-06] Define intent classification contract and eval set`
6. `[P2-07] Add Docker runtime smoke harness`
7. `[P2-08] Productize first-run setup state model`
8. `[P2-09] Add Gmail read and draft capability boundary`
9. `[P2-10] Stabilize activity feed and records output`
10. `[P2-11] Add lifecycle and recovery controls`
11. `[P2-12] Create Phase 2 golden demo acceptance runner`
12. `[P2-13] Phase 2 docs and closeout`

## Closeout Standard

Phase 2 can close only when AgentOS can truthfully state:

> Phase 2 proves AgentOS can run a local-first, user-owned Codex runtime loop
> that classifies user intent, executes bounded everyday-work capabilities,
> narrates progress, stores user-visible records, and recovers clearly from
> failure.
