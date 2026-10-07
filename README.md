# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

<!-- readme-parity:v1 -->
<!-- readme-section:hero -->

## A personal agent that carries your work forward

An assistant answers when you ask. A computer agent acts when you give it a command. But much of life does not arrive as a complete question or a one-off task. You mention a meeting, leave a decision open, return to it days later, and expect the work to have a next step.

**Personal AgentOS explores how to build a personal agent (PA) that stays with you and your unfinished work, in an environment you install and control.** It should keep track of what you meant, what remains unresolved and what it is waiting for. As the project grows, it should be able to prepare what comes next and bring a matter back when it needs your attention, while asking before an action needs your authority.

We call that continuing relationship **Presence**. Helping like an assistant is the starting role; the aim reaches across different kinds of work and survives a change of AI. Presence has to come from retained context, work and authority, not from a friendly tone.

<!-- readme-section:ownership -->

## Your agent, on your terms

The more kinds of work an agent helps with, the more it matters who holds its memory and decides what it can do. Your relationship with it should outlast a provider, a model or a chat session.

AgentOS keeps memory, work and authority in your environment. You choose the AI, the information it can use and the access you give it. Different expertise can serve the same owner; better AI should expand what your agent can do without making you start over.

Local-first is not local-only: you can use a local or hosted model. With a hosted model, the context used for a request is sent to that provider.

<!-- readme-section:presence -->

## Why the work can continue

Imagine saying, “Keep track of next week's project meeting. We still need to settle the proposal.” The direction for a PA is to connect that meeting to the open decision and prepare a useful brief before it happens. After you share the meeting notes, it should distinguish an accepted follow-up from a suggestion and carry the unfinished work forward. It can prepare a follow-up message; if sending it to another person exceeds the authority you granted, it asks first. **This is an illustrative product direction, not an observed run or a capability promised by today's Homebrew release.**

<picture>
  <source media="(max-width: 600px)" srcset="docs/assets/readme/presence-overview.en.narrow.svg">
  <img src="docs/assets/readme/presence-overview.en.svg" alt="Concept illustration: Assistant answers a question about NVIDIA; a computer agent acts on an Amazon command; Personal AgentOS carries a conversation over time. You talk to one PA, with context, work and authority held in AgentOS above replaceable AI and tools. The examples illustrate product direction, not observed runs or shipped integrations.">
</picture>

AgentOS uses its judgment layer to choose AI and tools and check their results. You talk to the PA while AgentOS carries that structure underneath the conversation. **Same PA. Different AI.**

That takes more than a long chat history. Metadata can record the meeting's time, place and attendees. An **ontology** describes how the meeting relates to people, goals, decisions and commitments: an invitation is not an accepted task. A calendar view can arrange time while a project view tracks the decision, both grounded in the same sourced event. Durable work records what is still open; authority limits what the PA may do; evidence shows what actually happened.

The same distinction extends beyond meetings. A sourced stock holding can inform an asset-management view of the owner's finances; a discretionary-investment view must also check the explicit mandate and its constraints. Neither a role name nor a useful inference grants permission to trade.

AgentOS aims to connect facts, role-specific interpretations, delegated work, permissions and evidence in a structure the owner controls. This is how a paused task or a different AI could pick up the right next step without making you reconstruct it. These are design illustrations, not released financial services or observed runs. Proactive attention to changing circumstances is a direction beyond the current reactive Presence work, not a claim of always-on monitoring today.

<!-- readme-section:conversation -->

## Ordinary moments, the same PA

*Illustrative product direction, not an observed live run or a shipped shopping integration.*

The illustration below condenses three PA conversations: sharing a location to find dinner on the way home, comparing a golf belt and pausing for account login before a cart action, and continuing from a restaurant photo to a nearby walk. It is an edited illustrative reconstruction, not a verbatim product screenshot or proof of those integrations.

<picture>
  <source media="(max-width: 600px)" srcset="docs/assets/readme/owner-pilot-conversation.en.png">
  <img src="docs/assets/readme/owner-pilot-conversation.en.png" alt="Three reconstructed PA conversations in English: finding dinner after sharing a location, comparing golf belts before an account-login handoff, and continuing from a restaurant photo to a nearby walk. Illustrative, not a verbatim product screenshot.">
</picture>

[Open the English image at full size](docs/assets/readme/owner-pilot-conversation.en.png) · [View the original reference image](docs/assets/readme/owner-pilot-conversation-reference.jpg).

The image shows three separate conversations:

1. **On the way home:** “Dinner on my way back?” The PA asks for the current location, then offers three places with distance and open status. The owner picks the second.
2. **Find this for me:** The owner shares a belt photo. The PA compares three options and asks which one to use. When the owner asks to add the first to a cart, the PA asks for a shopping-account login before proceeding.
3. **I’m here. What next?** The owner shares a restaurant photo and asks what to do afterward. The PA offers a walk, café or bar nearby. The owner chooses the walk; the PA says it will check the route and hours.

Continuity also matters in smaller moments, hours apart:

> “We’re almost out of coffee.”<br>
> Hours later: “I’m heading out. Is there somewhere on the way I can pick it up?”<br>
> Later: “No time. Just get the same one as last time.”

The aspiration is simple: the PA follows what “it” and “the same one” mean, brings in relevant context, and asks for missing information or authority when needed. You keep talking; you do not assemble a workflow.

<!-- readme-section:try-today -->

## Try it

This earlier preview lets you start a conversation with your own model; it does not reproduce the meeting scene above.

On macOS with [Homebrew](https://brew.sh):

```sh
brew install jongtae/agentos/agentos
agentos start
```

1. Browser setup opens at [http://127.0.0.1:8787](http://127.0.0.1:8787/). Choose **바로 시작하기** (Start now).
2. Connect and test your own model: a tool-capable local Ollama model, or OpenAI, an OpenAI-compatible service or Anthropic with your API access. The setup interface is currently Korean.
3. In **설정 → 외부 연결** (Settings → External connections), connect your own bot using its BotFather token. Open the generated pairing link in Telegram and press **Start**.
4. In that Telegram chat, say: **“I need to finish a proposal this week. Help me break it into the next few steps.”**

Homebrew installs Python for you; model access is separate. Keep `agentos start` running while you talk. [QUICKSTART](QUICKSTART.md) covers model setup, file work, Telegram and running the newest code from source.

**Where it stands:** Homebrew installs **v1.1.0** (2026-09-23), an earlier preview. Newer Presence work on `main` is not included in this release. Calendar creation is unavailable in that release and research is partial; see the [release manifest](docs/release-manifest.json). [Product status](docs/product-status.en.md) separates what is available, what has been tested and what remains a goal.

<!-- readme-section:more -->

## Explore the ideas

- [Why this project exists](VISION.md) · [Whose agent?](docs/whitepapers/whose-agent.ko.md) (Korean strategy whitepaper) — why the agent's continuity should stay with the owner when AI changes.
- [Architecture and ontology](docs/personal-agentos-architecture.en.md) · [Presence](docs/presence-experience-contract.en.md) · [Roles and delegation](docs/research/role-ontology-and-mandate-2026-10-05.ko.md) (Korean research proposal) — how personal state, work and control can support one agent across different roles.
- [Research and references](docs/acknowledgements.en.md) — the work on personal agents, memory, owner models and provenance that informed the design.
- [Documentation map](docs/README.md) · [Contributing](CONTRIBUTING.md) — find the current contracts, inspect the implementation and help develop it.

<!-- readme-section:license -->

## Open source

This is a working exploration, open for others to run, question and improve. It does not have to be the final answer to be a useful beginning.

Code: [AGPL-3.0-only](LICENSE). The Personal AgentOS name and logo follow the [trademark notice](TRADEMARKS.md). Third-party work is credited in [acknowledgements](docs/acknowledgements.en.md).
