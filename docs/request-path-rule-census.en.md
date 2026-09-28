# Request-path rule census (ARCH-THIN-01 / #820)

## Status

Canonical record for ARCH-THIN-01 [#820](https://github.com/Jongtae/agentos/issues/820), under Constitution C16 and the #653 pilot posture. Owner direction (2026-09-28): finding failures one case at a time does not scale; find the root cause. On that day almost every live failure came from AgentOS layers between the owner and the AI worker, not from the model. These layers rewrote or narrowed the owner's words, overrode or hid the AI's answer, or stopped owner state from flowing.

This document is a census of every deterministic rule, and every judgment verdict, on the owner-request path that gates, withholds, filters, rewrites, narrows or overrides. For each one it records what the rule protects and what was done with it. Line numbers refer to the ARCH-THIN-01 head.

Evidence class: a static reading of the source plus deterministic unit tests with injected transports (`tests/test_orchestrator.py` `ThinOrchestration`, `OwnerQuestion`, `SecretaryStandard`; `tests/test_agency_loop.py`; `tests/test_truthful_terminal_result.py`; `tests/test_refused_write_outcome.py`; `tests/test_truth_integrity_history.py`). No live model behaviour was observed for this change.

## The three rules this census enforces

1. **The owner's words reach the worker verbatim.** They always arrive with the owner model (profile, current context), the recent conversation and the prepared answers. The plan call chooses the worker, model and tools. It may add notes. It never replaces, narrows or extends the owner's message.
2. **The AI's answer is always delivered.** AgentOS may add its own verified receipts and truthful qualifiers: the truth header, what did not complete, the unverified label, sources, and "nothing saved yet". It never hides the answer. The one exception is the mandatory `unknown` external-effect statement.
3. **One outcome judgment decides the Work's outcome.** The question is whether the reply served the owner's message, given the conversation. Tool results are evidence for that judgment and step bookkeeping is Evidence only. A reply's own claims of actions, or of current facts, count only when the recorded tool results support them.

## What a rule may protect

A rule stays only when it protects one of these pilot invariants (#653), or a boundary the canonical repository governance requires AgentOS to keep.

| Code | Protects |
|---|---|
| **a** | Secrets never enter a model prompt, a log or Evidence. |
| **b** | Payment needs a per-action owner approval. |
| **c** | Irreversible external effects are never replayed or duplicated, and `unknown` external-effect statements stay truthful. This includes not calling a state change done when it failed. |
| **d** | Owner-state provenance, and the owner's authority over canonical Memory (#597: canonical Memory vs MemoryCandidate). |
| **g** | Private-document egress guard. `AGENTS.md` requires it: "Preserve existing private-document transmission/search guards". It is not one of a–d. It is kept, and flagged for an owner decision (see *Open for the owner*). |
| **i** | Isolation or trust profile the owner selected (#616): sandbox and filesystem authority. |
| **bound** | A resource bound (size, time, turns, budget). It is not a judgment about the request. |
| **e** | None of the above. |

Dispositions:
- **Removed:** the rule is deleted.
- **Reduced:** the rule became a label, a note or Evidence that never changes what the owner sees or what the worker is asked.
- **Kept:** the rule protects one of the codes above.
- **Deferred:** the rule protects nothing (e), but it sits in the pre-worker command and intent layer, outside this change's bounded scope. It is listed under *Follow-up*.

## A. What the worker receives

| # | Location | Rule | Effect before #820 | Protects | Disposition |
|---|---|---|---|---|---|
| A1 | `orchestrator.py:53` `ALWAYS_SECTIONS`; `quickstart_service.py` CLI and API `turn_context` calls | The plan's `brief.context` chose which of `history` and `prepared` the worker received. | A plan without `history` sent the CLI no earlier turns and the API only the last message. | e | **Removed.** Every attempt receives every section. `Attempt.section` returns its value. |
| A2 | `orchestrator.py:150` `QUESTION` | The plan wrote `brief.goal` "at the level a capable personal secretary would deliver". It resolved follow-ups into the goal ("only when … continues recent_conversation"). It turned an owner statement into "acknowledge, update what AgentOS knows, propose a memory …". It told the worker to look things up or not, and not to ask the owner. | The worker was given a plan-written goal. Live cases: a new request was tied to the previous topic; "no search needed"; a statement narrowed to "record the state"; a short acknowledgement with no tools. | e | **Reduced.** The question says the plan does not rewrite the owner's message. The worker receives it verbatim with the conversation and decides what it needs. `brief.notes` are optional factual notes that never restate, narrow or extend the message, never tell the worker to skip a lookup or a tool, and never ask it to ask the owner. |
| A3 | `orchestrator.py` `plan_schema`, `plan_shape` | The brief schema was `{goal, context, completion_criteria}`. | A plan-written goal and criteria were required. | e | **Removed.** The brief is `{notes}` only. |
| A4 | `orchestrator.py:542` `Attempt.brief`; `agent_runtime.py:2320` `BRIEF_HEADING` | The brief rendered as `Goal: …` / `Done when: …` above the request. | It read as the task. | e | **Reduced.** It renders as `# Orchestration notes (supplementary; they never replace or narrow the owner's request below, which is the goal in full)`. It is omitted when there are no notes. |
| A5 | `orchestrator.py:698` `validate` | An empty `goal` made the plan invalid. | The owner's request fell back to the default worker. | e | **Removed.** Empty notes are valid. |
| A6 | `orchestrator.py:481` `subset_or_default`; `quickstart_service.py:6588` `allowed_tools&=attempt.tools` | A planned tool subset stands only when it keeps private reads and web search apart. Any other subset, including an empty one, becomes the full toolset. | Never narrows the goal. In the live Work, the empty subset "tools none" stayed the full toolset. | g | **Kept.** |
| A7 | `orchestrator.py:560` `Attempt.native_search`; `quickstart_service.py:1306` `cli_native_search`, `:3224` `native_search_blocking` | The CLI's own web search is off on a turn with spliced private material, a selected private-read tool, or an earlier attempt's private reads. | The worker searches through AgentOS instead. | g | **Kept.** |
| A8 | `bounded_execution.py:379` `native_search_withheld` | Private-read bridge tools are withheld on a native-search turn. `save_memory` stays offered. | Private reads are unavailable on that attempt. | g | **Kept.** |
| A9 | `bounded_execution.py:373` `NATIVE_SEARCH_REPLACED` | Bridge `web_search` and `bounded_public_research` are withheld while the CLI's own search is on. | No capability is lost: the CLI's own search replaces them. | e | **Kept:** a dedupe; it changes no capability. |
| A10 | `quickstart_service.py:6625` | The `/search` preflight is skipped when the validated subset leaves `web_search` out. | Follows A6. | g | **Kept.** |
| A11 | `quickstart_service.py:210` `subscription_public_lookup_query` | A `/search` query that names a credential word is not sent as a preflight. | The worker still runs; only the AgentOS preflight is skipped. | a | **Kept.** |
| A12 | `quickstart_service.py:6554` `pinned` | A Work carrying spliced private material, or an attachment approved for the default destination, may run only on the default worker. | Worker choice narrowed to the approved destination. | g | **Kept.** |
| A13 | `quickstart_service.py:2561` `document_boundary`; document-job history filtering in the turn | Document excerpts go to an external model only with the approval bound to that model and those folders. | Document turns are filtered from a CLI or unapproved worker's history. | g | **Kept.** |
| A14 | `bounded_execution.py` `CLI_PROFILES` trusted-local `unavailable` | `public_page_read`, `find_files`, `read_file` and `list_roots` are not offered on the CLI, because their approvals are bound to the direct-API model. | Fewer tools on the CLI. | g | **Kept.** |
| A15 | `bounded_execution.py` strict and isolated profiles; `:1236` `environment` | The owner-selected trust profile limits tools, environment and sandbox. | Fewer tools. | i, a | **Kept.** |
| A16 | `agent_runtime.py:925` `rebuild_lookup_value`, `:1855` `_public_task` | AgentOS-composed public lookups exclude private values (#605). | Search query words removed. | g | **Kept.** |
| A17 | `quickstart_service.py:6663` | When the envelope exceeds `MAX_PROMPT_BYTES`, only the bare request is sent. | The owner's words are still verbatim. | bound | **Kept.** Follow-up: shorten rather than drop. |
| A18 | `agent_runtime.py:2291` `CONTEXT_MESSAGES`, `turn_context` byte budget; `quickstart_service.py:6444` `history()[-16:]` | Older turns are dropped before the request is ever cut. | Long conversations are shortened. | bound | **Kept.** |
| A19 | `quickstart_service.py:3263` `planner_history(...)[-4:]`, `orchestrator.py:63` `CONVERSATION_CHARS` | The plan call reads a bounded conversation excerpt. | Before: it could narrow the worker through the brief. Now the worker always receives the conversation itself. | bound | **Kept.** |
| A20 | `quickstart_service.py:1817` `canonical_retry_source` | A retry replays the owner's original words. | It serves the verbatim rule. | c | **Kept.** |
| A21 | `quickstart_service.py:893` `preparation_history` | A preparation's run receives its accepted goal, not the later conversation. | Its request is the owner-accepted goal (#659). | e | **Deferred.** |
| A22 | `agent_runtime.py:2281` `CORE_INSTRUCTIONS` | "Address ONLY the latest user request … Never retry a previous failed request." | Generic worker guidance; it names no task. | c (no replay) | **Kept.** |
| A23 | `bounded_execution.py:89` `_SPECIALISTS` | `list_agents` and `delegate_agent` are not offered on a CLI. | No delegation from a CLI. | e | **Deferred.** |
| A24 | `bounded_execution.py:1681` | A prompt over 48 KB is refused. | The owner's request is refused. | bound | **Kept.** |
| A25 | `quickstart_service.py:170` `workspace_summary_request`, `:188` `workspace_search_request`, `:3118` `RULE_FALLTHROUGH_INTENTS`; `conversation_handoff.py:983` `_rule_settings`, `:457` `_strip_noise`, `:997` `_rule_workspace`, `:1025` `_note_content` | Command and intent-rule rewrites of the owner's words, such as a fixed summary query or a cue-stripped subject. | The rule layer, not the worker, receives a rewritten request. | e | **Deferred.** |

## B. What the owner sees

| # | Location | Rule | Effect before #820 | Protects | Disposition |
|---|---|---|---|---|---|
| B1 | `quickstart_service.py` `answer_withheld` (removed), `owner_jobs` `:3163`, `owner_messages` `:3173`, `task_progress` `result_available`, `save_workspace_result`, Telegram delivery and watch notices | A failed or partial Work's answer was hidden whenever a state-changing action fell short (`state_change_short`). | The Telegram bubble, the web transcript and the card showed no answer. | e (the truth header and cause already state what did not complete) | **Removed.** The answer is delivered under the truth header, the cause and the unverified label. |
| B2 | `conversation_projection.py:273` `terminal_text` | An `interrupted` Work never showed its answer. | Answer dropped. | e | **Removed.** An answer it has is shown under the interrupted header and the label. |
| B3 | `conversation_projection.py:273` failed/partial branch, `:37` `TERMINAL_ANSWER_LABEL` | The truth header and what did not complete come before the answer, which is labelled unverified. | Qualifier. | c | **Kept** (a qualifier; it never hides). |
| B4 | `conversation_projection.py:321` `unknown` branch; `quickstart_service.py:6837` | An `unknown` external effect: the effect statement is the whole bubble. | The mandatory exception. | c | **Kept.** |
| B5 | `conversation_projection.py:422` `qualify_transcript`, `:439` `context_message` | Label on the web transcript and on the next worker's context for an unverified outcome. | Label only. | c | **Kept.** |
| B6 | `agent_runtime.py:2934` `_budget_end` | When the budget or Stop ended the run, the model's draft was dropped and AgentOS's rendering shown instead. | The AI's answer was lost. | e | **Removed.** The draft is delivered, with the stop reason. |
| B7 | `agent_runtime.py:3060` execution check, `:2761` `COMPLETION_CHECK` | The API loop asks the model once more before a first tool-less reply or a plain reply after tools. | The text delivered is still the model's own. | e | **Kept.** It is a worker-loop nudge, not an override. |
| B8 | `bounded_execution.py:1670`, `agent_runtime.py` `conclude` 24,000-character cut; Telegram preview | Size bounds on the answer. | Long answers are cut, with a pointer to the web. | bound | **Kept.** |
| B9 | `bounded_execution.py` `_content` | An empty or oversized final record raises `invalid-output`. | No answer exists to deliver. | e | **Kept.** |
| B10 | `bounded_execution.py:531` `redact_reason`, `quickstart_service.py` `_redact_reason`, `scrub_work_text` | Secrets and prompt echoes are redacted from causes and from preparation answers. | Redaction. | a | **Kept.** |
| B11 | `quickstart_service.py` appended `조회 출처`, `컨텍스트 출처`, `NOTICE_ONCE`, `MEMORY_PENDING_*_NOTE` | Appended receipts and qualifiers. | Append-only. | c, d | **Kept.** |
| B12 | `orchestrator.py:854` `next` | A re-delegated Work shows the last attempt's answer. | A later attempt runs only after the earlier reply was judged not to serve. | e (orchestration) | **Kept.** |
| B13 | `conversation_handoff.py:1191` `_mixed`, `:1183` `_ambiguous`, `:1116` mixed mail action, `:651` `unsupported_capability`, `:572` `UNSUPPORTED_JUDGMENT_UNAVAILABLE`; `quickstart_service.py:6349` clarification, `:6351` greeting text, knowledge, mail and workspace raw-row replies | Canned AgentOS text instead of a worker answer. | The worker never runs. | e | **Deferred.** |
| B14 | `quickstart_service.py:6092` | Telegram text over 12,000 characters is silently skipped. | The owner's message is dropped. | e | **Deferred.** |

## C. What decides the outcome

| # | Location | Rule | Effect before #820 | Protects | Disposition |
|---|---|---|---|---|---|
| C1 | `conversation_handoff.py:560` `GOAL_REACHED_PROPOSITION`, `:724` `goal_reached` | The judgment looked at observations only ("not from any claim"). Every part of the request had to be visible in tool results. | A statement, an acknowledgement or ordinary conversation was judged `no`. In the live Work: three attempts, three judge calls, then `failed`. | e | **Reduced.** It is now *the* one judgment: did the reply serve the owner's message, read with the recent conversation (a needed question to the owner serves it)? Claims of actions and of current facts must be supported by the recorded tool results; the reply's own claims are not evidence. |
| C2 | `orchestrator.py` `owner_input_needed` (removed); `conversation_handoff.py` `OWNER_INPUT_PROPOSITION` (removed) | A second judgment, asked after `no`, decided whether the answer was a needed question. | A second verdict over the outcome. | e | **Removed.** Folded into C1. |
| C3 | `conversation_handoff.goal_reached(criteria=…)`, `orchestrator.evaluate_answer` (#767) | The judgment was held to the plan's completion criteria. | Plan-written criteria overrode the owner's message. | e | **Removed.** |
| C4 | `quickstart_service.py:3324` `orchestration_step` (#767 review) | A direct-route run its own #657 rule accepted was judged again against the criteria. | A second judgment could demote it. | e | **Removed.** |
| C5 | `agent_runtime.py:2993` `conclude` | A plain final reply after tools, without a `finish` claim, was always `partial` (`GOAL_NOT_CLAIMED`). | Bookkeeping decided the outcome. | e | **Reduced.** The reply is judged once by C1 over every succeeded observation. `GOAL_NOT_CLAIMED` stays only when no judgment is available. |
| C6 | `agent_runtime.py:1539` `outcome_from_events` (CLI) | The CLI Work's outcome came from its tool events. | Steps decided. | c (evidence) | **Kept** as Evidence. For an orchestrated CLI Work, C1 decides through the #752 upgrade and `cli_shortfall`. The steps decide only when no judgment exists (fallback, or budget `not_judged`). |
| C7 | `quickstart_service.py:3186` `goal_upgrade_allowed` | A `yes` verdict does not make the Work succeeded while (i) a browser approval is pending, or (ii) a state-changing action failed and never later succeeded. | Outcome stays partial or failed; the answer is still delivered. | (i) b; (ii) c | **Kept.** |
| C8 | `quickstart_service.py:3275` `cli_shortfall` | Not reached means `partial`/`failed` and unjudged means `partial`, each with the #657 statement. The #740/#753 owner-question branches are gone. | A qualifier; the answer is delivered. | c | **Reduced.** The owner-question branches are removed; the rest is a label. |
| C9 | `quickstart_service.py:7004` login page | Without a `yes` verdict, a run that reached a login page is `partial`, with that cause. | A qualifier; the answer is delivered. | c | **Kept.** |
| C10 | `orchestrator.py:871` `next` (`STOP_EFFECT`); `quickstart_service.py:3347` `repeatable`, `:3351` unmediated host action | No re-delegation after an effect, an unknown effect, or a trusted-local host action. | Re-delegation stops. | c | **Kept.** |
| C11 | `orchestrator.py:718` repeat signature, `MAX_REDELEGATIONS`, `:609` `budget_allows` | Re-delegation bounds. | Re-delegation stops. | bound | **Kept.** |
| C12 | `agent_runtime.py:2833` `check_claim` | A `done` claim must cite settled, existing observations. | The claim is rejected back to the model. | c | **Kept.** |
| C13 | `agent_runtime.py:2434` `withheld_effect`, `:1462` `recovered`, `:1511` `state_change_short`, `:2517` `INCOMPLETE_QUALIFIERS` | Classify withheld, incomplete and recovered steps. | Evidence for C1 and C7. | c, d | **Kept** as Evidence. |
| C14 | `agent_runtime.py:3145` `repeat_path`, `duplicate_call`; `cli_browser_relay.py:170` | The same page step or search is refused. | The worker is refused. | c for state-changing steps; e for reads | **Kept** for state-changing steps; **Deferred** for reads. |
| C15 | `decision.py:318` `DecisionPolicy` thresholds | A verdict below the confidence threshold is unavailable. | — | bound | **Kept.** |

## D. Owner state, approvals and effects

| # | Location | Rule | Protects | Disposition |
|---|---|---|---|---|
| D1 | `agent_runtime.py:362` `memory_write_refusal`; `quickstart_service.py:2642` `owner_memory_approval`; `conversation_handoff.py:745` `explicit_memory_request` | A Memory write is canonical only when the owner asked and the value is the owner's own; otherwise it is a MemoryCandidate. | d | **Kept.** |
| D2 | `quickstart_service.py:1057` `decide_memory_prompt` | A tap confirms only the exact value shown. | d | **Kept.** |
| D3 | `quickstart_service.py:755` `owner_model_eligible` | Owner-model upkeep only after a succeeded or partial worker Work. | d (owner-directed minimisation, #805) | **Kept.** |
| D4 | `quickstart_service.py:642` `preparation_scheduler` | A standing preparation is scheduled only on the owner's explicit request; otherwise it is proposed. | d (the owner's authority over standing owner Work, #659) | **Kept.** |
| D5 | `browser_session.py` payment guard; `quickstart_service.py:4546` `browser_approvals_for` | Every payment step needs exact, single-use owner approval. | b | **Kept**, unchanged. #759's regression is not repeated: nothing in the approval path changed. |
| D6 | `mcp_bridge.py:60` `_work_running`, `:140` `unexpected_error_result`, `:115` `tool_error_result`, `declared_effect` recorded before a call | A call outside a running Work is refused. An unmapped failure of a non-read is `unknown`. | c | **Kept.** |
| D7 | `quickstart_service.py:1723` `safe_retry`, `:1759` `effect_calls`, `:1774` `cli_host_actions`, `:1654` `retry_effect_note` | No replay of a Work with effects, unknown effects or unconfined host actions. | c (the status and artifact refusals: e) | **Kept.** The e parts are **Deferred**. |
| D8 | `quickstart_service.py:1168` `owner_profile_snapshot`, `:1465` `record_turn_sent`; `agent_runtime.py:1720` `judgment_text`, `:46` `recorded_arguments`; `conversation_handoff.py:616` `redact` | Secret and private-value redaction before any prompt, judgment, log or Evidence. | a | **Kept.** |
| D9 | `quickstart_service.py:6845` `BLOCKER_MODEL_UNVERIFIED` | An API route whose tool-call probe has not passed is blocked. | e (setup) | **Deferred.** |

## Counts

The census has 63 rows. Each row is counted once, under its primary code. The e parts of C14 (reads) and D7 (status and artifacts) are deferred inside rows that are otherwise kept.

| Protects | Rows | Removed | Reduced | Kept | Deferred |
|---|---|---|---|---|---|
| a: secrets | 3 | 0 | 0 | 3 | 0 |
| b: payment approval | 1 (plus C7 part i) | 0 | 0 | 1 | 0 |
| c: no replay, truthful effects | 16 | 0 | 1 | 15 | 0 |
| d: Memory authority, owner state | 4 | 0 | 0 | 4 | 0 |
| g: private-doc egress guard | 8 | 0 | 0 | 8 | 0 |
| i: isolation | 1 | 0 | 0 | 1 | 0 |
| bound | 7 | 0 | 0 | 7 | 0 |
| e: none | 23 | 9 | 4 | 4 | 6 |
| **Total** | **63** | **9** | **5** | **43** | **6** |

- **Every rule that protects a, b, c or d is kept.** The one reduction is C8: its owner-question branches went, and the rest is now a label.
- **Of the 23 rules that protect nothing:**
  - 9 are removed: A1, A3, A5, B1, B2, B6, C2, C3, C4.
  - 4 are reduced to notes or labels: A2, A4, C1, C5.
  - 4 are kept because they never change what the owner sees or what the worker is asked: A9, B7, B9, B12.
  - 6 are deferred. They sit in the pre-worker command and intent layer, or are setup blockers and bounds: A21, A23, A25, B13, B14, D9.
- **The removals and reductions cover every failure mode of the day:** rewriting the owner's words (A1–A5), overriding the AI's result (B1, B2, B6, C1–C5), and blocking owner-state flow (A1, and A6's empty subset staying the full toolset).

## Live case (Work of 2026-09-28 16:05 KST)

The owner said "점심은 이미 반포6 분짜오 먹었어" (a statement: "I already had lunch at X").

**Observed on 65e75e3:**
- The plan wrote "short acknowledgement" with an empty tool subset.
- The worker acknowledged.
- The goal judgment, which read observations only, said `not_reached` three times.
- Three workers and three judge calls ran, and the Work was stored `failed`.

**Now:**
- The worker receives the statement verbatim with the conversation and its full toolset. The empty subset becomes the full toolset, so `save_memory` stays offered.
- One judgment reads the reply and the conversation.
- A `yes` ends the Work `succeeded` after one attempt.
- A succeeded Work gets the #805 owner-model upkeep, which proposes the stated fact.
- A worker that proposes the fact itself (a pending MemoryCandidate) is not re-delegated, and the Work ends `succeeded`.
- A reply judged short is still delivered under the truthful header.

`tests/test_orchestrator.py` `ThinOrchestration` reproduces this sequence with injected transports.

## Open for the owner

- **g rows (private-document egress guards).** `AGENTS.md` requires them, so they are kept. They are not among the pilot invariants a–d. Removing them (for example, pairing private reads with the CLI's own web search, A7 and A8) would widen private-data egress. That needs an owner decision and independent review, not a thinning change.

## Follow-up (deferred e rules, outside this change)

- **The pre-worker command and intent layer:**
  - A25 and B13: canned clarifications, mixed and ambiguous refusals, rule rewrites, raw knowledge, mail and workspace rows, and the greeting text;
  - route these to the worker with the owner's words instead.
- **Silent drops and refusals:**
  - B14: a Telegram message over 12,000 characters is dropped silently;
  - D9: the unverified-model blocker;
  - A23: specialists on a CLI;
  - A21: a preparation's conversation.
- **C14 for reads:** repeated reads refused as `repeat_path`.
- **D7:** the `safe_retry` status and artifact refusals.
- **A17:** shorten the envelope instead of sending the bare request.
