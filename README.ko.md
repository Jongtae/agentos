# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

<!-- readme-parity:v1 -->
<!-- readme-section:hero -->

## 일은 맡기고, 통제는 내가.

**생활부터 업무까지, 실제 일을 맡길 수 있는 개인 AI.**

원하는 결과를 말하세요. Personal AgentOS는 내가 허용한 파일, 도구, 계정과 모델을 사용하고, 그 범위 안에서 일을 진행하며, 중요한 외부 행동 전에는 승인을 요청하고, 유용한 결과를 owner-controlled state에 남기도록 설계됩니다.

핵심 mental model은 단순합니다. **“AI와 대화한다”보다 “내 개인 AI에게 일을 맡긴다”에 가깝습니다.**

> **Personal AgentOS = 실제 일을 위임하는 개인 AI + 소유자 권한을 기준으로 동작하는 AI 환경**

<!-- readme-section:everyday-scene -->

## 먼저 생활의 한 장면으로 이해하기

<!-- capability:illustrative-product-direction -->

> **나:** “세제랑 휴지가 거의 떨어졌어. 평소 쓰던 제품이나 괜찮은 대안을 찾아서 가격과 배송비를 비교하고 구매 준비해줘. 주문하기 전에는 나한테 물어봐.”
>
> **Personal AgentOS:** 허용된 맥락을 모으고, 선택지를 조사하고, 확인된 정보와 아직 확인이 필요한 정보를 나누고, 다음 행동을 준비한 뒤 승인 경계에서 멈춥니다.

이것이 제품이 지향하는 경험입니다. **귀찮은 일은 맡기되, 결정은 내가 합니다.**

**이 장면은 product direction을 설명하기 위한 예시이며, 현재 자율 구매나 결제가 제공된다는 뜻이 아닙니다.** 현재 지원 범위와 근거는 아래에 별도로 적습니다. 예약 확정, 결제, 외부 메시지 전송 같은 중요한 외부 행동은 실제 구현과 증거가 있을 때만 지원한다고 표현합니다.

같은 패턴은 다른 생활 장면에도 적용됩니다.

- “토요일 오후 일정에 맞는 미용실을 찾아 예약 준비해줘. 확정하기 전에는 물어봐.”
- “이번 주말에 집을 비워. 허용한 일정과 정보를 보고 준비물과 살 것을 정리해서 다음에 이어서 볼 수 있게 남겨줘.”
- “이 자료들을 읽고 쓸 만한 결과로 정리해서 저장해줘. 재시작한 뒤에도 다시 찾게 해줘.”

<!-- readme-section:delegation-flow -->

## 이렇게 생각하면 됩니다

**🗣️ 맡기기 → 🔎 허용된 범위에서 일하기 → ✋ 필요할 때 승인받기 → 📦 결과 남기기**

1. **결과를 맡깁니다.** 통합 절차를 직접 조립하기보다 원하는 결과를 말합니다.
2. **허용 범위 안에서 일합니다.** AgentOS가 승인된 Context, Capability, 목적지와 Runtime/Model 사용을 중재합니다.
3. **중요한 결정은 소유자에게 남깁니다.** 새 권한이나 의미 있는 외부 효과는 그에 맞는 승인을 요구합니다.
4. **유용한 상태를 남깁니다.** Artifact, 승인된 Memory, Work/Event 기록과 Evidence는 교체 가능한 worker와 분리되어 남습니다.

<!-- readme-section:chatbot-difference -->

## 일반 챗봇과 무엇이 다른가

| 일반적인 챗봇 | Personal AgentOS가 지향하는 방식 |
| --- | --- |
| 질문에 답함 | 제한된 권한 안에서 일을 맡아 결과까지 진행 |
| 주로 현재 대화가 Context | 소유자가 허용한 파일, Memory, Connector와 작업 Context를 사용 |
| 결과가 대화창에 머무르기 쉬움 | 재사용 가능한 Artifact와 작업 기록을 남김 |
| Tool 권한이 암묵적이거나 서비스 중심일 수 있음 | Owner policy와 Grant가 무엇을 어디까지 쓸지 결정 |
| 특정 모델이 제품의 중심 | 모델과 Agent는 소유자 권한 아래의 교체 가능한 worker |

목표는 모든 것을 자동으로 실행하는 것이 아닙니다. **데이터, 권한, 결정과 장기 상태의 통제권을 넘기지 않으면서 실제 일을 맡길 수 있게 하는 것**이 목표입니다.

<!-- capability:current-supported-slice -->
<!-- readme-section:try-today -->

## 지금 검증된 범위를 직접 써보기

현재 가장 분명한 첫 작업은 파일 작업공간 흐름입니다. 저장 결과와 원본 보존, 재시작 후 재사용에 대한 구체적인 저장소 근거가 있습니다.

1. 전용 참고 폴더에 작은 Markdown/text 파일을 둡니다.
2. 그 폴더에는 읽기 권한을, 별도의 관리 작업공간에는 결과 저장 권한을 부여합니다.
3. **“‘Launch review’를 요약해서 ‘Launch notes’로 저장해줘.”**라고 요청합니다.
4. 관리 작업공간에 새 Markdown 결과가 생기고 원본은 바뀌지 않았는지 확인합니다.
5. AgentOS를 재시작한 뒤 저장한 결과를 다시 찾아달라고 요청합니다.

문서화된 파일 작업 경로에서는 지원되는 직접 모델 제공자 연결을 사용하고, 참고 폴더와 관리 작업공간을 명시적으로 허용하며, 외부 제공자에게 승인된 문서 맥락을 보내기 전 필요한 공유 승인을 거칩니다.

### 설치

```sh
brew install jongtae/agentos/agentos
agentos start
```

브라우저는 `http://127.0.0.1:8787`에서 열립니다.

**이 Homebrew 명령은 최신 공개 배포본 `v1.0.4`(2026-09-07)를 설치하며, 이 버전은 현재 `main`보다 뒤입니다.** `main`에는 이 배포본 이후의 기능 개발과 first-user 개선이 더 포함되어 있습니다. 정확한 지원 경로는 [QUICKSTART](QUICKSTART.md), 공개 상태는 [release procedure](docs/release.en.md)를 따르세요.

<!-- readme-section:status -->

## 지금 되는 것과 아직 마찰이 있는 부분

가장 최근의 synthetic first-user audit은 [#472](https://github.com/Jongtae/personal-agentos/issues/472)입니다. 실제 제품 구성에 injected transport를 사용해 검증했으며, **실제 외부 제공자 운영은 실행하지 않았습니다.** fixture 성공을 live service 성공으로 해석하면 안 됩니다.

| 영역 | 현재 근거 |
| --- | --- |
| 설치/시작/재시작 | #472에서 local deterministic first-use 경로 통과. 실제 새 Mac의 Homebrew/launchd 검증은 별도 운영 gate입니다. |
| 파일 | Synthetic **pass-with-friction**. 승인 폴더 요약, 관리 결과 저장, 재시작 후 재사용은 동작하지만 자연스러운 “그걸 파일로 저장해줘” 표현에는 아직 gap이 있습니다(#481). |
| Gmail | Synthetic **pass-with-friction**. 연결·재인증·검색·재개 경로가 있으나 contextual resume과 읽기/답장 UX defect가 남아 있습니다(#473, #478). |
| Calendar | Synthetic **pass-with-friction**. 제한된 create/preview/correct/cancel/approve 흐름은 근거가 있으나 조회와 승인 UX gap이 남아 있습니다(#475, #482, #483). |
| 조사 | Synthetic **pass-with-friction**. 공개 자료 조사에서 출처와 known/unknown을 나누는 결과를 만들 수 있으나 routing/context defect가 남아 있습니다(#448, #474). |
| Memory | Synthetic **pass-with-friction**. 기억·조회·수정과 owner-visible candidate는 있으나 삭제/receipt UX 마찰이 남아 있습니다(#479). |
| Agent 유통 | v0.1 schema/contract는 있지만 임의의 제3자 AgentPackage 실행이나 공개 Marketplace를 현재 지원한다고 주장하지 않습니다. |

현재 **자율 구매, 임의 컴퓨터 조작, 모든 웹 페이지 검증, 실시간 재고/결제 총액 확인, 임의 제3자 패키지 실행, 공개 Agent Marketplace**를 지원한다고 주장하지 않습니다.

<!-- readme-section:why-agentos -->

## 왜 이름이 “AgentOS”인가

내 개인 AI가 특정 모델 하나, 특정 회사 하나, 특정 Agent 하나와 같아져서는 안 되기 때문입니다.

Personal AgentOS는 소유자에게 귀속되는 계층과 교체 가능한 worker를 분리합니다.

`Owner · Context · Memory · Artifact · Capability · Runtime · Grant · Work · Event · Evidence`

모델, 코딩 Agent, Connector와 위임 Runtime은 바뀔 수 있습니다. 이들은 Capability를 요청하고, AgentOS policy와 소유자가 실제 권한을 결정합니다. Worker를 바꾸더라도 유용한 개인 상태가 함께 사라지지 않는 것이 핵심입니다.

<!-- readme-section:owner-control -->

## 통제권은 소유자에게

[Owner Control Contract](docs/owner-control-contract.en.md)는 여섯 가지 관찰 가능한 권리를 정의합니다.

1. **검토하기** — package/source, 제작자, 버전, 실행 방식과 요청 권한을 확인합니다.
2. **자료 선택하기** — 어떤 문서, Memory, 계정을 쓸 수 있는지 정합니다.
3. **목적지 보기** — 작업 정보가 어디로 가는지 확인합니다.
4. **행동 제한하기** — 설치/연결과 실제 행동 권한을 분리합니다.
5. **중지·회수하기** — 권한을 회수하고 진행 중 외부 효과의 불확실성을 솔직하게 표시합니다.
6. **상태 유지·이동하기** — worker를 제거하거나 교체해도 owner state를 보존합니다.

로컬 설치와 로컬 전용 처리는 같은 말이 아닙니다. 외부 모델을 쓰는 로컬 package는 승인된 Context를 그 제공자에게 보냅니다. 연결 해제, 권한 회수, worker 제거와 원격에 보관된 데이터 삭제는 서로 다른 작업입니다.

<!-- readme-section:architecture -->

## 제품을 이해한 다음 보는 구조

| 계층 | 책임 |
| --- | --- |
| **Owner plane** | Owner identity/policy, Context/Memory 권한, data/workspace, Grants/approvals, Work/Event, Artifacts, Evidence와 recovery |
| **Capability plane** | Typed tools/connectors와 제한된 runtime interface |
| **Distribution plane** | AgentPackage, Package Manager, Registry, trust metadata, 향후 Marketplace/discovery |
| **Worker plane** | 교체 가능한 model, Codex/Claude Code, local/API worker와 선택적 delegated runtime |
| **Experience plane** | Conversation, 유용한 결과, 관찰 가능한 progress, approval/control, 향후 agent discovery |

Kernel은 **agent-independent**일 수 있고 제품 경험은 **agent-centric**가 될 수 있습니다.

<!-- readme-section:bdi -->

## BDI-inspired attention lens

BDI는 **개념적 설계 렌즈**입니다. 이미 canonical BDI state machine이 구현되었다는 뜻도 아니고 hidden chain-of-thought를 노출하자는 뜻도 아닙니다.

- **Belief view:** 허용된 task context, 승인된 Memory, 관련 Evidence/Artifact, 현재 Capability/Grant 사실.
- **Desire:** 소유자가 원하는 결과와 성공 기준.
- **Attention:** 지금 중요한 것, 허용된 것, 관련 목적지/효과, 승인 필요 여부.
- **Intention:** 현재의 제한된 계획과 다음 실행 단계.
- **Execution:** Capability/Runtime 중재를 통해 관찰된 Work/Event, Artifact와 Evidence를 만듭니다.

결과가 다음 작업 Context에 도움을 줄 수는 있지만 모든 결과가 자동으로 durable Memory가 되는 것은 아닙니다. 제3자는 `MemoryCandidate`를 제안하고 policy/owner가 canonical Memory 반영 여부를 결정합니다.

<!-- readme-section:ecosystem -->

## Agent 생태계 방향

AgentPackage lifecycle은 다음 상태를 의도적으로 구분합니다.

`downloaded != installed != enabled != connected != authorized-for-action`

설치는 Grant를 자동 생성하지 않아야 합니다. Data, action, destination, Memory 또는 background behavior를 확대하는 update는 새 권한을 요구합니다. 제거는 package 권한을 회수하되 owner-owned output과 필요한 Evidence는 policy에 따라 보존합니다.

먼저 유용하고 제한된 Agent와 공개 authoring path를 입증하는 것이 우선이며, 큰 store나 결제 시스템이 첫 단계의 전제는 아닙니다. 자세한 내용은 [architecture](docs/personal-agentos-architecture.en.md), [PRD](PRD.md), [platform foundation](docs/agent-distribution-platform-foundation.en.md), [product vision](PRODUCT_VISION.ko.md), [roadmap](docs/roadmap.md)을 참고하세요.

<!-- readme-section:portability -->

## 이동성과 한계

```sh
scripts/agentos-backup.py DATA ARCHIVE
scripts/agentos-restore.py ARCHIVE EMPTY_DATA
```

지원되는 owner state와 검토된 선언은 무결성 검증과 함께 export/restore할 수 있습니다. Provider credential, session, local-folder Grant, engine/model 선택, Telegram pairing은 이 이동용 archive에 포함되지 않으며 다시 연결하거나 승인해야 합니다.

Local-first는 local-only나 자동 안전을 뜻하지 않습니다. Host security, package isolation, 이미 전송된 data와 remote provider retention은 여전히 실제 경계입니다.

<!-- readme-section:development -->

## 개발 거버넌스

이 프로젝트는 **coding harness, swarm framework, host kernel 또는 macOS/Linux 대체품이 아닙니다.** GitHub/Codex delivery automation은 Personal AgentOS를 만드는 개발 인프라이지 최종 사용자 제품이 아닙니다.

[AGENTS.md](AGENTS.md), [Development Constitution](docs/development-constitution.en.md), [Goal Execution Contract](docs/goal-execution-contract.en.md)에 따라 issue → bounded branch → implementation → validation → 필요한 independent review → merge/closeout 순서로 진행합니다.

제품 완료는 green CI, schema, 파일 수만으로 판단하지 않습니다. **유용한 결과 근거와 필요한 거부/recovery 근거가 함께 있어야 합니다.**
