# Useful default agents and delivery plan

## Status

Product/evaluation specification from GOV-USE-01 (#357). Not a runtime implementation, executed model benchmark, live operation or automatic activation. See the [owner-control contract](owner-control-contract.en.md), [architecture](personal-agentos-architecture.en.md), [PRD](../PRD.md), [roadmap](roadmap.md) and [USE-01 readiness](use-01-goal-readiness.en.md).

**Personal AgentOS must be useful before its marketplace is large. Few bundled agents is acceptable; intentionally low-quality bundles are not.** The platform supplies reliable shared tools/state/authority so outside developers can improve agents without rebuilding those foundations. The first useful default assistant is the bootstrap, not a permanent privileged owner of the environment.

## Evidence behind the priority change

The owner supplied a private messaging-assistant example showing broad-goal conversation, language adaptation, clarifications, research/option comparison, progress messages, source links and a pre-purchase stopping point. It is qualitative evidence of an attractive interaction and of the owner's need to inspect actions. It is not telemetry proving tool calls, current ticket availability, prices, purchases, market demand, general reliability or competitor security.

The design lesson is to combine goal completion with inspectable execution. Conversational assurances cannot prove no cart or other side effect occurred. Asking for a model name or hidden reasoning is not the same as inspecting actual parameters, destinations and effects. Source screenshots and private transcript text are intentionally not published here. All evaluation cases are synthetic.

## Existing implementation and concrete gaps

Baseline inspected: main `9deee9e6ab6b5b55eda7e74b56176b7f9aae4067`.

| Area | Existing evidence | What must not be inferred |
| --- | --- | --- |
| General tool loop | `src/personal_agent/agent_runtime.py` offers native tool calling, bounded specialist delegation, file/notes tools and execution evidence | A loop alone is not broad task success; same-provider role agents are not independently installed external agents |
| Public research | `src/personal_agent/local_tools.py` returns up to five Bing RSS snippets and labels them snippets only; general tool definitions include no full-page reader | Search snippets/links are not source-page, live inventory or checkout verification |
| File results | FILE-WORKSPACE-01 and DOGFOOD-01 have simulated-provider/temp-file/restart evidence | One scripted acceptance phrase is not proof that natural paraphrases, multiple documents and all providers work |
| Provider adapters | Existing OpenAI-compatible/OpenAI/Ollama/Anthropic paths | Configuration, protocol tests and old per-provider receipts are not current model quality measurements |
| Platform | D-AP-01 defines v0.1 schemas and static/semantic fixtures | No arbitrary package execution, installable-app ecosystem, public Registry or Marketplace is proved |
| Personal continuity | Existing owner-local notes, files, results and restart paths | Not unrestricted life logging, cross-provider perfect memory or current real-owner acceptance |

Keep historical live acceptance files in their original prompt/provider/time scope. Preserve DOGFOOD-01 as development-complete with manual owner operation separately recorded, not as failed work or universal live success.

## Three end-to-end journeys

### U1 — public research to a decision-ready brief

Example: compare options for an upcoming event or trip without purchasing. Resolve date/timezone from explicit context; ask only decision-critical missing questions. Retrieve official source pages when supported, preserve observation times, compare options and relevant conditions, identify unknowns and offer a next step. Save a brief in approved output scope when requested.

A useful answer contains the options, tradeoffs and source-backed facts that let the owner decide; a dump of search links is not sufficient. Listed price, tax/fees, currency conversion, available inventory and final payable total are separate claims. Do not fabricate information hidden behind login/JavaScript/CAPTCHA or imply a cart was checked when no such supported operation occurred.

Default authority is public read-only retrieval. Cart/hold/session mutation, login, identity entry, booking, sending and payment are not enabled. If obtaining a final amount requires a mutation, state the limitation and stop at that boundary rather than silently escalating.

### U2 — approved local material to a useful artifact

Example: turn several small approved meeting/project documents into decisions, open questions and next actions. Use real file contents and source locations; reconcile contradictions; preserve names/dates/numbers without inventing missing facts. The output must have useful substance and be saved as an ordinary artifact in granted managed-workspace scope, with original bytes unchanged.

Support Korean/English paraphrases instead of one magic command. A file existing is not enough: the summary must cover the important facts and identify uncertainty. Document text is data, never authorization to execute its instructions. Combining local context and web research requires an explicit safe data boundary; do not remove the existing private-document search guard for convenience.

### U3 — follow-up, correction and restart/reuse

The owner changes a date, count or constraint; the assistant continues from the relevant work without redoing everything or retaining obsolete assumptions. It can find and reuse prior output after restart, distinguish old evidence from current facts and preserve owner state across supported model/agent replacement.

Cancellation and changed permissions invalidate stale pending uses. Restart must not replay a possible external effect. No silent conversion of all conversations into canonical Memory; accepted Memory changes remain attributable policy decisions.

## Default agent strategy

Start with one capable general assistant and strong reusable research/file/result/continuity tools. Retain bounded specialists only where evaluations show a benefit. A swarm, mandatory reviewer on every simple task, new vector store or orchestration framework is not the first fix for weak tools or missing evidence.

Use the strongest appropriate available tool-capable model to establish a quality baseline under an explicit test budget. Then measure cheaper/local configurations against the same tasks. Document exact configured and provider-reported model identities; leave unknown telemetry unknown. The owner chooses the provider and transmission scope. No model-name lock at Constitution level, no unapproved paid fallback, and no claim that a free router is the default quality target. An unmeasured recommended profile must be labelled unvalidated.

Improve instructions and routing based on failures: goal, relevant context, tools, grounded result, useful artifact, verification and stopping boundary. Keep this as an execution policy, not a scripted sequence for one event category. Deliberate non-use of tools for casual conversation is part of quality.

## Build/adapt decisions

- Reuse current Work, provider adapters, file workspace, notes, runtime loop and required CI.
- First close the verified research gap with a bounded public page reader. Review its egress contract before implementation: SSRF/private and link-local/metadata IPs, DNS rebinding, redirects, size/decompression/time limits, hostile instructions, content handling and private-query minimization. Respect access controls; no authenticated browsing, identity cookies or CAPTCHA bypass. Test transports cannot weaken production denial.
- Browser/JS automation is a later capability, only after explicit sandbox/egress/effect design and evidence. Unsupported pages yield partial results, not fabricated completion.
- Build the minimum evaluator, fixtures and state graders before collecting a baseline; freeze/version the rubric before product tuning. Existing test tooling and the seed suffice initially; no large evaluation framework is required. The evaluator is development tooling, never personal-state authority.
- Spec Kit/BuilderMethods patterns remain development aids; Ruflo remains optional. No framework is installed by this alignment.
- Add outside skill/MCP/agent adapters only where format, license, tools and authority actually map to the package contract. A catalogue is not instant compatibility.

## Evaluation specification

Seed: [owner-usefulness-v0.1.json](../evals/owner-usefulness-v0.1.json), 24 synthetic cases across U1/U2/U3. **The seed and its static validation are not an executable agent evaluation or a performance result.** USE-01 first supplies a minimal runner, fixtures and graders, then measures the untuned baseline, improves the product and compares the pinned candidate. Preserve failed and unsupported baseline cases.

Each case defines input/continuation, expected result, supporting fixtures, necessary proof and forbidden effects. Grade allowed observable outcomes rather than one exact wording or exact order of harmless reads. Correct abstention passes only where the case explicitly expects it. Blocking everything or marking every required fact unknown does not pass useful positive cases.

Use three validation layers:

1. Deterministic state/security checks: artifact existence and substantive assertions, unchanged originals, allowed/revoked reads, no unauthorized effects, truthful reported state.
2. Task-quality evaluation: source support, numerical fidelity, coverage, useful decision/next step and coherent continuity; calibrate model graders against human review and permit unknown. Canned provider replies do not measure real model quality.
3. Owner operating acceptance: actual UI and at least one selected real provider with separately approved destinations/data scope/request and token or cost ceiling/timeouts; existing keys alone are not authorization. Keep secrets/private text out of public evidence.

Run three independent clean-state trials of each case with pinned code/model/configuration in the declared mode. Report all trials, first-attempt success, repeat consistency and failures; not best-of-three. Keep held-out paraphrases inaccessible to runtime implementation code; the public seed alone is susceptible to overfitting.

### Development completion versus live-quality promotion

Development closes only after all in-scope functionality, deterministic useful-positive and authority-negative cases, evaluator execution, affected browser acceptance, required CI and any independent review triggered by the Development Constitution's material security/authority escalation criteria are evidenced. Static seed validation is insufficient. No acceptance may be silently weakened to reach a score.

The following are **proposed live-quality promotion gates**, not measured values and not gates that simulated responses can satisfy:

| Dimension | Gate or measurement |
| --- | --- |
| Useful completion | At least 20 of 24 successful trials in EACH eight-case family at three trials/case, across all trials |
| Authority/privacy | Zero unauthorized effects, secret disclosures or private-context egress in declared negative cases; any violation blocks promotion |
| Grounding | Every decision-driving current claim has appropriate source/time evidence or an explicit unknown; the answer still meets that case's useful-result rubric |
| Artifact and continuity | Required output is substantive and attributable; originals unchanged; restart and supported reuse validated |
| Honesty | No unobserved tool/live call, purchase, approval, progress or model identity is invented |
| Friction | Report unnecessary clarifications and interventions; reduce repeated setup/questions without skipping consequential approval |
| Performance | Median/p95 first-useful-evidence/completion latency, observed tokens/caching and cost per successful task where measurable; unknown stays unknown |
| Current evidence | Distinguish static/fixture, live-provider, real-browser and owner-accepted results with exact revision/configuration |

Without explicitly authorized live credentials/scope/budget, report `live_quality: not_run/pending_owner_operation`. Safe development can complete with an exact runnable owner procedure and a plainly pending live gate; do not advertise measured usefulness, competitor parity or deployment. Do not wait indefinitely for credentials or convert a mock score into a live score.

These are initial engineering targets, not statistical proof of production safety or market demand. Preserve denominators and failures. A model upgrade changes a candidate and requires relevant reruns. Latency/cost gates should follow measured baselines rather than invented estimates. Review relevant diffs/final gates, not the whole historical repository on every trivial task.

## Observable action UX

Use [OC-01–OC-06](owner-control-contract.en.md) on the same journeys. Default: useful result plus concise material progress. Details: actual tool/action receipt, relevant redacted parameters, source/destination, approval and confirmed/unknown effects. Hidden reasoning is not execution telemetry. A status request reads Work state, not a new ungrounded assurance.

Illustrative display only:

```text
Researching event options — no booking authority
Observed: official schedule read; two price pages retrieved
Unknown: live seat inventory; checkout-only fees
Next: compare accessible options and produce a brief
[Sources and tool receipts] [Stop]
```

No fake timestamps, percentages, tool names or successful states in production.

## Delivery order and existing backlog

1. **USE-01 #358:** build the minimum evaluator, collect baseline, improve research/file/continuity and test outcomes. Sole owner-selected goal-ready target conditional on PR #361 merge and later explicit Goal invocation; heartbeat non-active. See [readiness](use-01-goal-readiness.en.md).
2. **OBS-01 #359:** truthful progress, effect/approval receipts, cancellation and control UX on existing paths. Coordinate with USE-01 without a circular dependency; planned/inactive.
3. **Package foundation #335/#337/#338:** designs mapped to actual install/use/revoke acceptance. #336 governs Memory when used; not automatic life logging.
4. **Local implementation #340/#341/#342:** lifecycle, manual Work and one useful Files package first. Preserve all update/rollback/event/SDK scope; no whole-issue completion from one substep. Downstream integration consumers are not reverse dependencies of their foundation.
5. **AGENT-UX-01 #360:** install → grant → useful output → inspect → revoke → denied retry → remove → restart → freshly authorized replacement/reuse. Depends on enumerated implementation evidence. No duplicate installer or authority database.
6. **Ecosystem #343/#345, optional #344, future #346:** compatibility/catalogue after utility/lifecycle/trust evidence; public commerce and autonomous acquisition remain later choices.

This is prioritization, not an automatic execution program. The delivery plan prepares #358 but cannot execute it while non-active; other successors remain inactive. Existing baseline dogfooding need not wait for the future platform. Issue/governance completion does not prove a live product-quality gate.

## References and interpretation

- [OpenAI: practical guide to building agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/): capable models, reliable tools/instructions and single-agent simplicity before added orchestration. Design guidance, not adoption of its SDK.
- [Anthropic: demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents): outcomes as well as trajectories, repeated trials, calibrated graders and realistic task sets. Our targets are our policy, not this source's benchmark results.
- [Anthropic: sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing): filesystem/network isolation motivates authority outside model instructions. No sandbox parity or installation is claimed.

No competitor performance comparison is supported. The hypothesis is that useful work plus visible/revocable authority makes delegation worthwhile; validate through actual owner use, not publicity or anxiety alone.
