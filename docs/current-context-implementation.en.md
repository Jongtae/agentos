# Current context: implementer playbook

Read [product/authority contract](current-context-contract.en.md) first. Adoption #625; INPUT #626; STATE #627. This is a ready-to-implement plan, **not implemented code or a benchmark**. Paths below were inspected at main `9aa0c3e6b3658842ab4c5da35d21c76b1384c219` (2026-09-26). Rebase after current owners finish and adapt moved symbols without repeating a whole-project design review. Proposed function/table names are explicitly marked below.

## 1. Read once, then implement

1. Read the two context documents, your child issue, root plan and the relevant file-owned predecessor PRs. GitHub is the source of execution state.
2. Run only the existing focused tests for the touched seam to establish its current behavior. Do not start with a paid model benchmark.
3. Implement INPUT in order I1–I4, then STATE S1–S4. Keep each issue's branch/PR and actual acceptance scope bounded. No shared service/store file is concurrently owned without explicit coordination.
4. Report changed symbols, reuse, focused tests, required CI and unresolved conditions in a short PR summary. No new evidence certificate, full-transcript archive or per-answer judge.
5. Stop only for an actual contract mismatch or new authority decision. Helper names, equivalent SQL indexes and renderer wording do not need another owner selection menu.

Dependency order: existing #605 → #606 → #607, then #626 → #627, then existing #608/#512/#513. #625's documentation can proceed while runtime owners work. Preserve #616's independently selected isolation dependency and the trusted-local risk record; this plan changes neither. #623 is a concrete Claude tool-allowlist defect, not a reason to assume that route works. A claimed supported Claude path must consume its actual fix or report the limitation. #624 does not authorize hidden Codex DecisionEngine input. #619's AI-settings redesign is not required for current context.

## 2. Observed code map versus new work

| Existing path/symbol | Observed responsibility / gap | Change owner |
| --- | --- | --- |
| `conversation_handoff.TELEGRAM_POLL_UPDATE_KINDS` | message/callback/stopped-generation, no edited_message | INPUT adds edited_message |
| `TelegramChannel.get_updates`, token/transport resolvers | Existing Bot API transport and live token lookup | INPUT reuses; no bot SDK migration |
| `AgentService.ingest_update` / `poll_telegram` | Owner/generation checks, text enqueue, durable cursor; location not consumed | INPUT normalizes and records location/time without job spam |
| `QuickStore.__init__` / `db` / `enqueue` / `history` | SQLite, additive column migrations, transaction-sharing enqueue, timestamped rows | INPUT adds source metadata; STATE adds derived projection |
| `ContextInbox` | Explicit submitted text/URL, independent sharing policy | Preserve; do not grant GPS or remote sharing through it |
| `MemoryService.write/propose/remember/correct/delete` | Explicit canonical writes; model proposals stay candidates | STATE reads only covering relevant sources, no policy bypass |
| `turn_context` / `render_turn_prompt` | Bounded shared API/CLI context; prior roles/content lose source time | Preserve text behavior, add bounded time/current-context envelope |
| `Capabilities.definitions/execute` and #604 catalog/facades | Actual available tools and authority/provenance checks | STATE adds one internal proposal operation and location-ref binding |
| `LocalTools.weather` | City geocoding followed by Open-Meteo forecast serialization | STATE reuses forecast portion for authorized coordinate refs |
| #605 source projection and MCP rehydration | Active PR #622, not merged at inspection | Reuse merged version; this playbook does not assert its private-flow claims were verified |
| Existing privacy Settings / authenticated routes | Owner control surface | Add small current-context subsection, not #619 redesign |

At inspection PR #622 describes word-subset composition and a destination-attempt cap. These are a **reviewed-PR claim, not an endorsed general solution**. Do not turn spelling inclusion into semantic identity. Keep existing protections while adding the narrow location/date reference projection below. #606/#607 own bounded retry/alternative semantics; this plan must not silently disable a security throttle or demand unlimited calls.

## 3. Reuse decision and references

Decision: **Adapt existing AgentOS storage/loop/policy and adopt platform/standard vocabulary.** Add only missing input normalization and derived-state projection glue. No replacement ContextInbox, Memory service, broker, event bus or conversation database.

| Candidate | Adopted use / reason not selected |
| --- | --- |
| Telegram Bot API | Use official `Update.message/edited_message`, `Message.date/edit_date`, `Location`, `KeyboardButton.request_location`. No new Mini App or mobile sensor framework |
| Python stdlib `datetime`, `zoneinfo`, `sqlite3`, `math` | UTC storage, IANA timezone/day boundaries, same-DB atomicity, finite coordinates. Use existing JSON/validation conventions |
| Schema.org | Map Person/Organization/Place, worksFor/homeLocation/workLocation/alternateName. Vocabulary only, no RDF runtime or web profile mining |
| OWL-Time | Valid instant/interval and explicit timezone semantics. Not a predictor of where a person is |
| PROV-O and SOSA/SSN | Source/derivation and observation-versus-result time terminology; no ontology server required |
| Graphiti | Real temporal-graph candidate; project documents graph backend plus LLM/embedding integration. Not selected: this two-slice scope needs neither graph ingestion nor a second durable authority/model-processing path. Reassess for a concrete temporal relation query, not because graph terminology sounds useful |
| Existing ModelAdapter / DecisionEngine / pytest fixtures | Reuse injected model/tool transport; no new testing SDK, paid evaluator or always-on extractor |

Primary references checked 2026-09-26 (upstream behavior, not AgentOS implementation evidence):
- https://core.telegram.org/bots/api#update
- https://core.telegram.org/bots/api#message
- https://core.telegram.org/bots/api#location
- https://core.telegram.org/bots/api#keyboardbutton
- https://docs.python.org/3/library/zoneinfo.html
- https://schema.org/Person
- https://www.w3.org/TR/owl-time/
- https://www.w3.org/TR/prov-o/
- https://www.w3.org/TR/vocab-ssn/
- https://github.com/getzep/graphiti

Do not pin an entire Bot API release based on a cached page; the fields above are the adopted subset. No third-party code is copied or package installed by this adoption. Existing AGPL-3.0-only remains. Any future dependency adoption must record actual version, licence, deployment, maintenance and egress fit; an ontology mapping is not an SDK migration. #383/#384 are historical product reasoning, not evidence those features run.

## 4. INPUT: I1–I4

### I1 — additive storage, identity and configuration

Proposed local schema below is the default implementation, not a new v0.1 public wire schema. Reuse an equivalent existing field if a predecessor already added it and record the mapping. Do not change old `created` timestamps or mutate original completed Work messages to look newly received.

- Add nullable `source_at`, `source_edited_at`, `source_message_key` to jobs; propagate to the corresponding messages as needed. `created` continues to mean local persistence time. `history()` returns existing keys plus nullable source metadata; old callers continue to work.
- Add `context_observations` in the **same** QuickStore DB: `id`, `owner_key`, `generation`, `context_epoch`, `source_key`, `source_revision`, `source_kind`, `source_job_id`, `observed_at`, `received_at`, `valid_until`, `expires_at`, `payload_json`, `state`.
- Unique `(owner_key,generation,context_epoch,source_key)`. Index `(owner_key,context_epoch,state,expires_at)` and source lookup. Source revision is `(source_edit_or_message_time, update_id)` for ordering, not a hash of sensitive values.
- Keep the latest location value per live-share source, not a movement-history database. Replacing a source increments its revision and invalidates dependent projections in the same transaction. For original text keep a source-job reference instead of a second transcript. A text edit may retain one bounded latest edited text value until expiry; original transcript/effect history stays unchanged.
- Config `current_context`: enabled flag, context epoch, accept-after/cutoff, timezone, retention/freshness defaults from the contract. Use existing private config/store methods. Reject non-finite/negative/overlarge settings. Initial UI can expose timezone/use/pause/clear only; numeric defaults remain internal versioned policy.
- Upgrades add columns/tables idempotently; no history scan, automatic location collection, model call or invented source dates. Privacy controls use existing owner authentication. A contextual opt-in is equivalent to the same explicit settings action and shows purpose/destination/retention.

Proposed functions: `record_observation(db, owner, envelope, now)`, `invalidate_source(db, source_id, revision)`, `list_usable_observations(owner, epoch, now)`. Inject `now`; one existing store remains authority. Do not expose raw sqlite rows as public tool arguments.

### I2 — normalize before enqueue

Telegram ingress algorithm:

```text
validate configured generation, update_id, private chat
if sender is unpaired: handle only the existing pairing command
  (`/start <pair_code>` with an unexpired code, constant-time compare, as in
  `AgentService.ingest_update`) — pair, advance the cursor, stop; drop anything else
require the paired owner for text, edits and location observations
select message or edited_message (preserve callback/Stop paths)
normalize source identity + source/receive times
BEGIN IMMEDIATE
  read current context epoch/use policy again
  dedupe update + source revision
  record eligible location/time or invalidate an edited text source
  enqueue only an actual NEW text request through existing enqueue(db=...)
  advance Telegram cursor in the same transaction
COMMIT
emit at most existing bounded acknowledgement; no model for a location tick
```

The pairing branch runs before the paired-owner requirement so a fresh installation or re-pair still works; it records no context observation and enqueues no Work. The source key includes generation/chat/message ID, so re-pairing or reused message IDs cannot cross owners. Known duplicate/invalid/unsupported events may advance the cursor transactionally without creating state. A storage failure rolls back the cursor so it can retry. Continue preserving callback/Stop cursor semantics. Delayed events older than the source revision cannot overwrite it. Respect the existing poll ordering contract; do not convert every late text edit into a new user action.

Validate `latitude [-90,90]`, `longitude [-180,180]`, finite numeric types (reject bool/NaN/Infinity), optional nonnegative accuracy, positive bounded message identifiers and known source dates. Telegram documents accuracy 0–1500m; missing accuracy stays unknown. Retain only the fields required by this scope; heading/proximity/bot metadata are not a free input bag.

### I3 — distinguish shared point from current position

A `request_location` reply keyboard is not an inline callback and provides no cryptographic evidence that GPS is true. Reuse existing owner/pending-request patterns: keep a pending purpose binding to one active Work/generation, bounded by the same handoff expiry, allow typed location instead, consume once, and remove the keyboard. A matching voluntary response is a **current-position report**, not a verified physical measurement.

Unsolicited static pin defaults to `place_reference`; venue/forwarded location cannot set current position automatically. Owner clarification can associate it with the current request without saving a permanent location. Live sharing is sender-reported current position only within the explicit current-context choice. For updates use `edit_date` when supplied, original message date otherwise with an uncertainty flag. `live_period` expiry is measured from original date, not reset by receipt. Very long/indefinite live periods still obey 15-minute point freshness. Missing/changed live fields never invent a physical movement or deleted message event.

A completed-text edit invalidates current hypotheses derived from the earlier wording and supplies the corrected source on the next ordinary turn if admitted. It must not resend mail, replay a research task or rewrite a previously observed effect.

### I4 — controls, retention and source time

Use the existing authenticated privacy section and handlers; proposed `GET /api/current-context` returns redacted current-state status, `POST /api/current-context` accepts exactly enabled/timezone/clear actions, implemented through the same owner/CSRF/local-session rules as sibling endpoints. These endpoints are **new proposed paths**, not currently available. Do not add broad arbitrary-config mutation. Existing Settings polling calls no provider or geocoder.

On pause/clear, serialize the policy revision/epoch change with the observation store. Clear temporary observations/claims and set an ingestion cutoff; incoming old edits/queued proposals under an earlier epoch cannot recreate them. Resuming admits new observations, not a backfill from all past messages. Clearing context is not deleting canonical Memory. Referencing an old place again is a new explicit task-purpose choice, never automatic resurrection.

Prune expired temporary values during existing ingress/snapshot/maintenance execution; no new daemon. Every read checks expiry even if physical cleanup has not run while the computer sleeps. Start/next use performs cleanup. Preserve only content-free existing audit metadata; no exact location in normal logs, rejection strings, raw CLI diagnostics or public fixtures. Existing backup/transcript retention remains separate and must be disclosed rather than falsely promised erased.

## 5. STATE: S1–S4

### S1 — source-bound hypotheses, not a new memory engine

Proposed `current_context.py` contains pure validity/conflict/snapshot functions and a small store facade. Add `current_state_claims` to QuickStore: `id`, `owner_key`, `context_epoch`, `predicate`, `value_json`, `kind`, `source_refs_json`, `effective_from`, `effective_until`, `expires_at`, `revision`, `supersedes`, `state`, `created_by_work`.

Initial predicates: `current_place`, `work_mode`, `availability_hint`; represent unknown explicitly. Kinds: `source_report`, `owner_statement_interpretation`, `inferred`. Habit/routine is reserved, not auto-populated. No arbitrary health/religion/identity profiling. Foreign identifiers, expired/revoked sources, unsupported predicates and invalid time intervals are refused. All reads filter owner, epoch, validity and current source revisions. No unrestricted full-store context dump.

Add a local internal tool `propose_current_state` to the existing #604 tool declaration/broker by default, reusing an existing equivalent structured output slot instead only if already available. The normal selected model can call it while handling the current message; it consumes the existing Work's tool/turn budget. No separate pre-pass, observer model, provider switch or post-answer evaluator is introduced. Device events and expiry never invoke it automatically.

Proposed arguments: `predicate`, bounded value or existing place/source ref, `source_refs`, `effective_from`, `effective_until`, optional `supersedes`. Owner/Work/epoch are supplied by the host, never by the model. Host attaches kind and truth qualification: a model call is interpretation/inference, never sensor_verified or owner_approved. A valid schema proves shape and provenance binding, **not semantic truth**. Higher-impact dispatch needs explicit target/source authority regardless of hypothesis confidence.

Source reports and model proposals remain different. An explicit current correction replaces only the matching proposition/time scope. Independent contradictory evidence remains visible as conflicting; do not resolve all contradictions by recency. “Today remote work” need not prove exact home GPS. “Usually at the office” alone cannot become a current position. Repeated assistant summaries retain original source refs and do not add evidence weight.

### S2 — build and actually consume the snapshot

Proposed `build_current_context(owner, work, admitted_sources, now, timezone)` returns:

```json
{
  "version": "current-context-v1",
  "as_of": "2026-09-26T03:00:00Z",
  "timezone": "Asia/Seoul",
  "entries": [{
    "predicate": "work_mode", "value": "remote",
    "kind": "owner_statement_interpretation", "state": "supported",
    "source_refs": [{"id": "synthetic-source", "revision": 1}],
    "effective_until": "2026-09-26T15:00:00Z"
  }]
}
```

This is a synthetic example, not the owner's actual timezone or work mode. `supported` means usable cited evidence, not verified physical truth. Do not include precise coordinates in the model snapshot when a location ref/region is sufficient.

Service composes this snapshot **before** the normal route call, after source/destination admission. Extend `turn_context(history, route, *, current_context=None, now=None, timezone=None)` compatibly and `render_turn_prompt` with an untrusted-data section. API and CLI get the same admitted semantics; retain route-specific tool guidance and existing byte/turn budget. Include source times/ages of recent messages; remove oldest context before the current request. The new 4096-byte slice fits inside the total limit.

Snapshot refs do not replace a dispatch-time lookup of current authority. When the model proposes a state during a turn, return the qualified result through the same observation loop so a subsequent tool can use it. A failed state write cannot block an unrelated harmless greeting or fabricate a remembered fact. Do not append the complete snapshot to canonical Memory, every transcript line, or a separate summary chain.

Relevant home/work anchors come from existing canonical Memory under its current read/disclosure policy. Use an existing explicit memory key/reference where available; if an unstructured legacy value is ambiguous, resolve in the normal turn or ask once. Do not backfill arbitrary old messages into a new home/work registry. No literal keyword routing required for interpreting “회사/집/여기”; source refs and host policy constrain the result of semantic interpretation.

### S3 — EGRESS: useful location transformation without laundering

Extend the **existing** weather tool schema with mutually exclusive existing `city[,country]` OR `location_ref` (opaque observation/approved-anchor ref). Do not let callers supply both ref and replacement coordinates. Host resolves source owner/revision/epoch/current authorization, chooses minimum required spatial precision, and invokes the shared forecast serializer. Factor the existing forecast request construction out of `LocalTools.weather` into a reused helper; retain its known endpoint, parameters, timeout, data timestamps and weather-model limitation. No mandatory reverse geocoder or new destination.

For local-information search, use the same admitted ref to produce the geographic portion of the query through host code (known source place label, or a task-authorized coarse coordinate token). The semantic task terms continue through the merged #605 policy; this is not authority to send a private parent summary. If a specific search provider needs a place label not currently available, a bounded permitted geocoding step may use the already-declared location service; otherwise ask for the needed region rather than opening a new endpoint silently. Prefer preserving native place spelling when supported; service-required normalization must be host-attributable.

The host binds the actual chosen location projection, task goal and source revision at dispatch. `location_ref` does not let a model choose an arbitrary home/location from another source, nor make private coordinates public by reference. The owner authorizes ordinary location use through the current task or its context-use scope; sensitive disclosure still needs covering authority. Checked payload equals sent payload. Recheck page-read and context permissions for every new dispatch, including after a Work has started. Reuse pending/resume approval match/expiry checks; no signed-ticket service.

A source that the trusted-local worker read outside the broker remains untracked. This feature does not strengthen that profile magically. #616 isolation is separate and all context flow claims must be scoped to the actual profile. No unqualified route is silently substituted merely to make the integration test pass.

### S4 — correction, expiry and rollout

Use source-utterance time plus owner timezone for “today/tomorrow”, with timezone-aware midnight boundaries including DST. `effective_until` and `expires_at` differ; earlier source/revoke expiry wins. A clock tick may expire a hypothesis; it may not invent a commute. Freshness thresholds govern use, not certainty claims. The host can use low-risk assumptions with stated context; precise-location ambiguity asks once. Payments, message sending and other consequential actions do not inherit approval from any inferred state.

Start behind the one current-context setting, leave old text operation available, and migrate additively. Rollback disables consumption/proposals and preserves canonical Memory/effect history and revoke epochs. Do not downgrade to a version that ignores a new source-revocation binding for a previously qualified claim. No live deployment is performed by the implementation issue.

## 6. Unit/boundary matrix — specifications, not executed results

Suggested new test files: `tests/test_context_observations.py` (INPUT), `tests/test_current_context.py` and `tests/test_context_consumption.py` (STATE). Existing tests should be reused, not copied into a parallel harness. Names below are stable behavior IDs, not runtime phrase rules.

| ID | Arrange / action | Required assertion |
| --- | --- | --- |
| CT-01 | Current-location response from paired owner; repeat foreign owner/chat/generation | Own observation accepted; foreign state absent |
| CT-02 | Duplicate update; injected failure before commit; retry | One observation/optional Work; cursor and state roll back together |
| CT-03 | Live point then edit, stale edit, stop/expiry, indefinite share without updates | Same source changes once; newest retained; old point loses fresh/live status |
| CT-04 | Venue, forwarded point, “tomorrow meet here” | Reference only; no current position |
| CT-05 | NaN/Infinity/bool/out-of-range coordinates; missing accuracy; future timestamp | Invalid rejected; missing remains unknown; future not current |
| CT-06 | Old message received now, then completed text edited | Source age retained; derived state invalidated; old action not replayed |
| CT-07 | Pause/clear, restart, late update and expired source | No automatic revival; context may be empty; old normal text still works |
| CT-08 | 20 location updates, no text request | Zero model/weather/search calls, no 20 Work rows or bubbles |
| CT-09 | Proposal from valid/foreign/revoked source; future/quoted/third-person text | Valid hypothesis qualified; no fake observation/owner consent |
| CT-10 | Work anchor plus “today work from home” | Temporary work-mode changes; canonical work/home Memory unchanged |
| CT-11 | Same-scope correction, contradictory independent point, assistant summary | Dependent state invalidated; conflict retained; no double evidence |
| CT-12 | Midnight/DST/unknown timezone, old source and implicit here | Right source-day interval; stale not current; no invented timezone |
| CT-13 | Fresh location → “here weather”, API and supported CLI | Actual broker receives ref; fake network sees admitted coordinates; result loops back |
| CT-14 | Prior authorized place → “near here”; home/work anchor; ambiguous precise target | Relevant ref reused; unrelated hidden anchor not disclosed; one needed question |
| CT-15 | Passport + hospital same/prior turn; permitted place/date normalization | Actual outbound args exclude sensitive value; permitted transform works |
| CT-16 | Revoke/source correction/clear between proposal and send | Next send refused/recomputed under current authority; no in-flight undo claim |
| CT-17 | Context snapshot injected into real API/CLI renderers, then removed | Actual model input contains bounded state/ages; consuming assertion detects missing wiring |
| CT-18 | Legacy DB, second migration, disabled setting and rollback | Idempotent upgrade; no fake source times; original Memory/effect state retained |

Focused commands after the child creates these files:

```sh
PYTHONPATH=src python3 -m pytest -q tests/test_context_observations.py
PYTHONPATH=src python3 -m pytest -q tests/test_current_context.py tests/test_context_consumption.py
```

Use injected `now`, fake Telegram/model/network transports and temporary QuickStore. Inspect the **actual** admitted tool parameters, source refs and context input; a stub returning a canned final answer is not a wiring test. Unit tests cannot prove a real model understands all language. Only when model/prompt/tool description changes or a model-dependent defect remains, run a small explicitly authorized sample; no automatic repeats, quota percentage or second-model grading.

## 7. Narrow design questions already answered

- May the assistant infer? Yes, as a revisable qualified hypothesis, not canonical Memory or permission.
- Must every location be pre-saved? No; a task-scoped observed/admitted ref is sufficient.
- Can current message bytes all be public? No. Can earlier context be used? Yes when task-purpose/source authority covers it.
- Is literal word matching the universal control? No; preserve #605 while adding the narrow attributable transformation rather than stripping labels.
- Does a useful state feature require background Attention or multi-person migration? No.
- Must we introduce ontology/graph infrastructure? No; reuse vocabulary now and reevaluate only for a selected missing query.
- Does every GPS tick need a model/Work? No; attributable ingestion is code and a location tick is not a research goal.
- What needs an owner decision? New collection/destination/background/canonical-memory authority, spend or external effects; not routine implementation detail.

## 8. Later work is staged, not forgotten

After #627, #383 reviews one pattern or preparation candidate when the owner selects it. Pattern ingestion must keep missing observations unknown, retain sample support/validity/exceptions, avoid counting generated summaries as evidence and remain pauseable. Initial future trial should prepare for an already accepted responsibility and show results on request before unsolicited notifications. This paragraph records the continuation trigger; it does not activate a timer, model budget, new graph store or background job.
