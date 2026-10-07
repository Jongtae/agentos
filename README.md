# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

<!-- readme-parity:v1 -->
<!-- readme-section:hero -->

## A personal agent that stays yours

We should be able to pick up yesterday’s conversation, share half a thought, and carry unfinished work forward without explaining our lives all over again. Whether we are planning a week, researching a question or preparing a purchase, we should be able to trust the environment that holds that context.

**Personal AgentOS explores how to build a continuing personal agent (PA) in an environment you install and control.** Helping like a good assistant is an important starting role, but it does not define the limits of the agent.

Assistants answer questions. Computer agents carry out commands. A personal agent should also stay with you across conversations, kinds of work and changes of AI. We call that continuity **Presence**.

<!-- readme-section:ownership -->

## Your agent, on your terms

The more kinds of work an agent helps with, the more it matters who holds its memory and decides what it can do. Your relationship with it should outlast a provider, a model or a chat session.

AgentOS keeps memory, work and authority in your environment. You choose the AI, the information it can use and the access you give it. Different expertise can serve the same owner; better AI should expand what your agent can do without making you start over.

Local-first is not local-only: you can use a local or hosted model. With a hosted model, the context used for a request is sent to that provider.

<!-- readme-section:presence -->

## What makes continuity possible

Presence needs more than a long chat history. The agent needs to connect what it knows about you, what is happening now, what you are working on, what you have allowed and what actually happened.

Metadata can list a meeting's time, place and attendees. An **ontology** also relates that event to people, goals and commitments: was it merely an invitation, or did someone accept a follow-up? A calendar view may use it to arrange time; a project view may use it to track a decision. Both should refer to the same meeting and its source, without turning an invitation into a promise.

The distinction matters beyond scheduling. Imagine the owner holds 1,000 shares. An asset-management view asks how that holding fits the owner's overall finances. A discretionary-investment view first asks whether it falls within a specific mandate and its constraints. Both use the same sourced position, but a role name alone never grants permission to trade.

AgentOS aims to connect these facts, role-specific interpretations, the work you delegated, actual permissions and evidence in one shared structure. That is how a change of AI or an interruption could leave a place to continue. These are design illustrations, not released financial services or observed runs.

<picture>
  <source media="(max-width: 600px)" srcset="docs/assets/readme/presence-overview.en.narrow.svg">
  <img src="docs/assets/readme/presence-overview.en.svg" alt="Concept illustration: Assistant answers a question about NVIDIA; a computer agent acts on an Amazon command; Personal AgentOS carries a conversation over time. You talk to one PA, with context, work and authority held in AgentOS above replaceable AI and tools. The examples illustrate product direction, not observed runs or shipped integrations.">
</picture>

AgentOS uses its judgment layer to choose AI and tools and check their results. You talk to the PA while AgentOS carries that structure underneath the conversation. **Same PA. Different AI.**

<!-- readme-section:conversation -->

## A conversation that carries on

*Illustrative product direction, not an observed live run or a shipped shopping integration.*

The English image below adapts the owner's Korean visual reference into three shorter conversations: sharing a location to find dinner on the way home, comparing a golf belt and pausing for account login before a cart action, and continuing from a restaurant photo to a nearby walk. It is an edited illustrative reconstruction, not a verbatim product screenshot or proof of those integrations.

<picture>
  <source media="(max-width: 600px)" srcset="docs/assets/readme/owner-pilot-conversation.en.png">
  <img src="docs/assets/readme/owner-pilot-conversation.en.png" alt="English three-panel image with three reconstructed PA conversations: finding dinner after sharing a location, comparing golf belts before an account-login handoff, and continuing from a restaurant photo to a nearby walk. Illustrative, not a verbatim product screenshot.">
</picture>

[Open the English image at full size](docs/assets/readme/owner-pilot-conversation.en.png) · [See the owner's original reference](docs/assets/readme/owner-pilot-conversation-reference.jpg).

The image shows three separate conversations:

1. **On the way home:** “Dinner on my way back?” The PA asks for the current location, then offers three places with distance and open status. The owner picks the second.
2. **Find this for me:** The owner shares a belt photo. The PA compares three options and asks which one to use. When the owner asks to add the first to a cart, the PA asks for a shopping-account login before proceeding.
3. **I’m here. What next?** The owner shares a restaurant photo and asks what to do afterward. The PA offers a walk, café or bar nearby. The owner chooses the walk; the PA says it will check the route and hours.

The same continuity matters in smaller moments, hours apart:

> “We’re almost out of coffee.”<br>
> Hours later: “I’m heading out. Is there somewhere on the way I can pick it up?”<br>
> Later: “No time. Just get the same one as last time.”

The aspiration is simple: the PA follows what “it” and “the same one” mean, brings in relevant context, and asks for missing information or authority when needed. You keep talking; you do not assemble a workflow.

<!-- readme-section:try-today -->

## Try it

On macOS with [Homebrew](https://brew.sh):

```sh
brew install jongtae/agentos/agentos
agentos start
```

1. Browser setup opens at [http://127.0.0.1:8787](http://127.0.0.1:8787/). Choose **바로 시작하기** (Start now).
2. Connect and test your own model: a tool-capable local Ollama model, or OpenAI, an OpenAI-compatible service or Anthropic with your API access. The setup interface is currently Korean.
3. In **설정 → 외부 연결** (Settings → External connections), connect your own bot using its BotFather token. Open the generated pairing link in Telegram and press **Start**.
4. In that Telegram chat, ask: **“Help me think through what to focus on this week.”**

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
