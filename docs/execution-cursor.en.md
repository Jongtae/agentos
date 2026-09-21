# Execution Cursor Protocol

## Purpose

The execution cursor is a compact GitHub-resident cache for resuming an explicitly active top-level program without rereading the entire issue/PR/CI/review graph every session.

It is **cache, not authority**. Current `main`, the active delivery plan, governing contracts, issues, PR heads, CI/review evidence and merge state remain canonical.

## Storage

Each active top-level program declares its cursor location and marker in the delivery plan.

EPIC-PA1 uses:
- issue: #386;
- storage: exactly one mutable top-level issue comment;
- marker: `<!-- agentos-execution-cursor:v1 -->`.

Update that same comment. Do not append cursor-history comments.

## Format

The marker is followed by exactly one fenced `json` object with schema `agentos-execution-cursor/v1`.

Required top-level fields:

- `schema`
- `generation`: integer >= 1, incremented for each replacement;
- `epic_issue`;
- `main_sha`: full 40-character commit SHA;
- `contracts`: path -> full blob SHA for governing contracts;
- `completed_children`: unique issue numbers already merged/closed for this program;
- `current`: zero or more unique current work entries;
- `waiting`: dependency waits;
- `owner_validation_pending`: concise non-secret strings;
- `protocol`: bootstrap/status metadata.

Each `current` entry contains `issue`, `pr`, `head_sha`, `state`, and `next_action`.

## Cursor-first resume

A new agent session should:

1. read repository bootstrap/governance;
2. fetch the single cursor comment;
3. validate its shape;
4. verify current `main`, governing contract blob SHAs and the referenced PR/head/state for the next action;
5. read only the referenced issue/PR/evidence needed for that action;
6. continue within existing authority.

If those checks match, do not perform broad GitHub rereads.

## Full reconciliation

Perform a bounded full reconciliation only when:
- the cursor is missing, duplicated or malformed;
- current main differs unexpectedly and no recorded transition explains it;
- a governing contract SHA changed;
- a referenced issue/PR/head/state differs unexpectedly;
- dependencies contradict the cursor;
- merge conflict or unexplained CI/review state exists;
- the cursor/handoff is incomplete enough that no safe next action can be chosen.

After reconciliation, replace the same cursor comment with corrected state and increment `generation`.

## Meaningful transition updates

Update the cursor only when the next decision changes:
- merge/close;
- coherent stable-head push;
- decisive CI/review result;
- new/cleared blocker;
- owner-validation change;
- durable session handoff.

Do not update it for local micro-edits, unchanged CI/review polls, or narrative progress.

## Concurrency and truthfulness

Before replacing the cursor, read its current `generation`. Increment by exactly one. If another writer already advanced it, reconcile instead of overwriting that newer state.

Cursor entries summarize observed GitHub/repository state. Do not mark a PR merged, CI green, review complete, or owner validation passed unless the canonical evidence currently shows that state.

Do not place credentials, private owner payloads, raw mail/calendar contents, hidden reasoning or other secrets in the cursor.

## Validation helper

`scripts/validate_execution_cursor.py <file>` validates a saved cursor comment. It checks the marker, JSON shape, SHAs, generation and uniqueness constraints. GitHub state consistency still requires live verification; the helper validates structure only.
