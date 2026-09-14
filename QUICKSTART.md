# AgentOS — install, configure, talk

AgentOS is a self-hosted personal agent preview. One local process serves a Korean web setup and chat interface. Docker and Kubernetes are not required. Homebrew installs Python automatically; model runtimes and model weights are separate.

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
live external-provider operation.

## Telegram

Create your own bot using Telegram's BotFather, paste its token into Settings, and open the generated pairing link in your own Telegram account. Only the paired private account can submit work. The web interface and Telegram share conversation history and notes. AgentOS uses outbound polling, so no public inbound port is needed for Telegram. Use a dedicated bot without an existing webhook.

The computer must remain running and awake for remote requests to be processed. This preview does not install a background login service. Keep the terminal open; Ctrl-C stops AgentOS.

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

Data persists in `~/.local/share/agentos`; uninstalling the formula does not delete it. Back up the entire data directory while AgentOS is stopped. This directory contains your private conversations and credentials; credentials have filesystem permissions, not application-level encryption.

If the browser does not open, use the link in `~/.local/share/agentos/private/setup-link.txt` locally. Do not share that file before setup. After setup, open `http://127.0.0.1:8787`; log in only if you chose a password. An occupied port can be changed using `agentos start --port 8788`. After an unexpected stop, AgentOS marks in-progress work as interrupted and an in-flight Telegram send as unknown; it never silently repeats either. Review the web record and submit a new request if needed. `agentos guide` shows counts and next steps only, never task text or credentials.

## Remote host / source installation

Python 3.12+ on macOS or Linux is required for source execution:

```sh
python3 -m personal_agent.quickstart start --no-browser
```

On a remote host, keep the default loopback binding and connect through SSH forwarding (`ssh -L 8787:127.0.0.1:8787 your-host`). Open the setup link through that tunnel. Public managed hosting, TLS termination, mobile apps and Kubernetes packaging are future deployment work.

## Preview scope

Implemented: single owner, password login, model adapters, persistent chat and notes, queued requests, private Telegram pairing and deduplication, connected TXT/Markdown/PDF/DOCX/XLSX folders with source evidence, explicit external-model document sharing approval, Docker Compose, and backup/restore scripts. Interrupted model work and uncertain Telegram delivery are shown without automatic replay.

Not yet implemented: arbitrary shell execution, calendar/email integrations, native desktop/mobile applications, managed unattended installation, or multi-user hosting. This is the first installation-to-task slice, not the complete AgentOS ecosystem.

## Advanced: local manifest plugins

Declaration-only plugins can add only the bounded host actions AgentOS already
supports; they never execute third-party code. Install a reviewed manifest and
manage it from the same local data directory:

```sh
agentos plugins install /path/to/manifest.json
agentos plugins list
agentos plugins disable example-plugin
agentos plugins remove example-plugin
```

Tests use simulated provider and Telegram responses, plus a real local HTTP server for setup/chat/authentication. Live provider and Telegram testing requires your credentials.

Source and Homebrew formula: [Jongtae/homebrew-agentos](https://github.com/Jongtae/homebrew-agentos).

## General tool runtime (0.2.0)

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
