# Personal Assistant Experience and Scoped Attention

> **Design candidate v0.3 — 2026-09-20. PLANNING ONLY; runtime implementation NOT ACTIVATED.**
> Discussion: [#381](https://github.com/Jongtae/personal-agentos/issues/381). Documentation work: [#383](https://github.com/Jongtae/personal-agentos/issues/383).
> Baseline inspected: `c6a78466ea82cfc90d79d434c733ccab37339039`. This document does not replace the current single-owner architecture or migrate v0.1 schemas.

## Reading guide and authority

This is the current consolidated **proposal** for the next assistant experience, not a claim of implemented features. Read [scenarios](personal-assistant-scenarios.en.md) for observable behavior and [decisions](personal-assistant-decisions.en.md) for owner-confirmed direction, assistant proposals, supersession and research provenance. Requirements below are requirements **of this candidate**; detailed mechanisms still require review and owner adoption.

The existing [architecture](../personal-agentos-architecture.en.md), [Owner Control Contract](../owner-control-contract.en.md), [core v0.1 contract](../core-primitives-agentpackage-v0.1.en.md) and [AGENTS.md](../../AGENTS.md) remain authoritative for shipped/versioned behavior. In particular, this proposal cannot weaken present per-request sharing checks by describing future standing permission. [#382](https://github.com/Jongtae/personal-agentos/issues/382) supplies the successor direction of Telegram conversation plus a local web management utility; its existence is not proof that this UI is implemented. Existing chat APIs/history must survive presentation changes.

Only these planning documents are changed by this work. No production source, schema, delivery-plan activation, account, shopping list, cart, model configuration, agent session or automation is changed. The earlier separately requested BDI research document/session is not created or delegated by this design work.

## 1. Product outcome

The owner says an ordinary sentence, receives a useful prepared option, and changes it with a short follow-up rather than repeatedly supplying their profile and coordinating people manually. Over time, the assistant should learn from permitted context and confirmed outcomes so that the owner has less explaining, choosing, relaying and checking to do. Within an accepted continuing responsibility and current authority it can prepare or act without decomposing every harmless step back into another approval question. Outside that responsibility it may notice a repeated burden and **propose** taking it on, but observation alone never activates authority. It speaks when useful, not merely because it has generated another idea.

One installation may eventually host several people, while each person has their own coherent assistant experience. Household, company, school and other collaborations are overlapping relationships, not a global shared memory. A household installation is a deployment hypothesis, not a forecast that every household will adopt the product.

The system must also work for someone with no public profile, no connected email/calendar and no peers. Start with the present request and permitted conversation; ask only missing decision-critical questions; build optional persistent context through explicit owner choices. Public self-research and social discovery are not prerequisites or defaults. A lack of external connectors should narrow capabilities honestly, not make ordinary dialogue unusable.

Product identity remains **owner-authoritative Personal AI Kernel + Agent Distribution Platform**. This design improves the default experience without replacing that identity, the useful file-workspace path or the package ecosystem with a family-only shopping assistant.

## 1.1 Enduring personal-assistant principles — candidate product constitution

These are the proposed **stable product promises** behind the mechanisms in this document. They are intentionally more durable than the current Attention data model, ranking algorithm, model provider or UI. A better implementation may replace Attention or a mandate representation; it should not casually reverse these promises.

**PA-P1 — Reduce the owner's burden, not merely complete internal steps.** Optimize for less repeated explanation, menu/list triage, manual relay, follow-up checking and avoidable decision work. Search, delegation, notification or queue insertion is not success unless it advances the user's intended outcome to the promised boundary. A blocked or partial result remains explicit.

**PA-P2 — Learn useful context without collapsing fact, inference, preference and temporary state.** Reuse permitted, still-valid context and confirmed outcomes so the assistant improves over time. Keep recommendations separate from actual choices, today's exception separate from durable preference, one family member's preference separate from another's, home location separate from current location, and model inference separate from authoritative Memory.

**PA-P3 — Be proactive inside accepted responsibility, and ask only for genuinely new judgment or authority.** Once the user has assigned an outcome and bounded scope, resolve routine sub-decisions with available evidence and allowed tools rather than asking permission for every harmless step. If information can be obtained through already-authorized retrieval, retrieve it before asking the user. Ask when the user's intent, another principal's commitment, a material constraint or authority must actually change.

**PA-P4 — Treat human attention as a scarce resource.** Preparing, executing and interrupting are separate decisions. Normal progress may remain silent or appear on the next relevant request; meaningful exceptions, deadline conflicts and decisions can justify interruption under policy. Silence is not success when an assigned outcome is predictably going to fail.

**PA-P5 — Preserve context boundaries and source authority across people and relationships.** Personal, household, company, school and other scopes do not merge merely because they share a device, person, model or peer. Share only the permitted projection required for the collaboration. The requester's authorized source governs what they requested; counterpart commitments, jointly accepted terms and external observations retain their own authorities.

**PA-P6 — Tell the truth about observed state and make correction, pause and recovery easy.** Requested, received, accepted, prepared, carted, ordered, delivered, failed and unknown are different states. Do not turn a timeout into success or a local cancellation into an external undo. A short correction should update only the intended scope and invalidate dependent preparation without forcing the user to restart the whole conversation.

**PA-P7 — Personalization is per person; durable state survives replaceable workers.** Tone, formality, preferred address, verbosity and reaction style are assistant settings. Context, Memory, responsibilities, Work, Artifacts, Evidence and authority belong to AgentOS/principals rather than a particular LLM, subscription CLI, channel or specialist. A future multi-principal installation must preserve this attribution during migration.

### Principles versus mechanisms

These principles are intended to provide **product constancy**. The implementation remains free to evolve. \`Attention\`, \`Responsibility mandate\`, a particular event loop, A2A, BDI-inspired vocabulary, notification ranking, model choice and storage layout are mechanisms or candidate contracts, not constitutional requirements by themselves.

When a future spec or PR materially affects the assistant experience, it should identify the relevant PA-P principles and demonstrate both sides of the requirement: useful allowed behavior and denied/contained unauthorized behavior. A change that lowers cost or simplifies code but causes repeated questions, lost context, unnecessary interruptions or hidden authority expansion is not automatically an improvement.

Adopting these principles into the canonical product/development constitution is a **separate governance change**. In particular, the current canonical development constitution says “one owner, one durable personal state”; future multi-principal support must amend or qualify that rule explicitly rather than treating this planning document as a silent migration.

## 2. Corrected architecture: a policy-controlled loop, not a linear autonomy ladder

```text
 Installation / host (resource provider, not a universal data owner)
     |
 Principal + verified channel binding + relationship/work scope
     |
 Source / purpose / destination / budget policy
     |
 +----------- Authorized context assembly -----------------------+
 | Memory | Current-state observations | Other observations      |
 | Explicit requests | Accepted responsibilities | Shared claims |
 | provenance + revision + validity + allowed use                 |
 +-----------------------+---------------------------------------+
                         v
                 ContextSnapshot
                         |
              Scoped Attention evaluation
              relevance / anticipation / freshness
                         |
       Policy chooses among permitted next steps
          |               |                 |
     ignore/defer     prepare/refresh    act/request-decision
          |               |                 |
          |      +--------v-----------------v-------------------+
          |      | Bounded Work + current Grant/effect checks    |
          |      | local reasoning, approved reads, shared edit, |
          |      | known-peer exchange, allowed external action  |
          |      +----------------------+-----------------------+
          |                             v
          |                   Artifact / Evidence / outcome
          |                             |
          +------> Per-person Interaction policy <--------------+
                   suppress / next reply / digest /
                   proposal / approval / urgent exception
                                 |
                         user's channel
                                 |
          correction / acceptance / rejection / observed outcome
                                 |
              invalidate dependent context and reevaluate
```

**Prepare is not outside Work.** A tool call, paid model call, persisted draft, shared-list edit or network lookup has a scope and potential effects even when nobody is notified. These operations use the same bounded execution/broker boundary as explicit work. Cheap deterministic filtering can run inside an authorized event handler; not every arithmetic comparison needs a separate Work row. Anything that invokes capabilities, transmits data or consumes a separately governed budget must be attributable.

**Interrupt is not a mandatory step before Act.** Standing permission can allow a list update without an interruption. Conversely, the assistant may ask a needed question without first researching anything. No path allows an Attention candidate to grant itself more authority. UI phrasing and execution authorization are independent.

**Evidence returns to the loop.** A prepared plan becomes stale when its source, request, scope, recipient, permission or validity changes. An observed purchase can resolve a supply concern; a suggestion or notification alone cannot.

## 3. Concepts and their boundaries

| Concept | Meaning in this proposal | Does not mean |
| --- | --- | --- |
| Principal | Human or explicitly authorized organizational identity whose data/authority is being used | Bot username, email match, device administrator or current model |
| Relationship/work scope | Accepted participants, purpose, permitted exchanges and validity for a specific relationship/workspace | Every contact or everyone reachable through a participant |
| Memory | Durable owner-controlled facts/preferences with provenance and correction | All conversation history or any model inference |
| Current state | Time-sensitive observations with observed/effective time and validity | A permanent fact or omniscient presence/location |
| Observation | Attributable user/device/tool/peer claim or measurement | Verified truth, canonical memory or consent |
| Responsibility mandate | User-approved continuing outcome to watch, with bounded event/data/prepare/notify/action permissions | A new entitlement inferred from a habit |
| Attention item | Scoped, evidence-backed hypothesis that an outcome, unresolved dependency or decision may need handling in a time window | Notification, executable command, universal importance score or Grant |
| Preparation artifact | Reusable bounded result with dependencies and freshness | Proof the user acted, consumed a meal or agreed |
| Work | Accepted/authorized execution with lifecycle and evidence | Merely thinking an action would help |

Salience and anticipation are **features of Attention evaluation**, not three compulsory LLM stages. For the meal case, 10:30 is an observation; proximity to the usual meal window contributes relevance; a possible upcoming food decision is an anticipation. Attention selection decides whether to track that candidate now. This is an application-level design term, not Transformer attention and not a claim of inventing attention management.

A lightweight BDI analogy is useful: supported beliefs correspond loosely to attributable context; desires to owner goals/candidate outcomes; intentions to accepted, bounded commitments. This is an analogy, not a one-to-one mapping, mandatory framework or justification for treating a generated desire as consent. BDI research and attention/interruption research are distinct references [R1–R3].

## 4. Identity, relationships and context assembly

### 4.1 Installation is not identity or sharing authority

Keep installation ID, principal ID, channel binding, assistant identity and execution runtime separate. A person's assistant can change model or channel without transferring ownership of memories. Sharing hardware does not merge histories or accounts. If one person belongs to a company and a household, an incoming company request selects the relevant work scope before retrieval, not after the model sees both contexts.

An installation administrator manages local operation; in-app administration must not implicitly authorize speaking as every member or using their accounts. This design promises no cryptographic protection from an administrator with full host access. Stronger threat models and encrypted isolation are separate implementation decisions.

### 4.2 Relationship establishment

Proposed progression: `unrecognized -> proposed connection -> verified identity binding -> accepted relationship -> explicitly scoped permissions`; suspend/revoke is possible at every active point. Identity proof, mutual acceptance and permission are separate properties, not one trust badge. Contact-book membership, a phone/email match, an Agent Card or a public profile is not permission to contact, disclose context or execute actions.

A relationship policy states the accountable counterpart, endpoint/key binding, purposes, allowed message kinds, permitted shared fields, expiry, notification rules and delegation limits. Replacing a peer's identity/endpoint requires controlled re-verification; it is not inherited solely from a familiar display name. Unknown inbound senders have no access to private context and cannot trigger autonomous replies, profile research, new relationships or expensive LLM processing. A bounded request inbox may present an owner-reviewable invitation without treating it as accepted. No automatic contact-graph crawling or transitive sharing.

### 4.3 Assemble before inference

A ContextSnapshot is purpose-specific. Its selection boundary is conceptually:

`principal + relationship/work scope + current request + recipient/runtime + current policy revision + valid source revisions`.

Authorize at retrieval, index/cache access, prompt assembly, model transmission and outbound delivery. Do not retrieve everyone's data and ask the LLM not to reveal it. Tenant/scope restrictions apply to summaries, embeddings, search results, caches, logs and backup/export paths as well as primary tables. A redacted output can still leak a forbidden fact; summaries retain source restrictions unless an explicit transformation/disclosure policy permits a bounded projection.

A source record should carry source kind, subject, statement type, accountable origin, observed/recorded/effective time, validity, revision, disclosure scope and opaque provenance reference. Confidence, authority and recency are not interchangeable. A user request is authoritative about requested intent; an inventory claim may be contradicted by another attributable observation. Time-to-live varies by source and action risk; no invented universal freshness threshold.

Location is user-supplied or explicitly permitted device data. A stored home is not a live position. The documented Sunday scene never becomes the current clock time on later reads. Missing permissions or observations remain unknown; calendar silence does not establish availability, and a household of three does not prove three people are home now.

### 4.4 Minimal disclosure across relationships

The local assistant may use permitted context to answer a narrow question and return only the approved result. Availability can be shared without appointment titles where the user has authorized that projection. A family item does not enter a company conversation because the same principal participates in both. The party asking for information does not get to choose the receiver's local disclosure policy.

## 5. Responsibility mandates: who asked the assistant to care?

Reactive requests need no standing mandate: they create their own bounded purpose. Proactivity needs an explicit or already-covering standing responsibility. A habit may suggest a mandate for review, but it cannot silently activate one.

Example **proposed setup**, not a permission already granted by the owner:

> “주말 식사는 평소 선호를 참고해서 미리 후보를 준비해줘. 내가 물으면 바로 보여주고, 먼저 말하는 건 필요한 경우만. 주문은 하지 마.”

The UI converts this into an understandable review of outcome, inputs, work window, allowed preparation, notification behavior, approved destinations/model profile and budget. Ambiguous phrases such as “필요한 경우” need a bounded preset or concrete interpretation before becoming an unattended policy. Advanced fields may be hidden behind task presets; scope and limits may not be omitted from enforcement.

Candidate mandate fields: owner principal; purpose/scope; outcome; event/source subscriptions; active window/timezone; observation and transmission Grants; allowed preparation capabilities; interruption policy; action policy; approved counterparts; per-run and cumulative budgets; expiry/review time; policy revision; revoke/pause state. These are semantic requirements to map to existing Grant/Event/Work contracts, not a new parallel permission database or already-valid v0.1 JSON shape.

Standing authority is not “approve everything once.” Adding new data, recipients, destinations, purchases, payment terms or a wider scope requires a covering renewed decision. Existing per-request context approvals remain enforced until a separately reviewed successor supports narrower standing grants. Withdrawal stops future activity; it does not unsend already disclosed data.

## 6. Attention evaluation and lifecycle

An Attention item should answer:

1. Whose possible need is this, in what relationship/work scope?
2. What outcome or decision may be needed, and why now?
3. Which source/request/mandate revisions support it? What is unknown?
4. When is it useful, obsolete or worth reevaluating?
5. Which next steps are currently permitted, affordable and available?
6. Is there already an item/Work for this occurrence? What would resolve it?

Candidate record fields: stable ID; principal/scope; goal/mandate/request references; evidence references and revisions; candidate type (`explicit-need`, `accepted-obligation`, `routine-forecast`, `dependency-risk`, `change-impact`); useful window; expires/next-review time; dedupe occurrence key; uncertainty reasons; available next steps; status; preparation/work references; interaction disposition. A dedupe key includes scope and occurrence; recurring Sunday meals are different occurrences. Similar words alone must not merge separate people's needs.

Proposed lifecycle: `candidate -> active -> tracking -> resolved`, with `deferred`, `dismissed`, `expired` and `invalidated` dispositions. Preparation/notification/work have their own states; do not encode every combination in an enormous Attention state machine. “Resolved” needs outcome evidence or an explicit owner disposition, not merely a message sent. An expired item is not a successful task. Changed inputs reopen only under current authority; an old dismissal must not be erased by paraphrasing the same candidate.

### 6.1 Three different priorities

- **Source authority:** who may change a particular statement/field.
- **Confidence/freshness:** how well supported and current an observation is.
- **Attention priority:** which permitted concern deserves scarce preparation or user attention now.

No priority or confidence score grants access or overrules source authority. Another assistant's “urgent” label is a claim, not a command to interrupt the user.

### 6.2 Select among permitted options, including doing nothing

First apply hard constraints: verified scope/identity, effective authority, source validity for the intended use, capability availability, duplicate/in-flight work and budget. Only then compare feasible alternatives: ignore, defer, locally prepare, approved refresh, show on next reply, ask, notify or execute.

Start with explainable ordered rules. An active user request or an agreed deadline can deserve priority over a speculative routine; a near deadline with credible loss may justify an allowed exception. Handle per-principal fairness and starvation; do not turn these examples into an unconditional global order.

Expected benefit, cost of delay, uncertainty, interruption burden, data exposure, token/network/resource cost and reversibility are useful design dimensions. **No uncalibrated LLM probability or arbitrary weighted score is a production acceptance rule.** Later learned ranking must be evaluated, retain deterministic authority gates and improve over the simple baseline. Bounded notification deferral and mixed-initiative interaction offer research background, not a ready-made policy for this product [R1–R2].

## 7. Preparation, interaction and action contracts

### 7.1 Preparation is bounded, cancellable Work

A preparation request references an Attention item or explicit user request, a ContextSnapshot and covering Grants. It reserves budget, records action intent, produces a source-grounded artifact and names the dependencies that invalidate it. Lookup results must distinguish published menus/prices from availability and payable totals. Store only required data with retention consistent with its sources.

A prepared artifact includes purpose/owner/scope, input revision fingerprint, observation time, valid-until or validity predicate, checked versus assumed facts, unresolved questions and supported next action. A user's follow-up can consume an existing artifact when still applicable; it must not spawn a duplicate search because it used different wording. A changed location, participant count, dietary constraint, supplier status or permission invalidates only affected results.

Silently preparing does not mean secretly transmitting. Approved external destinations and expenses are still inspectable. Information acquisition may itself disclose intent. Reversibility of a local draft is not reversibility of an API request or disclosure.

### 7.2 One interaction coordinator per person

Local product policy, not remote agents or specialist runtimes, chooses the audience, channel, timing and message type. Options include silent retention, attach to next relevant reply, digest, suggestion, decision/approval request, failure/deadline exception and permitted completion notice. A reply in an active conversation and an unsolicited push are different interactions.

Apply quiet periods, per-mandate and per-person caps, duplicate suppression, meaningful-change rules and an expiry horizon. Silence is a valid output. With only partial availability information, do not claim the person is not busy. A minimal per-person arbiter may compare redacted deadline/priority metadata across authorized scopes to avoid many simultaneous interruptions; it must not copy those scopes' content into one model prompt or expose private reasons to counterparts.

Feedback semantics are explicit: “이번에는 됐어” dismisses this occurrence; “나중에” needs an interpretable deferral boundary; “이건 앞으로 먼저 말하지 마” proposes a persistent notification-policy change through the applicable settings flow. Ignoring a suggestion does not count as approval, gratitude does not prove completion, and one correction does not authorize permanent profiling.

Tone, form of address, verbosity and reaction intensity belong in each person's settings. They cannot hide approvals, alter facts or authorize actions. Avoid a second LLM rewriting call for every reply and decorative reaction. Necessary sources/uncertainty stay accessible and relevant even in a concise reply.

### 7.3 Permissions are a matrix, not a slider

| Operation | Needed coverage | Non-implication |
| --- | --- | --- |
| Observe a source | Source, principal, purpose, retention and acquisition method | Read permission is not external transmission |
| Use an external model or lookup | Data/destination, invocation and usage budget | Local installation does not mean local processing |
| Prepare a local draft | Scope, permitted inputs and write location | Draft is not a shared list or external send |
| Update a household list | Shared-object edit and member/role policy | List update is not recipient acceptance or purchase |
| Ask a known peer | Accepted relationship, message kind, field disclosure, recipient consent/policy | Discovery is not relationship; relationship is not unlimited delegation |
| Send a proactive message | Recipient/channel/timing and notification authority | Urgency claim is not authority |
| Add to a merchant cart | Exact account, item/quantity/limits and mutation permission | Cart is not a read and not an order |
| Reserve/order/pay | Exact consequential effect, covering account-owner approval/terms | Prior recommendation/cart permission is insufficient |

Actions with no covering grant remain proposals or input-required Work. Do not force a redundant confirmation when a current narrow standing Grant already covers the exact operation; record which grant was used. In the first implementation candidate, checkout/payment is excluded.

## 8. Collaboration and reconciliation

### 8.1 Exchange work-scoped claims, not complete minds

Use one logical work identity with attributable contributions. Same-host participants may see scoped projections of local records; external peers can receive versioned projections without requiring a global database. Namespaced IDs prevent unrelated tasks from colliding. Each person's private context remains local to its permitted scope.

Proposed message semantics: `request`, `received`, `accept`, `decline`, `propose-change`, `revise`, `report-observation`, `withdraw`, `reconcile`. A message names issuer principal/acting agent, verified relationship, audience, purpose, work ID, message ID, base/source revision, affected fields, validity and evidence references. Do not trust these fields merely because a peer supplied them. A signature authenticates origin, not truth or authority to change arbitrary fields.

Request receipt, human reading, agent acceptance under delegated policy, human acceptance, list mutation and execution are different events. Reply state accurately; no “your spouse agreed” after a queue insert. Handoff is complete only to its specified boundary; delegation does not make the original supply need fulfilled.

### 8.2 Authority is field-specific

Requested product/quantity/deadline/withdrawal comes from the requester's authorized source. Recipient commitments, availability and fulfillment proposals come from that recipient's authorized record. Joint terms need acceptance of identified terms/revisions. Order/payment observations need applicable account/service evidence; human reports remain reports. Derived summaries never redefine their sources.

A later authorized causal revision supersedes an earlier request revision. Received-at time, model confidence or a newly written summary cannot win over source authority. Concurrent edits from the same base require conflict handling; issuer-local version numbers are not globally comparable. A requested deadline and a later possible delivery are distinct facts requiring negotiation, not two versions of the same truth.

Preserve executed facts when intent changes: requested two, purchased one means a remaining need to reconcile, not zero or two purchases. A different participant's extra unit is a separate need/allocation. Cancellation after a possible order requires external reconciliation, not deleting evidence. [R4–R5] provide relevant provenance and conditional-update concepts; neither specifies all these application rules.

### 8.3 Before and after external effects

Validate current request/acceptance/policy revisions and commit the local action intent within the same serialized/transactional boundary, including a per-action idempotency key. A compare-only check followed by an unguarded write leaves a race. Multi-resource grants and budget reservations need the same scrutiny.

External services generally do not share the local transaction. Bind receipts to the revision actually used, use provider idempotency/reconciliation where supported, and retain unknown outcomes when unavailable. Do not blindly replay a possibly completed mutation. Strong simultaneous consistency cannot be promised while peers are offline. An operation that needs fresh confirmation waits rather than assuming an offline replica is current. Subsequent cancellation is a new authorized operation, not time travel.

A2A is a candidate transport/task protocol, not a shared-memory system, contact graph or permission oracle. Its authorization model remains agent-defined [R6]. The inspected `a2a.py` is a compatibility test-peer adapter, not evidence of interoperability with Instinct or a current public A2A release. Pin and test a supported version only when that integration is separately selected.

## 9. Resource limits, offline operation and recovery

Use event-driven reevaluation and bounded scheduled wakes rather than permanent LLM thought loops. A timer is a reason to evaluate an existing mandate, not evidence that everyone is home or wants lunch. Only invalidate/recompute dependencies affected by an event. Self-generated summaries and notifications must not count as new independent evidence and retrigger themselves; preserve causal IDs and cap iteration/delegation.

Per-person and per-mandate resource budgets cover model requests/tokens or money when known, lookups, peer exchanges, concurrent work and wake frequency. Reserve capacity for active user requests, and prevent one member's proactive preparation from exhausting all shared resources. Unknown provider quotas/telemetry remain unknown; a reported limit error causes backoff until a changed condition, not speculative retries or silent paid-provider fallback. Application preparation budgets are separate from development-tool quotas.

When the model budget is zero, deterministic policy checks and already-available local views may still work, but do not pretend to generate new model-based advice. Keep genuinely pending work explicit, expose which operation is blocked and respect its deadline. Never make switching providers or exposing new data automatic just to continue.

A sleeping/offline laptop cannot perform local work. On recovery, reevaluate usefulness windows and current permission before resuming; do not send a morning meal suggestion in the afternoon or flood the user with missed routine notifications. Missed obligations may warrant one accurate exception. Durable queue records, leases, exact in-flight state and outbox delivery status are implementation candidates; “exactly once” external effects are not a blanket guarantee. No new cloud relay, wake service or background job is enabled by this document.

## 10. Requirements and traceability

| ID | Candidate requirement | Scenarios |
| --- | --- | --- |
| REQ-01 | Useful reactive dialogue without public profile, connectors or peers; no automatic identity hunt | S-00, S-10 |
| REQ-02 | Separate principal/channel/runtime/installation and support future safe single-owner migration | S-08, S-13 |
| REQ-03 | Scope retrieval, prompts, caches and outbound results before inference | S-08, S-09 |
| REQ-04 | Retain source authority, time, validity and revisions; unknown stays unknown | S-01, S-02, S-04, S-10 |
| REQ-05 | Source authority, confidence and attention priority cannot substitute for one another | S-04, S-05, S-09 |
| REQ-06 | Unsolicited evaluation/preparation requires an accepted bounded responsibility and current Grants | S-00, S-01, S-07 |
| REQ-07 | Attention is deduplicated by purpose/scope/occurrence and can expire/dismiss without action | S-01, S-06, S-07 |
| REQ-08 | Salience/anticipation are evaluation features, not a compulsory multi-LLM pipeline | S-01, S-11 |
| REQ-09 | Every preparation effect/cost uses bounded execution, evidence and cancellation | S-01, S-06, S-11 |
| REQ-10 | Prepared artifacts invalidate on relevant input/source/permission changes | S-02, S-04, S-12 |
| REQ-11 | One personal interaction policy supports silence, deferral, meaningful change and interruption limits | S-01, S-07, S-09 |
| REQ-12 | Presentation preferences are settings, not authority or product-wide persona | S-07, S-08 |
| REQ-13 | Preserve useful source-grounded results and distinguish suggestion from actual consumption/action | S-01, S-03, S-12 |
| REQ-14 | Shared work requires accepted relationships and non-transitive field disclosure | S-03, S-08, S-09 |
| REQ-15 | Request, receipt, acceptance, cart, purchase and delivery are distinct evidenced outcomes | S-03, S-05, S-12 |
| REQ-16 | Revisions cannot erase fulfillment; concurrent edits/conflicting terms need reconciliation | S-04, S-05, S-12 |
| REQ-17 | Exact current authority and request acceptance bind external-action intent; unknown effects are not replayed | S-04, S-12 |
| REQ-18 | Per-person budgets, fair scheduling, backoff and no unapproved paid fallback | S-06, S-11 |
| REQ-19 | Restart/offline behavior expires obsolete candidates and preserves unresolved obligations | S-06, S-12 |
| REQ-20 | Feedback/correction changes only its intended scope; no automatic memory/permission expansion | S-02, S-07 |
| REQ-21 | Reuse current primitives and retain source-controlled compatibility/migration boundaries | S-13 |
| REQ-22 | Separate source inspection, deterministic replay, model quality, live channels and real effects | S-00–S-14 |
| REQ-23 | Measure success by reduced owner explanation/decision/relay/checking burden at the promised outcome boundary, not internal activity counts | S-01, S-03, S-05, S-14 |
| REQ-24 | Permitted learning improves future assistance while keeping recommendation, actual outcome, temporary state, durable preference and person-specific facts distinct | S-01, S-02, S-10, S-14 |
| REQ-25 | Within accepted responsibility, resolve routine decisions using current evidence/allowed retrieval; ask only for missing material judgment or new authority | S-01, S-03, S-05, S-14 |
| REQ-26 | Preparation/execution/interaction priorities are distinct; user attention is budgeted and meaningful exceptions are not suppressed | S-01, S-06, S-07, S-14 |
| REQ-27 | The assistant may propose taking on a repeated burden but cannot silently convert observation or habit into a standing responsibility | S-00, S-07, S-10, S-14 |
| REQ-28 | Product-principle traceability is part of future specs/evals while mechanism choice remains replaceable | S-00–S-14 |
| REQ-29 | Future multi-principal durable state is attributed per principal and migrated explicitly from the current single-owner contract | S-08, S-13 |

## 11. Current-code seams and proposed changes

This is a mapping of inspected source and proposed responsibility, not an implementation plan already activated.

| Existing seam | Observed role / limitation | Candidate evolution |
| --- | --- | --- |
| `src/personal_agent/quickstart_service.py` | One paired Telegram owner, request queue, context assembly, card/result delivery; native and subscription prompts differ | Extract principal/scope-aware input and interaction seams without replacing the service wholesale; preserve delivery/approval semantics |
| `src/personal_agent/quickstart_store.py` | Local durable config, jobs, messages and memory-related state | Migrate identifiers/scopes explicitly before multi-member use; retain work/evidence rather than adding a separate family store |
| `src/personal_agent/context_inbox.py` | User-submitted text/URL only; explicit source enablement, expiry and policy plus per-request sharing | Preserve boundary; future observation adapters and narrow standing grants need their own reviewed contract |
| `src/personal_agent/agent_runtime.py` | Capability/native tool loop, evidence and memory-candidate paths | Use common bounded snapshots and selectively measured response checks; ranking/proactivity cannot bypass capability gates |
| `src/personal_agent/bounded_execution.py` and isolated engine path | Per-turn worker invocation and restricted tool facades | Adapt an authorized input contract, not full-store access or unrestricted persistent CLI sessions |
| `src/personal_agent/personal_assistant.py`, `settings_orchestrator.py` | Existing orchestration/settings policy seams | Review whether bounded responsibility presets fit here; no second settings/authority system |
| `src/personal_agent/a2a.py` | Local compatibility test peer | Reuse tested semantics where applicable; add authenticated relationship transport only as a later separate integration |
| `schemas/v0.1/` | Versioned Owner/Context/Memory/Grant/Work/Event/Evidence foundation | Map candidate concepts, document gaps and version changes; no silently invalid new enum fields |
| `src/personal_agent/web/` | Current UI with #382 successor plan | Management of scoped state/settings/receipts, not a new required attention dashboard or second chat client |

Attention and mandates can initially be typed local records/projections linked to existing primitives. They do not each require a microservice. Physical tables/modules are deliberately not finalized. No b3os dependency, message broker cluster, global vector memory, blanket browser control, mandatory BDI runtime or new model framework is required for the first slice.

## 12. Staged adoption and evidence gates

Before any stage is promoted, review its impact against PA-P1–PA-P7. The principles do not replace authority/security gates; they add the product-usefulness invariant that permitted assistance should actually reduce owner work. A stage that only adds internal machinery or notifications without improving a named scenario should not advance on that evidence alone.

**Stage 0 — this documentation candidate.** Resolve product semantics using scenario traces and decision records. No feature execution or claim of independent review. Separate canonical adoption from merging a clearly marked proposal.

**Stage 1 — scoped foundation plus reactive continuity.** Define principal/scope migration and source validity; unify permitted conversation inputs; preserve single-owner behavior and no-connector usefulness. A small two-principal fixture must prove no cross-talk before enabling multi-member use. No external assistant network.

**Stage 2 — one bounded responsibility in shadow mode.** Use the meal scenario with explicitly approved context. Replay synthetic events/frozen time and produce candidate decisions locally; no unsolicited sends, paid calls or actual purchase. Compare a simple baseline with scoped Attention; then separately permit a preparation-only trial. Even live shadow mode requires data/compute authority.

**Stage 3 — prepared answers and measured interaction.** Allow one approved preparation source/profile and artifact reuse; surface in requested answers first, then optionally test bounded proactive notifications. Pause/revoke/no-spam/zero-budget behavior must pass. Do not claim success merely because notifications were delivered.

**Stage 4 — two-member local shared work.** Prove the replenishment handoff, requester revisions, recipient decisions, deadlines and consistent views with no external cart. Use the same relationship and source-authority semantics later intended for remote peers.

**Stage 5 — one known external peer or merchant adapter.** Select one independently, verify protocol/account permissions, use scoped projections and reconcile unknown effects. No need to ship cross-household federation and shopping automation together. Checkout/payment is out of the initial scope.

Each stage needs separate owner activation, exact base/diff, acceptance coverage, relevant independent review and evidence-class reporting. No stage is auto-selected because the previous one finishes. All source guards and existing valid regression behavior remain; obsolete presentation assertions need explicit replacements.

Evaluation separates: deterministic state/policy tests; synthetic scenario replay; supported-model quality runs with explicit budget; actual Telegram/peer integration; owner experience feedback; real external side-effect evidence. Proposed measures: decision effort and repeated questions, usable-plan quality, first-useful-answer/completion latency, preparation reuse/waste, missed useful windows, accepted versus unwanted interruptions, scope violations, duplicate effects, reconciliation correctness, token/resource cost per useful outcome. Report denominators and unsupported cases. Numeric promotion thresholds require a reviewed baseline; none are fabricated here.

## 13. Open decisions

- Exact principal-to-existing-Owner mapping, migration and host-admin protection target.
- Relationship enrollment, counterpart verification/key changes, revocation and organizational policy precedence.
- Supported source adapters, source-specific freshness and user-friendly current-state controls.
- Mandate presets and confirmation/expiry; how existing per-request consent evolves without loss.
- Budget values, foreground reserve, scheduling fairness and observable provider quota behavior.
- Interaction caps/quiet times/urgent exceptions and uncertain user availability.
- Minimal persisted Attention record versus derived projection and retention of dismissed candidates.
- Exact joint-term/concurrent-edit semantics and offline freshness required for each effect.
- Evidence required to mark a meal consumed, a supply received or a delegated task complete.
- External peer/merchant feasibility, negotiated schema version and independent review strategy.

## References

All were consulted on 2026-09-20; they motivate distinctions, not claims of feature support.

- **R1:** Eric Horvitz, [Principles of Mixed-Initiative User Interfaces](https://www.microsoft.com/en-us/research/publication/principles-mixed-initiative-user-interfaces/), CHI 1999. Background for combining user initiative and bounded automation.
- **R2:** Eric Horvitz, Johnson Apacible and M. Subramani, [Balancing Awareness and Interruption](https://erichorvitz.com/bdef_studies.htm), User Modeling 2005. Background for bounded notification deferral.
- **R3:** Anand S. Rao and Michael P. Georgeff, [BDI Agents: From Theory to Practice](https://aaai.org/papers/icmas95-042-bdi-agents-from-theory-to-practice/), ICMAS 1995. The archive landing-page date is not the conference year. BDI is a research lineage, not an installation prerequisite.
- **R4:** W3C, [PROV-DM](https://www.w3.org/TR/prov-dm/). Attribution, derivation and revision vocabulary; not the product's conflict-resolution algorithm.
- **R5:** IETF, [RFC 9110, If-Match](https://www.rfc-editor.org/rfc/rfc9110.html#name-if-match). Conditional-update pattern; not atomic distributed purchase semantics.
- **R6:** [A2A specification](https://a2a-protocol.org/latest/specification/), especially in-task authorization and caller-scoped access. The online `latest` reference can change; pin a version before integration. It does not establish trust relationships for AgentOS.
- **R7:** Ian Park, [Instinct usage essay](https://ianpark.vc/p/instinct-10b/), 2026-09-17. The author reports unsolicited context preparation from public writing and discusses its uneven applicability. This is an attributed usage account, not audited architecture, product-wide reliability evidence or permission to mine users' identities. This design does not repeat valuation/funding claims or assume iMessage interoperability.
