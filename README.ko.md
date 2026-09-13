# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

**Personal AgentOS는 한 사람이 자신의 환경에 설치해 소유하는 로컬 우선 개인 AI 운영 환경입니다.**

장기 제품 방향은 다음 한 문장으로 요약합니다.

> **Personal AgentOS = 개인 AI 커널 + Agent 유통 플랫폼**

개인 PC와 개인 OS가 한 사람에게 지속되는 컴퓨팅 환경을 제공하듯, Personal AgentOS는 대화 하나나 특정 모델 하나를 넘어 계속 유지되는 개인 AI 환경을 지향합니다. 사용자가 제어하는 호스트/런타임 위에서 동작하며 정책, 개인 컨텍스트와 기억, 작업공간, 권한, 승인, 작업 상태, 결과물, 근거와 복구 상태를 AgentOS가 소유하는 경계 안에 둡니다.

커널은 의도적으로 **Agent 독립적**입니다. Codex, Claude Code, GPT 계열 모델, 로컬 모델, MCP 서버, 도구, 전문 Agent, Ruflo 같은 multi-agent runtime은 필요할 때 교체할 수 있는 실행자/기능입니다. 이들이 canonical Memory, Grant, Work 상태나 Evidence의 주인이 되어서는 안 됩니다.

반면 사용자 경험과 생태계는 **Agent 중심**일 수 있습니다. 잘 만들어진 외부 Agent를 앱처럼 발견하고, 검토하고, 설치하고, 권한을 부여하고, 실행하고, 업데이트·롤백·비활성화·제거할 수 있어야 합니다. 중요한 것은 Agent를 바꾸어도 나의 개인 AI 환경이 유지되는 것입니다.

**Personal AgentOS는 코딩 하네스나 Agent swarm 프레임워크가 아닙니다.** 코딩 자동화나 multi-agent orchestration은 AgentOS 위에서 실행되는 서비스/런타임이 될 수 있습니다. 이 저장소의 GitHub/Codex 자동화는 제품을 만드는 개발 인프라이지 일반 사용자가 사용하는 OS 기능 자체가 아닙니다. 또한 macOS/Linux를 대체하는 커널이나 하이퍼바이저가 아니라, 사용자가 소유한 호스트 위에서 지속되는 개인 AI 계층입니다.

## 제품 구조

| 계층 | 책임 |
| --- | --- |
| **Owner plane** | 사용자 정체성/정책, 개인 Context/Memory, 자료/작업공간, Grant, 승인, Work/Event, Artifact, Evidence, 복구 |
| **Capability plane** | 도구, connector, capability registry, runtime/engine boundary |
| **Distribution plane** | AgentPackage, Package Manager, Registry, trust metadata, Marketplace/discovery 경계 |
| **Worker plane** | 제한된 Codex, Claude Code, 외부/로컬 모델, Ruflo 또는 기타 runtime 실행 |
| **Experience plane** | 로컬 UI, Telegram/companion, 향후 Agent 탐색·설치·권한 UX |

영문 단일 원본 아키텍처는 [Personal AgentOS Architecture](docs/personal-agentos-architecture.en.md)입니다. 플랫폼 단계와 issue 구조는 [Agent Distribution Platform Foundation](docs/agent-distribution-platform-foundation.en.md)과 [#333](https://github.com/Jongtae/personal-agentos/issues/333)에 정리합니다.

### 커널 primitive

`Owner · Context · Memory · Artifact · Capability · Runtime · Grant · Work · Event · Evidence`

Agent 유통 플랫폼은 여기에 다음을 추가합니다.

`AgentPackage · Package Manager · Registry · Marketplace/Discovery · Trust/Verification`

## AgentPackage와 권한

AgentPackage는 사용자가 설치하는 Agent/app 단위입니다. package manifest는 장기적으로 package/publisher/version, AgentOS API 호환성, capability/action, runtime 요구사항, 파일·데이터 범위, 네트워크 목적지, secret reference, Memory 정책, Event/background 동작, 비용/시간 예산, 승인 필요 행동, Artifact, dependency, sandbox, health check, 업데이트·롤백·제거, provenance/signature/SBOM 등을 선언해야 합니다.

설치와 권한은 분리합니다.

`발견 → 검토 → 검증 → 설치(비활성) → 연결/Grant/활성 → 실행 → 업데이트/롤백 → 비활성 → 제거`

**다운로드됨, 설치됨, 활성화됨, 계정/credential이 연결됨, 특정 행동이 허가됨은 서로 다른 상태입니다.** 패키지를 설치했다고 Grant가 생기지 않으며, 업데이트가 권한·데이터 범위·외부 목적지·Memory/background 동작을 넓히면 다시 검토해야 합니다.

외부 Agent는 기본적으로 canonical 사용자 Memory를 직접 수정하지 않고 출처가 있는 MemoryCandidate를 제안합니다. AgentOS 정책/사용자가 실제 Memory 반영 여부를 결정합니다.

## Registry와 Marketplace

**Registry**는 package/publisher identity, exact version/digest, 호환성, signature/provenance, trust metadata, advisory/revocation/quarantine 같은 기술적 배포 메타데이터를 담당합니다.

**Marketplace/Discovery**는 검색, 추천, 랭킹, 리뷰, 큐레이션, 향후 상업 유통을 담당할 수 있습니다. 다운로드 수·별점·추천 순위는 권한이 아니며 quarantine/signature/AgentOS 정책을 덮어쓸 수 없습니다.

사용자의 private Context/Memory/Work 내용은 Registry/Marketplace의 상태가 되어서는 안 됩니다. Agent 탐색은 가능한 한 구조화된 capability metadata를 사용하고, raw 개인 prompt를 store 검색에 그대로 보내는 것을 기본으로 하지 않습니다.

## 초기 생태계 전략

초기 Personal AgentOS에 최고의 Agent가 모두 번들될 필요는 없습니다. 초기 MS-DOS/Linux/Ubuntu의 기본 앱처럼 General Assistant, Files, Research, Coding 정도의 작은 reference Agent 집합으로 시작할 수 있습니다.

이 번들 Agent의 목적은 최고의 앱을 직접 만드는 것이 아니라 **AgentOS 공개 계약을 검증하고 OS가 usable한 최소 baseline을 제공하는 것**입니다. 번들 Agent도 third-party Agent와 같은 Package/Runtime/Grant 계약을 사용하며 숨겨진 first-party 권한을 갖지 않습니다.

Marketplace가 비어 있는 chicken-and-egg 문제를 줄이기 위해, official format과 라이선스가 허용하는 범위에서 기존 MCP 및 OpenAI/Codex·Claude skill/plugin 생태계를 AgentPackage로 wrapping/import하는 방향을 계획합니다. Ruflo는 AgentOS의 kernel이 아니라 향후 bounded delegated Runtime Adapter 후보입니다.

## 현재 구현 기준선

첫 번째 사용 가능한 제품 단면은 **파일·폴더 기반 개인 작업공간**입니다. [#314 프로그램](https://github.com/Jongtae/personal-agentos/issues/314)은 완료되었고, 통합 파일 작업공간 구현은 [PR #320](https://github.com/Jongtae/personal-agentos/pull/320), 검증과 프로그램 종료는 [PR #324](https://github.com/Jongtae/personal-agentos/pull/324)에 병합되었습니다.

현재 흐름은 사용자 원본을 보존하고, 연결한 참고 폴더를 기본 읽기 전용으로 사용하며, 새 결과는 소유자가 허용한 관리 작업공간에만 기록합니다. 원본·파생물·초안·확정 기록의 출처 관계를 구별하고, 재생성 가능한 검색 인덱스와 지속되는 작업·승인·근거·복구·인증 상태를 분리하며, 앱 재시작 뒤에도 저장한 결과를 찾아 다시 사용할 수 있습니다.

증거의 범위도 구분합니다. 완료된 파일 작업공간 프로그램은 자동화된 deterministic model과 임시 로컬 파일 기반 검증에 근거합니다. 이것만으로 실제 외부 모델, Telegram, Google Drive/OAuth, 반복 스케줄러, 개인 폴더, AgentPackage 설치, Registry 또는 Marketplace 운영이 검증되었다고 주장하지 않습니다.

[#333 Agent Distribution Platform](https://github.com/Jongtae/personal-agentos/issues/333)과 #334–#346은 **계획된 후속 작업**입니다. 이슈가 만들어졌다는 사실만으로 자동 실행되는 작업 큐가 되지 않습니다. 활성 작업은 여전히 owner가 명시적으로 선택하고 Goal Execution Contract를 만족해야 합니다.

## 사용자 통제와 신뢰 경계

- 연결할 폴더, 서비스, 도구, AgentPackage, runtime은 사용자가 선택합니다.
- 연결한 참고 폴더는 기본 읽기 전용이며, 관리 작업공간 쓰기는 명시한 사용자 범위 안에서만 이뤄집니다.
- 외부 AgentPackage/runtime은 canonical Memory를 기본적으로 직접 수정하지 않습니다.
- 외부 AI, 메신저, 다른 Agent, package/runtime, 수신자에게 보내는 것은 로컬 저장과 별개의 정책 경계입니다.
- 외부 전송, 결제, 파괴적 파일/계정 변경, 권한 확대 같은 행동에는 명시적인 권한이 필요합니다.
- package signature/provenance는 identity/integrity 근거이지 '안전한 Agent'라는 보장이 아닙니다.
- 지원되는 범위에서 Work/Evidence를 남겨 취소, 재시도, 복구, 업데이트·롤백, 내보내기와 복원을 가능하게 합니다.

로컬 우선은 '어떤 정보도 기기 밖으로 나가지 않는다'는 뜻이 아닙니다. 사용자가 외부 AI, connector, AgentPackage/runtime, 메신저 또는 수신자를 선택하면 승인된 작업 Context가 해당 기능의 정책에 따라 전송될 수 있습니다. AgentOS는 이를 '로컬'이라는 말 뒤에 숨기지 않고 경계를 명확히 보여야 합니다.

## 상태 이동

사용자 상태는 다음 도구로 로컬 런타임 사이에서 이동할 수 있습니다.

```sh
scripts/agentos-backup.py DATA ARCHIVE
scripts/agentos-restore.py ARCHIVE EMPTY_DATA
```

아카이브는 무결성을 확인하고 Memory record, Work Evidence, 검토된 assistant/package declaration 같은 지속 상태를 담을 수 있습니다. provider credential, session, 로컬 폴더 Grant, 엔진/모델 선택 또는 Telegram pairing은 포함하지 않으며, 대상 런타임은 다시 명시적으로 claim하고 연결해야 합니다.

## 개발 설치

```sh
brew install jongtae/agentos/agentos
agentos start
```

일반 사용자 설치 경험을 다듬는 동안 Homebrew 경로는 개발자와 자체 호스팅 사용자용으로 유지합니다.

## 개발 거버넌스

저장소 개발은 [Development Constitution](docs/development-constitution.en.md), 이슈에 연결된 브랜치, PR, 필수 검증, [Goal 실행 계약](docs/goal-execution-contract.en.md)을 따릅니다.

개발 순서는 다음 원칙을 사용합니다.

`Constitution → Spec → Authority/Threat Model → Plan → Tasks → Implement → Verify → Converge`

Spec Kit·BuilderMethods Agent OS·Open AgentOS 계열에서 유용한 개발 패턴을 참고하지만 이들을 Personal AgentOS runtime dependency로 넣지 않습니다. 상태 기반 구현자/검토자 handoff도 저장소 개발 인프라이지 일반 사용자의 AgentOS runtime이나 실제 무인 운영을 증명하는 기능이 아닙니다.

구현 전 [AGENTS.md](AGENTS.md), [PRD.md](PRD.md), [TASKS.md](TASKS.md), [로드맵](docs/roadmap.md)을 확인하세요.
