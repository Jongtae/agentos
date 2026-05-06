# Intent Classification Contract

Status: Planned

Intent classification is a core AgentOS runtime contract. It is not owned by
Telegram, Gmail, Docker, or any single adapter.

Every user prompt that enters the Phase 2 runtime loop should produce an
intent decision before capability execution.

## Intent Vocabulary

Phase 2 uses this public vocabulary:

- `greeting`
- `status`
- `setup_help`
- `workspace_file_request`
- `web_search_request`
- `gmail_read_or_draft`
- `record_lookup`
- `lifecycle_recovery`
- `unknown_or_unsupported`

## Decision Fields

The classifier contract should expose:

- `intent`
- `capability`
- `confidence`
- `needs_confirmation`
- `reason`
- `source`

Phase 2 may keep legacy intent names internally while migration is underway,
but public acceptance and evals should use the Phase 2 vocabulary.

## Safety Rules

AgentOS should not execute by default when a prompt is:

- low-confidence
- ambiguous
- destructive
- external-send or mailbox-mutating
- lifecycle-changing
- outside the supported capability set

Those prompts should produce clarification, confirmation, or friendly
unsupported responses.

## Evaluation Set

The seed eval set is stored in `docs/acceptance/phase2-intent-eval.json`.

The eval set must include English and Korean examples for:

- greeting
- status
- setup help
- workspace/file requests
- web/search requests
- Gmail read/draft requests
- record lookup
- lifecycle/recovery
- unsupported or unsafe prompts

Stage C will wire this contract into an executable eval runner.

