# AgentOS — install, configure, talk

AgentOS is a self-hosted personal agent preview. One local process serves browser setup and task records; conversations take place in your paired Telegram chat. The browser screens are in English by default, with Korean, Simplified Chinese and Japanese selectable; some fixed Telegram status/progress lines and certain connection validation errors are still Korean. Docker and Kubernetes are not required. Homebrew installs Python automatically; model runtimes and model weights are separate.

## Current use versus planned work

The current owner test remains the small file-workspace journey below: configure a supported direct provider, explicitly grant a reference folder and output workspace, save a result, restart and find it again. DOGFOOD-01's repository evidence uses simulated providers and temporary files; actual owner browser/provider operation is a separate test. Check the installed revision when comparing a released Homebrew build with current source; a merged documentation PR is not a new application release.

[USE-01 / #358](https://github.com/Jongtae/agentos/issues/358) is prepared to improve ordinary research, substantive file results and follow-up continuity. It does not run merely because its issue exists. Public full-page reading, measured 24-case model quality, the expanded receipt/control UX and v0.1 agent installation are **not delivered by the preparation**. Current public search returns snippets, not full-page/inventory/checkout proof. The [usefulness specification](default-agent-usefulness.en.md) separates deterministic development tests from live-quality promotion; an unrun live gate is pending, not passed.

[Owner control requirements](owner-control-contract.en.md) describe implemented versus planned boundaries. A local install can use an external model; approve only the data/destinations you intend. No ticket/cart/booking/payment, account creation or new external action is part of the recommended test. Do not publish private documents, credentials or full tool payloads as repository evidence.

## Install on macOS or Linux

One command installs and starts AgentOS. You do not need Homebrew, Python, Docker or git:

```sh
curl -LsSf https://raw.githubusercontent.com/Jongtae/agentos/main/scripts/install.sh | sh
```

The [installer](../scripts/install.sh) first downloads the published release archive and checks its SHA-256 against the [release manifest](release-manifest.json); on a mismatch it installs nothing. If you do not already have a current [uv](https://docs.astral.sh/uv/), it installs a pinned version through Astral's official installer, which adds `~/.local/bin` to your shell `PATH`. It then installs AgentOS with a uv-managed Python, ignoring your own uv settings, and starts it. Set `AGENTOS_NO_START=1` to install without starting. Later, open a new terminal and run `agentos start`. Running the same command again after a release updates AgentOS. `uv tool uninstall personal-agentos` removes the program and keeps your data.

If you use Homebrew on macOS, this installs the same release:

```sh
brew install jongtae/agentos/agentos
agentos start
```

The browser opens at `http://127.0.0.1:8787`. Click **바로 시작하기** (Start now). There is no setup code to enter. A login password is optional for local use; expand **비밀번호 설정** to set one (12+ characters). Without a password, anyone using this computer can access the agent through its local address.

Connect the AI subscription you already have:

- **ChatGPT plan → Codex.** Install the official Codex CLI and log in (`codex login`), then select **Codex 로그인 완료 · 선택** in AgentOS (**전환** when switching from another subscription engine). AgentOS records only your confirmation; it does not request, read, or store the Codex login.
- **Claude plan → Claude Code.** Install Claude Code, run `claude setup-token`, and paste the token into the Claude Code token field once. AgentOS keeps it in this computer's private credential store and passes it only to Claude Code.

A connected subscription engine receives only the bounded AgentOS tools, not your local files, credentials, or arbitrary shell access. Requests send conversation content to OpenAI or Anthropic. No paid subscription is included with AgentOS.

### Other model connections

AgentOS can also use a direct model connection: Ollama (an already running local model server), OpenAI-compatible Chat Completions endpoints, or OpenAI and Anthropic API keys. Choose a provider, endpoint and model name, test the settings, and apply the successful configuration. API keys stay in a private local file. Results depend heavily on how well the chosen model uses tools, so start with a subscription if you can.

## Windows (WSL2)

AgentOS does not run natively on Windows yet ([#1168](https://github.com/Jongtae/agentos/issues/1168)). It runs in WSL2, the Linux environment built into Windows 10 and 11:

1. In PowerShell, run `wsl --install`, then restart Windows.
2. Open **Ubuntu** from the Start menu and create your Linux user name and password.
3. In Ubuntu, run the install command from [Install on macOS or Linux](#install-on-macos-or-linux).
4. If no browser window opens, open `http://127.0.0.1:8787` in your Windows browser. WSL2 forwards that local address to Windows.

Things that differ from macOS:

- A Codex or Claude Code subscription must be installed and logged in inside Ubuntu, not in Windows.
- Windows folders appear under `/mnt/c/`, for example `/mnt/c/Users/your-name/Documents/AgentOS`.
- Keep the Ubuntu window open while you talk. The background login service and the embedded browser tool are macOS only for now ([#682](https://github.com/Jongtae/agentos/issues/682)).

## First task

After connecting and testing your model, [pair your Telegram bot](#telegram), then talk in that Telegram chat as you normally would: “Cat hair everywhere; cleaning my small studio is a pain.” Without being asked, it keeps what matters and tells you what it kept, with an undo. Later, just ask: “Find me a robot vacuum under $500.” The answer should account for the cat and the studio without your repeating them. The browser is where you configure connections and inspect task records. For a model-free check after pairing, `/note Review the launch on Friday` followed by `/notes` saves and lists a note.

## Recommended owner dogfood task

Create two dedicated local folders (for example, `/Users/your-name/AgentOS-dogfood/reference`
and `/Users/your-name/AgentOS-dogfood/workspace`) and place one small Markdown or text note in the
reference folder. Put the words `Launch review` in that note. In **설정 → 파일 · 저장**
(Settings → Files · storage), enter the reference folder and workspace folder, then choose a
direct model-provider connection (OpenAI-compatible, OpenAI, Anthropic, or
Ollama) and complete its connection test; subscription engines do not run this
file-workspace path. If the selected provider is external, approve document
sharing before submitting the task. Ask in your paired Telegram chat:
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

Create your own bot using Telegram’s BotFather. In `v1.1.0` and later, open **설정 → 외부 연결** (Settings → External connections) in the browser, open **Telegram 연결 설정**, and paste the bot token. **Telegram 연결** saves the token and produces a pairing link. Open **Telegram 열기** in your own Telegram account and press **Start** to pair it. Only that paired private account can submit Telegram work. Send requests in that chat; use the browser to configure connections and inspect the resulting task records. AgentOS uses outbound polling, so no public inbound port is needed for Telegram. Use a dedicated bot without an existing webhook.

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
(`pip install -e '.[mcp-host]'`) or pass `--cli-path /full/path/to/agentos` explicitly. Use `--data` only
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
- **Released from `v1.1.0` (2026-09-23).** The published formula lives in the separate tap
  `Jongtae/homebrew-agentos` — it is not in this repository by design, so its absence from
  `git ls-files` here does not mean no artifact exists. `brew install` / `brew upgrade
  jongtae/agentos/agentos` at `v1.1.0` or later provides `agentos service`; `v1.0.4` and
  earlier do not. See [the release procedure](release.en.md).
- **Not covered by automated tests of real launchd.** Repository CI runs on Linux and cannot
  execute launchd. The automated evidence for these commands is injected-runner tests that
  substitute `launchctl`. The v1.3.0 Homebrew upgrade and foreground smoke were observed
  on the owner's Mac ([release manifest](release-manifest.json)); a real login service
  surviving a machine restart and an end-to-end Telegram result with no terminal open
  remain owner operating validation.

## An agent for a family member (macOS)

Each family member gets their own AgentOS instance on your Mac. An instance has its own memory, folders, approvals and work history, and its own Telegram bot paired to that person. Nothing is shared with your own instance.

**The simplest way is to ask your assistant**, for example "아내 비서 만들어줘". It shows what it will create; tap 👍 (or 적용), and the setup link arrives in the same chat for you to forward. It needs your own AgentOS Telegram bot to be connected, and its **Bot Management Mode** switched on once in the BotFather Mini App. The same setup is also one command:

```sh
agentos family add spouse --display-name "아내 비서"
```

Either way:
- creates and starts the instance;
- opens a temporary HTTPS link through your installed `ngrok` (about 30 minutes);
- sends the link to you on Telegram so you can forward it.

The family member opens the link on their phone:
1. They install Telegram.
2. They tap **텔레그램에서 봇 만들기**. Telegram shows a pre-filled "create bot" screen (Managed Bots); they confirm, and they own the new bot.
3. Your bot fetches the new bot's token, limits the bot to its owner, and hands the token to the instance on this Mac.
4. They tap **비서와 대화 시작**.

The link then closes by itself. Through the link, only the setup page and its status answer, and only with the link's one-time code. Once an instance was set up this way, no tunnel reaches anything else on it: a family instance is not meant to be served through `--public-tunnel-host`. The page tells the family member that the agent runs on your Mac with your AI subscription.

The instance runs on **your** AI route. `family add` copies your main AI and judgment AI settings, with only the keys or tokens those routes use. It copies nothing else: not your Telegram bot, folders, memory or other connections. An instance that already has a route keeps it. If you later change or rotate your AI key, the family instance keeps the old one until you set its route again.

The manual commands below remain available.

```sh
agentos service install --instance spouse --port 8797   # data: ~/.local/share/agentos-instances/spouse
agentos service status  --instance spouse
agentos service uninstall --instance spouse             # data is retained
```

- **Name and port.** The instance name uses lowercase letters, digits and hyphens. The port must be free and must not be 8787. The next port (8798 here) is used for its local handoff.
- **Data directory.** An instance never uses your own data directory or `AGENTOS_DATA`.
- **Setup.** Open `http://127.0.0.1:8797/` and use the setup link in that instance's `private/setup-link.txt`.
  - Codex uses this Mac's Codex login. Claude Code needs its setup token entered once in that instance.
  - Pair the family member's own Telegram bot the same way as in [Telegram](#telegram).
- **Google Calendar and Gmail.** An instance's callbacks use its own port, for example `http://localhost:8797/oauth/calendar/callback` and `.../oauth/gmail/callback`. Add those as authorised redirect URIs in your Google OAuth client.
- **Not yet covered.** The same "not covered" notes as [Background service](#background-service-macos) apply: tests substitute `launchctl`, and a real login service is owner operating validation.

## Google Drive, Gmail and Calendar

**Default: your AI's own Google connection.** Most AIs you can connect already offer a
Google connection of their own. Claude Code has claude.ai connectors, and Codex has ChatGPT
connector plugins. Letting AgentOS work use that connection is planned separately; AgentOS
keeps what was read and why, not the connection itself.

**Optional: your own Google client.** If you want AgentOS itself to hold the connection (for
example because your AI has no Google connection), add one Google OAuth client of your own.
One client covers all three services:

The same steps, with direct links, are in **설정 → 외부 연결 → 자체 Google client → client 만드는 방법**:

1. [Create a project](https://console.cloud.google.com/projectcreate) in Google Cloud.
2. [Enable the Drive, Gmail and Calendar APIs](https://console.cloud.google.com/flows/enableapi?apiid=drive.googleapis.com,gmail.googleapis.com,calendar-json.googleapis.com) in that project.
3. [Get started with Google Auth Platform](https://console.cloud.google.com/auth/overview): enter an app name and your email, and choose *External* as the audience. If *OAuth Overview* already shows, this step is done.
4. In [Branding](https://console.cloud.google.com/auth/branding), enter a home page and a privacy policy URL **that you manage** under *App domain*, add their domain under *Authorized domains*, and save. Without these, *Publish app* stays disabled (Google reports "Missing domain"). For an app only you use, Google does not review these values; to offer the app to others you need a domain you own and a real, published policy page. Do not upload a logo; a logo requires verification.
5. On [Audience](https://console.cloud.google.com/auth/audience), press *Publish app*, then *Confirm*. In *Testing*, Google expires the connection every 7 days.
6. [Create a client](https://console.cloud.google.com/auth/clients/create) of type **Desktop app**. Tick *Use this client for an AI-powered agent*, then download its JSON right away; Google shows the secret only at creation.
7. In AgentOS, open **설정 → 외부 연결 → 자체 Google client → client 넣기**, choose the downloaded file (or paste its contents) and save. Alternatively, point `AGENTOS_GOOGLE_CLIENT_FILE` at the file; an environment file wins over the saved one.

Then, on this computer, press **연결** on each service in the same section and approve Google's consent screen. Google consent is done on the desktop; a phone cannot reach this computer's sign-in callback.

| Service | Address | Access |
|---|---|---|
| Google Drive | `http://127.0.0.1:8787/google-drive-connect` | read the whole Drive (`drive.readonly`) |
| Gmail | `http://127.0.0.1:8787/google-gmail` | search and read mail (`gmail.readonly`) |
| Google Calendar | `http://127.0.0.1:8787/google-calendar?grant=read` | read events from every calendar you show in Google Calendar (`calendar.events.readonly`, `calendar.calendarlist.readonly`) |
| Calendar changes | `http://127.0.0.1:8787/google-calendar?grant=write` | create or change events, each after your approval (`calendar.events`) |

Google shows "Google hasn't verified this app" because the client is your own unverified
app. Choose *Advanced → continue*. You are its only user, so Google's verification and its
100-user limit for unverified apps do not apply to you.

After connecting Drive, your AI can search your Drive and read a file. Google Docs, Sheets
and Slides come back as text; PDF, DOCX, XLSX, TXT and MD are extracted on this computer.
The connections keep working after the one-hour Google access token expires, because
AgentOS renews it with the stored refresh token.

What this does and does not do:

- **Read-only Drive and Gmail.** AgentOS cannot change Drive files or send, delete or label
  mail. A calendar change is only drafted, and runs after you approve it.
- **Everything stays on this computer.** The client is kept in the AgentOS secret store.
  Tokens are stored encrypted, with the key in the macOS Keychain. No AgentOS server sits
  between you and Google, and no client ships with AgentOS. On Linux, set
  `AGENTOS_GOOGLE_OAUTH_KEY` to a Fernet key you keep outside the data folder.
- **Replacing the client** applies after AgentOS restarts, and each service must then be
  connected again.
- **A per-service client still wins.** If you configured Gmail or Calendar with a separate
  client (sections below), that configuration is used for that service.

## Google Calendar (source checkout)

AgentOS can read your calendar and draft changes to it, so `내일 일정 뭐 있어?` is
answered and `내일 3시에 회의 잡아줘` produces an exact preview for you to approve. It is
off unless you configure it, and configuring it connects nothing on its own.

**Read and write are two separate connections.** A read grant never becomes a write
grant: they are separate Google authorizations, separate credentials and separate
connector records, and you authorize each one deliberately.

Create a Google Cloud OAuth **web** client, add
`http://localhost:8787/oauth/calendar/callback` as an authorised redirect URI, download
the client JSON, then write the owner-only credential file:

```sh
agentos calendar-config \
  --oauth-client-json ~/Downloads/client_secret_XXXX.json \
  --secret-file /Users/your-name/.agentos-secrets/calendar.json
AGENTOS_CALENDAR_LOCAL_ONLY=1 \
AGENTOS_CALENDAR_SECRET_FILE=/Users/your-name/.agentos-secrets/calendar.json \
  agentos start
```

`calendar-config` behaves exactly like `gmail-config`: the encryption key is generated
locally, the file is `0600` and owned by you, a relative `--secret-file` is refused, and
an existing file is never overwritten. The client secret never becomes a command-line
argument, an environment value or log output.

Then open AgentOS on its local address and connect each grant from the settings page —
`/google-calendar?grant=read` and `/google-calendar?grant=write`. Both routes require
your owner session and refuse a tunnel host.

**What the model can and cannot do.** The model may read your calendar and may draft a
create, update or cancel. It has no tool that applies one. A draft carries the exact
payload that would be sent and its hash; applying it needs a one-time approval bound to
you, that draft, that payload and the current write connection, and only you can issue
that — through `/api/calendar/drafts`, on the local address only. That surface covers
drafts from both your Telegram conversation and the web, because both are you; each
still needs its own write grant. Attendee invitation and recurring events are not
supported and are refused rather than quietly dropped.

Reading your calendar puts event titles in the model's context, so for the rest of that
turn AgentOS refuses public destinations — web search, public page reads, weather —
exactly as it does after reading a connected document.

What this does **not** yet cover, stated exactly:

- **No live Google Calendar operation has been observed.** Every test uses an injected
  transport and a fixture token endpoint. A real OAuth consent, a real event created in
  a real calendar, and the behaviour of a revoked grant are owner validation this
  repository has not performed.
- **Released from `v1.1.0` (2026-09-23).** `v1.0.4` and earlier Homebrew builds do not
  include it; see [the release procedure](release.en.md).
- **The natural-language create path still asks a question.** `내일 3시에 회의 잡아줘`
  parks for a connection and then asks for the missing detail rather than producing a
  draft on its own; ask for the calendar explicitly, or read first and draft from what
  you see.

## Gmail (source checkout)

AgentOS can read and search your Gmail so a request such as
`메일에서 예산 관련 내용 찾아줘` is answered instead of refused. It is off unless you
configure it, and configuring it connects nothing on its own.

Create a Google Cloud OAuth **web** client, add
`http://localhost:8787/oauth/gmail/callback` as an authorised redirect URI, download the
client JSON, then write the owner-only credential file:

```sh
agentos gmail-config \
  --oauth-client-json ~/Downloads/client_secret_XXXX.json \
  --secret-file /Users/your-name/.agentos-secrets/gmail.json
AGENTOS_GMAIL_LOCAL_ONLY=1 \
AGENTOS_GMAIL_SECRET_FILE=/Users/your-name/.agentos-secrets/gmail.json \
  agentos start
```

`gmail-config` is the Gmail counterpart of `drive-config`: it generates the token-store
encryption key locally, writes a `0600` file owned by you, refuses a relative
`--secret-file`, and refuses to overwrite an existing one. The client secret and the
encryption key are never command-line arguments, environment values or log output. The
file must stay outside `~/.local/share/agentos`; otherwise startup fails closed. If you
prefer not to keep a file, the equivalent `AGENTOS_GMAIL_CLIENT_ID`,
`AGENTOS_GMAIL_CLIENT_SECRET` and `AGENTOS_GMAIL_ENCRYPTION_KEY` environment values are
still read, but the file is the supported boundary.

Then connect, from this computer's browser: **설정 → 외부 연결 → Google 연결 → 연결하기**,
or open `http://127.0.0.1:8787/google-gmail` in the same browser where you already
use AgentOS. Google asks you to approve read-only Gmail
access; AgentOS records the scope Google actually granted. If you asked for something over
Telegram that needs Gmail, the reply names the connection you need and carries this same
address, and the original request is resumed exactly once after you connect.

What this does **not** claim, stated exactly:

- **No live Google OAuth has been observed.** The automated evidence is a fixture token
  endpoint and a fixture Gmail transport inside the repository suite. A real Google
  consent screen, a real token exchange and a real message list are owner operating
  validation this repository has not performed.
- **Read-only.** The only scope requested is `gmail.readonly`, and the connection is
  recorded only if Google grants exactly that. AgentOS cannot send, reply to, delete,
  label or archive mail, and nothing here authorises a Calendar, Drive or send scope.
- **Released from `v1.1.0` (2026-09-23).** `brew install` / `brew upgrade
  jongtae/agentos/agentos` at `v1.1.0` or later provides `agentos gmail-config` and the
  Gmail route; `v1.0.4` and earlier do not.
- **Connecting is a separate decision from configuring.** Writing the credential file only
  lets this installation *offer* Gmail. It issues no grant, and the connector stays
  disconnected until you complete the authorisation yourself. The start route requires
  your local AgentOS session and refuses a tunnel host, so Gmail cannot be connected from
  a phone over the mobile pairing link.
- **Local install is not local-only processing.** Gmail metadata read this way is handled
  locally, but if you have connected an external model provider, answering a mail question
  can send that content to the provider you chose.

## Remote host / source installation

Python 3.12+ on macOS or Linux is required for source execution:

```sh
python3 -m personal_agent.quickstart start --no-browser
```

On a remote host, keep the default loopback binding and connect through SSH forwarding (`ssh -L 8787:127.0.0.1:8787 your-host`). Open the setup link through that tunnel. Public managed hosting, TLS termination, mobile apps and Kubernetes packaging are future deployment work.

## Preview scope

Implemented paths include single owner, password login, model adapters, persistent chat/notes, queued requests, private Telegram pairing/deduplication, connected TXT/Markdown/PDF/DOCX/XLSX folders with sources, explicit external-model document approval, Docker Compose and backup/restore scripts. Each path's actual operating evidence remains scoped to its recorded revision/configuration. Interrupted model work and uncertain Telegram delivery are shown without automatic replay.

Arbitrary shell, native desktop/mobile apps, managed unattended installation, multi-user hosting and the complete AgentPackage ecosystem are not this preview. Calendar/Drive-related design or mock-validated code elsewhere in the repository is not proof of a currently configured live integration. See the [roadmap](roadmap.md) for exact historical and planned states.

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
