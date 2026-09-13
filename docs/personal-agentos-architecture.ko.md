# Personal AgentOS 아키텍처 — 한국어 안내

> 이 문서는 사용자/소유자를 위한 한국어 companion이다. 내부 개발의 단일 원본은 [영문 Personal AgentOS Architecture](personal-agentos-architecture.en.md)다. 이 문서에 적힌 장기 구조가 현재 모두 구현되었다는 뜻은 아니며, 실제 지원 여부는 [로드맵](roadmap.md)과 이름이 지정된 검증 근거를 따른다.

## 제품 정의

**Personal AgentOS는 한 사람이 자신의 환경에 설치해 소유하는 로컬 우선 개인 AI 운영 환경이다.**

장기 아키텍처는 다음으로 요약한다.

> **Personal AgentOS = 소유자 중심 Personal AI Kernel + Agent Distribution Platform**

커널은 사용자의 지속 상태와 권한을 소유하고, Agent 유통 플랫폼은 외부 AgentPackage를 앱처럼 발견·검토·설치·업데이트·제거할 수 있게 한다. Agent, 모델, connector, marketplace, multi-agent framework가 사용자의 canonical state의 주인이 되어서는 안 된다.

## 계층

```text
                       OWNER
                         |
              대화 / 작업 / 승인 / 설치
                         |
+---------------------------------------------------+
|                  PERSONAL AGENTOS                 |
|                                                   |
| Owner plane                                       |
| - identity / policy                               |
| - Context / Memory                                |
| - data / workspace / Artifact                     |
| - Grant / approval                                |
| - Work / Event / Evidence / recovery              |
|                                                   |
| Capability plane                                  |
| - tools / connectors                              |
| - capability registry                             |
| - Runtime Adapter boundary                        |
|                                                   |
| Distribution plane                                |
| - AgentPackage / Package Manager                  |
| - Registry / trust metadata                       |
| - Marketplace / discovery                         |
|                                                   |
| Experience plane                                  |
| - local UI / Telegram / companion                 |
| - Agent inspect/install/permission UI             |
+-------------------------+-------------------------+
                          |
                   Work-scoped Grant
                          |
        Codex / Claude / Local / Ruflo / others
```

여기에서 OS라는 말은 macOS/Linux를 대체하는 host OS라는 뜻이 아니다. 한 사람의 AI 상태, 권한, Work, 결과와 근거를 특정 모델이나 Agent보다 오래 유지하는 지속 계층이라는 뜻이다.

## 커널 primitive

커널은 Agent 자체보다 다음 10개 primitive를 기준으로 동작한다.

- **Owner** — 이 Personal AgentOS의 human principal, 정책과 trust setting의 주체.
- **Context** — 특정 Work에 필요한 task-scoped 정보. 자동으로 영구 Memory가 되지 않는다.
- **Memory** — 출처·confidence·sensitivity·retention·supersession 의미를 가진 지속 owner knowledge.
- **Artifact** — 문서, 코드, 이미지, spreadsheet, report 같은 지속 결과물과 provenance.
- **Capability** — 특정 구현과 독립된 typed ability.
- **Runtime** — bounded Work를 수행하는 교체 가능한 실행 환경.
- **Grant** — resource/action/scope/destination/time/budget에 대한 명시적 권한.
- **Work** — goal, Context, Grant, runtime, checkpoint, Artifact, Evidence, recovery를 가진 지속 작업.
- **Event** — Work 생성을 유발할 수 있는 trigger. Event 자체가 행동 권한을 주지는 않는다.
- **Evidence** — 어떤 package/runtime/context/grant/tool/destination이 사용되었고 무엇이 바뀌었는지 남기는 근거.

사용자에게 Agent는 앱처럼 보일 수 있지만, 커널은 Agent-independent해야 한다. 그래야 LLM Agent, API, script, MCP server, Codex/Claude Code, local model, Ruflo 같은 framework를 같은 Work/Grant/Evidence 계약 아래 둘 수 있다.

## AgentPackage

**AgentPackage**는 사용자가 설치하는 Agent/app 단위다. package manifest는 최소한 다음 성격의 정보를 선언하도록 설계한다.

- package ID, publisher, version, AgentOS API compatibility;
- capability/action과 Runtime 요구사항;
- filesystem/data scope와 외부 network destination;
- secret/connector reference;
- Memory read와 MemoryCandidate write policy;
- Event/background subscription;
- time/cost/resource budget;
- consequential action approval;
- input/output Artifact;
- dependency와 sandbox profile;
- health check, install/update/rollback/remove behavior;
- licence, provenance, digest/signature/SBOM.

Package는 **필요하다고 주장하는 잠재 권한**을 설명할 뿐이다. 실제 권한은 AgentOS가 현재 정책과 Work-specific Grant를 평가한 뒤에만 생긴다.

## 설치와 권한은 다른 상태다

```text
발견
 → 검토
 → exact version/digest 확인
 → integrity/trust metadata 검증
 → 격리된 영역에 stage
 → health check
 → installed-disabled
 → 필요하면 credential/connection 별도 설정
 → owner/policy가 Grant/enable
 → Work 단위 실행
 → update / rollback
 → disable / quarantine
 → uninstall
```

다음을 절대로 같은 상태로 취급하지 않는다.

`downloaded != installed != enabled != connected != authorized-for-action`

Package 설치가 Grant를 만들지 않는다. Credential을 연결해도 그 credential이 기술적으로 가능한 모든 행동을 허용하는 것이 아니다. Event를 구독해도 trigger된 행동이 자동 승인되는 것이 아니다.

Update가 permission, data scope, external destination, Memory/background behavior, dependency, budget 또는 consequential action을 넓히면 기존 승인을 자동으로 상속하지 않고 새 policy/owner 결정을 요구한다.

## Context와 Memory

Work에는 AgentOS가 owner-authorized source에서 구성한 **ContextSnapshot**만 전달한다. 전체 대화나 모든 owner data를 기본 전달하지 않는다.

외부 AgentPackage는 canonical owner Memory를 기본적으로 직접 수정하지 않는다. 장기 기억 후보는 **MemoryCandidate**로 반환하고 source, confidence, sensitivity, retention/expiry, supersession 정보를 포함한다. AgentOS 정책/owner가 실제 Memory 반영 여부를 결정한다.

Package-local/runtime-local memory가 필요할 수는 있지만 package boundary에 종속된 implementation detail이며 owner Memory로 조용히 승격되어서는 안 된다.

## Runtime

Runtime은 Codex, Claude Code, model provider, local model, script/API executor, human-mediated worker, Ruflo 같은 delegated framework가 될 수 있다.

공통 원칙은 다음과 같다.

- Work-scoped Context와 effective Grant만 받는다.
- deadline, budget, cancel, idempotency를 지킨다.
- Artifact, Evidence, MemoryCandidate를 표준 형식으로 반환한다.
- Grant를 스스로 만들거나 넓힐 수 없다.
- canonical Memory를 직접 소유하거나 수정하지 않는다.
- sealed Evidence를 다시 쓰지 않는다.
- 최종 Work 완료는 worker 자기 선언이 아니라 AgentOS validation을 거친다.

### Ruflo

Ruflo는 강력한 multi-agent execution environment가 될 수 있지만 Personal AgentOS의 kernel은 아니다. AgentOS가 Ruflo를 사용하더라도 swarm 내부 agent/memory/state는 package/runtime-local이다. nested agent/tool은 parent Work Grant보다 넓은 권한을 가질 수 없다.

## Registry와 Marketplace

### Registry

Registry는 package 배포의 identity/integrity metadata plane이다.

- publisher namespace/identity;
- immutable exact release/version/digest;
- API/runtime compatibility;
- signature/provenance/SBOM;
- trust/evaluation metadata;
- advisory, revocation, quarantine;
- optional package location.

Registry에 private owner Context/Memory/Work 내용을 저장하지 않는다.

### Marketplace / Discovery

Marketplace는 검색, 추천, ranking, review, curation, 향후 commerce를 제공할 수 있다. 하지만 별점, install 수, ranking, payment는 security authority가 아니다.

인기 Agent라도 quarantine/signature/Grant 정책을 우회할 수 없다. Marketplace 검색을 위해 raw private prompt 전체를 외부로 보내는 것을 기본으로 하지 않고 구조화된 capability 요구와 최소 metadata를 우선한다.

## Trust는 하나의 별점이 아니다

다음 신호를 서로 구분한다.

- publisher identity;
- package signature/integrity;
- build provenance/SBOM;
- static policy/schema verification;
- behavioural conformance/evaluation;
- permission/data-destination risk;
- update/incident/revocation history;
- user/expert review, install base;
- curator status.

서명된 package도 악성일 수 있고 인기 package도 과도한 권한을 요구할 수 있다. `Verified`라는 말은 무엇을 검증했는지 항상 구체적으로 설명해야 한다.

## 초기 생태계와 reference Agent

초기 AgentOS는 General Assistant, Files, Research, Coding 같은 소수 reference package로 시작할 수 있다. 이들의 목적은 최고의 앱을 직접 제공하는 것이 아니라 OS와 공개 contract를 bootstrap하는 것이다.

reference package도 third-party package와 같은 Package/Runtime/Grant contract를 사용하고 숨겨진 특권을 받지 않는다.

생태계 cold start를 줄이기 위해 official format과 license가 허용하는 범위에서 MCP 및 선택된 OpenAI/Codex, Claude skill/plugin을 AgentPackage로 import/wrap할 수 있다. 외부 생태계 package도 AgentOS의 Grant, sandbox, Memory, Evidence 규칙을 그대로 적용받는다.

## Agent 자동 발견/설치의 단계

Capability acquisition은 행동 권한과 별도 축으로 본다.

1. **L1** owner가 직접 선택/설치.
2. **L2** AgentOS가 부족한 capability에 맞는 candidate를 추천.
3. **L3** exact source/version/digest/licence/permission/data destination/cost/removal/health 계획을 보여주고 owner 승인을 받아 설치.
4. **L4** 충분히 신뢰되는 low-risk package만 standing policy 아래 자동 설치 가능. enable/Grant는 별도.
5. **L5** 설치된 Agent가 다른 capability를 요청할 수 있으나 kernel을 통해서만 요청하고 우회 설치하지 못함.

첫 Agent Distribution Platform MVP는 L4/L5가 필요하지 않다.

## 현재 구현과 계획 구분

현재 완료된 첫 usable slice는 [#314](https://github.com/Jongtae/personal-agentos/issues/314)의 파일·폴더 개인 작업공간이다. 통합 구현은 PR #320, 검증/closeout은 PR #324에 기록되어 있다.

이 근거는 deterministic adapter와 임시 local file 기반 검증이며 외부 model, Telegram, Google Drive/OAuth, recurring scheduler, 개인 폴더, AgentPackage 설치, Registry, Marketplace, Ruflo 또는 자동 capability acquisition의 live operation을 증명하지 않는다.

Agent Distribution Platform은 [#333](https://github.com/Jongtae/personal-agentos/issues/333)과 #334–#346의 **계획된 후속 workstream**이다. 이슈가 있다는 이유만으로 실행이 활성화되지 않는다.

기존 D-MP2-02 capability recommendation 계약은 과거 read-only 추천 범위의 근거로 그대로 보존한다. 새 distribution contract가 이를 소급해 marketplace/install 권한이 있었던 것처럼 해석하지 않는다.

## 핵심 불변 조건

1. 한 사람의 durable personal state는 AgentOS가 소유한다.
2. kernel은 agent-independent하다.
3. install은 authorization이 아니다.
4. 외부 전송은 별도 policy boundary다.
5. package/runtime/nested agent는 minimum Work authority만 받는다.
6. send/payment/delete/privilege expansion 같은 consequential action은 명시적 권한이 필요하다.
7. canonical Memory는 owner-authoritative다.
8. Work는 restart/retry/update/runtime 교체에서 가능한 범위로 복구 가능하고 idempotent해야 한다.
9. exact package/runtime revision과 provenance를 Evidence에서 추적한다.
10. trust를 하나의 badge로 압축하지 않는다.
11. owner state는 provider credential/session/package cache/marketplace account와 독립적으로 portable해야 한다.
12. design/mock/fixture/signature/listing은 live operation의 증거가 아니다.
