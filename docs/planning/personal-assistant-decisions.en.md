# Personal Assistant Decision and Research Ledger

> **Design candidate v0.3 — 2026-09-20. Documentation only; runtime implementation NOT ACTIVATED.**
> [Experience/requirements](personal-assistant-experience.en.md) · [Scenarios](personal-assistant-scenarios.en.md)
> [Discussion #381](https://github.com/Jongtae/personal-agentos/issues/381) · [Documentation work #383](https://github.com/Jongtae/personal-agentos/issues/383)

## Purpose and status vocabulary

Preserve the source of a decision without making implementers reinterpret an ever-growing comment thread. The experience document expresses the current candidate; this ledger explains why it exists and what is or is not agreed. Old comments are not deleted. Their earlier proposals are qualified explicitly below.

- **Owner-confirmed direction:** a product principle supported by the owner's discussion. It is not automatically an implementation specification or activation.
- **Assistant proposal:** a concrete mechanism, default or decomposition offered for review; the owner has not separately approved every detail.
- **Existing contract:** a current repository rule, with its actual implementation/evidence limitations.
- **Open:** a choice with no adopted answer.
- **Superseded/qualified:** an earlier interpretation replaced or narrowed; preserve the historical source.

The repository account used to post a comment or commit is not proof the owner authored or approved every sentence. Attribute confirmed requirements to the underlying owner statement; label assistant deductions. Documentation scope is authorized by the owner's current request to deepen the project design. It permits this issue-linked documentation branch and draft PR, not source changes, merge, evaluation with paid models or product operation.

## Confirmed direction register

| ID | Direction and source | Qualification / affected requirements |
| --- | --- | --- |
| D-01 | Preserve Personal AgentOS; use b3os as reference rather than mandatory foundation. [Original planning issue](https://github.com/Jongtae/personal-agentos/issues/381) | Selective reuse remains a future license/maintenance decision. Not an instruction to fork or install. REQ-21. |
| D-02 | Tone, formality, address, verbosity and reactions belong in personal-assistant settings, not a fixed universal personality. [Owner clarification](https://github.com/Jongtae/personal-agentos/issues/381#issuecomment-5746720352) | Exact fields/defaults/UI remain proposed. Presentation never expands authority. REQ-12. |
| D-03 | Develop the experienced service through concrete conversation, not repeated abstract personality questionnaires. [Same clarification](https://github.com/Jongtae/personal-agentos/issues/381#issuecomment-5746720352) | Example dialogue is not evidence of execution. All scenario wording is illustrative unless marked supplied. REQ-13, REQ-22. |
| D-04 | Use permitted personal routine, preferences and current situation to reduce repeated explanation. [Concrete meal context](https://github.com/Jongtae/personal-agentos/issues/381#issuecomment-5747509645) | Current attendance/location and source freshness cannot be inferred permanently from family/background. REQ-01, REQ-04, REQ-10. |
| D-05 | Consider one installation serving several people, each with their own assistant and coordinated shared work. [Household extension](https://github.com/Jongtae/personal-agentos/issues/381#issuecomment-5746839491) | Deployment/product direction, not universal adoption forecast or existing multi-user support. No household-wide merged identity. REQ-02, REQ-14. |
| D-06 | Separate personal contexts and scope collaboration by relationship/work, including family, company and school. [Context refinement](https://github.com/Jongtae/personal-agentos/issues/381#issuecomment-5746903583) | Core separation precedes multi-user release; sophisticated privacy UI may be later. Host-admin cryptographic isolation is not proven. REQ-03, REQ-14. |
| D-07 | The requester's authorized source controls what they requested when another assistant's representation conflicts. [Context refinement](https://github.com/Jongtae/personal-agentos/issues/381#issuecomment-5746903583) | Field-specific recipient/fulfillment/joint-term rules below are design proposals, not “requester controls all facts.” REQ-05, REQ-16. |
| D-08 | Preserve decision-relevant concrete details for accurate scenarios rather than over-anonymizing. [Recording clarification](https://github.com/Jongtae/personal-agentos/issues/381#issuecomment-5747509645) | Purpose-bounded permission for supplied scene facts, not new private research or publication of credentials/full transcripts. S-01–S-03. |
| D-09 | Deepen Attention / Prepare / Interrupt / Act as the next design question. Source: owner's later discussion of the supplied structure, captured by [#383](https://github.com/Jongtae/personal-agentos/issues/383) | Approval to explore the concept, not approval of every lifecycle, mandate field or numeric threshold. REQ-06–REQ-11. |
| D-10 | Public self-research cannot be the product's required source of personalization; assistants should interact inside real, permitted relationships rather than autonomously choosing contacts. Source: owner's post-article objection and current design request, captured by [#383](https://github.com/Jongtae/personal-agentos/issues/383) | Do not assert that ordinary users can never benefit from public data; require usefulness without it and make it optional. Do not automatically contact even a known person without covering authority. REQ-01, REQ-14. |
| D-11 | Runtime implementation remains on hold; restored execution capacity alone does not activate a goal. [#381](https://github.com/Jongtae/personal-agentos/issues/381) | This later request enables bounded design documentation, not paid evaluation, background coding or product automation. |
| D-12 | The owner accepted the revised product center: the assistant should increasingly understand the person through permitted context, proactively handle routine parts of delegated life/work, and reduce repeated explaining, deciding, relaying and checking rather than becoming a passive “safe chatbot.” Source: the follow-up design discussion consolidated in [#383](https://github.com/Jongtae/personal-agentos/issues/383#issuecomment-5748808831). | Proactivity stays bounded by source/scope/action authority; this does not authorize a specific algorithm, connector or hidden background service. PA-P1–PA-P6; REQ-23–REQ-27. |
| D-13 | The owner explicitly asked that this thinking become durable principles so implementation, evolution and maintenance preserve the product's intent. [Owner direction](https://github.com/Jongtae/personal-agentos/issues/383#issuecomment-5748808831) | Product promises should have constancy; mechanisms remain replaceable. Canonical constitution adoption and the current single-owner invariant require a separate governance/adoption change. PA-P1–PA-P7; REQ-28–REQ-29. |

Repository-sourced companion direction: [#382](https://github.com/Jongtae/personal-agentos/issues/382) makes Telegram the default conversation surface and local web a management utility. Treat it as that issue's successor plan, not a change implemented by these documents. Preserve current APIs/history; do not launch a second chat-client redesign.

## Proposed architecture decisions

### P-01 — add bounded continuing responsibilities, not inferred blanket autonomy

**Status:** Assistant proposal. **Motivation:** The system needs a reason it is allowed to prepare before a request. A observed routine can be relevant evidence but is not consent.

Propose a responsibility mandate referencing owner outcome, relationship scope, permitted sources, event windows, preparation, notification/action policies and budgets. Present friendly task presets; retain precise enforcement internally. Reactive requests still work without setup. Map onto existing Grant/Event/Work rather than a second authority store.

**Alternative not chosen for this candidate:** automatically convert detected habits or external profile facts into unattended tasks. **Open:** exact presets, confirmation, expiry, migration of per-request consent. **References:** REQ-06, S-00/S-01/S-07.

### P-02 — preparation uses the same bounded Work boundary as other execution

**Status:** Assistant proposal. **Motivation:** Even a silent search can disclose information or consume money; a saved draft or shared-list edit has effects.

Move capability/model-backed Prepare inside bounded Work; maintain preparation artifacts with input revisions, source validity, unknowns and next actions. Interaction is a separate policy, not a necessary stage on the road to action. Cheap deterministic filtering need not create a Work per comparison.

**Alternative not chosen:** an unmetered background LLM outside normal grants/receipts. **Open:** smallest persistence representation and cancellation integration. **References:** REQ-09–REQ-11, S-01/S-11/S-12.

### P-03 — relationship-scoped Attention with a per-person interaction coordinator

**Status:** Assistant proposal. Attention tracks possible outcomes, relevance, time window, evidence and next allowed steps. Salience/anticipation are features, not compulsory model calls. Candidates can resolve, expire, be dismissed or deferred without a notification.

Each scope is evaluated separately. A local coordinator uses only authorized minimal metadata to avoid conflicting interruptions across a person's responsibilities. It does not become a global prompt containing private family/company/school data. Meaningful-change and notification budgets prevent peer urgency from becoming user spam.

**Alternative not chosen:** one global context/attention feed or one unsolicited message per AI thought. **Open:** state model, urgency exceptions, caps and ranking calibration. **References:** REQ-03, REQ-07, REQ-08, REQ-11, S-07–S-09.

### P-04 — typed source authority and causal reconciliation

**Status:** Assistant proposal building on D-07. Separate requester intent, recipient commitment, joint accepted terms, external observations and derived interpretations. A source-controlled causal revision may supersede its previous value; arrival time or a newer summary cannot. Fulfillment persists when intent changes. Concurrent edits and incompatible commitments need reconciliation.

Validate current authority/terms and commit action intent atomically within the local controlled state. A remote effect remains separately reconciled; no blanket exactly-once or automatic undo promise.

**Alternative not chosen:** merge all statements with an LLM or use last-write-wins for every field. **Open:** conflict ownership, delegated editors, version strategy and effect-specific offline freshness. **References:** REQ-05, REQ-15–REQ-17, S-04/S-05/S-12.

### P-05 — explicit onboarding and narrow optional external sources

**Status:** Assistant proposal building on D-04/D-10. Start from user requests and permissioned conversation, then offer minimal useful responsibilities. Do not search by email/phone to create a dossier or infer relationships. An optional owner-selected public source remains an observation with attribution/uncertainty, not automatically Memory or a goal.

**Alternative not chosen:** make an impressive public-profile cold-start the success criterion. **Open:** first-week experience, source addition and provenance UX. **References:** REQ-01, REQ-04, S-00/S-10.

### P-06 — budgeted event-driven execution and phased release

**Status:** Assistant proposal. Use typed events and bounded scheduled evaluation, avoid always-thinking agent loops, reserve foreground capacity and stop speculative retries when quota fails. Start with scoped reactive context, synthetic Attention replay, one preparation responsibility and then two local members; independently validate external peers/merchant mutations later.

**Alternative not chosen:** b3os runtime dependency, global vector memory, mandatory BDI engine, simultaneous household federation and shopping launch. **Open:** exact resource limits and evidence-based promotion thresholds. **References:** REQ-18–REQ-22, S-06/S-11/S-13.

### P-07 — use enduring product principles as a spec/evaluation gate, not as a frozen implementation

**Status:** Assistant proposal implementing D-13 in this candidate. **Motivation:** A sequence of individually reasonable features can drift into a product that is safe but passive, proactive but intrusive, or technically correct while increasing owner work. The product needs a stable layer above mechanisms.

Propose PA-P1–PA-P7 in the experience document as the candidate personal-assistant product constitution. Future assistant-facing specs and PRs identify the affected principles and show scenario evidence for useful allowed behavior as well as contained unauthorized behavior. Evaluation includes repeated explanation, unnecessary questions, manual relay/checking, interruption burden and correction effort—not merely tool-call success or notification counts.

Attention, mandates, BDI vocabulary, A2A, ranking functions, storage tables, UI layouts and model providers remain replaceable. Replacing a mechanism is welcome when it preserves or improves the principles. Weakening a principle or changing multi-principal ownership semantics requires an explicit adoption/governance decision and migration impact review rather than an incidental feature PR.

**Alternative not chosen:** freeze the current Attention architecture as the permanent product identity, or rely on general development/security rules without an assistant-experience invariant. **Open:** final constitutional wording, governance location and adoption timing. **References:** PA-P1–PA-P7, REQ-23–REQ-29, S-14.

## Supersession and clarification table

| Earlier shorthand | Current qualified meaning | Source |
| --- | --- | --- |
| “One assistant voice” | One coherent assistant experience **per person**, not one identity for a family | D-05/D-06 |
| “Personal / household shared” is sufficient | Household is one relationship; company/school/work scopes also matter | D-06 |
| “Privacy can be lower priority” | Advanced controls may wait; identity/scope/account ownership cannot be removed | D-06 |
| Only generic A/B/region examples may be recorded | Preserve specifically permitted, decision-relevant owner-provided scene details | D-08 |
| “Requester has priority” | Authority over request intent; not over counterpart consent, money or observed world facts | D-07 + P-04 |
| `Attention -> Prepare -> Interrupt -> Act` | A policy-controlled choice loop; some preparation uses Work, some work needs no interruption, some candidates cause no work | P-02/P-03 |
| Earlier stages need little/no permission | Observation, inference inputs, network reads and preparation also need applicable data/compute authority | P-01/P-02 |
| “Sunday 10:30 is salience” | Clock time is an observation; task relevance is evaluated from it | P-03 |
| Useful public-profile research is the default | Optional scoped source; no-profile/no-connector usefulness is required | D-10/P-05 |
| “BDI should be run” | Research analogy only; no BDI runtime selected or launched | P-06 |
| “Only explicitly delegated work may be proactive” | Reactive help remains available without setup; repeated burdens may trigger a bounded proposal to take responsibility, but unattended preparation/action begins only after covering authority | D-12 + P-01/P-07 |
| “The safest assistant asks whenever a decision appears” | Within accepted responsibility the assistant resolves routine sub-decisions using current evidence and allowed retrieval; it asks for genuinely new user judgment, counterpart commitment or authority | D-12 + PA-P3 |
| “Silence is a successful attention policy” | Silence can be correct for routine progress, but failing to surface a credible deadline/failure exception can violate the assigned outcome | D-12 + PA-P4 |
| “Attention is the permanent architecture” | Attention is a current mechanism/candidate contract; PA-P1–PA-P7 are the intended durable product promises | D-13 + P-07 |
| #381 says no branch solely because it exists | The owner's later explicit design request scopes documentation branch/PR in #383; implementation hold unchanged | D-11 / #383 |

The current canonical single-owner architecture and v0.1 schemas are **not superseded** by these proposal documents. A later explicit adoption/migration must identify exact clauses/versions changed and retain existing behavior. Neither doc length nor a merged proposal proves a runtime property.

## Candidate product-principle status

PA-P1–PA-P7 are now the v0.3 candidate's top-level assistant principles. They are stronger than ordinary design suggestions in this planning branch because D-13 explicitly asks for product constancy, but they are **not yet canonical repository constitution clauses**. The current canonical development constitution and single-owner architecture remain in force until a dedicated adoption issue analyzes conflicts, migration and evidence and receives the required review/owner approval.

This distinction is intentional: implementers should use the principles to evaluate this candidate and future proposals, while no document in this branch may silently mutate shipped ownership or authority semantics.

## Research provenance and limitations

See R1–R7 in the [experience document](personal-assistant-experience.en.md#references) for primary reference links and the attributed usage essay.

Mixed-initiative interfaces and attention-sensitive/deferrable notification have prior research; our use of the word Attention is not novel terminology or a packaged component. BDI supplies a distinct deliberation vocabulary. PROV supplies provenance vocabulary. HTTP conditional requests suggest lost-update controls. A2A supplies interoperability/task mechanisms with implementation-defined authorization. None automatically provides this project's consent, isolation, truth ordering or product usefulness.

The Instinct essay is a user's account and interpretation. Treat advance preparation as product inspiration; do not infer implementation internals, universal usability, current safety/reliability, actual integration availability or valuation facts. The owner's concern about limited public traces motivates explicit cold-start tests, not a categorical claim that public data can never help an ordinary user.

## Decision ownership, open work and evidence status

The owner chooses product priorities and acceptable behavior. Implementers/reviewers resolve technical choices within an adopted scope; they cannot convert model suggestions into owner consent. Relationship counterpart/account owners retain their own action authority.

Before adoption, resolve the open questions in experience section 13, identify which scenarios define the first useful slice, version the requirement/scenario baseline and choose a review/validation strategy. Further conversation can refine one scene without creating another execution issue or overwriting confirmed facts.

**Performed in this documentation work:** current GitHub discussion/architecture and named source seams were read; selected external reference pages were consulted; this design candidate was written. Reference inspection is not full academic-paper reproduction or a security review.

**Not performed:** runtime implementation, migration, new behavioral tests, model-quality benchmark, live Telegram/merchant/peer operation, independent design/authority review, BDI research-session delegation, provider/account configuration or automation activation. Repository PR CI, if it runs, has its own separately observed status and is not evidence for the proposed features.

This ledger will be amended with decision dates, affected IDs and explicit replacement relations. Ongoing personal scene data is not automatically added to runtime memory, sent to a third party or published merely because earlier supplied details were approved for documentation.
