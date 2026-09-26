# Personal AgentOS Presence Experience Contract

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

### Failure and recovery

Explain:
- what is known to have failed;
- what result must **not** be treated as successful;
- the safest useful next action available in conversation.

Do not default to “open the web console” when recovery can be explained or initiated in chat. Technical diagnostics remain available through Task/Evidence detail.

### Partial outcome

State the verified completed portion and the unavailable/failed portion separately. Never collapse partial into success.

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

Settings › AI 연결 names the two roles **기본 AI (Main AI)** — the Work route — and **판단 AI (Judgment AI)** — the DecisionEngine route, labelled 판단 AI (대화 해석) so that owner pointers to 설정 › 대화 해석 land on it. They appear as one card with the Judgment AI as a subordinate line; the Judgment AI follows the Main AI by default (#619, see the DecisionEngine contract). Changing either happens in a fixed-order chooser; a saved credential is shown as saved with its date, never as a value.

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
H. partial result → verified and failed portions separated;  
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
