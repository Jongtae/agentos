# Phase 2 Golden Runtime Loop Acceptance

Status: Planned

## Purpose

This document defines the minimum proof required for Phase 2 implementation.
Phase 2 is acceptable only when AgentOS can repeat a local-first Codex runtime
loop from prompt intake to bounded capability execution, narrated progress,
user-owned records, reply, and recovery.

The loop is:

```text
local or booted AgentOS runtime
-> setup/status is understandable
-> user prompt is received
-> intent is classified
-> bounded capability is selected
-> activity is narrated
-> result or failure is recorded
-> user receives a reply or recovery path
```

## Proof Boundaries

Docker preview may prove:

- runtime starts in a developer/demo environment
- setup status reports configured, missing, invalid, or degraded adapters
- prompt intake can feed the same intent and capability path used by AgentOS
- activity events are emitted for received, classified, running, completed,
  replied, and failed states
- user-owned outputs are written to a mounted or documented data path
- failure paths return friendly recovery guidance

Docker preview must not claim:

- boot ownership
- installer readiness
- reboot/rejoin proof
- kernel-level service supervision
- VM recovery proof
- ISO freshness

VM/ISO acceptance is required for:

- boot convergence into the managed AgentOS runtime
- install or reboot convergence back to the managed session
- recovery/rejoin proof
- service supervision under the target OS environment
- ISO asset and cleanup policy proof

## Required Scenarios

### Setup And Status

Acceptance:

- AgentOS reports runtime status without raw JSON or parser traces.
- Missing LLM, Telegram, Gmail, or external adapter configuration is shown as a
  friendly degraded state.
- The status output distinguishes local runtime readiness from external adapter
  readiness.
- Secrets are not printed in status, logs, records, or activity output.

### Greeting Or Start Prompt

Acceptance:

- A `/start`, greeting, or equivalent first prompt is classified as `greeting`.
- AgentOS replies with a short orientation to the local runtime state.
- Activity records show received, classified, completed, and replied.

### Runtime Status Prompt

Acceptance:

- A user prompt asking for AgentOS status is classified as `status`.
- AgentOS reports local runtime state, configured adapters, degraded adapters,
  and next recovery action when applicable.
- The result is saved as a user-visible record or activity artifact.

### Workspace Or File Request

Acceptance:

- A prompt asking to inspect, create, or summarize a workspace file is
  classified as `workspace_file_request`.
- AgentOS operates only inside the allowed workspace or user-owned data path.
- Generated output is written to user-owned storage.
- Activity records include the target path or a safe summary of it.

### Web Or Search-Like Request

Acceptance:

- A prompt asking for current or external information is classified as
  `web_search_request`.
- If web access is available, AgentOS records source references with the result.
- If web access is unavailable, AgentOS returns a friendly degraded response.
- The activity feed shows that an external adapter was used or unavailable.

### Gmail Read Or Draft Request

Acceptance:

- A prompt asking about inbox content, mail search, mail summary, or reply draft
  is classified as `gmail_read_or_draft`.
- Read/search/summarize/draft actions are allowed when Gmail is configured.
- Sending, deleting, archiving, or changing mailbox state requires explicit
  confirmation and is not part of the default Phase 2 proof.
- When Gmail is not configured, AgentOS explains the missing adapter without
  exposing tokens or OAuth details.

### Record Lookup

Acceptance:

- A prompt asking to find a prior note, transcript, summary, or work artifact is
  classified as `record_lookup`.
- AgentOS searches only the user-owned records boundary defined for the runtime.
- Results include source references when available.
- The response describes this as a searchable user-owned work archive, not a
  complete second brain.

### Controlled Failure

Acceptance:

- Unknown, ambiguous, low-confidence, destructive, external-send, or
  lifecycle-changing prompts do not execute by default.
- AgentOS asks for clarification or confirmation when needed.
- Raw JSON, stack traces, parser traces, tokens, and secrets are hidden from the
  user-facing response.
- Activity records show failed or blocked with a friendly recovery reason.

## Activity And Records Assertions

Every accepted runtime scenario should produce operator-visible activity using
this vocabulary:

- received
- classified
- running
- completed
- replied
- failed
- blocked

Every scenario that produces a durable output should write it under a
user-owned data boundary. Internal temp files, sockets, lock files, caches, and
secret material are not user-owned records.

## Closeout Requirements

Before Phase 2 or any implementation-heavy Phase 2 task closes:

- targeted checks or smokes for the affected scenarios must pass
- cleanup checks must pass or record an explicit exception
- stale temp artifacts must not remain hidden
- stale build-output artifacts must not remain hidden
- issue, branch, commit, merge, and ledger closeout must be complete

The required cleanup commands are:

```bash
python3 scripts/cleanup_temp_artifacts.py --delete --json
python3 scripts/cleanup_build_artifacts.py --delete --json
```

