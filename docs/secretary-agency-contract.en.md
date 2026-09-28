# Personal AgentOS Secretary Agency Contract

## Amendment — #818 (2026-09-28)

OWNER-MODEL-04 follows owner feedback on Works `18c91ca7` and `7767e7da`, where a stated fact became a pending MemoryCandidate and the owner saw only a failure:
- **A proposed memory is not a failed action.** A `save_memory` that #597 holds as a pending MemoryCandidate is a recorded proposal (trail state `proposed`). It neither withholds the answer (#752 `answer_withheld`) nor makes the Work partial or failed, and it is not evidence of the goal. The #488/#752 rule is unchanged for every other tool, for calendar drafts and for a memory write that errored.
- **The owner confirms in one tap.** After a Telegram Work's reply, one message lists that Work's pending candidates (key and value, bounded, stored secrets removed) with [기억하기] [아니요]. The buttons follow the #659 pattern: this notification, sent, the paired private chat, its generation and message, and the shown set's digest; a decided candidate is no longer offered, so a replayed tap does nothing. A yes goes through the existing owner approval path (`issue_candidate_memory_approval` → `accept_memory_candidate`); a no is the existing reject. The web keeps 내 기록.
- **Guidance only (C16).** `save_memory` content is the value in the owner's own words, and the key names the attribute. When the owner tells AgentOS something rather than asking, the plan question and the core instructions ask for a secretary's response: acknowledge it, update what AgentOS knows, and act on what it changes. No task logic.

## Amendment — #805 phase 1 (2026-09-28)

OWNER-MODEL-03 keeps the owner in mind after each Work, asynchronously and minimised (`src/personal_agent/owner_model.py`). It adds no data source, no monitoring and no task-specific code:
- **Trigger.** A Work a worker AI answered that ends `succeeded` or `partial` records one pending upkeep (`owner_model_upkeep`, keyed by the Work) in the transaction that settles it. Failed, cancelled and unknown Works, rule/command replies (no worker AI ran), preparation runs and location continuations record none. These are typed markers, not text rules.
- **When.** The existing service tick claims at most one pending upkeep. The check that no Work is queued or running and the claim are one immediate transaction, serialized with the Work claim. The upkeep then runs off the work thread, one at a time (single-flight). No model call starts after a five-minute deadline, and each call is also bounded by its adapter's own timeout. It never runs on a request path, and owner messages, reminders and notifications never wait on it. Nothing pending is one indexed query and no model call. A claimed upkeep never runs twice, even after a restart. A row still claimed an hour later, left by a crash, expires with an `owner_model` event (`expired`, reason `interrupted`).
- **Judgment (C16).** The owner's Judgment AI makes one `structured` call. It reads the owner's request (owner words), the final answer excerpt (model-stated), the profile snapshot and the clock. Every fact is redacted first with the judgment redaction, which removes stored secrets and credential shapes, plus the Work's saved private values from the model-stated facts. It proposes at most five facts, each with `category` (identity, place, routine, schedule or preference), `kind` (`stated` or `inferred`), a `profile.` key, content and evidence (each at most 200 characters), and an optional `supersedes_key`. The question is generic. Health, finances, relationships, beliefs, credentials and third parties are proposed only when the owner stated them for a purpose. In phase 1 this sensitive-category rule is in the prompt only; no AgentOS check enforces it, because detecting sensitivity would need a text rule.
- **Candidates versus canonical (C5, #597).** AgentOS drops a proposal that is out of shape, out of bounds or outside the enum, one without a `profile.` key, and one whose `supersedes_key` is not its own key. It also drops duplicates. A duplicate is the same content as a current `profile.` Memory value under any key, anything the source Work already wrote (the worker's own `save_memory`, as Memory or candidate, under any key), a pending candidate with the same key and content, or another proposal in the same answer. A `stated` fact becomes canonical Memory only on a yes from its own #597 judgment (`explicit_memory_fact`), asked per fact over the owner's message and the proposed key and value. The value-coverage and key-replacement checks that `save_memory` uses must also pass, and the write goes through the same candidate → exact approval → accept path. For both writers, a key is named by the owner only through its fact words: `profile` and the category words (identity, place, routine, schedule, preference and their inflections) never name a key. Otherwise it stays a pending MemoryCandidate. An `inferred` fact is always a candidate. Both are attributed to the source Work. Pending candidates do not decay yet; that is phase 2. An older value under a key the request did not name is never silently superseded. The #804 lookup exclusion applies unchanged: only accepted, owner-stated `profile.` facts are exempt.
- **Budget and pause.** Config `owner_model_upkeep` = `{enabled, daily_calls}`. Upkeep is enabled by default, and the cap defaults to 20 calls in a rolling 24 hours. The cap counts every model call that reached the Judgment AI's transport: the proposal and each per-fact #597 judgment, so at most six per run. A route that answers before any transport (not configured, invalid, cancelled, structured-unsupported) counts nothing; each adapter reports this as `DecisionConfidence.sent`. The pause switch and the rolling allowance are read again before each later call and each write. A pause stops the run with nothing more written. A spent cap or the deadline stops further calls, and a stated fact left unjudged stays a candidate. Evidence records which of these stopped the run (`stopped`). While paused, nothing is enqueued and nothing runs. A pending upkeep older than seven days expires without a call. The controls are `GET /api/owner-model` and `POST /api/owner-model/request` (`operation: read | set`); there is no Settings UI in this phase. The Jev route cannot answer `structured`, so its upkeep is recorded as unavailable.
- **Evidence.** Each run is one `owner_model` tool event on the source Work, with status `recorded`, `unavailable` or `expired`. It holds the decision outcome, the deciding route, provider and model, the confidence, and the input lengths. For each applied proposal it holds the key, category, kind, content length and outcome (memory or candidate, with the refusal reason). For each dropped proposal it holds only a short key digest and the reason, never the model-chosen key. It also holds the per-fact #597 verdicts. It never holds the input texts. The judgments' own audit rows are linked to the source Work, as a Work's are. The event is not a Work step, so outcome, retry and parking logic ignore it; #794 can show it.

## Amendment — #774 (2026-09-28)

The owner-state components the secretary relies on were unreachable from the owner's subscription CLI route. These are Memory and MemoryCandidate (#597), preparations and reminders (#659), and the calendar connector (#606). The trusted-local profile declared them unavailable because the CLI's MCP bridge is a separate process without the service's memory approval, connector or preparation acceptance.

They are now relayed to the service over the existing #701 relay (`cli_browser_relay`), like the browser tools, and run in the service's `Capabilities` under the direct route's unchanged gates:
- a memory write is a MemoryCandidate unless the owner explicitly asked (#597);
- a calendar write is a preview until approved;
- a preparation runs only once accepted;
- `ask_location` asks the owner in the paired Telegram chat to share a current position when a request depends on where the owner is now (the #626 one-time `request_location` prompt). The location that answers the pending request continues the asking Work exactly once: one new Work with the same request and channel, keyed by the consumed request and related to the asking Work as a `reference`, with the reported position bound to it as task-scoped current context. The asking Work is not re-run, an unrequested location still starts no Work, and a continuation never accepts a preparation or issues a memory approval by itself. A Work the owner stopped or cancelled is never continued, and stopping or cancelling it withdraws its pending request. When the asking Work already called an effect tool, the continuation's worker first reads the #730 effect note (tool names, hosts and observed outcomes, never stored as owner text) and checks state before repeating anything. A preparation run's continuation stays that preparation's run (same slot key, isolated history, prefix and scrub); the slot waits for the answer and keeps the continuation's result, or settles from the asking run once the request expires. The tool is offered only to a Work from the paired Telegram chat, on the direct route and through the trusted-local relay alike.

The strict-isolated and isolated profiles are unchanged. A bridge without the relay does not offer these tools. The #678 separation still holds: a turn with the CLI's own web search offers no private-store read (Memory, calendar reads), and the orchestrator chooses a no-search subset when a turn needs them (#735).

## Amendment — #677 (2026-09-27)

Owner decisions after re-analysis:
- **Search.** Web search defaults to the **connected AI's built-in web search**, so the user needs no extra key. Citations are recorded as evidence.
  - Fallbacks are site-internal search, an optional Brave key, and **Bing RSS as an owner opt-in for personal use**.
  - **Naver is removed**: its Search API terms ban AI use from 2026-09-07, and its developer keys end on 2027-06-30.
  - Google results are never scraped; its Terms and spam policy prohibit automated queries.
- **Browser.** There is no separate browser install. The browser capability uses the **macOS system WebKit inside the app** (SEC-BROWSER-02 #680). Cookies are kept in an AgentOS-encrypted jar whose key is in the macOS Keychain, and Settings lists and deletes sessions per site. Google sign-in is not supported inside the embedded engine. **Platform scope:** during the pilot the browser capability is macOS-only. On Linux and Windows it is reported as unavailable and browser-dependent goals end honestly as partial. The existing Playwright engine is removed only because the owner rejected a separate browser install. A non-macOS backend using the system web engine (WebKitGTK / WebView2, no download) is recorded as #682 and not selected.
- **Judgment AI.** It defaults to the **cheapest qualified model** of the selected route, and the owner can pick a model from a list in Settings. Codex judgments run under the #616 strict-isolated profile (SEC-JUDGE-01 #679).

The Capabilities table below is superseded where it names Naver; its Browser action row is updated for #680. In the pilot posture, Brave remains an optional key and Bing RSS an explicit opt-in.

## Amendment — #701 (2026-09-27)

SEC-CLI-01 makes the loop work on the owner's subscription CLI route (Codex or Claude Code, trusted-local profile):
- **Legacy provenance.** Works recorded before #605 are classified once from durable signals only (private tool events, the document-job list, context attachments, saved notes, the notes-summary command, turn records, whether a model produced the reply). A clean one is recorded as owner conversation; any private signal keeps it unrecorded. No judgment about text.
- **Native-search gate (owner decision on #701; superseded by #705).** The #678 gate read only what the shown messages' own Works read themselves, not the inherited `history:*` chain, so a Work that read notes blocked the CLI's own search while its messages were in the shown 16-message window. Since #705 the gate ignores prior conversation entirely (see the #705 amendment). Mediated browser output (`owner-browser-session`) never blocked it. The #605 inheritance rule, including the browser-session label, is unchanged for public-lookup composition and turn-record storage.
- **Search.** On a turn where the CLI's own web search is on, the bridge's `web_search` and `bounded_public_research` are not offered, so the CLI's own search answers. When it is off, the bridge search tools say why and name each provider's own caveat.
- **Browser.** The five browser tools are offered on the trusted-local CLI route. The bridge only relays each call to the AgentOS service, which runs it through the same `BrowserSession` as the direct route: mediation, the label-independent payment guard, approvals, budget, repeat key, loopback refusal, the one profile lock and the encrypted jar are unchanged. The strict-isolated and isolated profiles never offer them. On a native-search turn the browser tools stay; the pre-turn gate alone decides native search.
- **Turn records.** The local prompt envelope is kept after deterministic redaction of the Work's lookup-exclusion set (its Memory candidates, notes and calendar drafts), stored secret values and credential shapes. Profile values have no identifier marker and are kept as sent. Only a turn that carried a private store (notes, documents, Drive, context inbox, Memory reads, calendar, the browser session and the other private stores, including ones inherited from shown history under #605) keeps size and digest only. Turn records stay out of export and backup.
- **Settings** shows, per Main AI route, whether its own web search and the browser tools are available, and why not (including a CLI that is not installed or not signed in).

## Amendment — #705 (2026-09-27)

SEC-SEARCH-03, by owner direction under the pilot posture (#705; runtime-only scope under #707):
- **Native-search gate.** Prior conversation history no longer turns the CLI's own web search off. The gate is off only when the **current turn** carries an explicit private splice (a document, Drive file, context inbox, `/summarize` or notes pasted into the prompt at turn start), when the profile is strict-isolated or the isolated sidecar, or when the CLI's refusal is remembered. A shown earlier Work that read notes, Codex's own `list_notes` call, `unrecorded` legacy rows, `engine-unmediated-read` and `owner-browser-session` no longer matter to this gate.
- **Why.** The CLI's own search runs at the owner's configured AI provider (OpenAI for Codex, Anthropic for Claude Code), and the pilot posture already accepts egress to that provider. Offering `/new` to reset context was rejected for ordinary users (#704).
- **Accepted egress change.** Private material from earlier turns that the CLI is shown can now appear in the CLI model's own search queries to that provider. AgentOS does not compose or redact those queries. This weakens the #678 boundary by owner direction and takes independent review.
- **Unchanged.** The private-read bridge tools (`list_notes` and the other private-store reads) are still not offered on a native-search turn, so the model cannot read a store and search in the same turn. Notes reach a CLI turn as an explicit splice (`/summarize`) or through a search-off turn's `list_notes`, and search is off for that turn only. Stored secrets never enter prompts. The #605 inheritance rule is unchanged for AgentOS-composed third-party lookups (Bing, Brave) and for turn-record storage.

## Amendment — #710 (2026-09-27)

ORCH-01 (Constitution C16): for each Work the Judgment AI returns one validated plan choosing the worker (a configured, verified Main AI route) and model, the brief (goal, selected context sections, completion criteria) and optionally a tool subset; after the attempt the existing `goal_reached` judgment evaluates it and the orchestrator may re-delegate at most twice within the Work budget, never after an effect. Without a usable plan the default Main AI runs the raw request as before. The "Roles" below now include this orchestration step; see [Decision Layer — Orchestration](decision-layer.en.md#orchestration-orch-01--710).

## Amendment — #719 (2026-09-28)

SEC-ATTN-02 extends owner-accepted preparations (#659) with two generic capabilities; it adds no scheduler, tool or task-specific code:
- **Watch window.** A `prepare` preparation may repeat every N minutes (5–720) from `due` until `until` (at most 24 hours later), never more than `max_runs` Works (at most 48) and never at or after `until`. It runs on the existing service tick; a tick with nothing due makes no model call. A window that closed while AgentOS was down ends as `expired` without running. Each run is an ordinary Work under the existing per-Work budget.
- **Silent unless needed.** With delivery `when_needed`, each run stays in AgentOS (작업 현황). After it finishes, the Judgment AI answers one bounded proposition over the accepted goal, the run's scrubbed result and the last notification: does the owner need this now, and is it new? The typed decision (`notify` / `quiet`) and its reason code are recorded on the preparation and in the run's Evidence. Only `notify` queues one Telegram message, in the same transaction that settles the run. A result identical to the last notification is quiet without a judgment; without an available judgment the result is sent once and later unjudged runs stay quiet.
- **Owner control.** A watch is proposed and accepted with the #659 flow; the proposal states the interval, deadline, run bound and delivery. It is cancelled in Settings or with the 그만 지켜보기 button on its own notification.

Live-data tools (such as directions or traffic) remain an owner decision recorded on #719; none is added.

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
| Web search | `search(query, provider?, locale?)` returning ranked results with source URLs | the connected AI's own web search (default; OpenAI Responses `web_search`, Anthropic `web_search` server tool, OpenRouter `openrouter:web_search`, or the Codex / Claude Code CLI's own search inside its Work turn); Brave Search API; Bing RSS read as an owner opt-in for personal, non-commercial use (SEC-SEARCH-02 #678; Naver removed by #677) | none by default; optional Brave key; Bing RSS toggle in Settings |
| Page read | `read_page(url)` returning extracted text and links | existing public page reader; the browser profile for logged-in pages | none |
| Browser action | `browser.act(site_session, steps)` for navigate, click, type, read within the owner's logged-in profile; output is mediated (see below) | the macOS system WebKit embedded in AgentOS (SEC-BROWSER-02 #680): a PyObjC worker process with an in-memory website data store; sign-in cookies kept per site in an AgentOS-encrypted jar under `store.private` whose key is in the macOS Keychain. No Playwright and no `playwright install`; no browser download. macOS only during the pilot: elsewhere the capability is reported unavailable (`browser_unavailable_platform`); a non-macOS system-engine backend is #682, not selected | owner logs in once per site in the embedded login window (Settings › 브라우저 로그인 세션), where sessions are listed and deleted per site; Google sign-in is not supported in the embedded engine |
| Calendar | existing calendar read/create/reminder operations | existing Google Calendar connector | existing OAuth |
| Memory and context | existing Memory, MemoryCandidate and current-context reads/writes | existing stores | owner records preferences, allergies, locations |
| Delegation (phase 2) | `delegate(peer, task)` per the [A2A delegation contract](mp1-d04-a2a-delegation-contract.en.md) | new adapter: `a2a-sdk` adapted behind the D-04 interface (the earlier `a2a.py` was removed with the retired MP1 compatibility surface; no adapter exists on `main`) | peer configured by the owner |

**Browser output mediation (deterministic, part of pilot boundary 1).** Page content from a logged-in session can itself contain secrets (an account page showing an API key, a password field, a one-time code). Browser read output therefore passes through deterministic mediation before it reaches the model or Evidence: values of `password`-type inputs and of fields whose `autocomplete` names a credential, one-time code or card field are never returned; the existing saved-private-value redactor is applied to page text; the raw DOM and storage state are never returned. A negative test proves a fixture account page with a rendered token does not leak. This is exclusion of session and credential material, not a semantic judgment about the request.

**Payment guard is independent of the model's label (pilot boundary 2).** The model declares an effect class on browser actions, and that label can only add an approval requirement, never remove one. Deterministically, typing into a card-number, CVC or one-time-code field, and submitting a form that contains such a field, require an owner approval bound to Work, the page digest and the target element; the runtime verifies the token at execution. A model label of `navigate` or `mutate` on such an action does not lift the guard. Sites that complete purchase without card fields (stored payment methods) are covered by the owner not having connected payment; the pilot does not claim to detect every purchase button, and the owner is told this limitation in Settings.

Reuse governs: each capability issue records its Adopt / Adapt / Build review naming the existing repository symbol, the official SDK or API, and the thin AgentOS glue. Commodity mechanics (HTTP, browser automation, protocol clients) are adopted; AgentOS owns only Grants, sessions, secrets, evidence and the model-facing interface.

## Attention in this program

Attention is the anticipatory half of the secretary. In this program it is bounded to:

- preparing what a scheduled or predictable owner request will need (probe C), using current context and Memory;
- turning a calendar event into a timely reminder (probe B);
- proposing, not executing: an Attention candidate becomes Work only through the normal request path or an owner-accepted standing preparation.

It builds on the merged current-context work and CONTEXT-STATE-01 #627, which is re-parented into this program. Background pattern mining and unsolicited interruptions outside accepted preparations remain out of scope.

## Family collaboration (phase 2)

A request such as "아내 장바구니에 세탁세제 넣어줘" is fulfilled by delegating to the spouse's agent, never by acting with the spouse's session. A new delegation adapter implementing the D-04 interface (Agent Card validation, bounded task prompt, status polling, artifact validation, cancellation) is built by adapting `a2a-sdk`; the earlier compatibility adapter was removed from `main` with the retired MP1 surface and is prior art only. It lets a family peer can be configured by the owner and so that the peer's agent runs the same agency loop under its own owner's Grants. Where the peer's owner has not allowed the requested effect, the peer reports that and the requesting assistant reports it truthfully. Phase 2 starts only after the phase 1 completion audit.

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
