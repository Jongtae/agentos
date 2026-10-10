# Connection and Delegation Contract

## Status and precedence

CONN-DELEG-01 [#1221](https://github.com/Jongtae/agentos/issues/1221). Owner direction 2026-10-09 (design conversation): the concepts below are to be written down concretely enough that any session or AI can be briefed against them and its result judged by them.

This is a current product contract. It issues no authority and claims no shipped behavior. Capability claims still need merged code and named evidence (C6). It does not select a goal; [`delivery-plan.yaml`](../delivery-plan.yaml) does.

Precedence:

- The [Development Constitution](development-constitution.en.md) governs this contract.
- The [Secretary Agency Contract](secretary-agency-contract.en.md) **pilot posture** governs where the two differ: secrets never enter a model prompt, a log or Evidence; payment needs per-action owner approval; non-payment mutations on services the owner connected need no per-action approval. Nothing here adds a request-time protection layer that the pilot posture removed.
- The [Owner Control Contract](owner-control-contract.en.md) (effects, approvals, execution location, disconnect/revoke/forget) and the [architecture](personal-agentos-architecture.en.md) (kernel primitives, Runtime boundary) stay in force. This contract applies them to connections AgentOS does not hold and to delegation.

Sources it adopts rather than restates:

- [Role, mandate and authority research (2026-10-05, ko)](research/role-ontology-and-mandate-2026-10-05.ko.md): Role, Mandate and Authority are distinct; the execution-boundary intersection; the asset-management and discretionary-management case.
- [Whitepaper "Whose Agent?" (ko)](whitepapers/whose-agent.ko.md), §8–§9: a distributable skill format is not a trustworthy capability; connectivity is not owner independence. Both documents remain non-normative research; only what this contract states is current.

## 1. Who holds what

| Part | Holder | Replaceable? |
| --- | --- | --- |
| Brain (the model doing the work) | the owner's chosen AI: Codex, Claude Code, or a configured model API (C16) | yes |
| Hands (connections to services) | the AI's own connectors/MCP/plugins, AgentOS's own connections, or the browser | yes |
| Methods (how a kind of task is done) | skills: public first, AgentOS-reference second (C16 #974) | yes |
| **The owner's way** (which service, which option, what counts as news) | AgentOS, as owner state (§7) | no: it is the owner's |
| **Memory, judgment records, history, decisions** | AgentOS (C1): Memory, the #886 judgment journal, Work/Event/Evidence, the information-use audit, approvals, trust records (§6) | no |

**Switch test.** If the owner drops one AI subscription tomorrow, the bottom two rows stay whole. Hands are re-attached through another AI or through AgentOS's own connections. A design that fails this test is rejected.

AgentOS stays the commander even when it holds none of the hands. It decides which hands may act, approves what needs approval, defines what is delegated, judges results, and keeps the record.

## 2. Capability search order

When a request needs a capability the current Work does not have, the decision model (C16, #710) looks in this order. It moves to the next step only when the current one has nothing usable.

1. **The AI ecosystem's capabilities**: connectors, MCP servers and plugins the owner's AI already has, or that the official MCP Registry or the vendor's directory offers. A capability is "what can be done".
2. **Skills**: a public skill first, then an AgentOS reference skill. A skill is "how to do it". It never grants authority.
3. **Generic channels**: the signed-in browser (#680, #939), an authenticated API read by secret-slot reference (#1218), or public page reads.
4. **Build**: only for a concrete unmet contract, through the normal C15 review. Never a task-specific feature in core code (C16).

Generating a skill from scratch inside a Work is not part of this order yet. Curated procedural skills outperform naive self-generation (FinSkillBench, as summarised in the 2026-10-09 review). AI-authored owner skills need their own decision and a C16 #974 reading first.

## 3. Connection precedence

For each service, the hand used is chosen in this order:

| Order | Hand | When |
| --- | --- | --- |
| 1 | **AI-side connection**: the subscription AI's connector, MCP server or plugin | default |
| 2 | **AgentOS-owned connection**: own Google client (#1172), secret-slot API (#1218), an MCP server AgentOS connects to itself | the AI side offers no decision point for the effects needed (§4), the owner wants full control of that service, or the AI side is unavailable |
| 3 | **Browser**: the owner's signed-in session, with phone sign-in and AutoFill (#939, #1170) | neither 1 nor 2 exists for the service |
| 4 | **None** | say so plainly, and guide the owner to connect in conversation; never guess (#1197 acceptance) |

Rules:

- **The owner's choice per service is the owner's way (§7).** "I want AgentOS to hold this one" is stored and not asked again.
- **One subscription is enough.** With only Codex, only Claude Code or only a model API, the same order applies. Rows that subscription lacks are skipped.
- **Connections are shown where the owner manages everything else: in conversation first (#880).** Each service shows which hand it uses: AI connection, own connection, browser, or none. That is the #1197 Settings rule, generalised.
- **AI-side credentials stay where they are.** AgentOS never copies an AI vendor's connector tokens. AgentOS-owned secrets stay in the owner-local encrypted store with a Keychain-held key, and are referenced, never shown to a model.
- **Disconnect, revoke, remove and forget keep their Owner Control Contract meanings for every hand.** Disconnecting an AI-side connector (for example `claude mcp logout`) is not revocation at the provider and is described as such.

## 4. Control levels

AgentOS controls a hand at one of three levels:

| Level | What AgentOS does | Applies to |
| --- | --- | --- |
| **Mediate** | AgentOS makes the call itself: secrets injected, destination allowlist, payment guard, response provenance (§8), budget | AgentOS-owned connections, the browser |
| **Decide per call** | the AI's CLI stops before each tool call and AgentOS allows or refuses it, seeing the tool name and the actual input; then observes and records the call | AI-side connections, where the CLI offers a decision point (Claude Code `--permission-prompt-tool`, listed in 2.1.280's help; Codex: to be verified) |
| **Delegate** | AgentOS defines the mandate, judges the result and keeps the trust record (§5, §6); it does not see each step | other agents (A2A), external services acting on their own |

What each effect class needs, under the pilot posture:

| Effect | Mediate | Decide per call | AI-side, no decision point | Delegate |
| --- | --- | --- | --- | --- |
| read | yes, audited | yes, audited | read tools only, audited from the CLI's tool events (#1197 baseline) | yes; returned data is audited |
| mutate (non-payment) on a service the owner connected | yes, told after (pilot) | yes, told after (pilot) | **not offered**: AgentOS could neither stop nor reliably record it | only inside the mandate's stated scope |
| payment / money movement: payments, securities orders, transfers | per-action owner approval bound to exact parameters (Owner Control Contract) | per-action owner approval, decided at the CLI's decision point with the exact input | **not offered** | **never delegated** in the pilot; each such effect returns to the owner |

Classifying an effect:

- **Deterministic guards apply where they can see the effect.** Examples:
  - the card and one-time-code field guard (#698);
  - #1172's Drive transport, which refuses every method except GET;
  - #1218's API transport, which treats only GET and HEAD as reads and floors every other method to at least mutate.

  An HTTP method is not proof of no side effect: a GET that changes server state is a known #1218 follow-up.
- **A label can only add a requirement, never remove one.** This holds for the model's effect label and for an MCP server's `readOnlyHint`/`destructiveHint` annotations. Annotations are untrusted hints.
- **The owner can mark a connection as money-capable.** A brokerage is the obvious example. On a money-capable connection, a tool call counts as read only when an AgentOS-owned transport limits it to a read method (GET or HEAD), or when the owner reviewed that tool as read. Every other call there is payment-class.
- **Semantic effect judgment stays with the model; deterministic code enforces only these invariants.** There are no keyword rules (Decision Layer).

Decision points must be proven before they are relied on. A compatibility test shows that the CLI actually stops at the decision point for an AI-side connector's write tool, and that AgentOS's refusal holds. Until that observation exists, the column "AI-side, no decision point" applies.

Observed decision points (#1296):

- **Claude Code** (2.1.280): `--permission-prompt-tool` answers every AI-side tool call that is not pre-approved: claude.ai connectors (#1197) and the MCP servers the owner confirmed for Works. Observed 2026-10-10: under `--setting-sources project` a user-scope server in `~/.claude.json` is not started, and the same launch without that flag starts it. Only the confirmed entries reach a Work, through `--mcp-config`.
- **Names.** No owner server may be named `agentos` or start with `claude_ai`, so none can carry the bridge's or a claude.ai connector's tool name.
- **Codex** (codex-cli 0.153.4, observed 2026-10-10 on real turns with a local test server):
  - a session-flag `PreToolUse` hook receives the MCP tool name and its actual input;
  - a `deny` holds: the server never received the call;
  - empty output lets the call run; `allow` is unsupported and blocks the call;
  - without `--dangerously-bypass-hook-trust` the hook is skipped and the call runs, so AgentOS passes that flag whenever it loads an owner server.
- **Fail closed after the fact.** A call the worker's own stream shows completing without an AgentOS `allowed` decision is recorded, and the owner's servers are switched off for every engine until the owner confirms them again.
- **Which servers.** Only servers the owner confirmed for an engine load into a Work (empty by default). Their definitions are read from the owner's CLI at launch and never stored by AgentOS. For Codex, values that may be secret travel only in the CLI's environment and are withheld from the model's shell.

## 5. Delegation

The mandate fields adopt the research §06 list. A delegation states:

- **who**: principal (the owner via AgentOS) and delegate (an agent, AI or service);
- **purpose and completion condition**;
- **scope**: data, hands, effect classes;
- **exclusions**;
- **budget and validity**;
- **what to report**;
- **when to come back to the owner**.

A clear one-off request is its own mandate. The owner fills in no form. Only standing delegations need an explicit scope, expiry and end condition.

Rules:

- **Nested authority is a subset.** A delegate never gets more than the delegating Work has, and two delegates' scopes do not add up (architecture; research §06).
- **Context, not conclusion.** When the purpose is an independent judgment (a second opinion), the brief carries goal, facts and criteria, not the delegator's preferred answer. A brief that carries a conclusion must say so, and the result is not reported as independent.
- **AgentOS judges and declares completion.** The result is judged against:
  - the owner's way (§7);
  - the constitution and contracts (the owner's durable values);
  - the domain standard a loaded skill or cited source provides;
  - observed evidence (§8).

  The decision model may adjust and re-delegate within the existing #710 bound (at most twice, never after an effect). Where a delegate's answer conflicts with the owner's criteria, the conflict is shown to the owner rather than silently resolved.
- **Revoking a mandate stops new calls; it does not undo effects already made** (Owner Control Contract, OC-05).
- **Phase-2 family delegation** keeps its own contract (A2A D-04, Secretary Agency Contract §Family collaboration).

## 6. Trust ladder and trust record

One ladder for every third-party hand, skill or agent:

1. **Report**: read and summarise.
2. **Propose**: recommend an action; the owner acts.
3. **Act after per-action approval.**
4. **Act within a standing mandate.**

Rules:

- **Starting rung.** A newly introduced third-party hand, skill or agent starts at the rung the owner chooses when it is introduced. The recommended default is rung 1 for a money-capable domain and rung 3 otherwise. The owner's own AI working on owner-connected services already runs at the pilot defaults (§4); the ladder does not lower them.
- **Introduction is conversational.** The AI introduces the hand, skill or agent: what it is, its source and licence, what it can and cannot do, the proposed rung. It can run a trial that performs no effects first: reads only, or a provider's paper/sandbox mode.
- **Raising a rung is an owner decision, never automatic.** Lowering may be automatic after a failure or an owner correction, and the owner is told.
- **Payment never reaches rung 4 in the pilot.**
- **The trust record is owner state.** It holds, per hand, skill or agent: what was delegated, what was observed, owner corrections, and the owner's final decisions. Popularity, install counts and review scores never move a rung (C9).

## 7. The owner's way

The owner's way is how this owner wants things done: which service, which option, what time margin, what counts as worth an alert, which hand per service. "Personalisation" is not a goal here. Following the owner's way is the default.

Rules:

- **Precedence.** The owner's way, then a loaded skill's default, then AgentOS's default. No vendor, skill or package default silently replaces a known owner choice.
- **Slots first.** A ready-made method declares the slots it honours. Examples: the map-directions skill's "preferred map service", or a parameters file next to a skill such as `invest.md` in public investment skills.
  - When the owner's way needs something outside the slots, the AI first tries another hand that can honour it. The example is setting a route option in the map service through the browser, which `references/kakaomap.md` links cannot express.
  - If no hand can honour it, the AI says exactly what it could not honour.
- **Learning.** The owner's way is learned from what the owner states, from corrections, and from AgentOS's own records. It is saved under the #918 slice (a) rule: saved, told, exact undo. It is corrected and forgotten under #794.
  - When it is unknown and the answer would really change, the AI asks once and saves the answer. This is the map-directions pattern.
  - Wholesale observation of the owner outside AgentOS is not a learning source.

## 8. Data truthfulness

Every external read that feeds an answer keeps:

- its source;
- the time the source says the data is as of;
- the raw values apart from values AgentOS or the model computed;
- two independent states:
  - **freshness**: `fresh`, `stale` or `unknown`;
  - **completeness**: `complete`, `partial` or `inconsistent`.

  A response can be fresh and partial, or stale and complete.

These are generic Evidence semantics, introduced for API reads by #1218 with exactly these values. They are never domain-specific types in core code.

A report never upgrades a state. `stale` stays stale, `partial` is not reported as complete, and `inconsistent` values are not reconciled silently. Requested, observed, failed and unknown stay distinct (Secretary Agency Contract §Evidence-based completion). For money-related reads, the answer names the account and the as-of time it used.

## 9. Cost

- **Explore once, repeat cheaply.** The first time, a capable model works out how to do a task for this owner. Later runs re-use that method (skill plus the owner's way) on the cheapest model that is adequate. A situation-dependent reply still never drops to the lowest-cost model (#1008).
- **A watch costs nothing when nothing changed.** The #719 rule is kept: a result identical to the last one is quiet without a model call. A further step is a cheap model-free check before calling a model; it is listed as a gap (§12).
- **Repeating a method is not replaying an effect.** A repeated procedure re-reads current state and re-authorizes every effect. No replay, ever.
- **Budgets bound every Work and every watch.** Delegation budgets are part of the mandate.

## 10. Threat model

| Threat | Holding line |
| --- | --- |
| A third-party MCP server or plugin lies in its tool description or annotations (tool poisoning) | annotations only add requirements (§4); unknown and money-capable defaults; owner introduction (§6) |
| Prompt injection through tool results, pages or delegate answers | results are untrusted data; the AI cannot widen authority by what it reads; effects pass §4; the information-use audit records the source |
| Credential exposure | AgentOS secrets are referenced and never shown to a model; AI-side tokens are never copied; browser output mediation (#680) |
| A local MCP server runs code on the owner's Mac | only servers the owner already configured in their own CLI, after a one-time confirmation in conversation; no auto-install |
| Delegate scope creep, or chained delegation widening authority | subset rule; mandate exclusions; completion declared by AgentOS |
| Trust-record manipulation | only owner decisions raise a rung; popularity is not an input |
| Data retained by an AI vendor through its own connector | disclosed per service as an execution-location fact (Owner Control Contract); the owner chooses the AgentOS-owned hand when that matters |

Injection and exfiltration defences beyond these lines remain owner-deferred (trifecta proposal parked, 2026-09-28). This contract does not reopen that decision.

## 11. Observation cases

These are observation windows, not completion criteria. No site, provider or category is named in core code because of them (C16).

| Case | Expected behavior |
| --- | --- |
| "스크린골프장 약속 가는 길" | Uses the owner's saved map service. Honours "큰길 우선" when a hand can; otherwise says it could not. Gives leave-by time from the owner's start point (map-directions method). |
| Cart add on the owner's shop | Hand per §3. Exact item, variant and quantity read back. Payment never started (shopping-cart method; pilot posture). |
| "현재 자산 요약해줘" | Read-only. Hand per §3: an AI-side or registry MCP if the brokerage has one, otherwise #1218 or the browser. Account and as-of time named. Stale, partial and inconsistent shown (§8). No order tool offered without the §4 money rules. |
| Second opinion | An independent review is delegated to a different AI with context but no conclusion (§5). Disagreements are shown to the owner; the owner decides. |

## 12. Current state and gaps

| Piece | State | Where |
| --- | --- | --- |
| AgentOS-owned Google connections | merged | #1172, #1204, #1213/#1214 |
| Secret-slot API read with provenance | merged | #1218 |
| Public skills with a repository-root licence | merged | #1220 |
| AI-side connection first, read-only, audited (Google) | open | #1197 |
| AI-side connections generalised to all connectors, MCP servers and plugins | gap | successor of #1197 |
| Per-call decision point for AI-side tools | merged for Claude Code and Codex: claude.ai connectors and owner-confirmed MCP servers (§4 observed decision points); operations allowed still come from the reviewed read list | #1197, #1296; owner decisions per operation #1297 |
| AgentOS connecting to an MCP server itself | gap | none |
| Conversational secret entry (elicitation URL mode) | gap | none |
| Money-capable connection marking | gap | none |
| Trust record and ladder | gap | none |
| Owner-way slots beyond Memory facts | partial: map-directions preferred-service slot | #794 phase 3 for correction and forgetting |
| Model-free change check before a watch's model call | gap | none |
| Family A2A delegation | planned | #661 |

## 13. Constitutional amendment proposals (not applied)

The following are proposed for a separate governance issue once real use supports them. They are not in force through this contract.

- **Owner-choice precedence.** AgentOS, skills and packages never decide on the owner's behalf which service, option or hand to use when the owner's choice is known. When it is unknown, they learn it, and if it matters they ask once. This is the other half of C16: C16 forbids scripting the task; this forbids choosing for the owner.
- **Every hand is under decision or delegation.** Whoever holds a connection — the owner's AI vendor, AgentOS or another agent — a consequential effect happens only through an AgentOS decision point or inside an owner-defined mandate. Where neither exists, the effect is not offered.

## Non-goals

- Changing the pilot posture, or adding request-time sensitivity judgments.
- Copying AI-vendor credentials, syncing web-account connectors the CLI cannot reach, or importing plugin hooks and slash commands.
- An AgentOS skill marketplace or skill commerce.
- AI-authored owner skills (needs its own decision; §2).
- Task-, site-, provider- or category-specific core code.
