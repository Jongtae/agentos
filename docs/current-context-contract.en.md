# Current context: product and authority contract

## Status, reader and scope

Owner-requested direction, 2026-09-26; adoption issue [#625](https://github.com/Jongtae/agentos/issues/625). This contract becomes canonical for the two enumerated context slices on normal adoption merge. It is **not a statement of implemented or observed product behavior**. [Implementation playbook](current-context-implementation.en.md) supplies exact code seams, migration, sequence and tests. GitHub owns execution status; root `delivery-plan.yaml` owns selection and dependencies. #612's unit-test-first policy continues unchanged.

Outcome: **the assistant uses what the owner has already supplied, together with source time and relevant observations, to do useful work with fewer repeated questions.** It may estimate the current situation, but does not turn an estimate into a measurement, durable fact, consent or completed action.

First scope: one owner, Telegram volunteered location and conversation time, temporary work-mode/current-place hypotheses, existing weather and local-information requests. Two implementation issues: [#626 input](https://github.com/Jongtae/agentos/issues/626), then [#627 state and consumption](https://github.com/Jongtae/agentos/issues/627). Existing #605/#606/#607 remain their owners; this is not a replacement program, second scheduler or prerequisite for already-completed #604.

## Decision ledger: settled versus not selected

| ID | Decision | Implementation consequence |
| --- | --- | --- |
| CC-D01 | Adapt #383's PA-P2 and relevant PA-P1/P3/P6/P7, REQ-04/24/25 for single-owner reactive context now | Do not defer current-state understanding with all of Attention |
| CC-D02 | Facts, source reports, model interpretations, current hypotheses and habits differ | Preserve kind, source, time and validity; no inferred canonical Memory writes |
| CC-D03 | Conversation may be understood across turns; external disclosure is purpose-specific | Earlier does not mean unusable; current does not mean wholly public |
| CC-D04 | Volunteered Telegram location is an observation, not hidden GPS metadata | No location fetch from an ordinary text message; no background device tracking |
| CC-D05 | Reuse existing stores, loop and model calls | Same QuickStore; small projection helper; no standalone extractor/graph/attention service |
| CC-D06 | Useful normalization is allowed, not model-certified declassification | Host-resolved eligible location/date refs may transform; a word-subset test is not universal semantics or permission |
| CC-D07 | Current context has inspect/pause/clear/correct controls and bounded retention | Source withdrawal invalidates dependent state and future dispatch |
| CC-D08 | Unit tests are the primary development evidence | Fake clocks/transports and one real changed-boundary integration; optional model smoke is not a blanket gate |
| CC-D09 | Profile limits are real | Preserve #616 and the declared trusted-local limitation; do not claim complete provenance over a worker's hidden host reads |
| CC-D10 | The implementation path is finite | #607 → #626 → #627 → existing #608/#512/#513; patterns/preparation need a later bounded selection |

These are decisions for this implementation plan, not external research findings. No observed owner home/work address, routine or GPS is contained in the examples. The closed, unmerged [#384 v0.3](https://github.com/Jongtae/agentos/pull/384) remains historical input, not a merge vehicle to revive. Multi-principal relations, external peers, purchases, automatic habit mining and unsolicited preparation from that candidate are **not adopted here**.

## One product journey, two independently useful deliveries

Synthetic scene: the owner says “오늘은 회사 말고 집에서 일해.” Later “점심 먹을 데 찾아줘.” If an authorized home anchor exists, use it as a stated/assumed area, not as measured GPS. If none exists, ask only for the location needed. A new current-location share then supports “여기 비 와?” without asking again. Tomorrow the assistant must not call yesterday's location current or treat yesterday's exception as the permanent workplace.

#626 succeeds when authentic source identity/time/location updates survive ingestion and can be inspected without generating a model/research job. #627 succeeds when two actual task families (weather and local-information search) consume that information across supported API/CLI bindings, accept correction, and preserve disclosure/effect rules. A table, prompt sentence or unused JSON field alone is not delivery.

## Context kinds and truth

| Kind | Example | Authority and lifetime |
| --- | --- | --- |
| Canonical Memory | Owner-confirmed home/work anchor | Existing MemoryService policy; no new auto-promotion |
| Source observation/report | Owner-shared point at a specific time | The source reported it; not proof against spoofing or a permanent location |
| Statement interpretation | A model reads “today I work from home” | Attributable interpretation of an owner message; not sensor-verified |
| Current-state hypothesis | Probably in the home area now | Rebuildable, source-dependent, time-limited and correctable |
| Routine/pattern | Often at work in observed weekday mornings | Future scope; never evidence the person actually traveled today |

A future appointment is a plan; a forwarded location is a reference; a quoted or third-person statement is not automatically about the owner. Calendar silence does not establish availability. A model summary is not a second independent observation and cannot increase confidence by repeating itself. No invented percentage such as 97% confidence: use supported/uncertain/conflicting/unknown plus evidence; calibrated probabilities are outside this slice.

Fresh explicit correction of the same proposition can supersede an older claim. Do not use a global “newest always wins” rule across unrelated subjects or different time intervals. New GPS can contradict an inferred physical place without disproving a work-mode statement. Preserve contradictory source records while suppressing an unjustified definite current-state claim.

## Collection and user control

Normal conversation retains its existing handling. The new cross-turn context feature is off on upgrade until the paired owner enables it through a contextual opt-in or the existing privacy settings; fresh onboarding offers the same choice. Enabling it states the current model destination, temporary retention and optional volunteered-location use. It does not start GPS, a provider call or background analysis. Do not force a Settings tutorial or ask before every allowed lookup.

A request-location button for an immediate task explains its purpose (for example “이 위치로 날씨 확인”). Pressing it supplies a task-scoped location even if ongoing reuse is off; subsequent cross-turn reuse requires the above choice. A volunteered live share may be processed while that choice is enabled; the bot never starts a live share itself. Merely selecting a model, sharing a pin, or recording this design does not enroll the owner in continuous tracking.

Controls: inspect the current value/kind/source/age, pause future context use, clear the temporary context, and correct it through normal conversation. Pause stops use and new derived-state writes; resume does not replay observations received while paused. Clear removes temporary values and increments a context epoch so queued proposals, late updates and old transcript scans cannot resurrect them automatically. It does not erase canonical Memory or pretend to delete Telegram's/provider copies. Deleting a canonical source invalidates dependent hypotheses; use existing Memory deletion for the original.

No new remote model destination is implied by context enablement. A model used to interpret context must already be authorized for those sources. Existing local-only sources do not silently move to a remote DecisionEngine. The owner can use ordinary text commands and direct questions with context disabled.

## Time, place and initial configurable defaults

Keep source time and receipt time separate. Preserve original message time, edit time and update identity. Missing source time is unknown, not the worker start time. Relative dates refer to the source utterance's date in the owner-selected IANA timezone, not the current server date. Use stdlib `zoneinfo`; display any proposed timezone and obtain confirmation once rather than inferring it from language. UTC is an internal representation, not a claim about the owner's timezone. Missing timezone requires a question only where resolving a day/appointment materially depends on it.

Initial settings below are **engineering defaults, not measured accuracy guarantees**. Keep them in one configuration object and test them with a fake clock.

| Setting | Initial default / rule |
| --- | --- |
| Source/hypothesis retention | 24 hours for volunteered coordinates and temporary claims; existing transcript retention unchanged |
| Direct current-position freshness | 15 minutes from the last valid observation, also bounded by the share's lifetime |
| Stale context | Retain as last-known until retention expiry; not automatic current location for a new precise nearby request |
| “Today” work-mode validity | Until local midnight of the source day, capped by temporary retention; unknown timezone is not guessed |
| Implicit current-place hypothesis | At most 15 minutes unless an explicit interval supplies a shorter limit; source expiry/revoke always wins |
| New context budget | At most 8 current entries / 4096 UTF-8 bytes inside, not in addition to, the existing Work context budget |
| Source clock skew | More than 5 minutes in the future is unusable for current-state inference; preserve diagnostic reason only |
| Routine learning | Off; no habit inferred from a single observation or unobserved gaps |

A stale location can still answer “what was the place I sent?” or an explicit request about that place. That is reference use, not current-location inference. Low-risk suggestions may state a useful assumption; an ambiguous precise-place request asks once. Time passage can expire certainty but cannot prove movement, sleep, arrival or attendance.

Telegram `live_period` describes a sharing window relative to original message time, not freshness of the latest coordinate. A very long or indefinite share must still age between updates. An observed end of live sharing ends the live status; lack of an update is not a fabricated stop event. No per-tick reply or model invocation.

## Understanding versus disclosure

The full permitted private reasoning context and the projection sent to a search/weather/page endpoint are different. An inferred location remains private-derived; confidence or a source ID is not a Grant. Carry admissibility, owner/source revisions and the current task purpose into the broker's existing checks.

Preserve the [#605 F2/F4 owner decisions](https://github.com/Jongtae/agentos/issues/605#issuecomment-5842526660): ordinary search does not need per-search approval; current text is not all public; unrelated sensitive values are excluded even in the same message; necessary sensitive disclosure uses specific existing approval; checked arguments equal transmitted arguments; revoke is honored before subsequent dispatch. Never rename a guard failure as a useful result.

For this slice, `weather(location_ref)` and a nearby-search location ref are resolved by host code from an eligible owner observation/anchor. A ref contains no new permission. The host, not the private-context model, serializes location coordinates or a previously admitted place label and validates the destination. Prefer the coarse location needed for the task; do not send a home address, employer, full trajectory or unrelated profile. Rounding coordinates is minimization, not anonymization. If only exact GPS can satisfy a request, that exact disclosure must be covered by the task's location-sharing choice.

Allow established host-controlled normalization (dates, country enums, known place aliases and service coordinates). Do not require the API spelling to appear verbatim in the owner's message. Conversely, schema/length limits or a general LLM instruction do not prove absence of sensitive text. The existing free-text search path remains #605-owned; do not remove its controls to pass this feature. Extend only a narrowly reviewed source-ref projection where a literal matcher blocks authorized location/date transformation.

Revocation/current revision is checked at dispatch, serialized with local authorization state. A request authorized and dispatched before a revoke may be in flight; report it honestly. Neither context inference nor clearing local data promises remote undo. No hidden provider/account switch.

## Pattern and Attention exit conditions

#383 remains the continuation record for unadopted scope, not an indefinite exclusion bucket. Revisit it when #627 delivers both task families with correction/expiry and the owner selects one concrete continuing responsibility. First candidate: one observed routine, then preparation reused on request, then optionally interruption. Record selected sources, missing-observation bias, valid interval, sample support, exceptions, budget and revocation before enabling that candidate.

Reconsider a temporal graph library only when a selected task requires relation/time queries that the current indexed store cannot reasonably express, or a measured retrieval problem justifies it. Do not ingest a worldwide graph or import public personal profiles by default. An ontology describes relations; it does not measure the owner's current state or authorize action.

## Change ownership and definition of done

#605 owns general source/disclosure mediation; #606 ordinary execution; #607 effects/recovery; #616 actual CLI isolation. #623/#624 are specific route findings: consume the currently supported route, never silently bypass them. #626 owns input/time; #627 owns derived state and its actual consumption. Serialize shared service/store/runtime files. Context does not require #619's AI-settings redesign.

The implementer may select helper names, indexes and equivalent existing interfaces within this contract without asking the owner again. A new data source, remote destination, background responsibility, canonical Memory write policy, spend, real deployment or external effect requires a new scoped decision. Report concrete incompatibility, not a generic menu of architectures.

Default evidence is focused unit tests and one parameterized changed-boundary integration with fake model/network/clock/store. A small opt-in real-model or device smoke is separate, budgeted and truthfully unobserved if not performed. Review this plan's privacy/retention delta and each material implementation change under existing risk-based review; do not introduce another evaluator or continuous certification system.
