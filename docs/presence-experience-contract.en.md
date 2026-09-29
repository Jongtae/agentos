# Personal AgentOS Presence Experience Contract

## Current goal selection — SECRETARY-01 / #662 resumed (2026-09-28)

The owner resumed SECRETARY-01 / #662 as the current top-level goal on 2026-09-28 (GOV-SECRETARY-04 / #770) after UX-RENEW-01 closed out. This contract remains the owner-facing experience contract; the UX-RENEW-01 presentation below is merged and is regression input.

## Amendment — PRESENCE-MEM-01 / #836 (2026-09-28): one memory ask, spoken as the secretary

Owner feedback 2026-09-28 (live Telegram, one message about a discounted-sushi dinner): "두 번 물어봤고, 첫 번째에 답을 하면 그 뒤에 것도 처리가 되어야 함. 그리고 AgentOS가 라면서 시스템 툴을 다루듯이 했는데, 우리의 컨셉은 presence잖아." That one message produced two separate "기억해 둘까요?" asks, raw memory keys, and a reply that narrated AgentOS approval machinery. It amends the #818 rules in the [Secretary Agency Contract](secretary-agency-contract.en.md).
- **One ask per owner message (Work).** Every MemoryCandidate of the same Work is in one Telegram ask, whether the worker's `save_memory` or #805 upkeep proposed it. A candidate that arrives while the ask is open is added by editing that message (Telegram `editMessageText`); it is bound to the buttons only once the edit is confirmed. A candidate that arrives after the owner answered is settled by that answer, because the answer covers what the owner said in that message: yes saves it through the owner approval path, no drops it. The binding records it as decided by the owner's answer to that Work's ask. A yes never replaces a current Memory the owner was not shown, and mixed answers do not settle anything: in both cases the ask reopens with the new fact. Upkeep reads what the Work already noted and does not re-propose it.
- **Natural wording.** The ask lists each fact as its value, never a memory key; a value written like a key is shown as its words. Buttons are 기억하기 / 아니요. Once answered, the message reads "기억해 둘게요." or "기억하지 않을게요." with what is kept. The "기억한 내용은 내 기록에서 고치거나 지울 수 있습니다" line is gone.
- **No machinery in replies.** The worker reads a held `save_memory` only as "not remembered yet; the owner will be asked with one tap; do not describe how remembering works; you may say you would like to remember it". It never sees AgentOS, approval, candidate or storage wording. The core instructions say to speak as the owner's secretary and never narrate AgentOS, tools, approvals or internal states. Telegram no longer appends "기억은 아직 저장되지 않았어요…": the ask below the reply is the ask. The web, which has no inline ask, keeps one short line ("기억해 둘지는 내 기록에서 골라 주세요.") until the Work has nothing pending.
- **Kept.** Nothing becomes canonical Memory without the owner's answer or an explicit request (#597), secrets are never shown or saved, and nothing is described as remembered before it is (truth before fluency).

## UX-RENEW-01 / #688 (2026-09-27, complete)

The owner selected UX-RENEW-01 as the then-current top-level goal, with governance activation in #690 and sequential presentation-only work in #691–#696. The owner explicitly lifted the earlier Secretary program exclusion of revisiting merged Presence/Settings/Telegram/current-context presentation. This contract remains the owner-facing experience contract for those slices; all state, Grant, approval, privacy, connector, Work/Event/Evidence, and external-effect rules below remain in force. PR #687 has merged and released its overlapping `src/personal_agent/web` files; implementation starts after governance PR #697 merges. SECRETARY-01 / #662 was owner-paused by #690 with its agency scope and completion criteria preserved, and was resumed by #770.

## Secretary agency re-plan — #653 (2026-09-26, historical selection)

Owner decision 2026-09-26 originally activated **SECRETARY-01 [#662](https://github.com/Jongtae/agentos/issues/662)** under the canonical [Secretary Agency Contract](secretary-agency-contract.en.md), activated by GOV-SECRETARY-01 [#653](https://github.com/Jongtae/agentos/issues/653). On 2026-09-27, #690 paused it in favor of UX-RENEW-01; on 2026-09-28, #770 resumed it. The center of that program is the secretary agency loop: the decision model chooses providers, sites, queries and recovery paths from the owner's context; deterministic code enforces only Grants, approvals, secret exclusion, idempotency and Evidence. PRESENCE-01 #508 is owner-paused; its merged work is regression input.

**Pilot posture.** One owner, own machine, own accounts. Enforced at request time: secrets never enter a model prompt, log or Evidence; payment needs per-action owner approval. Per-request sensitivity judgments, re-asks, per-provider gating and the "no cart authority" rule are removed from the request path and deferred to a separately activated hardening program. The #625 paragraph below and the AGENCY/#605 egress-composition rules are historical for this program; Attention preparations and phase-2 family delegation are explicitly selected, not deferred.

**No scenario-specific code.** Probes (book → cart, calendar reminder, lunch with allergies, one held-out) are observation windows, not completion criteria. Decision/runtime code must not branch on a named site, provider or question category; every PR states whether it generalizes the loop or only makes a probe pass.

## Current-context adoption — #625 (2026-09-26)

For the selected single-owner current-state scope, read [Current context contract](current-context-contract.en.md) and [Implementer playbook](current-context-implementation.en.md). This selectively adopts #383 observation/time/current-state principles, not background Attention or multi-person collaboration. The plan is existing #605 → #606 → #607 → #626 input/time → #627 current-state consumption → #608/#512/#513; #625 is the immediate documentation adoption. Existing #616 and other independently directed work are preserved. Current-context claims remain unimplemented until those children deliver. Earlier blanket #383 deferrals do not exclude these two explicitly selected slices. #612 unit-test-first verification and concrete reuse still govern; no extra evaluator, graph platform or per-tick model calls. The new source-time, retention, inference/disclosure defaults and migration/test details are canonical in the two linked documents rather than duplicated here.

## Execution integration refinement — AGENCY #600

Presence requires useful action, not only natural projection. The [execution contract](assistant-execution-contract.en.md) and [delivery/ownership](assistant-execution-delivery.en.md) add actual tool reachability, safe context composition, typed recovery and separate model/installed-owner qualification. Reuse #597/#598 and #581. #512 can run fixture baselines early; final convergence follows #608 and cannot promote missing/xfail/stale or fixture-only evidence. No authority to weaken grants, privacy guards or uncertain-effect handling follows from this refinement.

## Status and purpose

This is the canonical owner-facing experience refinement for conversation, Settings, contextual capability handoff and recovery. It distills the 2026-09-23 focused [Presence and Settings UX research](research/presence-and-settings-ux.ko.md) into implementation and review rules. Experience convergence is tracked by [PRESENCE-01 #508](https://github.com/Jongtae/agentos/issues/508). On 2026-09-24 the owner selected Presence as the next product goal; governance migration is tracked by #523. This document still does not itself authorize runtime execution outside the delivery-plan contract.

It does **not** replace the kernel authority model, the Owner Control Contract, Work/Event/Evidence semantics, Grants/approvals, or the Goal Execution Contract. It does not claim every target behavior is shipped. Current capability claims still require merged implementation and named evidence.

## North Star

> **Personal AgentOS is not a chatbot that sounds more human. It is an owner-controlled kernel whose machinery recedes behind one continuous, truthful personal-assistant relationship.**

Use this as a product decision filter for owner-facing work: keep the kernel strict and inspectable, while moving internal execution machinery behind a continuous assistant relationship unless the owner explicitly asks to inspect it.

## Product definition of Presence

**Presence is the experience of one continuous, context-aware personal assistant across turns, tools, workers, failures, restarts and capability handoffs, while AgentOS continues to enforce truthful Evidence, explicit owner authority and inspectable technical state underneath.**

Presence is not anthropomorphic theater, verbose friendliness, fake emotion, artificial delay, or pretending uncertainty is certainty. The product should feel continuous because it resolves references, remembers authorized context, recovers conversationally, asks for authority at the moment of need and translates kernel state into the minimum owner-relevant explanation.

The kernel remains mechanical and strict:

`Work → Event → runtime/tool → Evidence → outcome`

The owner-facing projection should instead read as:

`owner intent → assistant understanding → contextual authority if needed → work → verified result → natural continuation`

## Experience principles

1. **Conversation first; receipts on demand.** Lead with the useful answer or next action. Technical receipts remain inspectable but are not the default conversation.
2. **One assistant voice over many workers.** Codex, Claude Code, models, connectors, MCP tools and specialist runtimes execute work; they do not become separate speaking identities.
3. **Continue before restarting.** Resolve a new turn against recent conversation focus, unresolved Work, corrections and approval state before creating an unrelated interaction.
4. **Communicate semantic progress, not scheduler state.** Do not mechanically project queued/running/completed lifecycle events. Send only progress that changes what the owner needs to know.
5. **Truth before fluency.** failed, partial, unknown and approval-pending state constrain the response before conversational wording is applied. Model prose never outranks observed Evidence.
6. **Ask at the moment of need; manage afterward.** Capability, folder and account authority should be requested contextually when needed. Settings is primarily for inspect/change/revoke/manage.
7. **Memory is useful, scoped and correctable.** Short-horizon conversational focus and durable Memory are distinct. Durable memory remains inspectable, correctable and revocable.
8. **Proactivity must earn the interruption.** Attention/heartbeat can amplify Presence later, but reactive Presence must work without it and unsolicited contact requires relevance, authority and timing.
9. **Model-first semantics; rules only where exactness is unavoidable.** Ordinary language/intent/reference/routing/recovery/projection decisions should use the provider-neutral DecisionEngine rather than keyword lists, regexes or capability-specific branches. Deterministic code remains authoritative for security, owner authority, approval, idempotency, effect/Evidence truth and protocol/state invariants.

## Model-first semantic interpretation

Presence must not become a larger hand-authored conversation rule engine.

Use the AgentOS-owned `DecisionEngine` boundary from [the decision-layer contract](decision-layer.en.md) for ordinary semantic judgment over bounded conversation/Work context. The initial production default is OpenAI `gpt-4o-mini`; the provider is configuration behind the neutral interface and may later be replaced by an owner-selected AI, a local model, Jev or another adapter.

Typical semantic decisions include:
- intent/focus and whether a turn is a new request, clarification, correction, continuation or reference;
- selecting among declared capabilities/workers that are already eligible under policy;
- resolving “that / try again / change it to 4pm” against relevant recent Work;
- choosing direct reply vs contextual handoff vs approval/recovery/long-running acknowledgement;
- selecting an owner-facing projection strategy for a truth-qualified outcome.

A deterministic/mock DecisionEngine is appropriate for CI and fixture-backed acceptance. It is not the normal production fallback for arbitrary language understanding. Provider failure should result in an explicit unavailable/unknown/clarification or safe-stop state, not silently re-enter a keyword/regex rule tree.

The model never owns truth or authority. Grants, approvals, effect classification, idempotency, cancellation/revocation, Evidence qualification and final success/partial/failed/unknown state remain deterministic AgentOS/kernel responsibilities.

## Surface responsibility

| Surface | Owns | Must not become |
| --- | --- | --- |
| Conversation / Telegram | intent, clarification, repair, answer, contextual handoff, meaningful progress, recovery, conversational approval | a Work-status or engine-log console |
| Local approval surface | filesystem picker, read/write grants, owner-bound OAuth, consequential preview, allow/deny | a remote chat link that silently grants host authority |
| Settings | inspect/manage/change/revoke AI route, connections, folder grants, Memory/preferences | mandatory tutorial/onboarding before ordinary tasks |
| Task / Evidence detail | exact Work timeline, worker/tool IDs, sources, errors, approvals, partial/unknown details | the primary path for every ordinary result or failure |
| Internal kernel | Work/Event/Evidence/Context/Memory/Grant/effect state/idempotency/routing | the user-visible personality |

## Conversation projection rules

### Short work

A short ordinary request should normally yield one useful answer. Internal Work and Event records may exist, but receipt/running/completed chatter is not emitted by default.

### Long-running work

One concise acknowledgement is allowed when latency or handoff makes it useful. Further updates require a meaningful owner-relevant state change such as a blocker, authority request, important partial result or completion. Event count must never mechanically determine message count.

### Telegram presence: reactions, thinking draft and typing (#581, #835, #858)

Owner feedback 2026-09-28 (#835) and 2026-09-29 (#858): a fixed reaction meant nothing, the "생각 중…" wait text felt stiff, and the header `typing…` ended too early. These changes stay presentation only: Work, Event, Evidence and outcome semantics are unchanged, and every reaction, chat action and draft is a best-effort call whose failure never fails, duplicates or changes Work.

- **Reaction on the owner's message.** For every natural-language turn (commands get none), 👀 is set immediately as the deterministic fallback, then the Judgment AI chooses a reaction from the curated documented Telegram emoji set using only the owner's message. A confident offered choice replaces 👀; unavailable, unconfident or `none-of-these` keeps 👀. When an observed running step changes, the Judgment AI may choose one progress reaction from the curated documented set using only that step's already Work-redacted progress line. One decision is made per distinct observed step identity, never per wait poll or draft refresh. The reaction replaces the prior one; Telegram permits only one regular bot reaction per message. Unavailable, invalid, unchanged or failed progress judgment leaves the current reaction untouched. Progress choices do not imply completion and are presentation only. When the Work has a succeeded, delivered, non-blocked answer with nothing awaiting the owner, the Judgment AI chooses the closing emoji from its curated documented set using the owner's message and content-free delivery facts (the answer was delivered and whether an observed note/Memory write occurred). The answer body is never sent to this presentation judgment because it may contain private source material. Unavailable, unconfident, a judgment error or `none-of-these` keeps the deterministic 👌 / ✍ choice. Telegram is not called when the chosen emoji equals the one already shown. No closing judgment is requested for any other outcome; `partial`, `failed`, `unknown`, `cancelled`, `interrupted`, a blocked reply, an uncertain delivery, or a succeeded Work that still waits for the owner's approval removes the reaction and shows no replacement emoji. A parked Work (awaiting a connection, Drive or context) keeps its reaction until it ends. Approval/payment steps receive no progress reaction. All judgment contexts use the existing secret redaction and contain no history, Memory, files or mail. Candidate emoji are curated from the set Telegram documents as available and exclude rude, mocking or dismissive reactions (pinned by a test).
- **Waiting draft.** From 5 s, `sendRichMessageDraft` with Stop shows Telegram's animated thinking block. Its text cycles through dots (`·`, `· ·`, `· · ·`), one edit per 1.5 s, with an observed step line (#718) kept before the dots. The #839 attention reminder is a following paragraph block, outside the thinking block. Edits use the same `draft_id`. If the rich method is refused for a Work, it is not retried; the plain `sendMessageDraft` carries the same dots and paragraph, and if that is refused too the existing fallback is `typing…` only. The thinking text is never empty (an empty plain draft is a blank bubble on the owner's iOS client, #581). While an approval prompt is pending it is the only surface.
- **Attention while waiting (ATTN-WAIT-01 / #839, owner direction 2026-09-28).** "생각하는 중을 보여 줄 때 틈새로 attention 기회로 삼아야 할 듯, 전달하려고 준비했던 걸 이때 상기시키는 게 어떨까 싶음." While the dots draft is shown, it may carry one more line, "참, …", that reminds the owner of ONE item AgentOS already prepared for them. Selection is deterministic from existing state and makes no model call: first a fresh prepared answer (#659) that did not reach the owner as a message, then an owner-accepted reminder due within 12 hours, then an ask still waiting for the owner (a proposed preparation, an open memory ask, #836). Items the current Work is itself about (its own preparation run, its own proposals or ask) are excluded; the same item is not repeated within 6 hours; at most one item per Work, kept on every frame of that Work's draft. Only when a draft is shown at all (from 5 s), so never during an approval or payment step, where the approval prompt is the only surface. The wording is the item's own text, redacted like any draft line, never a memory key. The draft is ephemeral, so the item's durable surface is unchanged: an ask keeps its own message and buttons, a reminder still fires at its time, nothing is decided, accepted or delivered by the draft. Each surfacing is recorded as a `presence` event with the item reference and shown line, so the Work's information-use audit (#826) lists it under 기다리는 동안 알린 것. Follow-up, not done here: repeating the line once on the final answer when the item is still pending.
- **Typing.** `typing…` is refreshed at least every 4 s for as long as the Work runs, a draft shown or not. Presence calls and the final reply are serialized under one lock, so no `typing…` or draft follows the answer; the optional Judgment AI closing choice runs after the lock is released so a slow judgment cannot block polling or Stop updates.

### Failure and recovery

Explain:
- what is known to have failed;
- what result must **not** be treated as successful;
- the safest useful next action available in conversation.

Do not default to “open the web console” when recovery can be explained or initiated in chat. Technical diagnostics remain available through Task/Evidence detail.

### Partial outcome

State the verified completed portion and the unavailable/failed portion separately. Never collapse partial into success.

**The goal decides the outcome, and the owner gets the answer (#752, owner direction 2026-09-28).** A Work's outcome is whether the owner's request was met, not whether every intermediate step succeeded. A worker that reads a bounded view of a long page, retries a click that found nothing, or works around a login page has not failed. When the goal judgment (#657 direct route, #710 CLI route, including after an effect) sees the request met, the Work succeeded, and its steps stay in Task/Evidence detail. The exceptions are a pending owner approval (C14) and a state-changing action that fell short without later succeeding: the verdict never outranks either. A `truncated` qualifier no longer makes a call incomplete.

A failed or partial Work that has an AI answer delivers that answer first, closed by one short note (#847, below). An `unknown` effect keeps its own statement. A login prompt is offered only when the Work did not succeed.

**The answer is the message; machinery stays in 상세 (PRESENCE-ANS-01 / #847, owner observation 2026-09-28).** A good Telegram answer arrived under three machinery lines: `일부 단계만 완료했습니다.` / `완료하지 못한 부분 — 브라우저에서 누르기: 일치하는 요소가 없습니다.` / `AI 답변 (위 부분은 확인되지 않았어요):`. That is the #836 presence violation on the answer path. Now the delivered message is the secretary's answer, and the truthful qualifier is at most a short closing note (`한 단계는 확인하지 못했어요.`, `요청하신 작업은 끝내지 못했어요.`, `중간에 멈춰서 끝까지 확인하지 못했어요.`): steps that errored are counted, never named; a withheld step's own next step (an approval, a login, a confirmation) is spoken as written; the worker's question to the owner and its proposed next step follow as sentences. Never a header block, a tool name, a host action or an element-matching error. Step-level detail stays in 상세/작업 현황 (the Work's technical cause and owner-word cause are unchanged). Invariant c holds: a failed state-changing step is never reported as done, `unknown` keeps its explicit statement, and a bubble without an answer is unchanged. Both the Telegram bubble and the watch notification use the same projection.

**Telegram renders Markdown tables as lines (PRESENCE-TG-03 / #848, owner observation 2026-09-28).** A worker answer with a Markdown table was delivered raw (`| 출발 코스 | 티타임 | 표시 가격 |`, `|---|---|---:|`); Telegram has no tables. The #581 HTML formatter now renders a table (a `|` row followed by a separator row) as one bold header line and one line per data row, cells joined with ` · `, alignment separators dropped, bold and links inside cells kept. Deterministic formatting, no model call; the stored answer keeps the model's own text.

### Unknown external effect

Say the external effect is unknown, explain duplicate-risk when relevant, and do not automatically retry a consequential effect without evidence/authority making that safe.

### Follow-up continuity

Turns such as “try again”, “does it work now?”, “make that 4pm”, “cancel that”, and corrections must resolve against the relevant recent intent/Work when unambiguous. Retry/recovery relationships remain attributable in Evidence.

## Identity and worker changes

The assistant identity is owned by Personal AgentOS, not by the selected model/runtime. Changing Codex → direct API → Claude Code must not feel like changing to a different assistant.

Worker/runtime identity is still inspectable in technical details when observed. Configured identity must not be presented as observed execution identity.

## Contextual setup and authority

A missing capability should produce one contextual next action tied to the owner’s task.

Examples:
- Gmail needed → request owner-bound connection, then resume the original Work exactly once.
- local folder needed → hand off to an owner-local folder picker showing read/write authority, then resume exactly once.
- consequential Calendar create → show exact effect preview and require covering approval.

Conversation may trigger the handoff; it must not bypass the local/owner authority boundary.

## Settings contract

Settings is a preferences/management surface.

Default rows should expose owner concepts such as:
- service / route / folder name;
- current owner-visible state;
- one obvious action.

Use distinct states for **currently used**, **configured**, **available**, **connected**, **needs attention**, and **not connected**. Never use “configured” as a synonym for “currently used”.

Raw connector IDs, capability IDs, grant IDs, provider diagnostics, scopes and verification timestamps belong under technical details unless directly necessary for an owner decision.

AI settings must show exactly one effective route when one is selected. A successful configuration test does not silently activate that route.

Settings › AI names two peer roles: **기본 AI (Main AI)** — the default Work route — and **판단 AI (Judgment AI)** — the orchestrating DecisionEngine route. Following the Main AI is a preference, not a subordinate role hierarchy (#780). Preserve owner pointers to 설정 › 대화 해석. The current compact settings specification is [UX-SPEC-02](design/settings-ux-renewal-spec.en.md): one sidebar, no in-content logo, current values before editing, verification separate from selection, access implications visible, all existing language controls preserved. Changing either AI uses a fixed-order chooser; saved credentials display presence/date, never values.

**Conversation-first settings (#814, owner direction 2026-09-28).** The owner's AI can read the basic settings in conversation (`settings_read`: Main AI route and model, Judgment AI mode and model, current context on/off and time zone, owner-model upkeep (#805) pause and daily call cap, connections; values, labels and allowed choices only) and propose a change (`settings_change`). A proposal is a digest-bound `SettingsOrchestrator` draft and applies nothing: the owner confirms it in the same conversation, and only then the service's existing setter runs, once, after re-checking the value is still current and allowed. **Owner direction 2026-09-29 (OWNER-SETTINGS-02 #855):** confirmation is a 적용 / 바꾸지 않음 button (Telegram, and the same pair on the web chat turn that proposed the change, through the Work-scoped draft endpoint) or the owner's next typed message in that conversation: the DecisionEngine judges, over the pending change and the message, whether it plainly confirms (apply, the buttons' own path) or plainly declines (cancel); anything else, including an unavailable judgment, leaves the draft pending and the message is handled as a normal turn. No command such as `/settings 확인 <id>` is ever shown to the owner - not in the worker's `settings_change` result, the draft prompt or the confirmation message; the typed forms remain accepted silently for compatibility only. Text confirmation counts only on a Work whose message the owner typed (web chat or Telegram text, the `owner_typed` job marker); a preparation goal, a continuation, a retry or any other AgentOS-run message can never confirm or cancel. A setter that only queues a change (Judgment AI 기본 AI 따라가기) is reported and audited as requested, not applied; a setter that probes or qualifies an AI is queued, in order, on one background worker off the caller's thread, and each result follows in the same conversation. The stale-value check and the setter run under one lock per category, so of two drafts with the same starting value only the first applies. A draft a restart cut off mid-apply is settled `unknown` (never re-applied), and the owner is told to check the current value. Values are fixed choices (a Main AI route only among connected and checked routes, which is a destination change) or a validated IANA zone. Credentials, keys, tokens, logins and endpoints are never read or changed in conversation; they stay in Settings. The tools are relayed on trusted-local and unavailable on strict-isolated/isolated. Follow-up: a first-run onboarding conversation (the typed yes was delivered by #855).

## Truth and authority invariants

Presence may change projection, never the underlying truth boundary:

- failed/partial/unknown remain distinct;
- unknown consequential effects are not blindly retried;
- approval is not removed to make conversation smoother;
- silent provider/paid-route fallback is not allowed;
- MemoryCandidate is not described as remembered until canonical Memory actually changes;
- owner-visible claims must be supported by observed Evidence;
- secrets/raw payloads/hidden reasoning do not become “transparency” requirements;
- projection never moves approval requests, data-destination/provider/route changes, consequential-effect outcomes, blockers or failed/unknown state into on-demand-only detail;
- this contract does not change which surface may authorize a consequential effect: conversational and local approval remain governed by the existing approval contracts and the [Owner Control Contract](owner-control-contract.en.md), including its messenger privacy boundary.

## Observable acceptance matrix

Presence work is not complete through copy review alone. Evidence should include owner-visible transcripts and their supporting internal state.

At minimum verify:

A. trivial request → useful answer without routine lifecycle bubbles;  
B. failed runtime → truthful conversational failure + safe next action;  
C. “try again / does it work now?” → resolves to prior failed Work;  
D. missing Gmail → contextual connect handoff + exactly-once resume;  
E. missing local folder → owner-local picker + scoped read/write grant + exactly-once resume;  
F. Calendar effect → exact preview + approval boundary;  
G. long research → selective semantic progress, not scheduler narration;  
H. partial result → truth header and failed portion first, then the labelled AI answer (withheld only after a failed state-changing action);  
I. unknown effect → unknown wording + no unsafe automatic duplicate;  
J. Memory correction → canonical/pending state reported truthfully.

For each relevant scenario capture:
- Telegram/message count and order;
- observed Work/Event/Evidence outcome;
- owner-visible claim ↔ Evidence correspondence;
- opposing failed/partial/unknown cases;
- restart/recovery where material.

## Architecture implication

Do not invent a second kernel or conversation database merely to implement Presence. Prefer an AgentOS-owned projection/policy layer over the existing authoritative state:

```text
internal state
+ conversation focus
+ relevant memory
        ↓
truth / authority gate
        ↓
conversation projection policy
        ↓
Telegram / conversation
```

Technical and preference projections remain separate:

```text
internal state → technical projection → Task / Evidence detail
canonical configuration → preference projection → Settings
```

## Relationship to planned work

The research recommends Presence as an **experience-convergence** program, not a new kernel architecture.

- #381 is the planning/research predecessor.
- retired #480/#477/#478 requirements are consolidated into #510 conversational projection instead of narrow phrase/capability fixes.
- #476 and #488 are truthfulness invariants/regressions, not Presence reimplementations.
- #494 is the consolidated Presence truth-integrity child for outcome/Evidence/history qualification (absorbing retired #489/#490/#493 requirements).
- #504 remains the effective AI-route owner-control issue.
- #505 is the contextual capability/local-authority handoff child; Calendar-read #475 is retained only as a fixture/example, not a dedicated intent rule.
- #506 remains the Settings grammar/state/action issue.
- #383 Attention/proactivity is later amplification, not a prerequisite for basic reactive Presence.
- completed #386/#393 mechanisms should be reused rather than reopened.

## Non-goals

This contract does not:
- weaken Work/Event/Evidence/Grant/approval semantics;
- create consciousness/personhood claims;
- require heartbeat or proactive monitoring;
- require a new UI framework;
- hide technical Evidence from the owner;
- grow a phrase/regex/rule-based production conversation engine;
- silently activate any GitHub issue or delivery-plan goal;
- turn the local web management utility into a second conversation client.

## Review rule

Any owner-facing conversation, recovery, model-route, contextual setup, Settings or capability-handoff change should explicitly state how it preserves this contract or why a bounded exception is necessary. A visually smoother UI or friendlier sentence is insufficient if continuity, truthfulness, authority or inspectability regresses.
