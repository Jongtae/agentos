# Personal AgentOS 제품 비전

> 이 문서는 사용자 관점의 제품 비전을 요약한다. 영문 단일 원본 아키텍처는 [Personal AgentOS Architecture](docs/personal-agentos-architecture.en.md)를 따른다. 현재 구현 상태는 [로드맵](docs/roadmap.md)과 이름이 지정된 검증 근거를 기준으로 판단하며, 장기 구조를 적었다고 해서 모든 기능이 구현되었다고 간주하지 않는다.

## 한 문장

**Personal AgentOS는 한 사람이 자신의 환경에 설치해 소유하고, 개인 컨텍스트·자료·권한·작업 상태를 특정 모델이나 Agent보다 오래 유지하며, 필요한 Agent를 앱처럼 설치·교체할 수 있게 하는 로컬 우선 개인 AI 운영 환경이다.**

장기 제품 전략은 다음으로 요약한다.

> **Personal AgentOS = 개인 AI 커널 + Agent 유통 플랫폼**

개인 PC와 개인 OS가 각 사람에게 지속되는 컴퓨팅 환경을 제공하고 그 위에 다양한 앱 생태계가 성장했듯, Personal AgentOS는 각 사람에게 지속되는 AI 환경과 Agent/capability 생태계를 제공하는 것을 목표로 한다. 사용자는 매번 AI 서비스마다 자신의 자료, 선호, 권한, 이전 결정을 처음부터 다시 구성하지 않고 하나의 소유 가능한 개인 AI 환경을 가진다.

## 여기서 OS가 의미하는 것

Personal AgentOS는 macOS나 Linux를 대체하는 운영체제 커널, 하이퍼바이저 또는 하드웨어 관리 계층이 아니다. 사용자가 제어하는 Mac 또는 격리된 사용자 런타임 위에서 동작하는 **지속적인 개인 AI 계층**이다.

AgentOS가 장기적으로 소유해야 하는 것은 사용자 정체성·정책, 명시적인 개인 Context/Memory, 자료와 관리 작업공간, Grant·승인, Work/Event 상태, Artifact, Evidence·복구, Capability 및 Runtime의 경계다.

Codex, Claude Code, GPT 계열 모델, 로컬 모델, MCP server, 외부 Agent 또는 Ruflo 같은 multi-agent runtime은 이 상태를 이용해 일하는 교체 가능한 실행자다. 실행 엔진이나 Agent를 바꾸어도 사용자의 개인 AI 환경 자체가 초기화되어서는 안 된다.

따라서 AgentOS는 코딩 하네스나 Agent swarm 프레임워크가 아니다. 코딩, 리서치, 커뮤니케이션, 일정·자동화 같은 기능과 외부 Agent는 같은 사용자 상태와 권한 경계 위에서 동작하는 서비스/앱이 될 수 있다. 이 저장소가 사용하는 GitHub issue/branch/PR, Goal 실행 계약, CI, 구현자–검토자 handoff는 제품을 만들기 위한 개발 인프라이며 일반 사용자가 사용하는 AgentOS 제품 자체가 아니다.

## 제품 구조

```text
                         사용자
                           |
               대화 / 작업 / 승인 / Agent 설치
                           |
+---------------------------------------------------------+
|                   PERSONAL AGENTOS                      |
|                                                         |
|  Owner plane                                            |
|  - 정체성 / 정책                                       |
|  - 개인 Context / Memory                               |
|  - 자료 / 관리 작업공간 / Artifact                    |
|  - Grant / 승인                                        |
|  - Work / Event / Evidence / 복구                     |
|                                                         |
|  Capability plane                                       |
|  - 도구 / connector                                    |
|  - capability registry                                 |
|  - runtime/engine boundary                             |
|                                                         |
|  Distribution plane                                     |
|  - AgentPackage / Package Manager                      |
|  - Registry / trust metadata                           |
|  - Marketplace / discovery                             |
|                                                         |
|  Experience plane                                       |
|  - 로컬 대화 / Telegram / companion                   |
|  - Agent 탐색·설치·권한 UI                             |
+--------------------------+------------------------------+
                           |
                    제한된 Work/Grant
                           |
          Codex / Claude / Local / Ruflo / 기타 runtime
```

Mac은 초기 공식 호스트 환경이며 일반 홈 디렉터리 전체를 Agent에 넘기지 않는다. AgentOS는 사용자 범위로 격리된 런타임과 전용 상태를 사용하고, 실행 엔진/Agent에는 AgentOS가 허용한 Context와 도구/Grant만 전달하는 방향을 유지한다.

## Agent는 제품에서는 앱이지만 커널에서는 특별한 존재가 아니다

사용자에게는 Agent가 설치 가능한 앱처럼 보여도 된다. 그러나 커널 내부에서 핵심 abstraction은 Agent 자체보다 다음 primitive다.

`Owner · Context · Memory · Artifact · Capability · Runtime · Grant · Work · Event · Evidence`

이렇게 해야 Agent가 LLM 기반이든, API/script든, MCP server든, Codex/Claude Code든, 사람을 포함한 mediated worker든 동일한 Work/Grant/Evidence 계약 아래에서 동작할 수 있다.

Distribution plane은 이 커널 위에 다음 개념을 추가한다.

`AgentPackage · Package Manager · Registry · Marketplace/Discovery · Trust/Verification`

## AgentPackage와 설치 경험

AgentPackage는 AgentOS에서 설치하는 application package에 해당한다. package는 자신이 필요한 capability, runtime, 파일·데이터 범위, 네트워크 목적지, secret/connector, Memory read/write policy, Event/background behavior, 비용·시간 한도, 승인 필요 행동, Artifact, dependency, sandbox, health check, update/rollback/remove, provenance/signature 등을 선언해야 한다.

설치는 곧 권한이 아니다.

```text
발견
  ↓
검토
  ↓
정확한 version/digest 확인
  ↓
검증
  ↓
격리된 영역에 설치 (비활성)
  ↓
health check
  ↓
필요한 connection / Grant를 별도 승인
  ↓
활성
  ↓
Work 단위 실행
  ↓
업데이트 / 롤백 / 비활성 / 제거
```

`다운로드됨 != 설치됨 != 활성화됨 != 계정이 연결됨 != 특정 행동이 허가됨`을 제품과 기술 모두에서 유지한다.

Package를 업데이트할 때 파일/데이터 범위, 외부 destination, Memory behavior, background Event, cost/resource, consequential action 권한이 커지면 기존 설치 승인을 자동 상속하지 않는다.

## Registry와 Marketplace

**Registry**는 package/publisher identity, exact release/version/digest, API/runtime compatibility, signature/provenance, trust/evaluation metadata, advisory/revocation/quarantine를 다룬다.

**Marketplace/Discovery**는 검색, 추천, ranking, review, editorial curation, 향후 commerce를 담당할 수 있다.

이 둘은 구분해야 한다. 인기 Agent라는 이유로 높은 권한을 가져서는 안 되고, 별점이나 install 수가 signature/quarantine/permission 정책을 덮어쓸 수 없다. `Verified`라는 표현도 무엇을 검증했는지(출판자 신원, 서명, build provenance, behavior eval 등)를 구체적으로 표시해야 한다.

사용자의 private Context/Memory/Work 내용을 marketplace 자체의 데이터로 만들지 않는다. AgentOS가 적합한 Agent를 추천할 때도 가능한 한 구조화된 capability 요구만 Registry/Marketplace에 전달하고 raw 개인 prompt 전체를 검색 payload로 보내지 않는 방향을 기본으로 한다.

## 초기 AgentOS는 기본 Agent가 부족해도 된다

초기 MS-DOS, Linux distribution, 초기 smartphone OS가 모든 최고의 앱을 직접 제공하지 않았듯 Personal AgentOS도 초기에는 번들 Agent가 적고 평범할 수 있다.

초기 reference/bundled Agent는 예를 들어 다음 정도면 충분하다.

- **General Assistant** — 기본 대화·작업 위임 경험
- **Files** — owner 파일/managed workspace의 안전한 기본 작업
- **Research** — web/document research와 출처가 있는 Artifact 생성
- **Coding** — bounded project coding/test/PR 준비

이들의 목적은 최고의 앱을 직접 만드는 것이 아니라 OS와 공개 AgentPackage 계약을 bootstrap하는 것이다. 번들 Agent도 외부 Agent와 같은 Package/Runtime/Grant 경계를 사용해야 하며 숨겨진 first-party 권한을 가져서는 안 된다.

## Agent 생태계는 처음부터 0에서 만들지 않는다

Marketplace의 chicken-and-egg 문제를 완화하기 위해 기존 생태계를 import/wrap할 수 있어야 한다.

우선순위는 official format과 라이선스가 허용하는 범위에서 MCP, 선택된 OpenAI/Codex 및 Claude skill/plugin metadata다. Import된 capability도 AgentPackage로 mapping되어 동일한 permission, sandbox, Memory, Evidence 규칙을 적용받아야 한다. 외부 format에서 권한을 명확히 mapping할 수 없는 기능은 자동으로 넓혀 해석하지 않고 partial/unsupported로 처리한다.

Ruflo는 좋은 Agent를 만드는 하나의 강력한 실행 환경이 될 수 있지만 Personal AgentOS의 kernel은 아니다. 향후 Ruflo-based Agent가 AgentPackage로 설치되거나 Ruflo가 Runtime Adapter로 사용되더라도 swarm 내부 memory/agent state는 package-local이며 canonical owner state는 AgentOS에 남아야 한다.

## AgentOS가 Agent를 찾아주는 경험

장기적으로는 사용자가 marketplace를 직접 검색하는 것뿐 아니라 AgentOS가 현재 설치된 capability로 목표를 달성할 수 없는 경우 필요한 capability를 식별하고 candidate package를 제시할 수 있어야 한다.

초기 단계는 다음처럼 보수적으로 진행한다.

1. 사용자가 직접 Agent를 선택/설치한다.
2. AgentOS가 적합한 Agent를 추천한다.
3. AgentOS가 exact package/source/version/licence/권한/데이터 destination/cost/removal/health plan을 만들어 설치 승인을 요청한다.
4. 향후 충분한 trust/policy가 갖춰진 low-risk package만 standing policy 아래 자동 설치할 수 있다.
5. 더 먼 미래에 Agent가 다른 capability를 요청할 수 있지만 반드시 kernel을 통해 요청하며 스스로 우회 설치하지 않는다.

Package acquisition autonomy와 실제 행동 권한은 별개다. Agent가 자동으로 설치되더라도 payment, send, delete, privilege expansion 같은 consequential action이 자동으로 허용되는 것은 아니다.

## 첫 제품 경험: 내 파일·폴더 + 내 AI

장기 제품 정체성이 OS + ecosystem이라고 해서 첫 사용 경험까지 복잡할 필요는 없다. 현재 첫 제품 단면은 **사용자가 소유한 파일·폴더 + 대화와 작업**이다.

사용자가 허용한 자료는 원본을 보존한 채 검색·이해·활용하고, 결과는 일반 앱으로 다시 열 수 있는 TXT/MD 같은 파일로 관리 작업공간에 저장한다. 연결한 참고 폴더는 기본 읽기 전용이며, 새 결과는 명시한 쓰기 범위 안에서만 생성한다. 원본, 추출 텍스트·요약, 초안, 확정 기록은 구별하고 재생성 가능한 검색 인덱스와 작업·승인·근거·복구·인증 같은 지속 운영 상태도 분리한다.

이 파일 작업공간 프로그램(#314/#315/#316)은 PR #320의 구현과 PR #324의 검증·종료 기록으로 완료되었다. 다만 현재 근거는 deterministic model과 임시 로컬 파일을 사용한 자동 검증이며 실제 외부 모델, Telegram, Google Drive/OAuth, 반복 스케줄러, 개인 폴더 또는 Agent Distribution Platform의 live operation을 검증했다는 뜻은 아니다.

## 개인 Context와 Memory

Personal AgentOS의 핵심 자산은 특정 LLM도 특정 Agent도 아니라 **지속되는 사용자 Context/Memory와 그 권한 관계**다. 하지만 모든 대화를 자동으로 영구 Memory로 만드는 것은 목표가 아니다.

Memory는 출처, confidence, sensitivity, retention/expiry, supersession/deletion을 가져야 한다. Work에 제공되는 ContextSnapshot은 해당 작업에 필요한 최소 정보만 포함하는 방향을 기본으로 한다.

외부 AgentPackage는 기본적으로 canonical Memory를 직접 수정하지 않는다. 새로운 장기 기억이 필요하면 source/confidence/sensitivity/expiry가 있는 MemoryCandidate를 제안하고 AgentOS 정책/사용자가 반영 여부를 결정한다.

## 실행 기반과 호스팅

초기 공식 런타임은 Mac이다. Mac이 꺼져 있으면 로컬 AgentOS는 실행되지 않는다. 향후 사용자는 자신의 AgentOS 상태를 다른 지원 Mac이나 관리형 인스턴스로 옮길 수 있어야 하지만 provider credential, package cache 또는 marketplace account 자체가 사용자의 영속 정체성이 되어서는 안 된다.

Kubernetes, VPS 또는 전용 기기는 배포 구현 선택지가 될 수 있지만 일반 사용자가 AgentOS를 이해하거나 설치하기 위한 제품 개념이 아니다. 관리형 호스팅을 제공하더라도 개인별 상태·권한·데이터 격리와 내보내기 가능성이 유지되어야 한다.

## 계획된 다음 단계

[#333 Agent Distribution Platform](https://github.com/Jongtae/personal-agentos/issues/333)은 다음 장기 workstream을 추적한다. #334–#339는 foundation contract, #340–#342는 local package platform/SDK, #343–#345는 ecosystem/registry, #346은 미래 capability-acquisition autonomy를 다룬다.

이 이슈들은 로드맵과 dependency를 표현할 뿐 자동 실행 authority가 아니다. 실제 개발은 owner가 goal-ready issue를 명시적으로 활성화했을 때만 진행한다.

## 성공 기준

단기 성공 기준은 사용자가 자료를 맡기고 결과를 파일로 남긴 뒤 앱을 다시 시작해 다른 대화에서도 그 결과를 찾고 활용하는 것이다. 그 과정에서 원본과 권한이 보존되고 무엇을 사용하거나 외부로 보냈는지 설명할 수 있어야 한다.

중기 성공 기준은 reference/third-party AgentPackage가 동일한 공개 contract로 설치·활성·실행·업데이트·롤백·제거되고, Agent를 바꿔도 사용자 state와 Artifact/Evidence가 유지되는 것이다.

장기 성공 기준은 사용자가 특정 provider나 Agent ecosystem에 자신의 AI 생활을 다시 구축하지 않고도, 필요한 Agent를 안전하게 선택·교체·확장할 수 있는 **자신의 Personal AI environment**를 갖는 것이다.
