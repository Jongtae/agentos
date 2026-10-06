# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

<!-- readme-parity:v1 -->
<!-- readme-section:hero -->

## A personal AI environment that stays yours.

**One assistant. Replaceable AI. Owner-controlled memory, context, tools and authority.**

![Two real conversations: a calendar draft that waits for approval, and a saved note found again after a restart](docs/assets/readme/hero.en.png)

These two scenes are observed product behaviour from the published v1 line, condensed and translated from Korean replies. Personal AgentOS runs on your own computer and keeps the owner state and authority layer separate from the AI worker. Local-first is not local-only: a model can be local or hosted; with a hosted model, permitted context goes to that provider.

<!-- readme-section:concept -->

## The idea in one sentence

> 내가 설치하고 통제하는 개인 AI 환경에서, 좋은 기본 기능으로 실제 일을 끝내고, 더 좋은 에이전트를 앱처럼 설치·교체해도 내 기억과 결과는 나에게 남는다.
>
> *A personal AI environment I install and control: good built-in abilities finish real work, and even when I install or swap in better agents like apps, my memory and results stay with me.*

The author's sentence, in the original Korean. Why the project exists and the documents that define the concept are gathered on one page: [VISION.md](VISION.md).

<!-- readme-section:working-software -->

## Working software, not only a concept

The repository now contains substantially more than the published v1.1.0 build. On `main`, the assistant is being exercised as a continuous secretary over replaceable Main AI and Judgment AI routes, durable Memory, Telegram conversation, contextual capability handoff, search/browser mediation, preparations and evidence-qualified recovery.

Evidence is deliberately separated:

- **Published release:** published release has installed-smoke and synthetic journey evidence recorded in the release manifest. It does **not** contain everything now on `main`.
- **Current `main`:** merged code and deterministic/fixture evidence support newer Secretary, Presence, Decision and execution contracts. A merged contract or test is not by itself a live-service claim.
- **Owner pilot:** some newer paths have been exercised in the owner's real Telegram/desktop environment. Public screenshots will be added only when the exact examples are selected, redacted and tied to their observed revision.
- **Direction:** shopping, booking and other future scenes remain product direction until implementation and evidence support a stronger claim.

See [what works and how we know](docs/product-status.en.md), the [release manifest](docs/release-manifest.json), and the [documentation map](docs/README.md).

<!-- readme-section:try-today -->

## Install

```sh
brew install jongtae/agentos/agentos
agentos start
```

You will see:

```text
AgentOS: http://127.0.0.1:8787/
초기 설정 링크: /Users/you/.local/share/agentos/private/setup-link.txt (개인 파일)
```

The browser opens on that address. Press **바로 시작하기** (Start now), connect a model, and you are talking to it. The interface is in Korean today; it understands requests in Korean or English.

**Homebrew installs the newest published release, `published release` (2026-09-23).** The release scenes below are limited to what that build carries. Newer Secretary/Presence/orchestration work on `main` is not in published release; for the newest code run from a source checkout (`git clone https://github.com/Jongtae/agentos.git`, then `python3 -m pip install -e .` on Python 3.12 or newer). [QUICKSTART](QUICKSTART.md) has every step.

<!-- capability:current-supported-slice -->
<!-- readme-section:scenes-today -->

## Then try these

![Five everyday requests that run today, and one after a restart](docs/assets/readme/scenes.en.png)

The journeys behind these were run end to end by the project's automated first-user check, against a local folder and stand-in mail, calendar and web services rather than live accounts. The wording is the wording that routes today.

- **Files.** *Summarize “Launch review” and save it as “Launch notes”.* It reads the folder you allowed, writes a new note into the workspace folder you chose and leaves the original untouched.
- **Mail.** *Find anything about the budget in my mail.* It searches only the mailbox you connected and shows what it found.
- **Calendar.** *Schedule a dentist appointment tomorrow at 3.* It shows an exact draft and creates the event only after you say approve. “Make it 4pm” and “cancel” work on the same draft.
- **Memory in published release.** *Remember that I have a peanut allergy.* The published build keeps durable memory and candidate review. **Current `main` has moved on:** the owner's own AI saves an eligible non-secret fact, tells you what it remembered and offers bounded undo; a third-party/delegated writer still uses the candidate/approval path.
- **Research.** *Look up these two products and compare them.* It searches, reads up to three public pages from that search, and returns what they say, what stayed unknown, and the links.

Then restart the app and ask *Find “Launch notes” in my saved results.* The saved result, the folders you allowed, memory and Telegram pairing survive the restart.

<!-- readme-section:settings -->

## The settings you will need

- **A model.** A local Ollama server, an OpenAI-compatible endpoint or Anthropic, with your own access. The file scene needs one of these direct connections.
- **Two folders.** In **내 에이전트 관리 → 내 자료**: one reference folder it may read, one workspace folder it may write into. Nothing outside them. With a hosted model you approve document sharing once before the file scene.
- **Mail and calendar, optional.** Your own Google account through a Google Cloud OAuth client you create, one setup command each (`agentos gmail-config`, `agentos calendar-config`), then connect read and write separately. QUICKSTART has the exact steps.
- **Telegram, optional.** Your own bot token from BotFather, pasted in Settings, then open the pairing link. Only your paired account can talk to it.

That is all of it.

<!-- readme-section:more -->

## More

[What works and what still has friction](docs/product-status.en.md) · [Where this is going](docs/product-status.en.md#where-this-is-going) · [Why this is different](docs/product-status.en.md#why-this-is-different) · [Under the hood](docs/product-status.en.md#under-the-hood-briefly) · License [AGPL-3.0-only](LICENSE) and [trademark notice](TRADEMARKS.md) · [How it is built](AGENTS.md) · [Acknowledgements and references](docs/acknowledgements.en.md)
