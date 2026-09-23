# Personal AgentOS: 지금 되는 것, 아직 마찰이 있는 것, 앞으로 가려는 곳

> **한국어 번역본.** 기준 문서는 [영어 원본](product-status.en.md)입니다.

[README](../README.ko.md) 뒤에 있는 근거와 경계 페이지입니다. README는 무엇을 할 수 있는지 보여주고, 이 페이지는 그것을 어떻게 아는지, 무엇이 아직 거친지, 무엇이 방향일 뿐인지, 프로젝트가 어떻게 만들어지고 어떤 라이선스인지 적습니다.

<!-- readme-section:status -->
## 지금 되는 것과 아직 마찰이 있는 것

가장 최근의 synthetic first-user audit은 [#472](https://github.com/Jongtae/personal-agentos/issues/472)입니다. 실제 제품 구성에 injected transport를 사용해 검증했으며, **실제 외부 제공자 운영은 실행하지 않았습니다.** fixture 성공은 live service 성공의 증거가 아닙니다.

| 영역 | 현재 근거 |
| --- | --- |
| 설치/시작/재시작 | 로컬 deterministic first-use 경로 통과. 실제 새 Mac의 Homebrew/launchd 검증은 별도 운영 gate입니다. |
| 파일 | Synthetic **pass-with-friction**. 인용 부호를 쓴 문구로 요약, 작업공간 저장, 재시작 후 재사용은 동작하지만 자연스러운 “그걸 파일로 저장해줘” 표현은 아직 놓칩니다(#481). |
| 메일 | Synthetic **pass-with-friction**. 연결·재인증·검색·재개는 동작하지만 찾은 메일을 대화에서 읽는 것은 아직 안 됩니다(#473, #478). |
| 일정 | Synthetic **pass-with-friction**. 생성·초안·수정·취소·승인은 동작하지만 일정 조회는 아직 설정 화면의 항목이 필요하고, 모델이 준비한 취소·변경 초안은 대화에서 승인할 길이 없습니다(#475, #482, #483). |
| 조사 | Synthetic **pass-with-friction**. 출처가 있는 known/unknown 결과는 동작하지만 “추천해줘” 표현과 파일 읽기 직후 요청은 잘못 라우팅됩니다(#448, #474). |
| 기억 | Synthetic **pass-with-friction**. 기억·조회·수정·검토 대기 항목은 동작하지만 삭제는 웹에서만 됩니다(#479). |
| 정직한 결과 | `main`에 병합됨: 텔레그램은 실패하거나 부분 완료된 턴을 더 이상 모델의 답으로 전달하지 않고(#476), 거부된 저장은 더 이상 성공으로 보고하지 않습니다(#488). 웹 화면과 완전히 실패한 위임에는 같은 처리가 아직 필요합니다(#489, #490, #493, #494). |
| 에이전트 배포 | v0.1 패키지 스키마와 계약은 있지만 제3자 패키지 실행과 공개 Marketplace는 현재 제품 주장이 **아닙니다**. |

자율 구매, 임의의 컴퓨터 사용, 범용 웹 검증, 실시간 재고/결제 검증, 임의의 제3자 패키지 실행, 공개 에이전트 마켓플레이스에 대한 **현재 주장은 없습니다.**

<!-- readme-section:everyday-scene -->
## 앞으로 가려는 곳

<!-- capability:illustrative-product-direction -->

> **Product direction — 현재 지원 기능을 뜻하지 않습니다.**

> **나:** “세제랑 휴지가 거의 떨어졌어. 평소 쓰던 제품이나 괜찮은 대안을 찾아서 가격과 배송비를 비교하고 구매 준비해줘. 주문하기 전에는 나한테 물어봐.”
>
> **Personal AgentOS:** 허용된 맥락을 모으고, 선택지를 조사하고, 확인된 정보와 아직 확인이 필요한 정보를 나누고, 다음 행동을 준비한 뒤 승인 경계에서 멈춥니다.

**이 장면은 product direction을 설명하기 위한 예시이며, 현재 자율 구매나 결제가 제공된다는 뜻이 아닙니다.** 미용실 예약, 허용한 정보로 여행 준비물 정리, 내 승낙을 기다리는 구매는 모두 같은 모양입니다. 귀찮은 부분은 맡기고, 결정은 내가 합니다. 예약, 결제, 외부 메시지 전송은 구현과 증거가 뒷받침될 때에만 지원한다고 표현합니다.

<!-- readme-section:delegation-flow -->
## 방금 무슨 일이 있었나

[README](../README.ko.md)의 장면 어느 것이든, 그 밑에서 일어난 일은 이렇습니다.

**일은 맡기고, 통제는 내가.**

- 내가 허용한 것만 썼습니다. 그 폴더, 그 메일함, 그 캘린더.
- 중요한 선 앞에서 멈췄습니다. 내가 승인이라고 말하기 전에는 바깥에 아무것도 만들거나 보내거나 바꾸지 않았습니다.
- 결과, 내가 받아들인 기억, 실제로 실행된 것의 기록을 남겼습니다. 그래서 다음 주에는 대화 기록이 아니라 결과에서, 어떤 모델로든 이어갑니다.
- 단계가 실패하거나 절반만 되면, 모델의 표현이 아니라 관측된 결과를 받습니다.

<!-- readme-section:chatbot-difference -->
## 무엇이 다른가

| | 호스팅 비서 | AI가 붙은 노트·할 일 워크스페이스 | Personal AgentOS |
| --- | --- | --- | --- |
| 어디서 도는가 | 벤더 서버 | 내 노트가 있는 곳 | 내 컴퓨터. 모델은 로컬이든 원격이든 선택 |
| 무엇에 손댈지 누가 정하는가 | 벤더 | 내가 목표·할 일·지식을 AI용으로 정리 | 내가 폴더·계정·도구 단위로 정함 |
| 중요한 행동 앞에서 | 벤더가 정한 방식대로 | 그 역할이 아님 | 멈추고 나에게 물음 |
| 끝난 뒤 남는 것 | 벤더 계정 안의 대화 기록 | 노트와 할 일 | 내가 소유한 결과·기억·실행 기록. 다른 모델로도 재사용 |
| 단계가 실패하면 | 모델의 표현 | 그 역할이 아님 | 실패 또는 부분으로 표시된 관측 결과(텔레그램은 지금, 웹 화면은 진행 중) |

워크스페이스는 AI를 *위해* 일을 정리합니다. Personal AgentOS는 AI가 *그 안에서* 일하는 환경입니다. AI가 무엇에 접근하고, 무엇을 할 수 있고, 실제로 무슨 일이 있었고, 모델을 바꿔도 무엇이 내 것으로 남는지를 정합니다.

<!-- readme-section:under-the-hood -->
## 내부는 짧게

내 개인 AI가 하나의 모델, 하나의 벤더, 하나의 에이전트와 같은 것이어서는 안 되므로, 내가 소유하는 층은 갈아 끼울 수 있는 일꾼과 분리되어 있습니다.

`Owner · Context · Memory · Artifact · Capability · Runtime · Grant · Work · Event · Evidence`

모델, 코딩 에이전트, 커넥터, 위임된 런타임은 능력을 요청하고, 나와 내 정책이 결정합니다. [owner-control contract](owner-control-contract.en.md)는 내가 언제나 할 수 있는 여섯 가지를 정합니다. 일꾼이 무엇이고 무엇을 요청하는지 확인하기, 사용할 데이터 고르기, 내 정보가 가는 곳 보기, 설치나 연결과 별개로 행동 제한하기, 솔직한 보고와 함께 멈추고 회수하기, 일꾼을 교체할 때 내 상태를 보존하고 옮기기입니다. 오너 상태는 백업·복원 스크립트로 무결성 검사와 함께 내보내고 복원할 수 있으며, 자격 증명·세션·폴더 허용은 의도적으로 제외되어 다시 연결해야 합니다.

설치형 에이전트에도 같은 규칙이 적용됩니다. `downloaded != installed != enabled != connected != authorized-for-action`. 패키지를 설치해도 아무 권한도 생기지 않고, 데이터나 행동을 넓히는 업데이트는 새 승인이 필요하며, 제거는 패키지 권한을 회수하되 내 산출물은 남깁니다. 다섯 개의 plane 구조와 BDI에서 영감을 받은 attention 렌즈(설계 렌즈이지 출시된 상태 기계가 아님)를 포함한 전체 그림은 [architecture](personal-agentos-architecture.en.md), [PRD](../PRD.md), [platform foundation](agent-distribution-platform-foundation.en.md), [product vision](../PRODUCT_VISION.ko.md), [roadmap](roadmap.md)에 있습니다.

<!-- readme-section:release -->
## Homebrew 배포본

**Homebrew 패키지는 최신 공개 배포본 `v1.1.0`(2026-09-23)을 설치하며, README의 모든 장면이 그 안에 들어 있습니다**(정확한 내용과 관측 기록은 [release manifest](release-manifest.json)에 있습니다). 그 태그 이후 `main`에 병합된 작업은 다음 배포 전까지 그 빌드에 없습니다.

```sh
brew install jongtae/agentos/agentos
agentos start
```

공개 상태는 [release procedure](release.en.md)에서 추적합니다. `v1.0.4` 이하에는 이 장면들이 하나도 없습니다.

<!-- readme-section:license -->
## 라이선스

코드는 [AGPL-3.0-only](../LICENSE)입니다. 실행하고, 고치고, 나눌 수 있으며, 수정본을 배포하거나 네트워크 서비스로 운영하면 그 사용자에게 수정된 소스를 제공해야 합니다. “Personal AgentOS” 이름과 로고는 코드 라이선스가 아니라 [상표 고지](../TRADEMARKS.md)를 따릅니다. 기여는 같은 라이선스로 받으며 CLA는 없습니다.

<!-- readme-section:development -->
## 어떻게 만드는가

이 프로젝트는 **코딩 하네스, 스웜 프레임워크, 호스트 커널, macOS/Linux 대체품이 아닙니다.** 이 저장소의 GitHub/Codex 전달 자동화는 Personal AgentOS를 만드는 도구이지 제품이 아닙니다. 기여자는 [AGENTS.md](../AGENTS.md), [Development Constitution](development-constitution.en.md), [Goal Execution Contract](goal-execution-contract.en.md)를 따릅니다. 제품 완료에는 유용한 결과 증거와 거부/복구 증거가 필요하며, 초록색 CI만으로는 제품 주장이 되지 않습니다.
