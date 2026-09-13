# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

**Personal AgentOS는 한 사람이 자신의 환경에 설치해 소유하는 로컬 우선 개인 AI 운영 환경입니다.**

개인 PC와 개인 OS가 한 사람에게 지속되는 컴퓨팅 환경을 제공하듯, Personal AgentOS는 대화 하나나 특정 모델 하나를 넘어 계속 유지되는 개인 AI 환경을 지향합니다. 사용자가 제어하는 Mac/런타임 위에서 동작하며 정책, 개인 컨텍스트, 작업공간, 권한, 승인, 작업 상태, 근거, 복구 상태를 AgentOS가 소유하는 경계 안에 둡니다.

Codex, Claude Code, GPT 계열 모델, 로컬 모델, 도구와 전문 Agent는 AgentOS가 필요할 때 사용하는 실행자 또는 기능입니다. 이들이 개인 상태의 원본이 되어서는 안 됩니다. 실행 엔진을 바꾸더라도 사용자의 기억·컨텍스트 기록, 권한, 승인 이력, 복구 가능한 작업과 근거가 사라지지 않는 것이 핵심입니다.

**Personal AgentOS는 코딩 하네스나 Agent swarm 프레임워크가 아닙니다.** 코딩 자동화는 AgentOS 안의 하나의 서비스가 될 수 있고, 이 저장소 자체도 GitHub/Codex 기반의 개발 자동화를 적극적으로 사용하지만 그것은 제품을 만드는 개발 인프라입니다. 또한 macOS/Linux를 대체하는 커널이나 하이퍼바이저가 아니라, 사용자가 소유한 호스트/런타임 위에서 지속되는 개인 AI 계층입니다.

## 제품 구조

장기 아키텍처는 지속되는 사용자 상태와 교체 가능한 실행자를 분리합니다.

| 계층 | 책임 |
| --- | --- |
| **Owner plane** | 사용자 정체성/정책, 개인 컨텍스트와 기억 경계, 자료/작업공간, 권한, 승인, 작업 상태, 근거, 복구 |
| **Capability plane** | 도구, connector, assistant, 전문 기능, runtime/engine registry |
| **Worker plane** | 제한된 Codex, Claude Code, 외부 모델 또는 로컬 런타임 실행 |
| **Experience plane** | 지원되는 로컬 UI, Telegram, companion 등을 통한 대화와 작업 |

영문 단일 원본 아키텍처 문서는 [Personal AgentOS Architecture](docs/personal-agentos-architecture.en.md)입니다. 여기에서 **OS**라는 표현이 호스트 운영체제를 대체한다는 뜻이 아니라, 한 사람의 AI 상태와 권한을 지속적으로 소유하는 계층이라는 의미를 정의합니다.

## 현재 구현 기준선

첫 번째 사용 가능한 제품 단면은 **파일·폴더 기반 개인 작업공간**입니다. [#314 프로그램](https://github.com/Jongtae/personal-agentos/issues/314)은 완료되었고, 통합 파일 작업공간 구현은 [PR #320](https://github.com/Jongtae/personal-agentos/pull/320), 검증과 프로그램 종료는 [PR #324](https://github.com/Jongtae/personal-agentos/pull/324)에 병합되었습니다.

현재 흐름은 사용자 원본을 보존하고, 연결한 참고 폴더를 기본 읽기 전용으로 사용하며, 새 결과는 소유자가 허용한 관리 작업공간에만 기록합니다. 원본·파생물·초안·확정 기록의 출처 관계를 구별하고, 재생성 가능한 검색 인덱스와 지속되는 작업·승인·근거·복구·인증 상태를 분리하며, 앱 재시작 뒤에도 저장한 결과를 찾아 다시 사용할 수 있습니다.

증거의 범위도 구분합니다. 완료된 파일 작업공간 프로그램은 자동화된 deterministic model과 임시 로컬 파일 기반 검증에 근거합니다. 이것만으로 실제 외부 모델, Telegram, Google Drive/OAuth, 반복 스케줄러 또는 개인 폴더에서의 운영이 검증되었다고 주장하지 않습니다. 선택형 Drive 작업과 공개 안내 사이트 게시 작업은 현재 핵심 경로에서 보류되어 있습니다. 구현·과거·보류·제안 상태는 [로드맵](docs/roadmap.md)을 기준으로 확인합니다.

## 사용자 통제와 신뢰 경계

- 연결할 폴더, 서비스, 도구, assistant, runtime은 사용자가 선택합니다.
- 연결한 참고 폴더는 기본 읽기 전용이며, 관리 작업공간 쓰기는 명시한 사용자 범위 안에서만 이뤄집니다.
- 원본은 추출 텍스트·요약·초안·확정 기록과 구별합니다.
- 검색 인덱스는 재생성 가능하며 작업·승인·근거·복구·인증 상태와 분리합니다.
- 외부 AI, 메신저, 다른 Agent, 수신자에게 보내는 것은 로컬 저장과 별개의 정책 경계입니다.
- 외부 전송이나 파괴적 파일/계정 변경 같은 중요한 행동에는 명시적인 권한이 필요합니다.
- 지원되는 범위에서 작업 상태와 근거를 남겨 취소, 재시도, 복구, 내보내기와 복원을 가능하게 합니다.

로컬 우선은 '어떤 정보도 기기 밖으로 나가지 않는다'는 뜻이 아닙니다. 사용자가 외부 AI 엔진, 메신저, connector 또는 수신자를 선택하면 승인된 작업 컨텍스트가 해당 기능의 정책에 따라 전송될 수 있습니다. AgentOS는 이를 '로컬'이라는 말 뒤에 숨기지 않고 경계를 명확히 드러내야 합니다.

## 상태 이동

사용자 상태는 다음 도구로 로컬 런타임 사이에서 이동할 수 있습니다.

```sh
scripts/agentos-backup.py DATA ARCHIVE
scripts/agentos-restore.py ARCHIVE EMPTY_DATA
```

아카이브는 무결성을 확인하고 기억 기록, 작업 근거, 검토된 assistant 선언 같은 지속 상태를 담습니다. provider 자격 증명, 세션, 로컬 폴더 권한, 엔진/모델 선택 또는 Telegram 페어링은 포함하지 않으며, 대상 런타임은 다시 명시적으로 claim하고 연결해야 합니다.

## 개발 설치

```sh
brew install jongtae/agentos/agentos
agentos start
```

일반 사용자 설치 경험을 다듬는 동안 Homebrew 경로는 개발자와 자체 호스팅 사용자용으로 유지합니다.

## 개발 거버넌스

저장소 개발은 이슈에 연결된 브랜치, PR, 필수 검증, [Goal 실행 계약](docs/goal-execution-contract.en.md)을 따릅니다. 상태 기반 구현자/검토자 handoff loop도 저장소 안에 있습니다. 이것들은 **Personal AgentOS를 만들기 위한 개발 인프라**이며, 일반 사용자가 실행하는 AgentOS 서비스나 실제 무인 운영의 증거가 아닙니다.

구현 전 [AGENTS.md](AGENTS.md), [PRD.md](PRD.md), [TASKS.md](TASKS.md), [로드맵](docs/roadmap.md)을 확인하세요.
