# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

<!-- readme-parity:v1 -->
<!-- readme-section:hero -->

## Delegate the work. Keep the control.

**A personal AI you can hand real work to — for everyday life and work.**

Tell Personal AgentOS the outcome you want. It is designed to use the files, tools, accounts and models you allow, do the work inside those boundaries, ask before consequential actions, and keep useful results in owner-controlled state.

The mental model is simple: **less “chat with an AI,” more “hand a task to your personal AI.”**

> **Personal AgentOS = a personal AI you delegate to, backed by an owner-authoritative AI environment.**

<!-- readme-section:everyday-scene -->

## Start with an everyday scene

<!-- capability:illustrative-product-direction -->

> **You:** “We’re almost out of detergent and paper towels. Find the usual products or good alternatives, compare price and delivery cost, and prepare the purchase. Ask me before placing the order.”
>
> **Personal AgentOS:** gathers the allowed context, researches the options, separates what is known from what still needs verification, prepares the next step, and stops at the approval boundary.

That is the product direction: delegate the annoying part, keep the decision.

**This scene is illustrative product direction, not a claim that autonomous shopping or checkout is shipped today.** Current support and evidence are listed below. Reservation, payment, outbound messaging and other consequential effects must never be implied as available unless the implementation and evidence actually support them.

Other scenes follow the same pattern:

- “Find a haircut slot that fits my Saturday afternoon and prepare the booking. Ask before confirming.”
- “I’m away this weekend. Look at what I’ve approved, make a packing/shopping list, and keep it so we can continue later.”
- “Read these approved notes, turn them into a useful result, save it, and let me find it again after restart.”

<!-- readme-section:delegation-flow -->

## The mental model

**🗣️ Delegate → 🔎 Work within permission → ✋ Approve when needed → 📦 Keep the result**

1. **Delegate an outcome.** Say what you want done rather than wiring an integration workflow.
2. **Let it work inside permission.** AgentOS mediates approved context, capabilities, destinations and runtimes/models.
3. **Keep consequential decisions with the owner.** New authority or meaningful external effects require the covering approval.
4. **Keep the useful state.** Artifacts, accepted Memory, Work/Event history and Evidence stay independent of a replaceable worker.

<!-- readme-section:chatbot-difference -->

## Why this is more than a chatbot

| Typical chatbot | Personal AgentOS direction |
| --- | --- |
| Answers a prompt | Takes a bounded task toward an outcome |
| Context is mostly the current conversation | Uses owner-approved files, Memory, connectors and task context |
| Results often end in chat | Keeps reusable Artifacts and work history |
| Tool authority can be implicit or provider-owned | Owner policy and Grants bound what can be used and where |
| The model is the center of the product | Models and agents are replaceable workers under owner authority |

Personal AgentOS is not trying to make every action autonomous. It is trying to make delegation useful **without giving up control of data, authority and durable state**.

<!-- capability:current-supported-slice -->
<!-- readme-section:try-today -->

## Try the supported slice today

The best bounded first task is still a file-workspace journey because it has concrete repository evidence:

1. Put a small Markdown/text note in a dedicated reference folder.
2. Grant that folder read access and a separate managed workspace for results.
3. Ask: **“Summarize ‘Launch review’ and save it as ‘Launch notes’.”**
4. Confirm a new Markdown result appears in the managed workspace and the original stays unchanged.
5. Restart AgentOS and ask it to find the saved result again.

For the documented file-workspace path, use a supported direct model-provider connection, explicitly grant the reference folder and managed workspace, and approve external document sharing before approved context is sent to an external provider.

### Install

```sh
brew install jongtae/agentos/agentos
agentos start
```

The browser opens at `http://127.0.0.1:8787`.

**The Homebrew command installs the newest published release, `v1.0.4` (2026-09-07), which is behind `main`.** Recent development on `main` includes capabilities and first-user fixes that are not present in that release. Follow [QUICKSTART](QUICKSTART.md) for the exact supported path and the [release procedure](docs/release.en.md) for publication status.

<!-- readme-section:status -->

## What works today — and what still has friction

The latest synthetic first-user audit is [#472](https://github.com/Jongtae/personal-agentos/issues/472). It exercised the shipped construction with injected transports; **live provider operation was not run**, so fixture success is not live-service proof.

| Area | Current evidence |
| --- | --- |
| Install/start/restart | Local deterministic first-use path passed in #472; real clean-machine Homebrew/launchd validation remains a separate operating gate. |
| Files | Synthetic **pass-with-friction**: approved-folder summary, managed save and restart/reuse work; natural “save that as a file” phrasing still has gaps (#481). |
| Gmail | Synthetic **pass-with-friction**: connect/re-auth/search/resume paths exist; contextual resume and read/reply UX still have open defects (#473, #478). |
| Calendar | Synthetic **pass-with-friction**: bounded create/preview/correct/cancel/approve paths have evidence; query/approval UX gaps remain (#475, #482, #483). |
| Research | Synthetic **pass-with-friction**: bounded public research can produce sourced known/unknown output; recommendation routing and context interactions still have defects (#448, #474). |
| Memory | Synthetic **pass-with-friction**: remember/inspect/correct and owner-visible candidates exist; deletion/receipt UX still has friction (#479). |
| Agent distribution | v0.1 schemas/contracts exist; arbitrary third-party AgentPackage execution and a public Marketplace are **not** current product claims. |

There is **no current claim** of autonomous purchasing, arbitrary computer use, universal web verification, live inventory/checkout verification, arbitrary third-party package execution or a public agent marketplace.

<!-- readme-section:why-agentos -->

## Why “AgentOS”?

Because your personal AI should not be identical to one model, one vendor or one agent.

Personal AgentOS keeps the owner-authoritative layer separate from replaceable workers:

`Owner · Context · Memory · Artifact · Capability · Runtime · Grant · Work · Event · Evidence`

Models, coding agents, connectors and delegated runtimes can change. They request capabilities; AgentOS policy and the owner decide the authority. Useful owner state should survive worker replacement instead of becoming property of the worker.

<!-- readme-section:owner-control -->

## Owner control by design

The [owner-control contract](docs/owner-control-contract.en.md) defines six observable rights:

1. **Inspect** package/source, publisher, version, execution mode and requested authority.
2. **Choose data** — which documents, memories and accounts may be used.
3. **See destinations** for task information.
4. **Bound actions** separately from installing or connecting.
5. **Stop and revoke** authority while reporting in-flight uncertainty honestly.
6. **Keep and move owner state** when workers are removed or replaced.

Local installation is not the same as local-only processing. A local package using an external model sends approved context to that provider. Disconnecting, revoking authority, removing a worker and deleting retained remote information are distinct operations.

<!-- readme-section:architecture -->

## Architecture, after the product mental model

| Layer | Responsibility |
| --- | --- |
| **Owner plane** | Owner identity/policy, Context/Memory authority, data/workspace, Grants/approvals, Work/Event, Artifacts, Evidence and recovery |
| **Capability plane** | Typed tools/connectors and bounded runtime interfaces |
| **Distribution plane** | AgentPackage, Package Manager, Registry, trust metadata and future Marketplace/discovery |
| **Worker plane** | Replaceable models, Codex/Claude Code, local/API workers and optional delegated runtimes |
| **Experience plane** | Conversation, useful results, inspectable progress, approval/control and future agent discovery |

The kernel can be **agent-independent** while the product experience becomes **agent-centric**.

<!-- readme-section:bdi -->

## BDI-inspired attention lens

BDI is a **conceptual design lens**, not a claim that a canonical BDI state machine is already shipped and not a request to expose hidden chain-of-thought.

- **Belief view:** authorized task context, accepted Memory, relevant Evidence/Artifacts and current capability/Grant facts.
- **Desire:** the owner’s wanted outcome and success criteria.
- **Attention:** what matters now, what is authorized, which destination/effect is involved and whether approval is needed.
- **Intention:** the current bounded plan and next executable step.
- **Execution:** capability/runtime mediation produces observed Work/Event records, Artifacts and Evidence.

Results may inform later context; that does not mean every result becomes durable Memory. Third parties propose a `MemoryCandidate`; policy/the owner decides canonical Memory disposition.

<!-- readme-section:ecosystem -->

## Agent ecosystem direction

The AgentPackage lifecycle deliberately distinguishes:

`downloaded != installed != enabled != connected != authorized-for-action`

Installation must not create a Grant. Updates that expand data, actions, destinations, Memory or background behavior require fresh authority. Removal revokes package authority while preserving owner-owned outputs and retained Evidence according to policy.

First prove useful bounded agents and a public authoring path; a large store and payments are not prerequisites. See the canonical [architecture](docs/personal-agentos-architecture.en.md), [PRD](PRD.md), [platform foundation](docs/agent-distribution-platform-foundation.en.md), [product vision](PRODUCT_VISION.ko.md) and [roadmap](docs/roadmap.md).

<!-- readme-section:portability -->

## Portability and limits

```sh
scripts/agentos-backup.py DATA ARCHIVE
scripts/agentos-restore.py ARCHIVE EMPTY_DATA
```

Supported owner state and reviewed declarations can be exported/restored with integrity checks. Provider credentials, sessions, local-folder Grants, engine/model selections and Telegram pairing are excluded from this portable archive and must be reconnected or re-approved.

Local-first does not mean local-only or automatically safe. Host security, package isolation, already transmitted data and remote-provider retention remain real boundaries.

<!-- readme-section:development -->

## Development governance

This is **not a coding harness, swarm framework, host kernel or replacement for macOS/Linux**. GitHub/Codex delivery automation builds Personal AgentOS; it is not the end-user product.

Follow [AGENTS.md](AGENTS.md), the [Development Constitution](docs/development-constitution.en.md) and [Goal Execution Contract](docs/goal-execution-contract.en.md): issue → bounded branch → implementation → validation → independent review where required → merge/closeout.

Product completion requires useful-outcome evidence **and** relevant denial/recovery evidence. Green CI, schemas or file counts alone are not a product claim.
