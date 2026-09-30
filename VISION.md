# Why Personal AgentOS Exists

Personal AgentOS is not an attempt to build the final personal AI assistant.

It is an attempt to explore, in working software, what a personal AI assistant could and should become.

Today, using a computer still means that a person must understand applications, interfaces, accounts, files, permissions, and workflows well enough to translate an intention into a sequence of operations. AI assistants can answer remarkably difficult questions, but they still often stop at the boundary between understanding what a person wants and actually helping them carry it through.

I want to explore a different relationship with computers.

A personal assistant should be able to understand an ordinary request, use the context and tools the owner has allowed, find a reasonable way forward, ask for authority when authority is actually needed, recover honestly when something fails, and continue the same relationship across tools, models, restarts, and tasks.

The complexity underneath may be substantial. The owner should not have to become the operator of that complexity.

## One assistant, many capabilities

Personal AgentOS may use different models, runtimes, tools, connectors, and specialist agents. Those are implementation details and replaceable workers.

The person using the system should experience one continuous assistant.

That continuity must not be an illusion built from friendly language. It has to be supported by real context, memory, permissions, recoverable work, and evidence of what actually happened.

The goal is not anthropomorphic theater. The goal is useful continuity.

## The owner remains the authority

An assistant that can act is useful only if the person it serves remains in control.

Personal AgentOS therefore treats authority, truthfulness, and inspectability as structural requirements rather than interface decorations.

The assistant should be able to do more without quietly acquiring the right to do everything.

It should distinguish understanding from permission, a proposed action from an executed action, success from partial success, and failure from an outcome that is simply unknown. Important external effects should remain attributable and inspectable.

Natural interaction and strict execution boundaries are not opposing goals. The project exists partly to explore how to make both true at the same time.

## Conversation first, machinery underneath

The internal system may need durable work records, events, evidence, grants, connectors, retries, and specialist runtimes.

Those concepts matter. They make the system reliable.

But they are not the relationship the user came for.

The ordinary experience should be closer to:

`my request → the assistant understands → asks when necessary → works → verifies → continues the conversation`

Technical receipts should remain available when they are useful, without turning every conversation into an operations console.

## Why open source

I do not expect to build the final form of a personal AI assistant alone.

The problem is too large, the possible directions are too numerous, and the best ideas will not all come from one person or one project.

That is one reason Personal AgentOS is open source.

My hope is to create a seed: something concrete enough to demonstrate a different relationship between people and computers, rigorous enough to be tested rather than merely imagined, and open enough that other people can question it, improve it, replace parts of it, fork it, or take its ideas somewhere I never could.

Maybe Personal AgentOS itself grows into that system.

Maybe something descended from it does.

Maybe most of the code eventually disappears and only a few ideas survive.

Any of those outcomes can still be worthwhile.

## What success means

Success is not measured only by whether this repository becomes the final product.

If this project can make the idea tangible—if it can show that a personal AI assistant can be capable without taking ownership away from its user, continuous without pretending to be human, and useful without exposing all of its machinery—then it has already contributed something.

The implementation should keep changing as reality teaches us where the idea is wrong.

The principles should be challenged by actual use, not protected from it.

This repository is an attempt to turn an ideal into something that can be run, criticized, measured, and continued by others.

**It does not have to be the final answer. It should be a meaningful beginning.**

---

## The concept on one page

This page is the entry point to the concept. Each idea below links to the document that defines it. Those documents govern; this list only points to them.

- **A secretary, not a chatbot.** One personal agent for one owner. It keeps the owner's preferences, situation and history in view and reaches the owner's goals through replaceable capabilities. See the [Secretary Agency Contract](docs/secretary-agency-contract.en.md).
- **AI is the engine.** The owner's chosen AI does the work: Codex, Claude Code or a configured model API. A decision model chooses the worker, writes the brief, checks the result and re-delegates when the goal is not met. AgentOS code never implements a specific request. See [C16 in the Development Constitution](docs/development-constitution.en.md).
- **The owner's state stays with the owner.** Memory, context, permissions, work records and evidence belong to AgentOS and the owner, not to whichever model or agent does the work. See the [architecture](docs/personal-agentos-architecture.en.md) and the [Owner Control Contract](docs/owner-control-contract.en.md).
- **Conversation first.** The owner manages AgentOS by talking to it. A page appears only for a result that text cannot carry, or an input that conversation cannot safely carry. See the [Presence Experience Contract](docs/presence-experience-contract.en.md).
- **Few protections, each one real.** During the pilot two rules hold on every request: secrets never reach a model, a log or Evidence, and each payment needs the owner's approval. Instead of more guards, each Work is to show which owner information it used and where it went. See the [pilot posture](docs/secretary-agency-contract.en.md#pilot-posture).
- **Installable agents, later.** In the long run, better agents can be installed and replaced like apps without taking the owner's memory or authority with them. See the [Agent Distribution Platform Foundation](docs/agent-distribution-platform-foundation.en.md).

What works today, and how we know, is on the [product status](docs/product-status.en.md) page. Earlier concept documents that this page replaces are kept in the [concept archive](docs/archive/concepts/README.md).
