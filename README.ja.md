# AgentOS

[English](README.md) | [한국어](README.ko.md) | [日本語](README.ja.md) | [中文](README.zh.md)

**agent-managed post-boot runtime を起動後の標準サーフェスにする、bootable で headless-first な OS プロトタイプです。**

AgentOS は、起動後の標準インターフェイスがアプリで埋まったデスクトップではなく、managed agent runtime だったら OS はどう見えるのかを探る実験です。

イメージを起動し、AgentOS operator surface に入り、ローカルまたはオンラインの LLM パスを設定し、TTY、Telegram、runtime command surface から入るリクエストを試せます。このプロトタイプは intent をルーティングし、ローカルツールを実行し、設定済みなら返信し、proof/log artifact を残します。

AgentOS は **公開プロトタイプ**であり、production AI OS distribution ではありません。

## AgentOS とは?

AgentOS は OS-native agent runtime の実験です。中心にある問いは一つです。

> OS が従来のデスクトップではなく agent operator surface に起動したらどうなるのか?

現代の OS は、まだ人間がアプリを手で開き、アプリ間でデータをコピーし、ワークフローを調整することを前提にしています。AgentOS は別の標準を試します。起動後、agent runtime が operator surface になり、status、workspace inspection、web access、LLM setup、Telegram setup、proof logging などの capability を調整します。

意図されたデモは bootable image です。repo から `python3 src/main.py` を実行する方法は、OS image を起動せずに同じ runtime surface の一部を試すための developer shortcut です。

## Demo Idea

小さな proof loop は次の通りです。

```text
小さな AgentOS VM を起動
-> terminal-first AgentOS operator surface に到達
-> LLM / Telegram runtime settings を設定
-> TTY または Telegram からリクエストを送る
-> リクエスト intent を分類
-> 対応する capability または tool を実行
-> 返信し、proof/log event を記録
```

プロトタイプで試せるリクエスト例:

```text
status
search AgentOS roadmap and summarize it
workspace 파일 목록 보여줘
```

Telegram と web-based setup path は UTF-8 テキストを扱えます。直接 TTY での多言語入力の polish は、まだ Phase 2/i18n usability の対象です。

## 現在動くもの

Phase 1 は、狭いながら実際に動く OS-native loop を証明します。

- ローカル VM 実験用の bootable AgentOS ISO プロトタイプ。
- 起動時の headless-first terminal operator surface。
- Bubble Tea/Lip Gloss ベースの full-screen operator TUI。
- Agent mode と shell mode:
  - Agent mode: AgentOS と会話します。
  - Shell mode: Linux コマンドを直接実行します。
  - `% <command>`: agent mode から Linux コマンドを一つ実行します。
- LLM、Telegram、Web、workspace、IP、state の runtime readiness 表示。
- tiny baseline model `smollm2:135m-instruct-q5_K_M` を使う bundled local Ollama path。
- local Ollama または OpenAI/Codex-style provider configuration のための LLM setup surface。
- プロトタイプの OpenAI/Codex path は `gpt-4o-mini` に固定されています。
- Telegram setup page と QR-oriented setup flow。
- 設定済みの場合の Telegram receive/reply 実験。
- greeting、status、search-style request、workspace-oriented request の intent dispatch。
- human-readable activity feed hook。
- workspace 配下の proof/log artifact。例: `artifacts/os_events.jsonl`。
- status、guided operator、workflow status、setup、activity、intent dispatch のための `agentos-kernelctl` command surface。

## Quick Start

ISO を起動することが実際の AgentOS concept demo です。repo から実行する方法は、最速の developer shortcut です。

### Concept Demo: OS Image を起動する

ローカル ISO をビルドします。

```bash
git clone git@github.com:Jongtae/agentos.git
cd agentos
./scripts/build_latest_agentos_iso.sh
```

生成された image はここに出力されます。

```text
build-output/release/
```

Apple Silicon のローカルテストでは、ARM64 image と UTM の Linux VM を使います。

1. [UTM](https://mac.getutm.app/) をインストールします。
2. ARM64 virtualization の Linux VM を作ります。
3. 生成された AgentOS ARM64 ISO を接続します。
4. VM を起動します。
5. AgentOS terminal operator surface が表示されることを確認します。

期待される起動フロー:

```text
Boot
-> AgentOS TTY/operator surface
-> managed agent runtime
-> LLM / Telegram / Web readiness
-> AgentOS prompt and command shortcuts
```

Notes:

- ISO build/remaster 作業には host tooling と elevated permission が必要な場合があります。
- 生成された ISO、`build-output/`、runtime workspace、artifact は Git から除外されます。
- 個人 API key や Telegram token を ISO に bake しないでください。

### Developer Shortcut: Repo から実行する

VM を起動せずに runtime を確認または開発したい場合に使います。

```bash
git clone git@github.com:Jongtae/agentos.git
cd agentos
cp .env.example .env
python3 src/main.py --doctor
python3 src/main.py --no-tui
```

同じ runtime surface を直接確認します。

```bash
./scripts/agentos-kernelctl status --json
./scripts/agentos-kernelctl guided-operator --workspace ./workspaces/default --json
./scripts/agentos-kernelctl workflow-status --workspace ./workspaces/default --json
./scripts/agentos-kernelctl activity-feed --workspace ./workspaces/default --json
```

## Architecture

```text
Bootable OS image
  |
  v
AgentOS runtime
  |
  v
TTY / Telegram / setup page input
  |
  v
Command router / intent dispatcher
  |
  v
Tools and surfaces
  - LLM provider status
  - workspace/files
  - web access
  - Telegram setup/reply
  - proof/activity log
  |
  v
Reply + proof log
```

重要な entrypoint:

- `cmd/agentos-operator-tui/` - full-screen terminal operator frontend
- `scripts/agentos-kernelctl` - main runtime command surface
- `scripts/kernel_intent_dispatch.py` - intent dispatch surface
- `scripts/kernel_activity_feed.py` - activity feed surface
- `scripts/kernel_llm_setup.py` - LLM setup surface
- `scripts/kernel_telegram_setup.py` - Telegram setup surface
- `src/kernel/event_fabric/` - event/proof substrate

## Commands / Operator Surface

AgentOS TUI の中で:

```text
/help              例とショートカットを表示
/status            human-readable runtime status を表示
/mode agent        AgentOS と通常会話
/mode shell        Linux コマンドを直接入力
/setup llm         LLM setup page / QR flow を開く
/engine ollama     bundled local Ollama を強制
/engine codex      gpt-4o-mini を使う OpenAI/Codex path を選択
/setup telegram    Telegram setup page / QR flow を開く
/test telegram     manual Telegram drain/fallback receive-send check
/power             restart/reboot/shutdown options を表示
/clear             visible activity area をクリア
% <command>        agent mode から Linux コマンドを一つ実行
```

TUI が product-facing surface です。Raw Python command はほとんど developer shortcut です。

## Proof Logs

AgentOS は proof-first です。リクエストは trace を残すべきです。

```text
request received
-> intent classified
-> capability started
-> capability completed or failed
-> reply sent or surfaced to the operator
```

典型的な workspace path:

```text
/home/ubuntu/agentos-ws/artifacts/os_events.jsonl
/home/ubuntu/agentos-ws/artifacts/
```

repo checkout から:

```bash
./scripts/agentos-kernelctl activity-feed --workspace ./workspaces/default --json
```

現在の proof surface は prototype-grade です。Phase 2 では activity feed をより信頼でき、読みやすく、operator UI の中心にしていきます。

## Roadmap

Phase 1 は public prototype として close されています。

近い Phase 2 focus:

- productized first-run setup
- 信頼できる always-on Telegram receiver/reply loop
- より明確な setup completion feedback
- richer operator activity narration
- restart、reboot、shutdown、service recovery の lifecycle controls
- friendlier error recovery
- acceptance-driven demo flow
- 直接 TTY 多言語入力の改善を含む i18n usability

Future tracks:

- より広い app/message adapter
- stronger local models
- installer distribution
- verified boot, attestation, updater hardening
- production credential/security model

## Limitations

AgentOS はまだ次のものではありません。

- production desktop OS
- secure multi-user OS
- Linux、macOS、ChromeOS の代替
- fully autonomous OS
- polished consumer installer
- production Telegram automation platform

既知の prototype limitation:

- GUI は primary interface ではありません。
- Telegram support はありますが、product-grade always-on loop は Phase 2 の作業です。
- 非技術ユーザー向け setup UX はまだ polish が必要です。
- 直接 TTY 多言語入力はまだ polished experience ではありません。
- credential handling は repo では secret-free ですが、production runtime security model はまだ発展中です。
- Gmail、Drive、Calendar、より広い app adapter は、明示的に branch で実装されていない限り future work です。

## Security And Secrets

AgentOS は public code と public image を secret-free に保ちます。

絶対に commit しないでください。

- `.env`
- Telegram bot tokens
- OpenAI または他 provider の API keys
- generated ISO artifacts
- local state を含む runtime workspace artifacts
- 実際の conversation logs

Runtime setup は、ユーザーが提供した secret を committed artifact ではなく local runtime env file に書くべきです。

一般的な runtime variables:

```bash
OPENAI_API_KEY=...
AGENTOS_TELEGRAM_BOT_TOKEN=...
AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS=...
```

## Contributing

初期の contribution に向いている領域:

- TUI usability と activity feed presentation
- command router と intent dispatch rules
- workspace/file tools
- web-access reliability
- i18n と Korean/English examples
- UTM/QEMU platforms での VM boot testing
- docs と reproducible demo scripts

Repository workflow は `AGENTS.md` を参照してください。

## License

MIT. `LICENSE` を参照してください。
