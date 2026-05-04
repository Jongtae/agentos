# AgentOS

[English](README.md) | [한국어](README.ko.md) | [日本語](README.ja.md) | [中文](README.zh.md)

**agent-managed post-boot runtime을 기본 표면으로 삼는, 부팅 가능한 headless-first OS 프로토타입입니다.**

AgentOS는 부팅 후 기본 인터페이스가 앱으로 가득 찬 데스크톱이 아니라 managed agent runtime이라면 운영체제가 어떤 모습일지 탐구합니다.

이미지를 부팅하고 AgentOS operator surface에 도달한 뒤, 로컬 또는 온라인 LLM 경로를 설정하고 TTY, Telegram, runtime command surface로 들어오는 요청을 실험할 수 있습니다. 이 프로토타입은 intent를 라우팅하고, 로컬 도구를 실행하고, 설정된 경우 답장을 보내며, proof/log artifact를 남깁니다.

AgentOS는 **공개 프로토타입**이며, production AI OS 배포판이 아닙니다.

## AgentOS란?

AgentOS는 OS-native agent runtime 실험입니다. 중심 질문은 하나입니다.

> 운영체제가 전통적인 데스크톱 대신 agent operator surface로 부팅된다면 어떨까?

현대 운영체제는 여전히 사람이 앱을 직접 열고, 앱 사이에서 데이터를 복사하고, 워크플로를 조정한다고 가정합니다. AgentOS는 다른 기본값을 실험합니다. 부팅 후 agent runtime이 operator surface가 되고, status, workspace inspection, web access, LLM setup, Telegram setup, proof logging 같은 capability를 조정합니다.

의도된 데모는 bootable image입니다. repo에서 `python3 src/main.py`를 실행하는 것은 OS image를 부팅하지 않고 일부 runtime surface를 개발용으로 확인하기 위한 shortcut입니다.

## Demo Idea

작은 proof loop는 다음과 같습니다.

```text
작은 AgentOS VM 부팅
-> terminal-first AgentOS operator surface 진입
-> LLM / Telegram runtime 설정
-> TTY 또는 Telegram으로 요청 전송
-> 요청 intent 분류
-> 맞는 capability 또는 tool 실행
-> 답장하고 proof/log event 기록
```

프로토타입에서 시도해볼 수 있는 예시:

```text
status
search AgentOS roadmap and summarize it
workspace 파일 목록 보여줘
```

Telegram과 web-based setup path는 UTF-8 텍스트를 다룰 수 있습니다. 다만 직접 TTY에서의 다국어 입력 polish는 아직 Phase 2/i18n usability 목표입니다.

## 현재 동작하는 것

Phase 1은 좁지만 실제적인 OS-native loop를 증명합니다.

- 로컬 VM 실험용 bootable AgentOS ISO 프로토타입.
- 부팅 시 headless-first terminal operator surface.
- Bubble Tea/Lip Gloss 기반 full-screen operator TUI.
- Agent mode와 shell mode:
  - Agent mode: AgentOS와 대화합니다.
  - Shell mode: Linux 명령을 직접 실행합니다.
  - `% <command>`: agent mode에서 Linux 명령 하나를 실행합니다.
- LLM, Telegram, Web, workspace, IP, state runtime readiness 표시.
- tiny baseline model인 `smollm2:135m-instruct-q5_K_M`을 사용하는 bundled local Ollama path.
- local Ollama 또는 OpenAI/Codex-style provider 설정을 위한 LLM setup surface.
- 프로토타입의 OpenAI/Codex path는 `gpt-4o-mini`로 고정됩니다.
- Telegram setup page와 QR-oriented setup flow.
- 설정된 경우 Telegram receive/reply 실험.
- greeting, status, search-style request, workspace-oriented request에 대한 intent dispatch.
- 사람이 읽을 수 있는 activity feed hook.
- workspace 아래 proof/log artifact. 예: `artifacts/os_events.jsonl`.
- status, guided operator, workflow status, setup, activity, intent dispatch를 위한 `agentos-kernelctl` command surface.

## Quick Start

ISO를 부팅하는 것이 실제 AgentOS concept demo입니다. repo에서 실행하는 경로는 가장 빠른 developer shortcut입니다.

### Concept Demo: OS Image 부팅

로컬 ISO를 빌드합니다.

```bash
git clone git@github.com:Jongtae/agentos.git
cd agentos
./scripts/build_latest_agentos_iso.sh
```

생성된 이미지는 다음 위치에 기록됩니다.

```text
build-output/release/
```

Apple Silicon 로컬 테스트는 ARM64 image와 UTM Linux VM을 사용합니다.

1. [UTM](https://mac.getutm.app/)을 설치합니다.
2. ARM64 virtualization Linux VM을 만듭니다.
3. 생성된 AgentOS ARM64 ISO를 연결합니다.
4. VM을 부팅합니다.
5. AgentOS terminal operator surface가 표시되는 것을 기대합니다.

예상 부팅 흐름:

```text
Boot
-> AgentOS TTY/operator surface
-> managed agent runtime
-> LLM / Telegram / Web readiness
-> AgentOS prompt and command shortcuts
```

참고:

- ISO build/remaster 작업은 host tooling과 elevated permission이 필요할 수 있습니다.
- 생성된 ISO, `build-output/`, runtime workspace, artifact는 Git에서 제외됩니다.
- 개인 API key나 Telegram token을 ISO에 bake하지 마세요.

### Developer Shortcut: Repo에서 실행

VM을 부팅하지 않고 runtime을 확인하거나 개발할 때 사용합니다.

```bash
git clone git@github.com:Jongtae/agentos.git
cd agentos
cp .env.example .env
python3 src/main.py --doctor
python3 src/main.py --no-tui
```

같은 runtime surface를 직접 확인합니다.

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

중요 entrypoint:

- `cmd/agentos-operator-tui/` - full-screen terminal operator frontend
- `scripts/agentos-kernelctl` - main runtime command surface
- `scripts/kernel_intent_dispatch.py` - intent dispatch surface
- `scripts/kernel_activity_feed.py` - activity feed surface
- `scripts/kernel_llm_setup.py` - LLM setup surface
- `scripts/kernel_telegram_setup.py` - Telegram setup surface
- `src/kernel/event_fabric/` - event/proof substrate

## Commands / Operator Surface

AgentOS TUI 안에서:

```text
/help              예시와 shortcut 표시
/status            사람이 읽을 수 있는 runtime status 표시
/mode agent        AgentOS와 일반 대화
/mode shell        Linux 명령 직접 입력
/setup llm         LLM setup page / QR flow 열기
/engine ollama     bundled local Ollama 강제
/engine codex      gpt-4o-mini를 사용하는 OpenAI/Codex path 선택
/setup telegram    Telegram setup page / QR flow 열기
/test telegram     수동 Telegram drain/fallback receive-send check
/power             restart/reboot/shutdown 옵션 표시
/clear             visible activity area 정리
% <command>        agent mode에서 Linux 명령 하나 실행
```

TUI가 product-facing surface입니다. Raw Python command는 대부분 developer shortcut입니다.

## Proof Logs

AgentOS는 proof-first입니다. 요청은 trace를 남겨야 합니다.

```text
request received
-> intent classified
-> capability started
-> capability completed or failed
-> reply sent or surfaced to the operator
```

일반적인 workspace path:

```text
/home/ubuntu/agentos-ws/artifacts/os_events.jsonl
/home/ubuntu/agentos-ws/artifacts/
```

repo checkout에서:

```bash
./scripts/agentos-kernelctl activity-feed --workspace ./workspaces/default --json
```

현재 proof surface는 prototype-grade입니다. Phase 2에서는 activity feed를 더 안정적이고 읽기 쉽게 만들고 operator UI의 중심으로 강화할 예정입니다.

## Roadmap

Phase 1은 public prototype으로 닫혔습니다.

가까운 Phase 2 focus:

- productized first-run setup
- 안정적인 always-on Telegram receiver/reply loop
- 더 명확한 setup completion feedback
- 더 풍부한 operator activity narration
- restart, reboot, shutdown, service recovery lifecycle control
- 친절한 error recovery
- acceptance-driven demo flow
- 직접 TTY 다국어 입력 개선을 포함한 i18n usability

향후 track:

- 더 넓은 app/message adapter
- 더 강한 local model
- installer distribution
- verified boot, attestation, updater hardening
- production credential/security model

## Limitations

AgentOS는 아직 다음이 아닙니다.

- production desktop OS
- secure multi-user OS
- Linux, macOS, ChromeOS 대체제
- fully autonomous OS
- polished consumer installer
- production Telegram automation platform

알려진 prototype limitation:

- GUI는 primary interface가 아닙니다.
- Telegram support는 있지만 product-grade always-on loop는 Phase 2 작업입니다.
- 비기술 사용자를 위한 setup UX는 아직 polish가 필요합니다.
- 직접 TTY 다국어 입력은 아직 polished experience가 아닙니다.
- credential handling은 repo에서는 secret-free이지만, production runtime security model은 아직 발전 중입니다.
- Gmail, Drive, Calendar 및 broader app adapter는 별도 branch에서 명시적으로 구현되지 않은 한 future work입니다.

## Security And Secrets

AgentOS는 public code와 public image를 secret-free로 유지합니다.

절대 commit하지 마세요.

- `.env`
- Telegram bot token
- OpenAI 또는 다른 provider API key
- generated ISO artifact
- local state가 들어 있는 runtime workspace artifact
- 실제 conversation log

Runtime setup은 사용자가 제공한 secret을 committed artifact가 아니라 local runtime env file에 써야 합니다.

일반적인 runtime variable:

```bash
OPENAI_API_KEY=...
AGENTOS_TELEGRAM_BOT_TOKEN=...
AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS=...
```

## Contributing

초기 기여에 좋은 영역:

- TUI usability와 activity feed presentation
- command router와 intent dispatch rule
- workspace/file tool
- web-access reliability
- i18n 및 한국어/영어 예시
- UTM/QEMU platform의 VM boot testing
- docs와 reproducible demo script

Repository workflow는 `AGENTS.md`를 참고하세요.

## License

MIT. `LICENSE`를 참고하세요.
