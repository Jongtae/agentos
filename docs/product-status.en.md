# Personal AgentOS: what works today, what still has friction, and where it is going

This is the evidence and boundary page behind the [README](../README.md). The README shows what you can do; this page says how we know, what is still rough, what is only a direction, and how the project is built and licensed.

<!-- readme-section:status -->
## What works, what still has friction

The latest synthetic first-user audit is [#472](https://github.com/Jongtae/personal-agentos/issues/472). It drove the shipped construction with injected transports; **live provider operation was not run**, so fixture success is not live-service proof.

| Area | Current evidence |
| --- | --- |
| Install/start/restart | Local deterministic first-use path passed; real clean-machine Homebrew/launchd validation is a separate operating gate. |
| Files | Synthetic **pass-with-friction**: summary, workspace save and restart/reuse work with the quoted wording; natural “save that as a file” phrasing still misses (#481). |
| Mail | Synthetic **pass-with-friction**: connect, re-auth, search and resume work; reading a found mail from the conversation does not yet (#473, #478). |
| Calendar | Synthetic **pass-with-friction**: create, draft, correct, cancel and approve work; a calendar query still needs a Settings row, and cancel or update drafts the model prepares have no approval path from the conversation (#475, #482, #483). |
| Research | Synthetic **pass-with-friction**: sourced known/unknown output works; “recommend” phrasing and requests right after a file read misroute (#448, #474). |
| Memory | Synthetic **pass-with-friction**: remember, inspect, correct and held candidates work; delete is web-only (#479). |
| Honest results | Merged on `main`: Telegram no longer delivers a failed or partial turn as the model's answer (#476) and a refused save no longer reports success (#488). The web view and wholly failed delegations still need the same treatment (#489, #490, #493, #494). |
| Agent distribution | v0.1 package schemas and contracts exist; third-party package execution and a public Marketplace are **not** current claims. |

There is **no current claim** of autonomous purchasing, arbitrary computer use, universal web verification, live inventory/checkout verification, arbitrary third-party package execution or a public agent marketplace.

<!-- readme-section:everyday-scene -->
## Where this is going

<!-- capability:illustrative-product-direction -->

> **Product direction — not a current capability claim.**

> **You:** “We’re almost out of detergent and paper towels. Find the usual products or good alternatives, compare price and delivery cost, and prepare the purchase. Ask me before placing the order.”
>
> **Personal AgentOS:** gathers the allowed context, researches the options, separates what is known from what still needs verification, prepares the next step, and stops at the approval boundary.

**This scene is illustrative product direction, not a claim that autonomous shopping or checkout is shipped today.** Booking a haircut, preparing a trip list from what you approved, or a purchase that waits for your yes all have the same shape: the annoying part is delegated, the decision stays with you. Reservation, payment and outbound messages will be described as available only when the implementation and evidence support them.

<!-- readme-section:delegation-flow -->
## What just happened

After any of the scenes in the [README](../README.md), this is what took place underneath.

**Delegate the work. Keep the control.**

- It used only what you allowed: that folder, that mailbox, that calendar.
- It stopped at the line that matters. Nothing was created, sent or changed outside until you said approve.
- It kept the result, the memory you accepted and a record of what actually ran, so next week you continue from the result, not from a chat log, with whichever model you like.
- When a step fails or only half-happens, you get the observed outcome, not the model's wording.

<!-- readme-section:chatbot-difference -->
## Why this is different

| | A hosted assistant | A notes and tasks workspace with AI | Personal AgentOS |
| --- | --- | --- | --- |
| Where it runs | The vendor's servers | Wherever your notes live | Your machine; the model can be local or remote |
| Who decides what it can touch | The vendor | You organise goals, tasks and knowledge for it | You, per folder, account and tool |
| Before a consequential action | On the vendor's terms | Not its job | Stops and asks you |
| What remains afterwards | A chat log in their account | Notes and tasks | Results, memory and the record of what ran, all yours, reusable with another model |
| When a step fails | The model's wording | Not its job | The observed outcome, marked failed or partial (Telegram today; web view in progress) |

A workspace organises work *for* an AI. Personal AgentOS is the environment the AI works *in*: it decides what the AI may access, what it may do, what actually happened, and what stays yours when you swap the model.

<!-- readme-section:under-the-hood -->
## Under the hood, briefly

Your personal AI should not be identical to one model, one vendor or one agent, so the layer you own is kept separate from the workers you can swap:

`Owner · Context · Memory · Artifact · Capability · Runtime · Grant · Work · Event · Evidence`

Models, coding agents, connectors and delegated runtimes request capabilities; you and your policy decide. The [owner-control contract](owner-control-contract.en.md) spells out six things you can always do: inspect what a worker is and asks for, choose the data it may use, see where your information goes, bound actions separately from installing or connecting, stop and revoke with honest reporting, and keep and move your state when a worker is replaced. Owner state exports and restores with integrity checks through the backup and restore scripts; credentials, sessions and folder permissions are deliberately excluded and must be reconnected.

For installable agents the same rule holds: `downloaded != installed != enabled != connected != authorized-for-action`. Installing a package never grants it anything, updates that widen data or actions need fresh approval, and removal revokes the package's authority while keeping your outputs. The full picture, including the five-plane architecture and the BDI-inspired attention lens (a design lens, not a shipped state machine), is in the [architecture](personal-agentos-architecture.en.md), [PRD](../PRD.md), [platform foundation](agent-distribution-platform-foundation.en.md), [product vision](../PRODUCT_VISION.ko.md) and [roadmap](roadmap.md).

<!-- readme-section:release -->
## The Homebrew release

**The Homebrew package installs the newest published release, `v1.1.0` (2026-09-23), which carries every scene in the README** (see the [release manifest](release-manifest.json) for exactly what it contains and what was observed). Work merged to `main` after that tag is not in it until the next release.

```sh
brew install jongtae/agentos/agentos
agentos start
```

The [release procedure](release.en.md) tracks publication. `v1.0.4` and earlier contain none of the scenes.

<!-- readme-section:license -->
## License

The code is [AGPL-3.0-only](../LICENSE): run it, change it and share it; if you distribute a modified version or run one as a network service, make your modified source available to its users. The “Personal AgentOS” name and logo are covered by the [trademark notice](../TRADEMARKS.md), not by the code licence. Contributions are accepted under the same licence; there is no CLA.

<!-- readme-section:development -->
## How it is built

This is **not a coding harness, swarm framework, host kernel or replacement for macOS/Linux**. The GitHub/Codex delivery automation in this repository builds Personal AgentOS; it is not the product. Contributors follow [AGENTS.md](../AGENTS.md), the [Development Constitution](development-constitution.en.md) and the [Goal Execution Contract](goal-execution-contract.en.md). Product completion needs useful-outcome evidence and denial/recovery evidence; green CI alone is not a product claim.
