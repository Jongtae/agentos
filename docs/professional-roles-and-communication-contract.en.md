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
First map current symbols and runtime paths for semantic events, conversation focus, corrections/cancel, Evidence and message rendering. Specify the smallest generalizable gap before implementation. Prefer existing Decision Model, Work/Event, Memory, Grant and Presence mechanisms. No role-specific kernel switch statements, universal ontology database, new scheduler or duplicate conversation store by default. This contract does not reopen closed work or change the current selected delivery plan.
