# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

<!-- readme-parity:v1 -->
<!-- readme-section:hero -->

## What if Jarvis belonged to another company?

Imagine Tony Stark had spent years working with Jarvis — sharing context, leaving decisions open, delegating work and learning how to work together.

Now imagine a better AI appears.

**Should Tony have to lose Jarvis to use it?**

Should he lose what Jarvis remembers about him, the work they have not finished, the authority he has delegated, and the way they have learned to work together — simply because the intelligence provider changes?

**The AI can change. Your personal agent should remain yours.**

Personal AgentOS is an open-source, self-hosted environment exploring that idea: keep the PA's context, unfinished work, authority and evidence in an environment you control, while letting different AI systems work underneath it.

The goal is not another chatbot with a longer history. It is one continuing personal agent.

**Same PA. Different AI.**

> **Current status:** Personal AgentOS is a working exploration, not a finished autonomous assistant. The published build can be installed and used with your own model; the richer meeting, map and shopping scenes below are product direction unless explicitly marked otherwise.

<!-- readme-section:ownership -->

## What stays yours?

The Jarvis thought experiment becomes a concrete design question here: which parts should survive when the intelligence underneath changes?

| | Personal AgentOS |
| --- | --- |
| **Context** | Your PA's retained context lives in your environment |
| **Unfinished work** | Work can remain open instead of disappearing into chat history |
| **AI** | Local, hosted and subscription-backed workers can serve the same PA |
| **Authority** | Access and consequential actions stay bounded by owner control |
| **Evidence** | What actually happened is kept separate from what a model merely said |

Two owner-control mechanisms ship today: when your own AI saves a fact to Memory, it tells you afterwards and offers an exact undo; each Work records which owner information it used and where that information went.

Local-first is not local-only. If you choose a hosted model, the context needed for that request is sent to that provider.

The broader question is simple: **if a better AI appears tomorrow, why should you have to rebuild the agent that already knows how you work?** The strategy whitepaper, [Whose agent?](docs/whitepapers/whose-agent.ko.md), develops that argument.

<!-- readme-section:presence -->

## Try it today

On macOS with [Homebrew](https://brew.sh):

```sh
brew install jongtae/agentos/agentos
agentos start
```

1. The browser setup opens at `http://127.0.0.1:8787`. Choose **바로 시작하기** (Start now).
2. Connect your own model: a tool-capable local Ollama model, OpenAI, an OpenAI-compatible service, Anthropic, or a supported Codex / Claude Code subscription route. Model access is separate.
3. In **설정 → 외부 연결** (Settings → External connections), connect your own Telegram bot with its BotFather token and open the pairing link.
4. Say: **“I need to finish a proposal this week. Help me break it into the next few steps.”**

The setup interface is currently Korean. Keep `agentos start` running while you talk. [QUICKSTART](QUICKSTART.md) covers model setup, file work, Telegram and running from source.

**Published release:** Homebrew installs **v1.1.1** (2026-10-07). The [release manifest](docs/release-manifest.json) records source coverage and installed checks. [Product status](docs/product-status.en.md) separates shipped behavior, fixture evidence, owner-pilot evidence and future direction.

<!-- readme-section:conversation -->

## What the project is reaching for

A personal agent should be able to continue a matter, not just answer the latest prompt.

Imagine saying:

> “Keep track of next week's project meeting. We still need to settle the proposal.”

The PA should be able to connect the meeting to allowed context, keep the unresolved decision open, prepare what comes next, and stop when your authority is required. A draft is not a sent email. An invitation is not an accepted commitment. A model saying something happened is not evidence that it did.

<picture>
  <source media="(max-width: 600px)" srcset="docs/assets/readme/presence-overview.en.narrow.svg">
  <img src="docs/assets/readme/presence-overview.en.svg" alt="Concept figure: an Assistant answers a question, a task agent handles an explicit cart request, and a PA carries an open meeting decision forward. Illustrative product direction, not an observed run or shipped integration.">
</picture>

That continuing relationship is what this project calls **Presence**: not a friendly persona, but continuity across turns, tools, workers, failures and model changes while truth and owner authority remain intact.

The architecture behind that idea is described in [Architecture and ontology](docs/personal-agentos-architecture.en.md) and the [Presence experience contract](docs/presence-experience-contract.en.md).

## Ordinary moments, the same PA

The same idea matters in smaller moments:

> “We’re almost out of coffee.”  
> Hours later: “I’m heading out. Is there somewhere on the way I can pick it up?”  
> Later: “No time. Just get the same one as last time.”

The aspiration is that you keep talking instead of assembling a workflow: the PA carries the relevant context forward, asks only for what is missing, and stops at the boundary where your account or authority is needed.

The image below is a condensed, redacted reconstruction based on owner-pilot conversations. It is **not** a verbatim product screenshot or an evidence record. The map and shopping integrations shown are product direction, not shipped features.

<picture>
  <source media="(max-width: 600px)" srcset="docs/assets/readme/owner-pilot-conversation.en.png">
  <img src="docs/assets/readme/owner-pilot-conversation.en.png" alt="Three reconstructed PA conversations: finding dinner after sharing a location, comparing a golf belt before an account-login handoff, and continuing from a restaurant photo to a nearby walk. Illustrative, not a verbatim product screenshot.">
</picture>

[Open the image at full size](docs/assets/readme/owner-pilot-conversation.en.png) · [View the original reference image](docs/assets/readme/owner-pilot-conversation-reference.jpg)

The common path is:

**what you say or show → allowed context with source and time → useful question or tool → authority boundary → observed result**

<!-- readme-section:try-today -->

## What works now — and what does not

The repository deliberately distinguishes **working software**, **test/fixture evidence**, **owner-pilot observations** and **product direction**.

Today, the published build provides an installable local runtime, model connection, conversation surfaces and source work around owner context, Work continuity, model switching, browser/sign-in handoff, skill routing and Presence behavior. Installed checks establish package installation and local foreground operation.

It does **not** currently claim autonomous purchasing, arbitrary computer use, universal web verification, live inventory or checkout verification, a public agent marketplace, or that the meeting and shopping scenes above work end-to-end in v1.1.1.

For the exact boundary, see [Product status](docs/product-status.en.md). For release-specific evidence, see the [release manifest](docs/release-manifest.json).

<!-- readme-section:more -->

## Explore the project

- [Why this project exists](VISION.md) · [Whose agent?](docs/whitepapers/whose-agent.ko.md) — the product and industry argument for owner-held continuity.
- [Architecture and ontology](docs/personal-agentos-architecture.en.md) · [Presence](docs/presence-experience-contract.en.md) · [Roles and delegation](docs/research/role-ontology-and-mandate-2026-10-05.ko.md) — how context, work, authority and evidence fit together.
- [Research and references](docs/acknowledgements.en.md) — prior work that informed the design.
- [Documentation map](docs/README.md) · [Contributing](CONTRIBUTING.md) — inspect the current contracts, implementation and contribution path.

<!-- readme-section:license -->

## Open source

Personal AgentOS is a working exploration, open for others to run, question, and improve. It does not have to be the final answer to be a useful beginning.

Code: [AGPL-3.0-only](LICENSE). The Personal AgentOS name and logo follow the [trademark notice](TRADEMARKS.md). Third-party work is credited in [acknowledgements](docs/acknowledgements.en.md).

