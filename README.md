# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

<!-- readme-parity:v1 -->
<!-- readme-section:hero -->

## The personal assistant we wanted

We should be able to pick up yesterday’s conversation, share half a thought, and carry unfinished work forward without explaining our lives all over again. And we should be able to trust the environment that holds that knowledge.

**Personal AgentOS explores how to build that kind of personal assistant (PA) in an environment you install and control.**

Assistants answer questions. Computer agents carry out commands. A personal agent should also stay with you across conversations, tasks and changes of AI. We call that continuity **Presence**.

<!-- readme-section:ownership -->

## Your assistant, on your terms

The more an assistant knows about your life, the more it matters who holds its memory and decides what it can do. Your relationship with it should outlast a provider, a model or a chat session.

AgentOS keeps memory, work and authority in your environment. You choose the AI, the information it can use and the access you give it. Better AI should make your assistant more capable without making you start over.

Local-first is not local-only: you can use a local or hosted model. With a hosted model, the context used for a request is sent to that provider.

<!-- readme-section:presence -->

## What makes continuity possible

Presence needs more than a long chat history. The assistant needs to connect what it knows about you, what is happening now, what you are working on, what you have allowed and what actually happened.

AgentOS gives these things a shared structure—its **ontology**. A piece of work links its context, permissions, results and evidence. A new event or correction can inform what happens next. So when the AI changes or work is interrupted, what it knew and where to continue can remain available.

<picture>
  <source media="(max-width: 600px)" srcset="docs/assets/readme/presence-overview.en.narrow.svg">
  <img src="docs/assets/readme/presence-overview.en.svg" alt="Concept illustration: Assistant answers a question about NVIDIA; a computer agent acts on an Amazon command; Personal AgentOS carries a conversation over time. You talk to one PA, with context, work and authority held in AgentOS above replaceable AI and tools. The coffee sequence illustrates product direction, not an observed run or shipped integrations.">
</picture>

AgentOS uses its judgment layer to choose AI and tools and check their results. You talk to the PA while AgentOS carries that structure underneath the conversation. **Same PA. Different AI.**

<!-- readme-section:conversation -->

## A conversation that carries on

> “We’re almost out of coffee.”<br>
> Hours later: “I’m heading out. Is there somewhere on the way I can pick it up?”<br>
> Later: “No time. Just get the same one as last time.”

The aspiration is simple: the PA follows what “it” and “the same one” mean, brings in relevant context, and asks for missing information or authority when needed. You keep talking; you do not assemble a workflow.

*Illustrative product direction, not an observed live run or a shipped shopping integration.*

<!-- readme-section:try-today -->

## Try it

On macOS with [Homebrew](https://brew.sh):

```sh
brew install jongtae/agentos/agentos
agentos start
```

1. The browser opens at [http://127.0.0.1:8787](http://127.0.0.1:8787/). Choose **바로 시작하기** (Start now).
2. Connect and test your own model: a tool-capable local Ollama model, or OpenAI, an OpenAI-compatible service or Anthropic with your API access. The setup interface is currently Korean.
3. Start a conversation: **“Help me think through what to focus on this week.”**

Homebrew installs Python for you; model access is separate. [QUICKSTART](QUICKSTART.md) covers model setup, file work, Telegram and running the newest code from source.

**Where it stands:** Homebrew installs **v1.1.0** (2026-09-23), an earlier preview. Newer Presence work on `main` is not included in this release. Calendar creation is unavailable in that release and research is partial; see the [release manifest](docs/release-manifest.json). [Product status](docs/product-status.en.md) separates what is available, what has been tested and what remains a goal.

<!-- readme-section:more -->

## Explore the ideas

- [Why this project exists](VISION.md) — the relationship with computers this project is trying to make possible.
- [Architecture and ontology](docs/personal-agentos-architecture.en.md) · [Presence](docs/presence-experience-contract.en.md) — how personal state, work and control support one continuing assistant.
- [Research and references](docs/acknowledgements.en.md) — the work on personal agents, memory, owner models and provenance that informed the design.
- [Documentation map](docs/README.md) · [Contributing](CONTRIBUTING.md) — find the current contracts, inspect the implementation and help develop it.

<!-- readme-section:license -->

## Open source

This is a working exploration, open for others to run, question and improve. It does not have to be the final answer to be a useful beginning.

Code: [AGPL-3.0-only](LICENSE). The Personal AgentOS name and logo follow the [trademark notice](TRADEMARKS.md). Third-party work is credited in [acknowledgements](docs/acknowledgements.en.md).
