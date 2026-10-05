# OWNER-MODEL-01 phase 3 — current delivery contract

Governance: [GOV-DELIVERY-06 #1021](https://github.com/Jongtae/agentos/issues/1021), owner direction 2026-10-06. Implementation: [#794](https://github.com/Jongtae/agentos/issues/794). Parent: SECRETARY-01 [#662](https://github.com/Jongtae/agentos/issues/662). Root [delivery-plan.yaml](../delivery-plan.yaml) owns selection and dependencies; GitHub Issues, PRs and required Checks own execution status.

This is a bounded delivery refinement of the existing owner-model and [#918](https://github.com/Jongtae/agentos/issues/918) decisions, not a new memory architecture. It does not claim phase 3 is implemented.

## 1. Current work and order

The next coding unit is **#794 phase 3 only**. Its iteration is enumerated under SECRETARY-01 and `parent-controlled`; the parent's `active_substeps` names `OWNER-MODEL-01`. The checked-in `next_goal` deliberately remains `owner-activated-goal-ready`. This resting planning state does not start Codex, enable a heartbeat or authorize an owner-live run. An execution controller must still follow the existing Goal Execution Contract and inspect current GitHub state before work.

Current order:

1. #794 phase 3: individual correction / forget and durable receipts.
2. #660: owner-operated A/B/C and held-out D, plus phase-1 completion audit on the closeout head.
3. GOV-OSS-01 #875 Track A: a separately made-ready memory-interchange implementation.
4. #661: family delegation through A2A.

`OSS-MEMORY-01` in the root plan is a **reserved dependency gate without an implementation issue**, not permission to start coding. After #794 and #660, give it its own bounded issue, goal-ready scope, interfaces, ownership and acceptance before implementation. Do not skip the gate to reach #661. A new explicit owner re-plan can change this order; closing a child cannot.

## 2. Reuse; do not repeat completed work

The source review for this refresh used main `735bfebe4a1555d4e8b7e4ce0acbc94fbd1f4e89` and the issue/PR evidence below. Implement on current main, not on that historical inspection head.

| Existing work | Use in phase 3 | Do not redo |
| --- | --- | --- |
| #886, #794 phase 1 | Durable per-Work judgment journal and export | A new journal or hidden chain-of-thought storage |
| #896, #794 phase 2 | Existing source Work lookup and truthful source status | A new owner-model management page or source store |
| #972, #918 slice (a) | Current Memory saves, supersession, exact retraction and save-notice undo | The already-shipped save-without-asking feature |
| MemoryService / QuickStore | Existing owner-scoped reads, correction, deletion and transaction seams | A second canonical memory database |
| Current context / observations | Existing item identity, validity, source and owner-control seams | A new inference engine or collection source |
| #894 completed spike | Later Track A compatibility input | Repeating the whole public-memory research as implementation |

Decision: **Adapt** the existing contracts and mechanisms. For this governance change, reuse root JSON-compatible YAML, the existing `DeliveryPlan` and `tests/delivery_state_invariants.py`; add no selector or scheduler. For phase-3 implementation, inspect the current symbols and tests before choosing the smallest change. Reuse Python/SQLite transactions, the current service tick and existing owner-bound callback/receipt patterns. A new dependency, framework or replacement store needs a concrete unmet requirement and its own C15 review; none is selected here.

## 3. Required owner outcomes

A clear request is handled in conversation; the owner does not navigate a management console. The AI resolves meaning through the existing semantic path. Deterministic code enforces owner scope, exact item/version, state transitions and truthful receipts rather than recognizing task/site-specific phrases.

**Correct.** For a request such as “그건 잘못 기억했어. 지금은 이렇게 바뀌었어”, change the identified Memory or current-state claim through its owning service. Subsequent current retrieval uses the corrected information. Distinguish a correction from a fact that became outdated. Ask a clarifying question only when the target or requested change is genuinely unresolved.

**Forget.** Apply #918 option B: the identified Memory, claim or observation is immediately excluded from current use, with a durable receipt and an exact 7-day undo; then purge the covered payload when the window expires. Resuming after a process restart must preserve the exclusion and execute overdue cleanup safely. Do not conflate this with the already-implemented undo of a newly saved Memory.

**Complete deletion.** An explicit request such as “완전히 지워” uses the immediate-purge path without waiting for the undo window. Report success only for the deletion actually performed; stale targets, partial deletion and failure have distinct truthful results.

An undo binds to owner, exact item and version. It must not restore another owner's item, revive an expired/purged item, or overwrite a later correction. Repeated delivery or callbacks must not repeat the state change.

## 4. Deletion scope and evidence

Before implementation, name the existing local payloads, derived retrieval entries and pending reuse paths covered by each operation. Prevent information excluded by this operation from reappearing through those retained derived paths, restart recovery or upkeep. A later explicit owner statement is distinct from reprocessing a withdrawn source.

Keep a durable, content-free receipt: operation identity, affected item identities, scope, time, state, counts and result are sufficient. Do not retain the deleted personal content inside the receipt. Preserve useful audit truth without indiscriminately deleting every Work or treating every retained historical record as current Memory.

No claim is made that local forgetting erases copies already sent to an external provider, separately exported bundles, backups or every physical storage remnant. State the implemented local scope and any remaining references precisely. Do not silently expand this task into a global data-erasure or storage-forensics program.

## 5. Boundaries and ownership

Use the `owns` list on the #794 iteration in the root plan. Only touch the owner-state and conversation/service seams required by phase 3, their focused tests and relevant contracts. Shared `quickstart_store.py`, `quickstart_service.py`, runtime/bridge and owner-model files serialize with other sessions. The broad `tests/` entry permits relevant tests, not unrelated cleanup.

Preserve #972's owner-worker versus third-party Memory boundary, existing folder/owner Grants, secrets exclusion, payment approval, idempotency and truthful unknown-effect handling. Do not add a new management UI, hard-coded site behavior, new collection sources, external destinations, a runtime plan mirror or a scheduler. **#918 slice (b), settings/family auto-apply, is not selected by this task.**

The subsequent implementation changes owner-state semantics and **requires independent review** under the existing risk rule. This governance refresh changes planning only; it neither supplies nor fabricates that implementation review.

## 6. Bounded verification

Use temporary stores, injected model/tool transports and fake clocks. Extend the existing memory-service, memory-continuity/search, save-undo, current-context/observation, upkeep and information-use tests. Add only the small service/serialization integration checks needed to exercise the real affected boundary.

Required phase-3 counterexamples cover: wrong owner; wrong or stale item/version; later correction before undo; repeated request/callback; restart during the undo window; overdue purge after restart; failed/partial purge; and exclusion from the declared current/derived reuse paths. Keep the no-scenario-code check. Do not mock away the actual database transition or claim fixture results as live owner operation.

No broad live-model sweep, new evaluator or repeated-trial quota is required. Required exact-head CI and the risk-triggered implementation review remain mandatory.

## 7. Completion and handoff

Close #794 only after its remaining acceptance is mapped to merged implementation, relevant regression evidence, required CI and the required independent review. Reuse phases 1/2 as evidence; do not close #794 merely because a plan or an undo button exists. Preserve GitHub-native execution status rather than copying every PR transition into trackers.

Then #660 remains necessary: run its owner-authorized, budgeted probes and audit, including the native Telegram concerns consolidated from #581. Recheck account/session/profile prerequisites at operating time; the 2026-09-28 observations are not proof of the owner's current configuration. Held-out D must not become a development fixture. Missing owner-live authorization blocks an operating claim, not safe phase-3 coding.

For Track A, reuse #894 and verify only current, concrete format/SDK compatibility gaps. Its reserved entry becomes executable only with a separately recorded implementation issue and authority. #661 follows completed predecessors, not just a completed format spike or governance issue. Closed legacy #581/#667/#805/#814/#842/#893/#894/#897 remain history and must not be reopened from outdated queue prose.
