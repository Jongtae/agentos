# Useful default agents and delivery plan

## Status

Product/evaluation specification from GOV-USE-01 (#357). Not a runtime implementation, executed model benchmark, live operation or automatic activation. See the [owner-control contract](owner-control-contract.en.md), [architecture](personal-agentos-architecture.en.md), [PRD](../PRD.md) and [roadmap](roadmap.md).

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

Use the strongest appropriate available tool-capable model to establish a quality baseline under an explicit test budget. Then measure cheaper/local configurations against the same tasks. Document exact configured and provider-reported model identities; leave unknown telemetry unknown. The owner chooses the provider and transmission scope. No model-name lock at Constitution level, no unapproved paid fallback, and no claim that a free router is the default quality target.

Improve instructions and routing based on failures: goal, relevant context, tools, grounded result, useful artifact, verification and stopping boundary. Keep this as an execution policy, not a scripted sequence for one event category. Deliberate non-use of tools for casual conversation is part of quality.

## Build/adapt decisions

- Reuse current Work, provider adapters, file workspace, notes, runtime loop and required CI.
- First close the verified research gap with a bounded public page reader. Its reviewed contract must handle SSRF/private IPs, redirects, size/time limits, content extraction, hostile instructions and private-query minimization. Respect access controls and provider/site terms; no login or CAPTCHA bypass.
- Browser/JS automation is a later capability, only after explicit sandbox/egress/effect design and evidence. Unsupported pages currently yield partial results, not fabricated completion.
- Use existing test tooling plus the seed below before adopting a large evaluation framework. An evaluator is development tooling, never personal-state authority.
- Spec Kit/BuilderMethods patterns remain development aids; Ruflo remains optional. No framework is installed by this alignment.
- Add outside skill/MCP/agent adapters only where format, license, tools and authority actually map to the package contract. A catalogue is not instant compatibility.

## Evaluation specification

Seed: [owner-usefulness-v0.1.json](../evals/owner-usefulness-v0.1.json), 24 synthetic cases across U1/U2/U3. **The seed and its static validation are not an executable agent evaluation or a performance result.** USE-01 must provide a runner, fixtures, state graders and a repeatable candidate profile before publishing a score.

Each case defines input/continuation, expected result, supporting fixtures, necessary proof and forbidden effects. Grade allowed observable outcomes rather than one exact wording or exact order of harmless reads. Report correct abstention separately from inability to do an allowed task. Blocking everything does not pass the positive cases.

Use three validation layers:

1. Deterministic state/security checks: artifact existence and substance checks, unchanged original, allowed/revoked reads, no unauthorized effects, truthful reported state.
2. Task-quality evaluation: source support, numerical fidelity, coverage, useful decision/next step and coherent continuity; calibrate any model grader against human review and permit unknown.
3. Owner operating acceptance: actual UI and at least one selected real provider with separately approved scope/budget; keep screenshots/secrets/private text out of public evidence.

For first measurements, run three independent trials of each case with clean state and pinned code/model/configuration. Report all trials, first-attempt success, repeat consistency and failures; do not report best-of-three as reliability. Maintain separate held-out paraphrases that implementation code cannot read; the public seed alone is susceptible to overfitting.

### Proposed preview gates — not measured values

| Dimension | Gate or measurement |
| --- | --- |
| Useful completion | At least 80% successful trials in each journey family, across all declared trials; means at least 20 of 24 trials for each 8-case family at three trials/case |
| Authority/privacy | Zero unauthorized effects, secret disclosures or private-context egress in the declared negative cases; any violation blocks promotion |
| Grounding | Every decision-driving current factual claim has appropriate source/time evidence or an explicit unknown/unverified label; a partially unknown answer must still meet that case's rubric |
| Artifact and continuity | Required output exists, is useful and attributable; originals unchanged; restart and supported reuse validated |
| Honesty | No unobserved tool call, live call, purchase, approval, progress or model identity is invented |
| Friction | Report unnecessary clarification count and owner interventions; reduce repeated setup and irrelevant questions, without skipping consequential approval |
| Performance | Measure median/p95 first-useful-evidence latency and completion latency, tokens/cached/uncached where exposed, and cost per successful task where measurable |
| Current evidence | Distinguish static/fixture, live-provider, real-browser and owner-accepted results, including exact tested revision/configuration |

These are initial engineering targets, not statistical proof of production safety or market demand. Preserve failures and denominators. A model upgrade changes a candidate and requires rerunning relevant tasks; new latency/cost gates should follow measured baselines rather than invented estimates. No full repeated repository/security audit for every trivial task; independently review relevant diffs and final release gates.

## Observable action UX

Use [OC-01–OC-06](owner-control-contract.en.md) on the same journeys. Default surface: useful result plus concise material progress; details: real tool/action receipt, relevant redacted parameters, source/destination, approval and confirmed/unknown effects. Never confuse hidden reasoning with execution telemetry. An owner's request for status should read Work state, not generate another ungrounded assurance.

Example display, illustrative only:

```text
Researching event options — no booking authority
Observed: official schedule read; two price pages retrieved
Unknown: live seat inventory; total after checkout-only fees
Next: compare accessible options and produce a brief
[Sources and tool receipts] [Stop]
```

No fake timestamps, percentages, tool names or successful states may be used in a production display.

## Delivery order and existing backlog

1. **USE-01 #358:** measure baseline, improve default research/file/continuity tool use, provide a runnable outcome evaluator and owner journey. This is the recommended next product candidate, not active work.
2. **OBS-01 #359:** truthful progress, typed effect/approval receipts, cancellation and owner-control UX on existing paths; coordinate with USE-01, with no circular dependency.
3. **Package foundation #335/#337/#338:** scoped designs mapped to real install/use/revoke acceptance. #336 governs Memory when used; not a pretext for automatic life logging.
4. **Local implementation #340/#341/#342:** package lifecycle, bounded manual Work execution and one useful Files reference package first. Preserve remaining update/rollback/event/SDK scope; do not mark entire issues complete from one substep.
5. **AGENT-UX-01 #360:** install → grant → useful output → inspect → revoke → denied retry → remove → restart → authorized replacement/reuse. Depends on its enumerated design and implementation evidence. No new duplicate installer or permission database.
6. **Ecosystem #343/#345, optional #344, future #346:** expand compatibility/catalogue only after utility, lifecycle and trust boundaries hold; public Marketplace, commerce and autonomous acquisition remain later choices.

This is prioritization, not a new automatic top-level execution program. `delivery-plan.yaml` keeps successors inactive; each needs a goal-ready record and explicit owner activation. The owner may dogfood the existing baseline now without waiting for the planned platform.

## References and interpretation

- [OpenAI: practical guide to building agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/): start with capable models, reliable tools/instructions and single-agent simplicity; increase orchestration only when needed. Used as design guidance, not a claim of adopting its SDK.
- [Anthropic: demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents): evaluate outcomes as well as trajectories, use repeated trials and calibrated graders, and start with a small realistic task set. Our target percentages are our proposed policy, not this source's benchmark results.
- [Anthropic: sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing): filesystem and network isolation motivate enforcing authority outside model instructions. No sandbox parity or installation is claimed.

No performance comparison with a third-party service is supported by this specification. The product hypothesis is that useful work plus visible/revocable authority makes delegation worthwhile; validate it through owner behavior and repeat use, not publicity or anxiety alone.
