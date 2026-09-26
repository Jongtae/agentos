# Personal AgentOS Secretary Agency Contract

## Status and purpose

This is the canonical product and execution contract for the **SECRETARY-01** program, activated by the owner on 2026-09-26 through [GOV-SECRETARY-01 #653](https://github.com/Jongtae/agentos/issues/653). It distills the owner's product specification, preserved as [research](research/secretary-agency-spec-2026-09-26.ko.md), and the owner decisions recorded in #653.

It supersedes the PRESENCE-01 program's execution queue as the active goal. It does **not** replace the kernel authority model in [Personal AgentOS Architecture](personal-agentos-architecture.en.md), the [Decision Layer](decision-layer.en.md) boundary, Work/Event/Evidence semantics, or the [Goal Execution Contract](goal-execution-contract.en.md). Where the [Owner Control Contract](owner-control-contract.en.md) or the [Assistant Execution Contract](assistant-execution-contract.en.md) conflict with the pilot posture below, this contract governs for the duration of the pilot and the conflicting text is marked as conditional in place.

It does not claim any described behavior is shipped. Capability claims still require merged implementation and named evidence.

## Why the program exists

The repository had narrowed the product to a rule-guarded public search path. The decision model was introduced so that the assistant can choose among alternatives and recover when one fails; it was instead used to add per-query blocking judgments. The documented worldview (secretary, personal context and memory, Attention, goal-directed agency, family collaboration, replaceable capabilities) was not what the code did. The owner's problem statement is preserved verbatim in the research document.

This program moves the center of the product from "does each tool work" to "does the assistant reach the owner's goal through whatever path is available, and can it prove it".

## Product definition

Personal AgentOS is a **secretary**: one personal agent for one owner that keeps the owner's preferences, situation and history, anticipates what the owner will need, and completes goals through replaceable capabilities while the owner keeps authority over personal state.

Six axes, all of which are part of the product and none of which is optional:

1. **Secretary** — responds to requests with the owner's preferences, situation, family and environment in view.
2. **Personal context and memory** — durable, attributable owner state: preferences, allergies, locations, schedules, prior results, prior interactions and their evidence. Canonical Memory stays AgentOS-owned; see [Current Context Contract](current-context-contract.en.md) for source-bound current state.
3. **Attention** — anticipating what the owner will need from time, place, schedule and goals, and preparing it: a reminder before an event, a lunch suggestion ready before the owner asks, a suggested errand. Attention produces candidates and preparations, not consequential effects; it is not deferred in this program.
4. **Goal-directed agency** — decomposing a stated goal into steps, choosing tools and paths, evaluating results against the goal, re-planning when a path fails, and stopping only on evidence.
5. **Family and other-agent collaboration** — delegating work that belongs to another person's agent (for example adding an item to a spouse's cart) through an agent-to-agent request rather than by acting with that person's authority. Second phase of this program.
6. **Capabilities** — web search, page reading, browser action in a logged-in session, calendar, mail and files, shopping. Each is a replaceable module behind a generic interface; providers and sites are chosen by the model at run time, not fixed in code.

## The agency loop

### Roles

- **The decision model chooses what to do.** Given the goal, the owner's context and the capability set, it selects the next action: which provider to search, which result to open, which site to act on, whether to ask the owner, whether the goal is reached. It re-plans on failure. Provider, site, query rewriting and recovery choices are model decisions and are expected to vary with the owner's language, location and question category.
- **The execution environment checks whether it may be done, and does it.** It holds Grants, sessions, secrets and budgets; runs the tool; and returns the observed result with evidence. It does not second-guess the model's semantic choice. It refuses only when the action is outside the allowed set defined below.
- **Completion is decided from observed environment state**, not from tool success and not from the model's own claim. See "Evidence-based completion".

This is the existing Decision Layer boundary: judgment behind the model, exact invariants in deterministic code. What changes is that deterministic code stops making semantic judgments about ordinary requests.

### Alternatives are mandatory

When a path does not produce what the goal needs, the loop must try another path before giving up: rewrite the query (keywords only, alternate spelling, transliteration), switch provider, move from general search to a site's internal search, open a different result, or ask the owner one specific question. The same path with the same input must not be repeated. Only after alternatives are exhausted, or a step needs authority the owner has not given, does the loop stop and report what it found, what it could not do and why, and what it proposes next.

### Evidence-based completion

A goal is complete when the environment shows it. Examples of acceptable evidence:

- product found: title, author and edition on the product page or API response match the request;
- item in cart: the cart page or cart API lists that item after the action;
- reminder set: the reminder exists in the store that will fire it, with the intended time;
- lunch suggestion ready: the suggestion cites current sources, respects recorded allergies and preferences, and is attached to the owner's context for the expected time.

"No error was raised" is never completion. The final report must match the observed state: if the report says the item was added, the cart must show it; otherwise the report states exactly what was observed. Requested, observed, failed and unknown remain distinct.

### Failure modes

| Situation | Required behavior |
| --- | --- |
| Login required | Report that the site needs a login in the dedicated browser profile; do not enter credentials; continue with the parts that do not need it. |
| Page error or unexpected structure | Retry once, then search the page for the intended element, then try another route to the same outcome. |
| Provider returns irrelevant results | Rewrite the query or switch provider; do not repeat the same query to the same provider. |
| Action outside allowed set | Stop that action, report "this needs your approval or is outside the pilot boundary", finish the rest. |
| Partial success | Report what was achieved with evidence, what was not, and a concrete next step. |

## Pilot posture

The pilot runs with one owner, on the owner's own machine, using the owner's own accounts and keys. The owner has decided to reduce the request-time protection layer to the smallest set that still protects the owner, and to defer the rest to a separately activated hardening program.

**In force during the pilot:**

1. Passwords, tokens, cookies and API keys never enter a model prompt, a log or Evidence. Browser sessions live in a dedicated profile owned by the execution environment; the owner logs in there once, manually. The model receives page content and action results, never session material.
2. Payment is never executed without a per-action owner approval in the conversation. Cart add, hold and similar non-payment mutations on sites the owner has connected need no approval.

**Removed from the request path during the pilot:**

- per-query sensitivity judgments on the owner's own typed request before public lookup (the `uncertain` fail-closed path and its variants);
- re-asking the owner whether ordinary product, person, place or title terms may be searched;
- the "initial research slice has no cart authority" rule in the Owner Control Contract, which becomes conditional on this posture;
- provider or destination gating that requires a separate owner decision per provider once the owner has configured that provider's key.

**Unchanged:**

- saved private values (secrets, identifiers the owner marked private) are still redacted from outgoing text by deterministic code;
- private documents are not transmitted externally without the existing document-sharing grant;
- Memory writes from workers remain candidates;
- Work/Event/Evidence recording, receipts and inspection.

The hardening program is not enumerated by this contract and is not activated by pilot completion. Findings that would justify a protection layer are recorded as issues under a "hardening" label without being implemented in this program, unless the owner selects them.

## Probe scenarios and the no-scenario-code rule

Three scenarios exercise the loop during development. They are **probes**, not the goal.

| Probe | Owner request (Telegram) | Capabilities exercised | Completion evidence |
| --- | --- | --- | --- |
| A. Book to cart | "《리더는 언제 차이를 만들어내는가》 사서 볼 수 있게 장바구니에 넣어둬" | search (model-chosen provider), page read, browser action in logged-in profile, memory (owner's preferred bookstore) | product identity confirmed; cart page lists the item; report matches |
| B. Schedule reminder | "내일 일정 보고 미리 알려줘" | calendar read, current context/time, Attention preparation, Telegram delivery | reminder stored with correct time; delivered before the event; report matches |
| C. Lunch suggestion | "점심 뭐 먹지?" (with allergies, preferences and location on record) | memory/context read, search (model-chosen provider by location), page read, Attention preparation | suggestion respects allergies/preferences, cites current sources, is ready at the expected time |

A **fourth, held-out scenario** is chosen by the owner at closeout, must not have been used during development, and is run on the closeout head. If the loop fails it for a reason that would have required scenario-specific code, completion is rejected.

**No scenario-specific code.** Decision and runtime code must not branch on a named site, provider, product category or question type. The runtime exposes generic capabilities and grant checks; the model chooses among them. A PR that makes a probe pass by naming that probe's site or provider in code is rejected. Every PR under this program states in its description whether it generalizes the loop or only makes a scenario pass.

## Capabilities

Each capability is a generic interface with replaceable providers; the model selects the provider through a parameter, and the owner configures which providers exist and their keys in Settings.

| Capability | Interface (model-facing) | Providers in this program | Owner setup |
| --- | --- | --- | --- |
| Web search | `search(query, provider?, locale?)` returning ranked results with source URLs | existing Bing RSS read; Naver Search API (web, book); Brave Search API | Naver client id/secret, Brave key in Settings |
| Page read | `read_page(url)` returning extracted text and links | existing public page reader; the browser profile for logged-in pages | none |
| Browser action | `browser.act(site_session, steps)` for navigate, click, type, read within the owner's logged-in profile | Playwright with a persistent profile owned by the execution environment | owner logs in once per site in that profile |
| Calendar | existing calendar read/create/reminder operations | existing Google Calendar connector | existing OAuth |
| Memory and context | existing Memory, MemoryCandidate and current-context reads/writes | existing stores | owner records preferences, allergies, locations |
| Delegation (phase 2) | `delegate(peer, task)` per the [A2A delegation contract](mp1-d04-a2a-delegation-contract.en.md) | existing compatibility A2A adapter extended to a family peer | peer configured by the owner |

Reuse governs: each capability issue records its Adopt / Adapt / Build review naming the existing repository symbol, the official SDK or API, and the thin AgentOS glue. Commodity mechanics (HTTP, browser automation, protocol clients) are adopted; AgentOS owns only Grants, sessions, secrets, evidence and the model-facing interface.

## Attention in this program

Attention is the anticipatory half of the secretary. In this program it is bounded to:

- preparing what a scheduled or predictable owner request will need (probe C), using current context and Memory;
- turning a calendar event into a timely reminder (probe B);
- proposing, not executing: an Attention candidate becomes Work only through the normal request path or an owner-accepted standing preparation.

It builds on the merged current-context work and CONTEXT-STATE-01 #627, which is re-parented into this program. Background pattern mining and unsolicited interruptions outside accepted preparations remain out of scope.

## Family collaboration (phase 2)

A request such as "아내 장바구니에 세탁세제 넣어줘" is fulfilled by delegating to the spouse's agent, never by acting with the spouse's session. The existing A2A delegation adapter (Agent Card validation, bounded task prompt, status polling, artifact validation, cancellation) is extended so that a family peer can be configured by the owner and so that the peer's agent runs the same agency loop under its own owner's Grants. Where the peer's owner has not allowed the requested effect, the peer reports that and the requesting assistant reports it truthfully. Phase 2 starts only after the phase 1 completion audit.

## Completion rule

The program is complete when all of the following hold on one closeout head:

1. **Alternatives observed.** Automated tests with injected model transports and at least one recorded live run show the loop moving to a different provider, query or route after a failed path, without repeating the same path.
2. **Evidence-based completion enforced.** `succeeded` is never emitted without matching observed state; tests cover a tool that "succeeds" without the goal being reached.
3. **Reports match observation.** Transcript fixtures and live runs show requested/observed/failed/unknown stated correctly.
4. **Execution environment enforces only the allowed set.** Negative tests show payment blocked without approval and secrets absent from prompts, logs and Evidence; positive tests show cart add, provider choice and page reads proceed without re-asking.
5. **No scenario-specific code.** Review confirms no site, provider or category branch in decision/runtime code.
6. **Probes A, B, C and the held-out scenario** complete on the owner's installation with their evidence recorded. Live runs are owner-operated and budgeted; a fixture pass alone does not satisfy this item.
7. **Phase 2** delegation completes its own audit, or the owner explicitly closes the program at phase 1 and records phase 2 as the successor.

Completion does not select a successor. The hardening program and any further capability are separate owner activations.

## Non-goals

- Payment, order submission or any effect the owner has not connected.
- Background pattern mining, habit inference or unsolicited interruptions beyond accepted preparations.
- Multiple principals on one installation; the family peer is a separate agent.
- A new coordinator, planner framework, graph store or evaluation platform.
- Rewriting merged Presence, Settings, Telegram or current-context work; they are regression inputs.
- Re-adding request-time sensitivity judgments removed by the pilot posture, unless the hardening program is activated.

## Related documents

- [Research: secretary agency specification (ko)](research/secretary-agency-spec-2026-09-26.ko.md)
- [Decision Layer](decision-layer.en.md) — judgment versus authority
- [Assistant Execution Contract](assistant-execution-contract.en.md) — loop, capabilities and typed outcomes reused by this program; its egress composition rules are conditional on the pilot posture
- [Current Context Contract](current-context-contract.en.md) and [implementation](current-context-implementation.en.md)
- [Owner Control Contract](owner-control-contract.en.md) — effects and approvals; cart rule conditional on the pilot posture
- [A2A delegation contract](mp1-d04-a2a-delegation-contract.en.md), [calendar contract](mp1-d05-calendar-contract.en.md)
- [Presence Experience Contract](presence-experience-contract.en.md) — owner-facing experience rules, still applicable
