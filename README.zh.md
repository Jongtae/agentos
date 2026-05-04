# AgentOS

[English](README.md) | [한국어](README.ko.md) | [日本語](README.ja.md) | [中文](README.zh.md)

**一个可启动、headless-first 的 OS 原型，其启动后的默认界面是 agent-managed runtime。**

AgentOS 探索这样一个问题：如果操作系统启动后的默认界面不是充满应用图标的传统桌面，而是一个 managed agent runtime，OS 会是什么样子？

启动镜像，进入 AgentOS operator surface，配置本地或在线 LLM 路径，然后通过 TTY、Telegram 和 runtime command surface 发送请求进行实验。这个原型会路由 intent，运行本地工具，在配置完成后发送回复，并留下 proof/log artifacts。

AgentOS 是一个 **公开原型**，不是生产级 AI OS 发行版。

## AgentOS 是什么？

AgentOS 是一个 OS-native agent runtime 实验。它围绕一个问题展开：

> 如果操作系统启动后进入 agent operator surface，而不是传统桌面，会怎样？

现代操作系统仍然假设人类手动打开应用、在应用之间复制数据，并协调整个工作流。AgentOS 尝试另一个默认方式：启动后，agent runtime 成为 operator surface，并协调 status、workspace inspection、web access、LLM setup、Telegram setup、proof logging 等 capabilities。

预期的演示方式是 bootable image。在 repo 中运行 `python3 src/main.py` 是 developer shortcut，用来在不启动 OS image 的情况下体验部分相同的 runtime surfaces。

## Demo Idea

这个小型 proof loop 如下：

```text
启动一个小型 AgentOS VM
-> 进入 terminal-first AgentOS operator surface
-> 配置 LLM / Telegram runtime settings
-> 通过 TTY 或 Telegram 发送请求
-> 对请求 intent 进行分类
-> 运行对应 capability 或 tool
-> 回复并记录 proof/log events
```

可以在原型中尝试的请求：

```text
status
search AgentOS roadmap and summarize it
workspace 파일 목록 보여줘
```

Telegram 和 web-based setup paths 可以处理 UTF-8 文本。直接在 TTY 中进行多语言输入的体验仍是 Phase 2/i18n usability 目标。

## 当前可用功能

Phase 1 证明了一个范围很窄但真实可运行的 OS-native loop：

- 用于本地 VM 实验的 bootable AgentOS ISO prototype。
- 启动后的 headless-first terminal operator surface。
- 基于 Bubble Tea/Lip Gloss 的 full-screen operator TUI。
- Agent 和 shell 两种模式：
  - Agent mode：与 AgentOS 对话。
  - Shell mode：直接运行 Linux 命令。
  - `% <command>`：在 agent mode 中运行一条 Linux 命令。
- 显示 LLM、Telegram、Web、workspace、IP 和 state 的 runtime readiness。
- Bundled local Ollama path，使用 `smollm2:135m-instruct-q5_K_M` 作为 tiny baseline model。
- 用于 local Ollama 或 OpenAI/Codex-style provider configuration 的 LLM setup surface。
- 原型中的 OpenAI/Codex path 固定为 `gpt-4o-mini`。
- Telegram setup page 和 QR-oriented setup flow。
- 配置完成后可进行 Telegram receive/reply 实验。
- 对 greeting、status、search-style requests、workspace-oriented requests 进行 intent dispatch。
- Human-readable activity feed hooks。
- workspace 下的 proof/log artifacts，包括 `artifacts/os_events.jsonl`。
- 用于 status、guided operator、workflow status、setup、activity、intent dispatch 的 `agentos-kernelctl` command surfaces。

## Quick Start

启动 ISO 才是实际的 AgentOS concept demo；从 repo 运行是最快的 developer shortcut。

### Concept Demo：启动 OS Image

构建本地 ISO：

```bash
git clone git@github.com:Jongtae/agentos.git
cd agentos
./scripts/build_latest_agentos_iso.sh
```

生成的镜像会写入：

```text
build-output/release/
```

在 Apple Silicon 上进行本地测试时，使用 ARM64 image 和 UTM Linux VM：

1. 安装 [UTM](https://mac.getutm.app/)。
2. 创建使用 ARM64 virtualization 的 Linux VM。
3. 挂载生成的 AgentOS ARM64 ISO。
4. 启动 VM。
5. 预期看到 AgentOS terminal operator surface。

预期启动流程：

```text
Boot
-> AgentOS TTY/operator surface
-> managed agent runtime
-> LLM / Telegram / Web readiness
-> AgentOS prompt and command shortcuts
```

注意：

- ISO build/remaster 工作可能需要 host tooling 和 elevated permissions。
- 生成的 ISO、`build-output/`、runtime workspaces 和 artifacts 都会被 Git 忽略。
- 不要把个人 API keys 或 Telegram tokens bake 到 ISO 中。

### Developer Shortcut：从 Repo 运行

当你想在不启动 VM 的情况下检查或开发 runtime 时，使用这个路径：

```bash
git clone git@github.com:Jongtae/agentos.git
cd agentos
cp .env.example .env
python3 src/main.py --doctor
python3 src/main.py --no-tui
```

直接检查相同的 runtime surfaces：

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

重要 entrypoints：

- `cmd/agentos-operator-tui/` - full-screen terminal operator frontend
- `scripts/agentos-kernelctl` - main runtime command surface
- `scripts/kernel_intent_dispatch.py` - intent dispatch surface
- `scripts/kernel_activity_feed.py` - activity feed surface
- `scripts/kernel_llm_setup.py` - LLM setup surface
- `scripts/kernel_telegram_setup.py` - Telegram setup surface
- `src/kernel/event_fabric/` - event/proof substrate

## Commands / Operator Surface

在 AgentOS TUI 中：

```text
/help              显示示例和快捷方式
/status            显示 human-readable runtime status
/mode agent        正常与 AgentOS 对话
/mode shell        直接输入 Linux 命令
/setup llm         打开 LLM setup page / QR flow
/engine ollama     强制使用 bundled local Ollama
/engine codex      选择使用 gpt-4o-mini 的 OpenAI/Codex path
/setup telegram    打开 Telegram setup page / QR flow
/test telegram     manual Telegram drain/fallback receive-send check
/power             显示 restart/reboot/shutdown options
/clear             清空 visible activity area
% <command>        在 agent mode 中运行一条 Linux 命令
```

TUI 是 product-facing surface。Raw Python commands 大多只是 developer shortcuts。

## Proof Logs

AgentOS 是 proof-first 的。请求应该留下 trace：

```text
request received
-> intent classified
-> capability started
-> capability completed or failed
-> reply sent or surfaced to the operator
```

典型 workspace paths：

```text
/home/ubuntu/agentos-ws/artifacts/os_events.jsonl
/home/ubuntu/agentos-ws/artifacts/
```

从 repo checkout 中：

```bash
./scripts/agentos-kernelctl activity-feed --workspace ./workspaces/default --json
```

当前 proof surfaces 仍是 prototype-grade。Phase 2 会让 activity feed 更可靠、更易读，并让它成为 operator UI 的核心部分。

## Roadmap

Phase 1 已作为 public prototype 关闭。

近期 Phase 2 focus：

- productized first-run setup
- 可靠的 always-on Telegram receiver/reply loop
- 更清晰的 setup completion feedback
- 更丰富的 operator activity narration
- restart、reboot、shutdown、service recovery 的 lifecycle controls
- 更友好的 error recovery
- acceptance-driven demo flow
- i18n usability，包括更好的直接 TTY 多语言输入

Future tracks：

- 更广泛的 app/message adapters
- stronger local models
- installer distribution
- verified boot、attestation、updater hardening
- production credential/security model

## Limitations

AgentOS 目前还不是：

- production desktop OS
- secure multi-user OS
- Linux、macOS 或 ChromeOS 的替代品
- fully autonomous OS
- polished consumer installer
- production Telegram automation platform

已知 prototype limitations：

- GUI 不是 primary interface。
- Telegram support 已存在，但 product-grade always-on loop 是 Phase 2 工作。
- 面向非技术用户的 setup UX 仍需要打磨。
- 直接 TTY 多语言输入还不是 polished experience。
- credential handling 在 repo 中保持 secret-free，但 production runtime security model 仍在演进。
- Gmail、Drive、Calendar 和更广泛的 app adapters 都是 future work，除非某个 branch 中明确实现。

## Security And Secrets

AgentOS 保持 public code 和 public images secret-free。

不要提交：

- `.env`
- Telegram bot tokens
- OpenAI 或其他 provider API keys
- generated ISO artifacts
- 包含 local state 的 runtime workspace artifacts
- 真实 conversation logs

Runtime setup 应该把用户提供的 secrets 写入 local runtime env files，而不是 committed artifacts。

常见 runtime variables：

```bash
OPENAI_API_KEY=...
AGENTOS_TELEGRAM_BOT_TOKEN=...
AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS=...
```

## Contributing

适合早期贡献的方向：

- TUI usability 和 activity feed presentation
- command router 和 intent dispatch rules
- workspace/file tools
- web-access reliability
- i18n 和 Korean/English examples
- UTM/QEMU platforms 上的 VM boot testing
- docs 和 reproducible demo scripts

请参阅 `AGENTS.md` 了解 repository workflow。

## License

MIT. 参见 `LICENSE`。
