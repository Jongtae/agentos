# Supplied Skills and Reusable Execution — Implementation Preparation

**Programme:** [SKILL-SUPPLY-01 #959](https://github.com/Jongtae/agentos/issues/959)  
**Date:** 2026-10-01  
**Status:** preparation proposal; runtime implementation is not activated  
**Inspected baseline:** `4e518550b13e13c3cd06cdf05987948ac8169fca`  
**Owner companion:** [Korean discussion and decisions](research/skill-supply-and-execution-2026-10-01.ko.md)

**Owner follow-up:** [Section 18](#18-owner-follow-up-interface-first-change-and-bounded-verification) makes interface-first design, preservation of existing behavior and bounded verification explicit. It governs migration and verification sequencing throughout this preparation; it does not activate runtime work.

## 1. Purpose and authority

The owner requested that the discussion about reusable agents, system-management skills and externally supplied skills become documentation and implementation-preparation issues. This document is the canonical English preparation specification for that request, not an amendment to the active runtime contract.

Documentation and issue preparation are authorized. Installing packages, running account mutations, changing AI routes, executing paid evaluations, deploying software and changing `delivery-plan.yaml` are not authorized by this document. Existing GitHub issues/PRs/checks remain execution-status authority; the existing delivery plan remains active-goal authority. No parallel plan engine or status database is introduced.

Sections marked **Baseline** report inspected code. **Owner direction** preserves the discussion. Other requirements are **proposed implementation contracts**, to be reconciled and activated in bounded issues. External documentation establishes published interfaces, not tested AgentOS compatibility. No live model, external cart or family runtime was exercised for this preparation.

## 2. Owner direction: supply first

The product must not require every user to rediscover how a site works through failed attempts. Someone else may have already developed a useful skill; the service provider may distribute one officially. AgentOS should use that supplied expertise before attempting to invent its own.

**Supply first, adapt second, learn only the missing parts.**

The desired outcomes are:

- Useful first use: an appropriate supplied skill can work without a user-specific history of failures.
- Reuse: repeated tasks reuse methods instead of reconstructing the same instructions and delegation briefs.
- Componentization: shopping knowledge, site knowledge and AgentOS management knowledge have explicit reusable boundaries.
- One assistant: the owner talks to the same personal assistant despite different skills and execution models.
- Portability: changing a supported Main AI route does not discard supplied know-how or the identity of an unfinished task.
- Trustworthy results: reusable methods do not replace current observations or current authority.

A large marketplace, a swarm of agents and automatic skill learning are not prerequisites. Frontier positioning is a hypothesis about measurable first-use utility, portability and repeat efficiency, not a claim of novelty from supporting skills.

## 3. Baseline: existing seams and actual gaps

All source links below are pinned to the inspected baseline. Recheck them at activation.

| Seam | Baseline observation | Proposed treatment |
| --- | --- | --- |
| [`manifests.py`](https://github.com/Jongtae/agentos/blob/4e518550b13e13c3cd06cdf05987948ac8169fca/src/personal_agent/manifests.py) | Version-1 manifests declare roles/instructions/tools. Tools map to existing `HOST_ACTIONS`; built-in roles are researcher, reviewer and planner. | Extend the existing package representation with skill references and explicit compatibility metadata. Do not invent a second tool registry. |
| [`plugins.py`](https://github.com/Jongtae/agentos/blob/4e518550b13e13c3cd06cdf05987948ac8169fca/src/personal_agent/plugins.py) | `PluginRegistry` stores validated JSON declarations; its current install writes `enabled=True`. It does not execute arbitrary package code. | Distinguish the current local declaration lifecycle from the proposed external acquisition/staging lifecycle. Do not claim staging already exists. |
| [`agent_runtime.py`](https://github.com/Jongtae/agentos/blob/4e518550b13e13c3cd06cdf05987948ac8169fca/src/personal_agent/agent_runtime.py) | Module-level `action_definitions`, `Capabilities` and route-neutral guidance expose tools. `delegate_agent` creates a read-only child without browser/settings handlers, shares the Work budget and returns a report. | Prefer same-agent skill loading. Action-capable specialists require separate wiring and authority design; changing a role manifest alone is insufficient. |
| [`settings_orchestrator.py`](https://github.com/Jongtae/agentos/blob/4e518550b13e13c3cd06cdf05987948ac8169fca/src/personal_agent/settings_orchestrator.py) | Authoritative services expose settings and family operations, including draft/apply/recovery behavior. | Management skills use existing reads/setters. Reconcile later owner-directed behavior rather than reimplementing control state. |
| [`browser_session.py`](https://github.com/Jongtae/agentos/blob/4e518550b13e13c3cd06cdf05987948ac8169fca/src/personal_agent/browser_session.py) | macOS WebKit sessions, mediated observations, payment checks, limits and stateful browser actions already exist. | Reuse them; supplied skills cannot install another browser or bypass the session broker. |
| [`family_share.py`](https://github.com/Jongtae/agentos/blob/4e518550b13e13c3cd06cdf05987948ac8169fca/src/personal_agent/family_share.py) | Per-site cookies are pushed between same-Mac instances; receiving AgentOS enforces payment refusal and revocation can remain pending. | Preserve this boundary. It is not a provider-issued cart-only credential and not evidence of cross-vendor A2A support. |
| [`shopping.json`](https://github.com/Jongtae/agentos/blob/4e518550b13e13c3cd06cdf05987948ac8169fca/evals/scenarios/shopping.json) | The two scenarios concern comparison and follow-up constraints, not cart mutation or supplied-skill first use. | Keep them and extend the existing evaluation harness with the missing cases. |

The missing connection is between reusable, distributed methods and the current execution/evidence paths. Core tool availability is not the same as supplied-skill execution support.

### Historical and concurrent work

[#343](https://github.com/Jongtae/agentos/issues/343) was checked as closed with `state_reason=not_planned`. Its ecosystem-import contract is prior art, not an active implementation queue. Do not reopen or rewrite it merely to attach this proposal. The [distribution foundation](agent-distribution-platform-foundation.en.md) and #333/#334 remain reusable historical contracts, not a requirement to revive their entire programme.

[#548](https://github.com/Jongtae/agentos/issues/548) concerns development-only skills; files under `.claude/skills` are not proof of product runtime support. [#661](https://github.com/Jongtae/agentos/issues/661) already owns family A2A; this plan does not duplicate it. [#918](https://github.com/Jongtae/agentos/issues/918) records owner-typed settings/family apply-notice-undo direction. Its actual merged implementation must be reconciled before management work; do not restore blanket confirmation from older text. Existing name/session/browser blocker fixes remain separate dependencies where applicable.

## 4. Existing Solutions Review: Adopt / Adapt before Build

The sources in section 16 were checked on 2026-10-01. These findings concern documented interfaces, not an AgentOS installation test.

| Need | Public option | Preparation decision |
| --- | --- | --- |
| Portable method representation | Agent Skills: `SKILL.md` with optional resources; compatibility metadata; experimental `allowed-tools` [E1] | **Adopt** the supported representation. Treat tool declarations as metadata, not grants. Keep AgentOS execution extensions distinct. |
| Skill loading and resource supply | Microsoft Agent Framework `SkillsProvider`, public source/provider interfaces [E2] | **Evaluate for Adapt** behind current routes; prove independent use and dependency fit before selection. No whole-framework replacement. |
| Multi-source supply | Hermes Skills Hub and skills.sh [E6, E7] | **Evaluate for Adapt** discovery/source conventions, pinning and lifecycle mechanics rather than build a catalogue network from scratch. |
| OpenAI, Claude and Google packages | OpenAI plugin packaging, Claude marketplace catalogues, Gemini CLI extensions [E3–E5] | Inspect legally available source and format. Import only a supported subset; never assume platform installations or account grants are portable. |
| Tool discovery | MCP Registry [E8] | Treat as tool-server metadata, not skill content or authorization. Connecting new servers is outside the instruction-only first slice. |
| Reference validation | `skills-ref` [E9] | Its README says demonstration code, not production-ready. Use as a format/reference candidate, not an unexamined production dependency. |

Public market, provider-authored package, compatible package and behaviorally verified package are separate attributes. No official Emart/SSG skill is established by this review. A directory may contain only hosted agents, proprietary packages or unsupported scripts; catalogue presence proves neither download rights nor compatibility.

[#960](https://github.com/Jongtae/agentos/issues/960) must select exact library/source revisions and licences, inspect release/maintenance activity, dependency footprint, execution behavior and redistribution terms, and run a small model-free compatibility spike. There is no selected dependency version in this preparation. Existing stdlib/path/hash/JSON facilities and repository serializers should be reused for the narrow AgentOS glue; choose an established safe frontmatter/schema parser where suitable. Build requires a documented unmet contract, not preference for fewer dependencies.

## 5. Vocabulary and proposed composition

| Component | Responsibility | Separate model execution? |
| --- | --- | --- |
| Personal Assistant | Owner intent, continuity, current constraints and final voice | Existing main execution |
| Skill | Reusable instructions, references, examples and required observations | No |
| Specialist Agent | Independent bounded reasoning/execution when justified | Optional |
| Capability | Actual browser, settings, file, calendar or connector operation | No new model implied |
| AgentPackage | Versioned distribution/compatibility/lifecycle unit | No |
| Kernel/services | Current state, sessions, authority, effect records and recovery | Not a semantic omniscient verifier |

```text
Owner request, preserved verbatim
  -> existing assistant/orchestration
       <- optional skill knowledge through the supply/loading boundary
          agentos-management | shopping + site know-how
  -> existing AgentOS capabilities and service setters
  -> observed results + existing Work outcome contract
  -> one assistant response

Only on an actual capability gap:
  bounded supply discovery -> compatibility -> pinned acquisition -> permitted use
```

This is a responsibility diagram, not a mandate for new classes, stores or model calls. Shopping and site knowledge can load into the same existing execution. A domain skill plus a site skill must not automatically become two nested LLMs. General exploration remains available when a compatible recipe is absent or stale. The optional knowledge branch is not a mandatory execution gateway; section 18 specifies the no-skill path.

## 6. C16 reconciliation — proposed, not yet amended

**Superseded:** [#974](https://github.com/Jongtae/agentos/issues/974) amended C16 on 2026-10-02 (constitution C16 and AGENTS.md). The rest of this section is kept as the original proposal.

Current [AGENTS.md](../AGENTS.md) prohibits task-named guidance as well as site/provider/category code branches. Therefore, saying that a site skill already complies without qualification would be inaccurate.

Proposed amendment for #960:

> Core runtime must not contain hidden execution branches for a particular owner utterance, site or product. Domain and site know-how may be distributed as explicit, inspectable, versioned Skill/AgentPackage content. The owner's AI selects and uses that knowledge through the same host capabilities and Work/authority/evidence paths. Skill instructions cannot grant authority or certify an unobserved effect.

Update the canonical constitution and relevant instructions/tests together only when that amendment is activated. Preserve tests against hidden scenario logic. Moving an Emart-specific Python workflow into another core module is not a fix. Site hints/selectors in packages may be useful, but current targets must be verified and stale hints must permit rediscovery. Deterministic host code still implements service state transitions; putting setup/revocation logic into prompts would not simplify the kernel.

## 7. Supply and compatibility contract

### R1 — supply before user-specific learning

A supported first-use path must work from an already supplied package, not require a failed trajectory or user-authored instructions. Bundled management knowledge and a genuinely external instruction/resource package are both required demonstrations; they prove different things. A locally authored Emart reference does not prove foreign-package import.

### R2 — bounded discovery, persistent reuse

Offer installed/bundled eligible skill descriptions first. Discover outside sources only for a real gap, an explicit request or a documented update/repair policy. The AI judges semantic fit; deterministic validation checks source/format/environment and actual authority. Do not encode a new phrase-to-site router.

An official service package is a useful candidate, not an unconditional winner. Inspect provenance, supported actions, compatibility and available authority. Catalogue queries use minimal capability metadata, not raw owner conversations or account contents. Use only supported/public source interfaces. No scraping of closed stores, silent purchase or automatic execution of installation commands.

Once accepted, reuse exact content. Provider outage must not break an installed compatible skill. Negative discovery results may have bounded expiry. Initial MVP supports bundled packages plus one external source selected by #960; it does not promise every marketplace adapter.

### R3 — three distinct integration modes

1. **Import a skill:** bring instructions/resources into the existing worker context.
2. **Connect a tool:** configure an MCP/API capability with its own current connection and authorization.
3. **Delegate a task:** send bounded work to another agent under a separate peer contract, such as #661.

The first implementation handles mode 1 over existing tools. Metadata can report a mode-2/3 requirement without pretending to satisfy it. A fresh empty cart exposed by a provider API is not automatically the user's existing signed-in cart.

### R4 — explicit compatibility and identity

At minimum record publisher/source identity, upstream package/name, source URI, immutable revision, content digest, licence, local adaptation revision, supported environment, required capabilities and unsupported features. A hash proves content identity, not publisher ownership, safety or task quality.

An instruction/resource-only subset is the default. Scripts, hooks, shell commands, binaries, foreign auto-install behavior and new runtime servers remain unsupported until separately reviewed. If a script is essential, removing it must not produce a false compatible status. Unknown licence or unverifiable source stays explicit.

A logical package layout may be:

```text
existing AgentPackage
  manifest / AgentOS execution binding
  skills/<name>/SKILL.md
  skills/<name>/references/...
  provenance and compatibility metadata
  package-specific acceptance fixtures
```

This is not accepted input to today's version-1 manifest validator. Exact field mapping/migration belongs to #960/#961. Agent Skills frontmatter remains standard; AgentOS-specific input/output and evidence requirements are explicit extensions, not advertised as part of that standard.

## 8. Loading, execution and lifecycle contract

### R5 — one content source across routes

Metadata is advertised within a bounded context budget. Load only the selected skill and necessary references. Use the same AgentOS-owned revision through direct API and supported trusted-local Codex/Claude bridge paths. Do not depend solely on a development `.claude` directory or let a CLI silently discover an unreviewed version elsewhere.

Reuse module-level `action_definitions`, `Capabilities`, existing context construction and broker serialization. Source-specific tool names need an explicit supported mapping; do not silently reinterpret an incompatible browser or shell tool. Strict-isolated paths retain their existing limits. Unsupported routes explain the actual missing capability.

Original owner intent and constraints remain authoritative. Selection/loading must not narrow a compound request or elevate external page text into trusted skill updates. Normal skill loading does not require another planner, specialist or outcome judge call. Existing Work budgets cover loading and execution; discovery/update budgets must be bounded and attributable too.

### R6 — lifecycle is not authority

Proposed external-content lifecycle:

`candidate -> inspected/pinned -> staged/validated -> installed -> enabled -> connected where needed -> authorized use`

Those distinctions need not all become new persistent enum states. Extend the existing lifecycle only as required. Installation never creates account authority. A trusted, enabled instruction read needs no new prompt on each task. First acquisition and materially expanded execution authority follow an explicit owner/package policy; this proposal does not authorize arbitrary automatic marketplace installs.

Stage exact bytes and validate before replacing an enabled package. Resource access stays inside the pinned root; test path traversal, escaping symlinks, oversized content and ID collisions. Pin the skill version for the Work. Update failure retains a usable prior revision where supported. No mid-Work silent version swap. Rollback restores content, not revoked grants or external state.

Disabling only the loader is insufficient once instructions are in a model context. Bind loaded-skill provenance to the Work and subsequent capability calls through the existing broker. Disable/remove/revoke must block further package-scoped use; terminate or rebuild affected context without silently retrying effects. Whether the owner later runs an equivalent goal with a different permitted method is a new authorized selection, not stale-skill continuation.

Removal preserves owner Memory, Artifacts and retained execution evidence according to existing policies. In-flight effects may remain unknown and need reconciliation. No promise to undo a remote action or erase a model's already transmitted context.

### R7 — current authority remains in host services

Effective authority is no greater than the current Work authority, current account/connection permissions, route limits and package binding. `allowed-tools` and model effect labels do not mint permission. Passwords, cookies, tokens and approval secrets stay with current host services. Do not distribute personal session state as a skill asset.

Retain folder scope, payment boundaries, memory ownership, stop and no-blind-replay behavior. Do not revive unrelated per-query sensitivity gates under the label of skill support. New package/source trust boundaries need a scoped review; ordinary permitted skill reads should remain unobtrusive.

## 9. Observed-result and continuation contract

### R8 — reuse methods, re-read facts

Methods and stable hints may persist. Prices, stock, sign-in, cart contents, selected runtime readiness and sharing authority are current facts. Do not cache their old values as completion evidence. Maintain separate meanings for owner Memory, package know-how and unfinished Work state, preferably using existing storage seams rather than new databases.

A conceptual request binding contains the original goal, account/assistant reference, constraints, intended state change and captured skill/runtime revisions. A conceptual result contains the existing outcome classification, attributable observation references, completed/remaining obligations, failed/unknown effects and a continuation reference when applicable. These are mappings to existing Work fields, not a new orchestration schema requirement.

The current runtime's `finish`, `check_claim` and `goal_judgment` already separate referenced observations from a model claim. Preserve this distinction. A specialist's `{cart_present: true}` is model output until tied to an actual observation. Kernel checks can establish reference validity, state and permission; semantic product matching may still require a model judgment. Reuse the existing judgment path, rather than add one verifier agent per component.

### R9 — reconcile before replay

Read-before/write/read-after can help establish a requested change, but does not guarantee exactly-once effects on arbitrary websites. Use provider idempotency only when actually supported. After timeout/restart/unknown response, inspect present state before reissuing a mutation. If another actor changed the shared cart or causal attribution is unavailable, preserve unknown/partial instead of claiming success or duplicating the action.

Human login/setup/approval is a continuation state, not permission to create duplicate work. Bind continuation to current owner/assistant/account and request version. Changed intent invalidates stale steps; revoked access invalidates continuation. UI drift falls back to bounded exploration with the same constraints, not blind selector replay.

## 10. Reference slice: AgentOS management

[#962](https://github.com/Jongtae/agentos/issues/962) supplies `agentos-management` through the common contract. It calls existing `settings_read`, `settings_change` and authoritative service setters; it is not another control plane or a privileged System Agent.

| Goal | Required observations | Failure/continuation rules |
| --- | --- | --- |
| Change Main AI | Resolve target instance; enumerate usable choices; distinguish requested, configured, effective, executable and actually observed route | Do not claim a paid smoke test ran. Proposed default: current Work stays on its captured route; later Work uses the new effective route. Reconcile actual current semantics before change. |
| Create family assistant | Instance prepared, setup link ready, member paired, ready-to-use are distinct | Repeated request/restart does not create another instance; expired setup link does not imply a paired assistant is disconnected. |
| Share/revoke site session | Giver/receiver/site identity and delivered/pending/revoking/confirmed state from owning service | Preserve existing sharing scope; unknown delivery is not completion. Do not widen direction or implement A2A in the skill. |

Use stable internal IDs after resolving human-readable names; duplicate names require clarification when needed. Main Agent identity is not the selected Main AI provider. Follow #918's implemented owner-typed apply/notice/undo semantics; preserve required confirmation for inferred changes. Undo means only what the service can actually reverse, not deleting a family member's later work. No arbitrary store edits, credentials or service commands in the skill.

## 11. Reference slice: shopping and site knowledge

[#963](https://github.com/Jongtae/agentos/issues/963) separates shared shopping semantics from site navigation knowledge. Inspect available public/provider packages first. If no suitable Emart package exists, publish an explicitly AgentOS-authored reference; record the missing supplier rather than invent an official package.

Shared shopping knowledge covers product identity, variants, brand/pack/unit constraints, quantity meaning, alternatives allowed by the request, target account and outcome evidence. Site content covers entry points and navigation hints, contextual product controls and how to observe the result. Do not embed browser-engine replacement or per-site Python branches in core.

`Add one more`, `set total to one` and `ensure at least one` are not equivalent. Observe the existing cart and make only the requested change; preserve unrelated items. Check product/variant/quantity and relevant current facts before mutation, then read back the cart. A clicked button is not a finished goal. Do not silently substitute a product, account or site.

A changed label/button order or stale selector triggers rediscovery through existing tools. Browser visibility/transport defects remain generic capability bugs; a skill cannot compensate for an unreachable control by claiming completion. Reuse login continuation, limits, payment enforcement and family restrictions. Account results are explained in the site's signed-in app/website context, not through a misleading link that opens signed out.

A second site fixture must use the same common contract without core edits. It shows local generality, not real-world compatibility with every store. Optional held-out live-site validation is separately authorized.

## 12. Family knowledge, specialists and learning: retained later direction

**R10 — knowledge is not authority.** Family assistants may eventually share public methods without sharing personal preferences, order history or credentials. Current cookie-sharing restrictions remain. Account-owner-side execution of limited delegated tasks is a promising later approach, but belongs to a separately scoped continuation of #661, not this MVP. Cross-agent concurrent effects need account-level observation/coordination; per-instance deduplication alone is not a proof.

**R11 — specialists are optional.** Same-agent skill loading is first. A future action specialist would need scoped tools, host-mediated browser/settings access, shared budgets, cancellation, parent-child observation references and non-duplicating continuation. Existing read-only delegation does not already provide that. Adopt an existing agents-as-tools pattern only after a measured need; one assistant keeps the owner-facing voice.

**R12 — learning fills gaps, not the catalogue.** A future improvement path may derive a candidate method from redacted execution evidence, record its preconditions and failure cases, evaluate it against independent fixtures, and publish a reviewed new version. One successful trace cannot self-promote to a trusted skill. Never publish owner history/secrets in a learned package. Track upstream revisions and local adaptations separately; decide whether to contribute generic fixes upstream. Validated replay/compilation remains an experiment, not a first-slice requirement or replacement for current-state checks.

## 13. Acceptance and measurement

[#964](https://github.com/Jongtae/agentos/issues/964) adapts the current evaluation harness. Freeze A/B conditions before tuning: A is existing AgentOS; B uses supplied skill knowledge with the same supported model/tools; optional future C adds validated learned/replay behavior. A does not receive hidden warm-up knowledge. Reset fixture state so an already-added item is not counted as another completed mutation.

The matrix below is a coverage inventory, not a mandatory live-model sweep for every child or content revision. Section 18 assigns preservation checks from #961 onward and limits verification to changed contracts. #964 consolidates reusable evidence and fills concrete gaps; it is not the first regression gate.

| ID | Acceptance case | Evidence required |
| --- | --- | --- |
| A01 | Fresh user uses supplied expertise without prior failures | Clean-store fixture; supplied package identity and observed result |
| A02 | External package is actually imported | Non-AgentOS-authored upstream package through real source/loader boundary |
| A03 | Repeat reuses methods, not market lookup every time | Source-call trace, pinned version; changing current facts re-observed |
| A04 | Supported API/CLI parity | Scripted direct/Codex/Claude route inputs, version and tool-binding equivalence |
| A05 | Unsupported environment stays explicit | No accidental scripts, hooks, browser or isolation expansion |
| A06 | Main AI change is truthful and continuous | Existing setter/readback and current-versus-next Work tests |
| A07 | Family setup/sharing recover correctly | Repeated create, duplicate names, expired link, pending/revoking fixtures |
| A08 | Product/variant/quantity semantics survive reuse | Existing cart baseline and resulting requested delta |
| A09 | UI drift and wrong account do not cause wrong action | Changed controls/labels and account-mismatch counterexamples |
| A10 | Timeout/restart/concurrency do not imply blind replay | Actual mutation/readback boundary; unresolvable attribution remains unknown |
| A11 | Disable/update/remove after loading are enforced | Broker-level stale-skill call, version pin and rollback tests |
| A12 | Source and resource hazards are bounded | Tampering, unknown licence, traversal, symlink escape, oversized and unsupported content |
| A13 | Another site uses the same contract | Second fixture/package without core edits; live claim remains separate |
| A14 | One voice and low interaction burden | Owner-visible transcript, no extra routine asks or machinery narration |

Measure goal satisfaction from underlying observations, false completions, duplicate/unrequested effects, owner interventions, latency, model/tool calls, available tokens/usage, supplier calls and maintenance changes. Report sample size, exact code/skill revisions, model, environment and evidence class. Missing usage stays unknown.

Amortized cost includes discovery/acquisition/validation, repeated execution, updates and recovery. A subscription route is not zero-cost merely because no per-call API price is visible. Success and truthful uncertainty must not regress to manufacture lower latency.

Normal development uses focused tests, fake source/service transports, temporary stores and model-free bridge integration. No new runtime verifier swarm. Relevant current manifest/plugin/browser/settings/family/recovery regressions and required exact-head CI remain. Opt-in live tests need named sites/accounts, allowed changes, cleanup, sample/usage/time caps and a predeclared decision criterion. Missing live authorization prevents live-quality claims, not ordinary fixture-based development closure.

## 14. Ordered preparation and implementation units

| Order | Issue | Scope | Gate |
| --- | --- | --- | --- |
| 0 | [#959](https://github.com/Jongtae/agentos/issues/959) | This proposal, owner companion and bounded issue preparation | Documentation review; no runtime activation |
| 1 | [#960](https://github.com/Jongtae/agentos/issues/960) | Interface/pattern decision, C16 reconciliation and pinned reuse/compatibility spike | Stable behavioral contracts, bounded change surface and selected APIs/source/licence |
| 2 | [#961](https://github.com/Jongtae/agentos/issues/961) | Optional supplied knowledge, existing lifecycle and API/CLI loading | No-skill/off/miss path preserved; one real external source; focused boundary evidence |
| 3a | [#962](https://github.com/Jongtae/agentos/issues/962) | Built-in management skill | #961; existing setters and #918 behavior preserved |
| 3b | [#963](https://github.com/Jongtae/agentos/issues/963) | Common shopping and site packages | #961; existing browser contract preserved; no common-runtime rewrite |
| 4 | [#964](https://github.com/Jongtae/agentos/issues/964) | Consolidate first-use/repeat/recovery/portability evidence | Reuse child evidence; fill changed-contract gaps; bounded live opt-in separate |

All children are proposed and unassigned, not autonomous queues. Evaluation design may start after #960; results depend on implemented slices. #962/#963 may run in parallel only with separate content/test ownership after shared seams stabilize. Do not add these to an active delivery sequence without explicit bounded activation.

## 15. Non-goals and readiness decisions

No public marketplace launch; no closed-store scraping or bulk auto-install; no arbitrary scripts/hooks/executables; no new browser engine, orchestrator, personal-memory store or permission database; no forced specialist on every task; no payment expansion; no remote family protocol implementation; no auto-promotion of learned methods; no promised universal compatibility or unmeasured superiority.

Before #961 implementation, #960 must decide the pinned loader/parser and dependency versions; initial external supplier; immutable identity and adaptation mapping; exact public-format subset; resource/context/discovery budgets; package acquisition/enable policy; current #918 behavior; and affected API/CLI/profile coverage. These are specific spike outputs, not reasons to invent a large architecture upfront.

For later rollout, choose a staged default package set and rollback behavior with owner feedback. A preinstalled reviewed skill should not burden every user with the same source review. Supplier/provider identity, AgentOS compatibility, tested behavior and current account authority remain separately inspectable.

## 16. Evidence and public references

Repository evidence: pinned source links in section 3; [AGENTS.md baseline](https://github.com/Jongtae/agentos/blob/4e518550b13e13c3cd06cdf05987948ac8169fca/AGENTS.md); [distribution foundation baseline](https://github.com/Jongtae/agentos/blob/4e518550b13e13c3cd06cdf05987948ac8169fca/docs/agent-distribution-platform-foundation.en.md); current issue links in sections 3 and 14. The conversation supplies owner intent, not measurements.

Public primary sources checked 2026-10-01; mutable documentation is a research reference and must be pinned/rechecked before dependency selection:

- **E1:** [Agent Skills specification](https://agentskills.io/specification).
- **E2:** [Microsoft Agent Framework — Agent Skills](https://learn.microsoft.com/en-us/agent-framework/agents/skills).
- **E3:** [OpenAI — Package your plugin](https://developers.openai.com/plugins/build/plugins) and [Build skills](https://developers.openai.com/plugins/build/skills). Platform-specific source/availability differences are not an interoperability guarantee.
- **E4:** [Claude Code — plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces).
- **E5:** [Gemini CLI — extensions](https://geminicli.com/docs/extensions/).
- **E6:** [skills.sh documentation](https://www.skills.sh/docs).
- **E7:** [Hermes Agent — Skills System and Skills Hub](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/).
- **E8:** [MCP Registry overview](https://modelcontextprotocol.io/registry/about).
- **E9:** [Agent Skills reference library README](https://github.com/agentskills/agentskills/tree/main/skills-ref).

Other markets discussed with the owner (Microsoft/Google enterprise agent stores, AWS, Salesforce, ClawHub and additional framework examples) are discovery candidates, not dependencies selected or compatibility tested by this preparation. A product advertised in a marketplace is not evidence that AgentOS may download its implementation or inherit its accounts.

## 17. Preparation completion rule

This preparation is complete when the English specification and Korean companion are reviewable in a docs-only PR, the bounded issues are linked, source/claim distinctions and activation gates are explicit, and documentation validation is reported accurately. Runtime children remain open until separately activated and completed. No runtime behavior, dependency, credential, deployment or active goal is changed by these documents.

## 18. Owner follow-up: interface-first change and bounded verification

**Owner direction, 2026-10-01:** preserve previously working cart and other behavior; do not compensate for a broad redesign with excessive token-consuming tests. Review design patterns to establish stable interfacing first. This section records that direction and the proposed implementation obligations. It refines sections 5, 8 and 13–15 without weakening authority, required CI or truthful evidence requirements. No additional issue or architecture programme is needed.

**Success means existing useful behavior is retained and repeated reasoning is reduced, not merely that a skill system exists.** A skill is optional know-how, not a prerequisite or licence for an existing capability.

### 18.1 Compact design decision inside #960

Produce one short ADR (an in-document decision record is sufficient) and one behavioral interface table before loader implementation. Map selected patterns to existing symbols and record what will not change. Do not redesign the whole repository to fit a pattern catalogue.

| Pattern / principle | Proposed use in AgentOS | Avoid |
| --- | --- | --- |
| Ports & Adapters | Separate the skill-supply port from existing action ports; reuse `PluginRegistry`, `runtime_packages`, `action_definitions` and `Capabilities` as seams | A new service/class for every conceptual box or a second execution framework |
| Adapter / Anti-Corruption Layer | Normalize foreign metadata/resources and explicitly map supported tool semantics at acquisition/binding time | Importing foreign account authority, guessing semantic equivalence or a translator LLM on every call |
| Design by Contract | Define preconditions, postconditions, invariants, side effects and failure/retry semantics at each boundary | Treating matching JSON shapes or a model's success flag as behavioral compatibility |
| Branch by Abstraction | Add optional knowledge behind a narrow seam; keep the original executor and a reversible rollout switch | Two complete runtimes, a big-bang replacement or running two mutations in parallel |

Pattern references from the discussion: [Cockburn — Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture), [Microsoft — Anti-Corruption Layer](https://learn.microsoft.com/en-us/azure/architecture/patterns/anti-corruption-layer), [Eiffel — Design by Contract](https://www.eiffel.com/values/design-by-contract/introduction/), [Fowler — Branch by Abstraction](https://martinfowler.com/bliki/BranchByAbstraction.html). Their AgentOS mapping above is a proposal, not implemented framework adoption. Design by Contract is a principle, not a GoF pattern. A skill document is not automatically an executable Strategy; do not introduce site inheritance trees or specialist chains just for naming consistency.

### 18.2 Behavioral interface contract

For each boundary, #960 names the existing owner/symbol, input meaning, output meaning, permitted side effects, error class, retry/continuation rule, version compatibility and allowed change surface. Reuse existing types and error vocabulary where possible; conceptual names here do not mandate new APIs.

| Boundary | Required promise |
| --- | --- |
| Supply / resource loading | Return bounded descriptors or pinned instructions/resources. Listing/loading never launches a browser, changes settings, installs hooks or mutates an account. Separate missing/incompatible/unavailable knowledge from denied account authority. |
| Knowledge / existing worker | Add only selected, attributable knowledge. Preserve the original request, constraints, account/session binding, current route policy and independently available tools. A content miss is not a capability denial. |
| Worker / host action | Keep argument meanings, current session ownership, authorization, side effects, observations, failure states and cancellation semantics. Additive optional skill provenance cannot require old callers to invent a skill ID or silently reclassify a successful old call. |
| Observation / outcome / resume | Tool transport success is not goal success. Preserve underlying observation references and existing partial/unknown states. Changing methods does not reset effect history or authorize replay. |

A foreign tool binding must preserve semantics, not only its name; incompatible element IDs, browser profiles or quantity meanings are not interchangeable. Exact source/adapter selection remains #960's compatibility output. No new AI call is required merely to translate a supported interface or validate its schema.

### 18.3 R13 — additive adoption and existing-function preservation

- With skill support off, retain the pre-skill request/tool path without skill selection, loader, catalogue or extra model calls as mandatory dependencies. With support on but zero compatible skills, the independently permitted general path remains usable. Existing users need not reinstall skills, re-login, recreate family assistants or reset model settings merely to upgrade.
- A missing/broken/incompatible skill or unavailable supplier must not remove previously available browser/settings/calendar/file capabilities. Handle knowledge failure at its boundary. Do not turn a revoked account grant into a fallback; R6/R7 still apply. If a revoked or untrusted skill was already loaded, stop or rebuild the affected context through existing recovery, preserving the original authorized goal, effect ledger and current authority. A new permitted method is a distinct selection, not stale-skill continuation or a forced repetition of the user's request.
- Do not reimplement `BrowserSession`, settings setters, login, payment, family setup/share/revoke or Work recovery inside skill prompts. Package metadata/provenance integration may touch shared seams, but changes to the behavioral contracts require a separately bounded justification. Adding a supplier should normally change its adapter; adding a site should normally change content/binding and its focused cases, not unrelated services.
- Keep knowledge selection/loading bounded within the existing Work budget so catalogue exploration cannot consume the whole useful-action allowance; choose the concrete limit in #960 rather than adding a second budget service. Do not promise zero total token overhead: loading content can add context and a normal tool round-trip. The design target is no compulsory new planner/specialist/verifier calls and no discovery on every turn.
- Stage rollout with support off first, then explicitly enable selected packages. Keep a rollback switch for knowledge enrichment that preserves sessions, settings, Memory and existing Work/evidence. Do not run old/new account mutations concurrently as a shadow comparison. After any possible mutation, reconcile current state before changing method or retrying; disabling the feature cannot undo a cart change.
- Start from existing fixtures and already available, redacted records of the owner's successful behavior. Record their actual code/model/environment and observation class; the inspected `main` SHA is not automatically a known-good live baseline. Missing live evidence is stated, not manufactured through a mandatory new sweep. Preservation is a #961 gate onward, not deferred to #964; known unresolved regressions prevent promotion of the affected default path, not every unrelated change.

### 18.4 R14 — verification follows the changed contract

Use this plan together with the existing AGENTS.md verification budget. The section-13 matrix remains required coverage for the implemented scope, but it is not an instruction to rerun every case with every live model/site on every patch.

| Change | Smallest appropriate evidence |
| --- | --- |
| Documents / ADR only | Changed-text, link/consistency and diff-scope checks plus required CI; no model or real-account execution |
| New supplier / format adapter | Relevant parser/resource and compatibility contract tests with fake transports; not a whole shopping regression sweep |
| Skill instructions / site hints | Existing content/binding checks and affected representative behavior; a small real-model sample only for a justified, authorized quality question |
| Shared runtime / authority / serializer / resume boundary | Related contract regressions and an actual model-free boundary integration/counterexample; broaden and independently review when the changed risk requires it |

Each implementation PR states changed boundary, reused evidence/tests, the concrete uncovered risk, selected additional check and live-call budget if any. Reuse prior results only when relevant code/content/bindings remain applicable; required exact-head CI still runs. No separate evaluator, self-created full-suite cadence, default all-provider/all-site matrix, duplicate judges, automatic retries until green or repeated reviews of an unchanged head.

Normal development defaults to no paid model calls or real account mutations. Any necessary live sample first declares affected route/cases, call/token-or-cost and time cap, stop condition and allowed effects/cleanup; no automatic expansion after an inconclusive result. Return the uncertainty and a bounded next decision instead. Existing risk-triggered review and mandatory checks are not waived to save tokens.

Model-free tests spend no inference tokens during execution, but AI-authored tests, repeated implementation/review and full log reading still cost tokens. Keep one focused contract suite at existing seams, batch fixes into a stable head, read summaries on success and relevant failing excerpts only. Follow the existing stable-head broad-validation budget rather than adding another round in each child. #964 consolidates child evidence and runs only justified gaps/integration checks; it does not repeat completed work wholesale.

Behavioral compatibility does not prove identical LLM choices. New instructions can still change product selection or response quality; distinguish structural preservation from model-quality evidence. Do not claim unchanged real Emart success or quantified savings solely from schema tests.

### 18.5 Issue-level obligations

- #960: interface/pattern ADR and change-surface table first; then the already scoped dependency/source compatibility spike, with bounded evidence. No additional design-pattern project. Recorded in [SKILL-PREP-01 decision](skill-prep-01-interface-decision.en.md) (2026-10-02).
- #961: implement the optional knowledge seam; check off, empty/missing, source-failure and stale-loaded-skill recovery paths while keeping action semantics. Preservation precedes default activation.
- #962/#963: content and binding changes over stable settings/browser ports; targeted representative checks. Do not rescript the service or retest every unrelated feature because a skill changed.
- #964: own the coverage/evidence map from #960 onward; reuse applicable child results and separate any explicitly budgeted live promotion. It is not the first time existing functions are checked.

This follow-up adds no runtime activation, deployment, live test permission, new public marketplace or new issue. The current C16 amendment remains proposed until its existing bounded activation/review path is followed.
