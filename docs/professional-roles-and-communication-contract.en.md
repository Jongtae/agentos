# Professional Roles, Mandates and Communication Contract

## Status and precedence
Normative **product design and acceptance** contract, not evidence of shipped functionality and not an activation of delivery. Read with [Architecture](personal-agentos-architecture.en.md), [Decision Layer](decision-layer.en.md), [Presence](presence-experience-contract.en.md), [Secretary Agency](secretary-agency-contract.en.md), [Development Constitution](development-constitution.en.md) and [Connection and Delegation](connection-delegation-contract.en.md). Root `delivery-plan.yaml` alone selects the active development goal. Existing owner authority, memory, egress, payment, external-effect and evidence rules take precedence; this document cannot silently expand them.

## Product thesis
Personal AgentOS is an **owner-centered operating environment for multiple professional roles**, not a secretary-only application. Secretary/Executive Assistant is one role among finance, investment analysis, research, purchasing, travel, project and health coordination. One continuous owner-facing agent can use multiple professional lenses without creating separate speaking identities. A role is neither a permission grant nor proof of professional licensure or regulated authority.

## Semantic composition
- **Core world concepts:** person, organization, account, asset, money, document, message, event, contract, transaction and place. Preserve provenance, identity and time.
- **Domain lens:** concepts and relationships appropriate to finance, scheduling, travel, health, research, etc.
- **Professional role lens:** interpretation, standards of practice, expected evidence, escalation and reporting obligations; several lenses may contribute to one request.
- **Owner context:** goals, preferences, relationships, existing work and commitments; distinguish ephemeral context from durable Memory.
- **Mandate:** task/role objective, scope, exclusions, limits, duration and completion/follow-up criteria.
- **Authority:** independently enforced current Grants, approval and external-action boundaries. A mandate or role never authorizes an action by itself.
- **Decision model:** interpret goal and situation, identify relevant lenses, choose reason/ask/delegate/act/stop, evaluate observations and outcomes, and revise when the owner intervenes.
- **Execution:** owner-chosen AI and bounded tools/skills/specialists; no site-, scenario-, domain- or role-specific branching in core AgentOS code. Versioned skill content may supply expertise but not authority.
- **Evidence, outcome and commitment:** distinguish observed fact, inference, recommendation, authorized external effect, verified completion and still-open obligation. A commitment may be represented with existing durable primitives; do not add a store without a demonstrated missing invariant.

## Three dimensions, and lenses across them
- **Ontology** settles *what is understood*: sourced facts, identities, relationships and time.
- **Decision Model** settles *what to do*: reason, act, delegate, ask, report, follow up or stop.
- **Presence** settles *how the relationship is kept while acting together*: one voice, fitting communication, continuing collaboration.
- A **professional lens** gives all three its professional context. It is not a fourth layer and not a speaking identity.

## Presence is not a role
Presence is the common interaction capability that must hold **across** every role. The Presence research definition stays: **Continuity + One Voice + Situational Responsiveness + Memory + Availability + Conversational Recovery** ([research](research/presence-and-settings-ux.ko.md)). What makes it operate is that it is connected to the Decision Model *during* execution, not rendered after it (see *Decision Model ↔ Presence contract*).

The reporting, asking, discretion and follow-up principles learned from systematising secretary work are useful, but they are **one role's protocol**, not Presence itself. The same market drop is read differently:

| | Assistant | Wealth manager | Discretionary investment role |
| --- | --- | --- | --- |
| Reading | notable news | a risk to the person's asset goals | an event bearing on mandate constraints and positions |
| Judgment | should the person hear this? | what does it do to the portfolio? | is an adjustment needed within the mandate? |
| Action | notify by importance | analyse risk, offer options | decide and execute only where actually authorised |
| Communication | the key event | asset impact and choices | rationale, execution result, risk and constraint report |
| Follow-up | related schedule and tasks | revisit the financial plan | monitor positions and risk limits |

Understanding the discretionary role is not holding a legal or contractual discretionary mandate. The person saying “I delegate this to you” does not create regulated status or trading authority.

Communication therefore splits in two:
- **Common Communication Grammar** (every role, part of Presence): understand the request and confirm only when needed; report or stay quiet by importance and situation; separate observed fact from judgment and estimate; accept changed instructions; explain uncertainty and failure and recover; keep promises and follow-ups.
- **Role-specific Communication Protocol** (part of a lens): *what* counts as important and *how* it is reported in that practice — risk, liquidity and goal fit for wealth management; source reliability and uncertainty for research; price, stock, delivery and payment approval for purchasing. The same AgentOS speaks; the professional norms applied change with the situation.

## A professional lens is not a persona
Naming a prompt “Investment Advisor” only looks like a role. A lens defines at least the seven elements below. Each maps onto an existing mechanism, so a lens needs no new store, router or kernel branch (C16, #974):

| Element | Meaning | Where it lives today |
| --- | --- | --- |
| Domain Semantics | how the field's objects and relations are understood | versioned skill content loaded by the person's AI (`skill_load`) |
| Professional Practice | procedures and judgment standards applied | skill content |
| Mandate | for whom, with what goals and constraints | the Work's request, scope and orchestration brief |
| Authority | what is actually allowed | Grants and approvals, unchanged |
| Evidence Standard | what evidence a claimed result needs | `goal_reached` evidence judgment, plus skill content |
| Communication Protocol | what to report, when and how | skill content, read by the Decision Model's relevance judgments |
| Commitment Lifecycle | what responsibility remains after execution | existing preparation/watch scheduling and Work state |

The Decision Model (the person's AI) chooses which lenses apply per request; core code never selects a lens by name. When several lenses apply and disagree, the disagreement, its reasons and the authority boundary are reported; they are not merged into one unqualified answer.

## Cross-role communication and Presence
Presence is a **bidirectional operating relationship**, not a status renderer and not an extra specialist persona. Across all roles the agent should:
1. Give immediate, unobtrusive ambient feedback for latency; do not narrate every tool event.
2. Decide whether to communicate based on owner relevance: consequential discoveries, changed expectations, blockers, meaningful partial results, uncertainty, necessary choices and verified outcomes.
3. Apply role-appropriate communication protocols: a financial analysis discusses exposure, assumptions and risk; research discusses provenance and confidence; scheduling discusses constraints and commitments. Never present inferred or model-generated findings as verified.
4. Distinguish **inform**, **recommend**, **clarify**, **request approval**, **report outcome** and **follow up**. Do not ask for routine decisions within existing authority; do not treat silence as permission.
5. Accept mid-execution owner questions, corrections, priority changes and cancellation. Reconcile them with active Work, invalidate stale plans/approvals, and acknowledge effects that have already happened. If the runtime cannot be steered, disclose that limitation rather than pretending the correction took effect.
6. Track promised follow-up only when a real durable continuation/watch mechanism exists and is authorized. Do not promise monitoring from an ordinary one-shot response.
7. Preserve one speaking identity across roles and workers; technical receipts remain inspectable.

## UX contract: three distinct surfaces of feedback
- **Ambient:** native typing/thinking/progress indicator; transient, not a permanent conversation bubble; may be silent for fast tasks.
- **Semantic:** concise owner-relevant observations, plans, deviations and outcomes. Meaning and verified evidence matter more than source/tool counts.
- **Collaborative:** user can respond, correct, cancel, choose and approve; the interaction must causally affect the Work or transparently explain why it cannot.

Time thresholds can govern ambient feedback, **not** fabricate semantic progress. Repeated retries remain in technical Evidence; disclose only those that change owner expectations, authority, risk, reliability or choices. `unknown` consequential effects must never be silently retried.

## Decision Model ↔ Presence contract
The two directions already exist as separate judgments; this contract binds them. Inventory at 2026-10-10 (static reading of `conversation_handoff.py`, `quickstart_service.py`, `orchestrator.py`, `agent_runtime.py`, `mcp_bridge.py`):

- **Person → decision:** `steers_running_work` (#999: does a message sent mid-Work steer it; a yes reaches the worker with its next tool result on the direct route and the MCP bridge), `followup_relation` (retry, correction or new request), `parked_work_withdrawn`, `settings_draft_confirmed`/`declined`, `memory_withdrawn`.
- **Decision → person:** `owner_input_needed` (#740: ask), `goal_reached` (succeeded, partial, failed, unknown), `watch_notification_needed` (#719: notify or stay quiet, the only existing *should this be reported* judgment), and the ambient `turn_reaction`/`progress_reaction`/`closing_reaction`.

Gaps found:
1. No *should this be reported now* judgment or channel exists for foreground Work; the only mid-Work surface is the transient 40-character tool `status`, so fixed tool-name lines (#718) fill the space.
2. A steer reaches the running worker but not the orchestrator: a re-delegation plan can be made without the correction (stale plan).
3. The disposition of a steer is not told: a folded steer gets only a reaction, and a steer the worker never received (it called no AgentOS tool before finishing) silently runs as its own Work afterwards.
4. Relevance judgments carry no role or mandate, so “important” has one implicit (assistant) standard.

Rules:
1. **The Decision Model decides what to say; Presence decides how it is carried.** The decision side emits a communicative act (inform, recommend, clarify, request approval, report outcome, follow up), its content and its evidence level (observed or inferred). Presence picks the surface (ambient, semantic, collaborative), timing and the one voice. Presence never invents content.
2. **Relevance is judged by the person's AI against the Mandate and the active lenses' Communication Protocol** (the market-drop table). Core code holds no role rule; it keeps only budgets (messages per Work), authority and truth labels.
3. **Every message from the person mid-Work gets a disposition**, decided and then told: applied now, applied from the next step, cannot apply (effect already happened, worker not steerable) or handled as a new request.
4. **A correction reaches planning**, not only the running worker; approvals that no longer cover the changed constraint are invalidated through the existing digest-bound approval path.
5. **Communication never creates authority.** A stated delegation is mandate input, never a Grant or regulated status.

## Conversation style: warm, never flattering
How the voice sounds is part of the common grammar. Evidence-backed defaults:
- **Respond to what the person said before moving on.** Follow-up questions and visible responsiveness (listening, understanding, validation, care) increase liking across live conversations ([Huang et al., 2017](https://pubmed.ncbi.nlm.nih.gov/28447835/)). Ask a genuine follow-up only when it helps; never interrogate.
- **Meet good news actively and constructively.** Enthusiastic, engaged responses to a shared positive event predict relationship satisfaction and closeness better than understated or dismissive ones ([Gable et al.](https://www.researchgate.net/publication/6737400_Will_You_Be_There_for_Me_When_Things_Go_Right_Supportive_Responses_to_Positive_Event_Disclosures)).
- **Thank rather than over-apologise for small delays or hiccups.** “기다려 줘서 고마워요” restores satisfaction better than repeated apology in service recovery ([AMA summary of You et al., 2020](https://www.ama.org/2020/04/12/when-and-why-saying-thank-you-is-better-than-saying-sorry-in-redressing-service-failures-the-role-of-self-esteem/)). A real failure is still stated plainly and owned.
- **Warmth must not cost accuracy.** Models tuned for warmth were markedly more error-prone and about 40% more likely to affirm a user's mistaken belief, worst when the user sounded sad ([Ibrahim et al., Nature](https://www.nature.com/articles/s41586-026-10410-0)). Kind wording carries the same facts, uncertainty and disagreement; never praise or agree to please.
- **Speak like a capable person who knows them**: natural everyday register in the person's language (for Korean, a soft 해요체 rather than formal 합니다체 or report style), short sentences, the person's own words, no system vocabulary (Work, tool, route), no titles or master/servant framing.

## Example: cross-role interpretation
Owner: “I may buy a home in December; should I sell some shares?” Interpret housing goal, liquidity, taxes, investment risk and timing together. Ask only for missing decisive information; provide sourced scenarios and uncertainty. Do not place trades without a valid applicable mandate, actual brokerage capability, and separately enforced authority. Investment-management vocabulary or an owner request alone does not establish legal entitlement to regulated discretionary management.

## Acceptance: user-visible, causal and evidence-backed
- Short request: answer without routine queued/running/completed bubbles.
- Long request: transient ambient feedback; a semantic update only for a material change.
- Discovery: distinguish opened sources from verified findings.
- Correction while executing: new constraint changes downstream actions, or an explicit inability is communicated; stale actions cannot proceed.
- Cross-role request: uses relevant lenses without separate worker personalities, contradictory unqualified advice or implicit authorization.
- Financial role: advice, mandate and trade authority are separately represented; no unsupported execution claim.
- External effect: completed, partial, failed and unknown are distinct, supported by Evidence and no duplicate replay.
- Commitment: no false future follow-up promise; accepted follow-up survives restart and is cancelable where supported.
- Evaluation: owner-visible Telegram/browser transcripts, execution/effect records, interruption and negative authority tests. Synthetic, deterministic and live evidence remain distinct.

## Implementation boundaries
First map current symbols and runtime paths for semantic events, conversation focus, corrections/cancel, Evidence and message rendering. Specify the smallest generalizable gap before implementation. Two tracks stay separate so the near-term work does not wait for the long-term design: **near-term Presence** closes the four gaps above on the existing execution structure (meaningful feedback, continuity, mid-Work intervention, exact completion and failure reports) with the common grammar only and a slot for the mandate; **long-term design** defines the common contract connecting domain ontology, lenses, mandate, Decision Model, communication protocol and commitment. Neither requires finishing the other first. Prefer existing Decision Model, Work/Event, Memory, Grant and Presence mechanisms. No role-specific kernel switch statements, universal ontology database, new scheduler or duplicate conversation store by default. This contract does not reopen closed work or change the current selected delivery plan.
