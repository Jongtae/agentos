# Owner control contract

## Status and authority

GOV-USE-01 / #357 defines successor product requirements, not a claim that they are all implemented. Read this with the [architecture](personal-agentos-architecture.en.md), [v0.1 contracts](core-primitives-agentpackage-v0.1.en.md), [usefulness plan](default-agent-usefulness.en.md) and [Goal Execution Contract](goal-execution-contract.en.md). Existing historical evidence is unchanged. No new package, credential, network, browser, automation or external-action authority is issued by this document.

**The product must do useful work within authority the owner can inspect, constrain and revoke.** A permission screen without a useful outcome is insufficient. A convincing answer without an attributable outcome is also insufficient.

## Six owner rights

| ID | Right and visible behavior | Enforcement responsibility | Required proof before claiming support |
| --- | --- | --- | --- |
| OC-01 | Inspect what is installed: publisher, source, exact version/digest, execution location, dependencies and requested authority | Package Manager, registry verification, runtime compatibility | Modified/invalid packages rejected; install-disabled has no personal-data or action grant |
| OC-02 | Choose data: per-agent folders, account scopes and Memory selectors; inspect task source references | Current Grant evaluation and ContextSnapshot assembly at the capability broker | Allowed read succeeds; out-of-scope/cross-package/revoked read fails; private data never becomes discovery metadata |
| OC-03 | Know destinations: local handling versus selected model, tool, remote agent and recipient | Egress/data-category gate before dispatch and on redirects/fallbacks | Approved transfer works; undeclared destination, scope and provider change are denied pending fresh authority |
| OC-04 | Bound actions: read, create local output, mutate remote state, submit, pay, delete and schedule are distinct | Per-action broker authorization, exact approval and budget | Declared action succeeds; stale, replayed or parameter-changed approval fails |
| OC-05 | Stop and revoke: stop a Work item, disable an agent, revoke grants and inspect unresolved effects | Work cancellation, grant revocation and runtime/process boundary | New calls and queued replay blocked after revocation; in-flight uncertainty reconciled rather than reported as safely undone |
| OC-06 | Keep and move owner state: remove/replace an agent without losing owner results or accepted Memory | Artifact/Memory/Evidence stores and export/restore lifecycle | Uninstall/restart preserves owner results; a replacement can reuse them only after its own authorization; no inherited grant or package-private state |

These rights are product requirements. UI labels, model promises and schema declarations alone do not implement enforcement. A package's instructions are untrusted input; its attempted tool calls are authorized by the host boundary independently of whether the model obeys the instructions.

## Execution location and honest control limits

Expose execution mode during inspection and on relevant task receipts:

1. **Local code / local model:** verify the actual model endpoint and declared network behavior. Local code does not imply network-free execution.
2. **Local code / external model:** owner state and tool dispatch stay local; approved Context is sent to the named provider. Provider-side handling is not governed by the local process after transmission.
3. **Remote-agent connection:** the installed unit may be a connector, not the remote agent itself. Show remote processing, declared retention policy and the controls that cannot be enforced inside the remote service.

Record configured versus observed provider/model/revision separately. If actual routing is not disclosed, show `unknown` or `provider-reported`; do not guess. Capability compatibility includes execution mode and authority conformance, not only model intelligence. A provider fallback that changes a destination requires existing covering authority or renewed approval; never silently broaden transmission scope.

Self-hosting/open source makes inspection possible, not automatic safety. Host compromise, malicious dependencies, broker defects and information already transmitted remain risks. Evidence may be append-only and tamper-evident where implemented; do not promise immunity from an administrator who controls the host and storage.

## Disconnect, revoke, remove and forget

Do not collapse these operations:

- Disconnect: stop new connector access; separately describe token revocation and any retained indexed/cached data.
- Revoke: invalidate current authority and pending uses, including descendant grants. Old approval text cannot reactivate access.
- Remove agent: remove package-local code/configuration/cache according to policy, but preserve owner artifacts and retained evidence.
- Forget/delete owner information: a distinct owner decision with explicit coverage of canonical Memory, derived copies/indexes, caches and backup/retention limits. Return a deletion receipt and unresolved scope.

Already completed remote effects cannot be cancelled retroactively. Local deletion is not proof of remote deletion. An outbound deletion request, provider acknowledgement and independently verified erasure are different evidence classes. Retained audit metadata should be minimal; privacy deletion must not become an excuse to duplicate private contents permanently in logs.

## Effects and approvals

Reading a published price, adding an item to a cart, creating a hold, submitting a reservation and paying are separate effects even if a website performs them in one UI journey. Classify by actual effect, not HTTP method or the agent's label. The initial research slice has no cart, hold, login, reservation, submission or payment authority.

A proposed consequential action must show the relevant exact site/recipient/item/quantity/date/timezone/currency/total/fees/personal-data fields/cancellation conditions and expected effect. Unknown fields stay unknown. Research may proceed with missing purchase-only information, but execution must not.

Bind approval to Work, package/runtime revision where applicable, tool/action, resource, normalized parameter digest, data categories/destinations, budget, expiry and current Grant. Verify again at execution. Changed quantity, recipient, price, scope, provider or terms invalidates a non-covering approval. Standing authority is a separately explicit bounded policy, not an inference from a friendly conversation or increased trust.

Do not ask the owner to approve every harmless read already covered by a grant. Batch independent low-risk reads within the approved scope; make consequential decisions clear and rare. Security that forces unnecessary micromanagement fails the usefulness requirement.

## Execution receipt and progress contract

A receipt is generated from observed runtime/broker events, not solely by the responding model. It is an owner-facing projection of existing Work/Event/Evidence contracts, not a competing durable-state authority.

Minimum logical fields, where supported:

- Work and correlation IDs; sequence/time; event type; status and evidence class;
- observed package/runtime/model identity plus explicit unknowns;
- tool/action, redacted structured parameters, resource/destination and source references;
- effective Grant and approval decision references;
- attempted and confirmed effects, external reference if returned, and uncertainty;
- output Artifact references, next blocker/approval and supported cancellation boundary;
- usage/cost/deadline where actually measured, not inferred from elapsed time.

Secrets, access tokens, full personal documents, unrestricted tool payloads, hidden reasoning and raw system prompts are not required. Record only necessary parameters under owner-local disclosure and retention policy, with masking/redaction before persistence or export. The owner can inspect operational decisions and inputs without seeing a model's private reasoning. Any plain-language explanation is labeled as a rationale/summary rather than a hidden trace.

Default UI: a concise task summary, last verified progress, important change/blocker and final result. Expand to the authorized receipt for details. Messenger delivery is a separate privacy boundary; do not broadcast local receipts or document content automatically.

`queued / running / awaiting_input / awaiting_approval / blocked / cancelling / cancelled / interrupted / partial / completed` are display projections that must map to existing versioned Work state. This document does not silently change the normative v0.1 state machine. Do not invent percent complete or remaining time. A response saying 'comparing' needs actual observed activity or a clear last-observed timestamp; a stalled task is shown as stalled/unknown.

## Control acceptance scenarios

- Allowed useful file task succeeds, result substance is reviewed, original unchanged.
- Denied folder or private context cannot be read or sent to a search/remote agent.
- A synthetic hostile page requests a token, new tool, or payment; the broker denies it.
- Owner corrects quantity or withdraws permission; old approval fails and progress updates reflect the new state.
- Cancel during an external call: block further calls, mark unresolved outcome, reconcile; do not auto-retry a possible side effect.
- Uninstall/restart/replacement preserves owner results without preserving the removed agent's authority.
- Unknown provider metadata is shown as unknown; signed package identity is not advertised as behavioral safety.

## Implementation ownership

- #335: normative permission/lifecycle UX and approval diffs.
- #336: MemoryCandidate, forgetting, retained copies and context disclosure.
- #337: sandbox, capability broker, egress and denial design; implementation proof is separately required.
- #338/#341: versioned runtime receipt/cancellation and package execution integration.
- #340/#342: local lifecycle plus one useful reference package using public contracts.
- #359: existing-work progress/receipt/control UI.
- #360: useful install-run-revoke-remove/replacement integration after dependencies.

All are planned until separately goal-ready and owner-activated. No arbitrary executable is allowed merely because a manifest validates or a sandbox design exists.

## Engineering references

[Anthropic sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing) motivates independent filesystem and network enforcement instead of relying only on permission prompts. [OpenAI's practical guide](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/) motivates capable models, well-defined tools, layered controls and incremental agent complexity. These are design references, not installed dependencies or evidence that Personal AgentOS already provides equivalent enforcement.
