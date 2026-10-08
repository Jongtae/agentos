# Personal AgentOS: 지금 되는 것, 아직 마찰이 있는 것, 앞으로 가려는 곳

[README](../README.ko.md) 뒤에 있는 근거와 경계 페이지입니다. 최신 공개 배포본과 더 새로운 `main` 구현을 구분하고 synthetic/fixture, installed-smoke, owner-live, product-direction 증거를 서로 섞지 않습니다.

## 증거를 읽는 기준

- **공개 배포본:** 해당 빌드의 설치 smoke와 synthetic 여정 증거는 release manifest에 기록합니다.
- **현재 main:** 병합된 코드와 모의 환경·fixture 점검이 새 계약을 뒷받침합니다. 전체 경험을 실제 외부 서비스에서 관찰했다는 뜻은 아닙니다.
- **소유자 파일럿:** 공개용으로 선택한 소유자 녹화에는 별도의 출처와 화면 관찰 범위가 있습니다. 특정 리비전의 반복 재현이나 배포판 검증과는 구분합니다.
- **제품 방향:** README의 이어지는 대화와 아래 예시는 지향하는 경험을 설명합니다. 하나의 관찰된 실행이나 배포된 구매 통합 기능이 아닙니다.

<!-- readme-section:demo-recording -->
## README 데모

README 데모는 2026-10-07에 녹화한 Telegram 화면 녹화 네 개를 편집한 것으로, 2026-10-08에 공개용으로 선택했습니다. 저녁 약속의 경로·식당 대화, 이마트 장바구니에 작은 상품 하나를 담고 결제는 맡기는 장면, 교보문고 장바구니 할인 질문에 확인하지 못한 단계를 밝히는 장면을 보여 줍니다. [데모 기록](assets/readme/demo/README.md)에 원본 해시, 편집 구간, 가림 처리를 남깁니다.

증거 범위는 **편집한 화면 녹화**입니다. 화면은 PA의 응답을 보여 줄 뿐 독립적인 백엔드·도구 실행 기록이 아니며, 앱 리비전이나 모델은 표시되지 않습니다. AI 교체, 결제 완료, 공개 배포판의 반복 재현 검증을 보여 주지는 않습니다. 아래의 과거 synthetic 감사와 재구성 그림은 원래 증거 범위를 유지합니다.

<!-- readme-section:status -->
## 지금 되는 것과 아직 마찰이 있는 것

아래 v1 journey 표의 근거는 synthetic first-user audit [#472](https://github.com/Jongtae/agentos/issues/472)입니다. 실제 제품 구성에 injected transport를 사용해 검증했으며, **실제 외부 제공자 운영은 실행하지 않았습니다.** 현재 배포 태그에는 이후의 Presence/Decision/execution 소스가 포함되지만, 이 역사적 표가 통합된 경험을 실제 서비스에서 검증한 것은 아닙니다. 이후 작업의 계약과 병합 테스트는 각각의 근거 수준에서 읽어야 합니다.

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

<!-- readme-section:release-illustrations -->
## 공개 배포본의 여정 설명

아래 그림은 모의 서비스를 사용한 v1 일정·파일 여정을 재구성하고 축약한 설명입니다. 실제 계정의 스크린샷이나 공개 배포본에서 모든 여정을 실행할 수 있다는 약속은 아닙니다. 한국어 답변을 바탕으로 작성했으며, 배포본별 한계는 [release manifest](release-manifest.json)에 기록되어 있습니다.

![재구성한 synthetic v1 일정·파일 여정](assets/readme/hero.ko.png)

![Synthetic 첫 사용자 여정: 파일, 메일, 일정, 기억, 조사와 재시작 후 이어가기](assets/readme/scenes.ko.png)

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

위의 synthetic v1 여정이 지향하는 위임 방식은 다음과 같습니다. 정확히 실행 가능한 범위와 마찰은 근거 표와 release manifest에 기록되어 있으며, README의 대표 대화는 제품 방향을 설명합니다.

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

설치형 에이전트에도 같은 규칙이 적용됩니다. `downloaded != installed != enabled != connected != authorized-for-action`. 패키지를 설치해도 아무 권한도 생기지 않고, 데이터나 행동을 넓히는 업데이트는 새 승인이 필요하며, 제거는 패키지 권한을 회수하되 내 산출물은 남깁니다. 다섯 개의 plane 구조와 BDI에서 영감을 받은 attention 렌즈(설계 렌즈이지 출시된 상태 기계가 아님)를 포함한 전체 그림은 [컨셉 페이지](../VISION.md), [architecture](personal-agentos-architecture.en.md), [platform foundation](agent-distribution-platform-foundation.en.md), [roadmap](roadmap.md)에 있습니다.

<!-- readme-section:release -->
## Homebrew 배포본

**Homebrew 패키지는 태그가 붙은 main 커밋의 최신 공개 배포본 `v1.1.1`(2026-10-07)을 설치합니다.** [release manifest](release-manifest.json)에 포함 소스와 로컬 설치 검증을 기록했습니다. 그 검증은 패키지 설치와 포그라운드 동작에 대한 것이며 실제 Telegram·Google·쇼핑이나 README의 미팅 장면 전체를 입증하지 않습니다. README의 대표 대화는 제품 방향 예시입니다.

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

이 프로젝트는 **코딩 하네스, 스웜 프레임워크, 호스트 커널, macOS/Linux 대체품이 아닙니다.** 이 저장소의 GitHub/Codex 전달 자동화는 Personal AgentOS를 만드는 도구이지 제품이 아닙니다. 기여하려면 [CONTRIBUTING.md](../CONTRIBUTING.md)부터 읽어 주세요. 기여자는 [AGENTS.md](../AGENTS.md), [Development Constitution](development-constitution.en.md), [Goal Execution Contract](goal-execution-contract.en.md)를 따릅니다. 제품 완료에는 유용한 결과 증거와 거부/복구 증거가 필요하며, 초록색 CI만으로는 제품 주장이 되지 않습니다.
