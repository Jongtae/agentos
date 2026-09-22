# AgentOS — install, configure, talk

AgentOS is a self-hosted personal agent preview. One local process serves a Korean web setup and chat interface. Docker and Kubernetes are not required. Homebrew installs Python automatically; model runtimes and model weights are separate.

## Current use versus planned work

The current owner test remains the small file-workspace journey below: configure a supported direct provider, explicitly grant a reference folder and output workspace, save a result, restart and find it again. DOGFOOD-01's repository evidence uses simulated providers and temporary files; actual owner browser/provider operation is a separate test. Check the installed revision when comparing a released Homebrew build with current source; a merged documentation PR is not a new application release.

[USE-01 / #358](https://github.com/Jongtae/personal-agentos/issues/358) is prepared to improve ordinary research, substantive file results and follow-up continuity. It does not run merely because its issue exists. Public full-page reading, measured 24-case model quality, the expanded receipt/control UX and v0.1 agent installation are **not delivered by the preparation**. Current public search returns snippets, not full-page/inventory/checkout proof. The [usefulness specification](docs/default-agent-usefulness.en.md) separates deterministic development tests from live-quality promotion; an unrun live gate is pending, not passed.

[Owner control requirements](docs/owner-control-contract.en.md) describe implemented versus planned boundaries. A local install can use an external model; approve only the data/destinations you intend. No ticket/cart/booking/payment, account creation or new external action is part of the recommended test. Do not publish private documents, credentials or full tool payloads as repository evidence.

## Install on macOS

Install Homebrew from [brew.sh](https://brew.sh) if needed, then:

```sh
brew install jongtae/agentos/agentos
agentos start
```

The browser opens at `http://127.0.0.1:8787`. Click **바로 시작하기** (Start now). There is no setup code to enter. A login password is optional for local use; expand **비밀번호 설정 · 선택** to set one (12+ characters). Without a password, anyone using this computer can access the agent through its local address.

For a ChatGPT/Codex subscription, install and log in to the official Codex CLI first (`codex login`), then select **Codex 로그인 완료 · 연결** in AgentOS. AgentOS records only your confirmation; it does not request, read, or store the Codex login. A connected subscription engine receives only the bounded AgentOS tools, not your local files, credentials, or arbitrary shell access. Alternatively, choose a model provider, endpoint and model name, then use Save and Test connection. API keys stay in a private local file. Cloud requests send conversation content to your selected provider.

Supported connections: Ollama (an already running local model server), OpenAI-compatible Chat Completions endpoints, and Anthropic Messages. Bring your own model access; no paid model subscription is included.

## First task

In web chat, enter `/note Review the launch on Friday`, then `/notes`. These work without a model. After connecting a model, try `/summarize` or a normal conversation.

## Recommended owner dogfood task

Create two dedicated local folders (for example, `/Users/your-name/AgentOS-dogfood/reference`
and `/Users/your-name/AgentOS-dogfood/workspace`) and place one small Markdown or text note in the
reference folder. Put the words `Launch review` in that note. In **내 에이전트
관리 → 내 자료**, enter the reference folder and workspace folder, then choose a
direct model-provider connection (OpenAI-compatible, OpenAI, Anthropic, or
Ollama) and complete its connection test; subscription engines do not run this
file-workspace path. If the selected provider is external, approve document
sharing before submitting the task. Ask the chat:
`“Launch review” 자료를 요약해 “Launch notes”로 저장해줘`. Confirm that a
Markdown result appears only in the managed workspace and that the original note
is unchanged. Stop AgentOS with Ctrl-C, run `agentos start` again, and ask
`저장된 작업공간에서 “Launch notes” 찾아줘` to reuse the saved result.

This local test uses a real folder and a real provider only when you supply the
provider credentials. Repository tests use a simulated provider and do not prove
live external-provider operation. After this bounded smoke test, record useful-result quality,
missing facts, awkward clarifications and failures; the exact sample phrase is not a claim that
all natural-language requests work. Share redacted observations, not private documents.

## Telegram

Create your own bot using Telegram's BotFather, paste its token into Settings, and open the generated pairing link in your own Telegram account. Only the paired private account can submit work. The web interface and Telegram share conversation history and notes. AgentOS uses outbound polling, so no public inbound port is needed for Telegram. Use a dedicated bot without an existing webhook.

The computer must remain running and awake for remote requests to be processed. From a source checkout you can register a background login service instead of holding a terminal open; see [Background service (macOS)](#background-service-macos) for exactly what that does and does not cover. Without that service, keep the terminal open; Ctrl-C stops AgentOS.

## Restart and update

```sh
agentos start
# Stop the process before upgrading:
brew update
brew upgrade jongtae/agentos/agentos
agentos start
# View only credential-free setup and recovery state:
agentos guide
```

If you registered the background login service from a source checkout, run `agentos service upgrade` after replacing the executable rather than relying on the foreground command.

Data persists in `~/.local/share/agentos`; uninstalling the formula does not delete it. Back up the entire data directory while AgentOS is stopped. This directory contains your private conversations and credentials; credentials have filesystem permissions, not application-level encryption.

If the browser does not open, use the link in `~/.local/share/agentos/private/setup-link.txt` locally. Do not share that file before setup. After setup, open `http://127.0.0.1:8787`; log in only if you chose a password. An occupied port can be changed using `agentos start --port 8788`. After an unexpected stop, AgentOS marks in-progress work as interrupted and an in-flight Telegram send as unknown; it never silently repeats either. Review the web record and submit a new request if needed. `agentos guide` shows counts and next steps only, never task text or credentials.

## Background service (macOS)

`agentos start` runs in the foreground. On macOS the same executable can instead be
registered as a per-user launchd login service, so Telegram and web requests are handled
without an interactive terminal session:

```sh
agentos service install    # register and start the login service
agentos service status     # report the observed launchd state and health
agentos service restart
agentos service stop       # stop and persistently disable it
agentos service uninstall  # remove the registration; owner data is retained
agentos service upgrade    # replace an existing definition, rolling back on failure
```

From a source checkout the same actions are available as
`python3 -m personal_agent.quickstart service <action>`. `install` and `upgrade` must record
an absolute path to the executable launchd will run; they resolve `agentos` from `PATH` and
then from the Homebrew prefix, so from a source checkout either install the console script
(`pip install -e .`) or pass `--cli-path /full/path/to/agentos` explicitly. Use `--data` only
to override the data directory: with no `--data`, the other actions report the directory
recorded in the installed service definition.

Each action prints the receipt it actually observed and exits non-zero when the operation
did not succeed. A refused, unhealthy or unreadable service is reported as a failure with a
`next_action`, never as a success: `background_available` is reported only when a running
process also passed the loopback health check. `uninstall` removes only the service
registration and never deletes `~/.local/share/agentos`. The service definition is bound to
loopback and sets `RunAtLoad`/`KeepAlive`, so it is designed to start again at login.

What this does **not** yet cover, stated exactly:

- **macOS only.** The lifecycle is launchd-specific. There is no systemd equivalent here.
- **Not in any released build.** The most recent release tag is `v1.0.4` (2026-09-07), which
  predates this command, and this repository contains no Homebrew formula, tap or checksum.
  `brew install` / `brew upgrade jongtae/agentos/agentos` will not provide `agentos service`
  until a later release; today it is reachable only from a source checkout.
- **Not covered by automated tests of real launchd.** Repository CI runs on Linux and cannot
  execute launchd. The automated evidence for these commands is injected-runner tests that
  substitute `launchctl`. A real Homebrew install, a real login service surviving a machine
  restart, and an end-to-end Telegram result with no terminal open are owner operating
  validation that this repository has not performed.

## Remote host / source installation

Python 3.12+ on macOS or Linux is required for source execution:

```sh
python3 -m personal_agent.quickstart start --no-browser
```

On a remote host, keep the default loopback binding and connect through SSH forwarding (`ssh -L 8787:127.0.0.1:8787 your-host`). Open the setup link through that tunnel. Public managed hosting, TLS termination, mobile apps and Kubernetes packaging are future deployment work.

## Preview scope

Implemented paths include single owner, password login, model adapters, persistent chat/notes, queued requests, private Telegram pairing/deduplication, connected TXT/Markdown/PDF/DOCX/XLSX folders with sources, explicit external-model document approval, Docker Compose and backup/restore scripts. Each path's actual operating evidence remains scoped to its recorded revision/configuration. Interrupted model work and uncertain Telegram delivery are shown without automatic replay.

Arbitrary shell, native desktop/mobile apps, managed unattended installation, multi-user hosting and the complete AgentPackage ecosystem are not this preview. Calendar/Drive-related design or mock-validated code elsewhere in the repository is not proof of a currently configured live integration. See the [roadmap](docs/roadmap.md) for exact historical and planned states.

## Advanced: local manifest plugins

Declaration-only plugins can add only the bounded host actions AgentOS already
supports; they never execute third-party code. They are the legacy declaration path,
not proof of the planned v0.1 AgentPackage installer or arbitrary binary support.
Install a reviewed manifest and manage it from the same local data directory:

```sh
agentos plugins install /path/to/manifest.json
agentos plugins list
agentos plugins disable example-plugin
agentos plugins remove example-plugin
```

Tests use simulated provider and Telegram responses, plus a real local HTTP server for setup/chat/authentication. Live provider and Telegram testing requires your credentials and explicit operating scope.

Source and Homebrew formula: [Jongtae/homebrew-agentos](https://github.com/Jongtae/homebrew-agentos).

## Historical general tool runtime (0.2.0)

The following describes that release's recorded behavior and limits, not a new live
acceptance or a promise that its limits match every later source revision.

Normal messages use a shared native tool-call loop. The model selects from web search,
weather, connected-folder search/read, personal notes, and built-in researcher/reviewer
agents. No keyword rule forces weather or search. OpenRouter's free router chooses a
model for each request; that model is kept for the remainder of the tool loop.
Free-provider availability and quotas can still interrupt a request; failures are shown.

Under **연결 설정 → 내 파일 연결**, register specific folders on the AgentOS host.
Connected UTF-8 TXT/Markdown, PDF, DOCX, and XLSX files up to 1 MB are supported
(16,000 characters per read). For cloud models, document search and excerpts are
blocked until the owner approves the current model-and-folder scope; the approval
is cleared when either changes. Mobile clients access the host's connected folders.

Try these in the same conversation:
- “Kubernetes 공식 문서를 검색해 줘.”
- “내 파일에서 Aurora 출시 계획을 찾아서 읽어 줘.”
- “그 내용을 검토 에이전트에게 전달해 줘.”
- “이제 도구 없이 안녕이라고만 답해 줘.”
- “출시 검토가 필요하다고 메모해 줘.”

Specialists run separate conversations with the configured model provider and read-only
tools. They are not external Codex/Claude Code processes. Recursive delegation and
shell commands are unavailable. **최근 도구 실행 기록** shows actual tool execution.

`python3 -m unittest discover -s tests -q` checks local contracts and errors.
`scripts/verify_general_agent.py` runs live multi-topic acceptance with the configured
provider in a temporary store; `--installed` verifies the Homebrew installation.
It creates a synthetic local document and never changes personal chat or notes.
Run a live verifier only after explicitly choosing provider/data scope and budget;
its historical result is not the new USE-01 24-case quality gate.
