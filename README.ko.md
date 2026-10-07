# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

<!-- readme-parity:v1 -->
<!-- readme-section:hero -->

## 자비스가 다른 회사의 서비스였다면?

토니 스타크가 오랫동안 자비스와 함께 일해 왔다고 생각해 봅시다. 자신의 맥락을 공유하고, 결정을 남겨 두고, 일을 맡기면서 서로 일하는 방식을 쌓아 왔습니다.

그런데 어느 날 더 좋은 AI가 등장합니다.

**토니는 더 좋은 AI를 쓰기 위해 자비스까지 잃어야 할까요?**

지능을 공급하는 회사가 바뀐다는 이유만으로, 자비스가 기억하는 토니에 대한 맥락, 아직 끝나지 않은 일, 맡겨 둔 권한, 함께 만들어 온 작업 방식까지 처음부터 다시 만들어야 할까요?

**AI는 바뀔 수 있어도, 나의 개인 에이전트는 나에게 남아야 합니다.**

Personal AgentOS는 이 생각을 실제로 탐구하는 오픈소스 개인 에이전트 환경입니다. PA의 맥락·진행 중인 일·권한·실행 근거는 내가 통제하는 환경에 남기고, 그 아래에서 일하는 AI는 선택하고 바꿀 수 있게 하려 합니다.

목표는 대화 기록이 더 긴 챗봇이 아닙니다. AI가 바뀌어도 이어지는 하나의 개인 에이전트입니다.

**같은 PA, 다른 AI.**

> **현재 단계:** Personal AgentOS는 완성된 자율 비서가 아니라 실제로 실행 가능한 탐구 단계의 프로젝트입니다. 공개 배포본에서 내 모델을 연결해 사용할 수 있지만, 아래의 미팅·지도·쇼핑 장면은 별도 표시가 없는 한 제품 방향을 설명하는 예시입니다.

<!-- readme-section:ownership -->

## 무엇이 나에게 남는가

자비스 사고실험은 여기서 구체적인 설계 질문이 됩니다. 아래에서 일하는 지능이 바뀌어도 무엇이 계속 나에게 남아야 할까요?

| | Personal AgentOS |
| --- | --- |
| **맥락** | PA가 이어갈 맥락을 내 환경에 둡니다 |
| **진행 중인 일** | 끝나지 않은 일을 채팅 기록 속에 묻지 않고 이어갈 수 있게 합니다 |
| **AI** | 로컬·외부·구독 기반 AI가 같은 PA를 위해 일할 수 있습니다 |
| **권한** | 정보 접근과 중요한 행동은 소유자의 통제 범위 안에 둡니다 |
| **근거** | 모델이 말했다는 것과 실제로 일어난 일을 구분해 남깁니다 |

이 통제 중 두 가지는 현재 배포본에 들어 있습니다. 내가 고른 AI가 사실을 Memory에 저장하면 저장한 뒤 알려 주고 정확히 되돌릴 수 있게 하며, 각 Work는 내 정보 중 무엇을 사용했고 어디로 보냈는지 기록합니다.

로컬 우선(local-first)은 로컬 전용(local-only)이 아닙니다. 외부 모델을 선택하면 해당 요청에 필요한 맥락은 그 제공자에게 전송됩니다.

더 큰 질문은 단순합니다. **내일 더 좋은 AI가 나온다면, 왜 이미 나와 일해 온 에이전트까지 처음부터 다시 만들어야 할까요?** [누구의 에이전트인가](docs/whitepapers/whose-agent.ko.md) 백서에서 이 문제를 산업과 제품 관점으로 확장합니다.

<!-- readme-section:presence -->

## 지금 실행해 보기

macOS에서 [Homebrew](https://brew.sh)를 사용한다면:

```sh
brew install jongtae/agentos/agentos
agentos start
```

1. 브라우저에서 `http://127.0.0.1:8787` 설정 화면이 열리면 **바로 시작하기**를 누릅니다.
2. 내 모델을 연결합니다. 도구 호출을 지원하는 로컬 Ollama 모델, OpenAI·OpenAI 호환 서비스·Anthropic 또는 지원되는 Codex / Claude Code 구독 경로를 사용할 수 있습니다. 모델 이용 권한은 별도입니다.
3. **설정 → 외부 연결**에서 BotFather로 만든 내 Telegram 봇을 연결하고 표시된 페어링 링크를 엽니다.
4. 대화에서 **“이번 주에 제안서 초안을 마무리해야 해. 다음 할 일을 몇 단계로 정리해줘.”**라고 말해 보세요.

대화하는 동안 `agentos start`를 실행한 상태로 둡니다. 모델 설정, 파일 작업, Telegram, 최신 소스 실행은 [QUICKSTART](QUICKSTART.md)에 안내되어 있습니다.

**공개 배포본:** Homebrew는 **v1.1.1**(2026-10-07)을 설치합니다. [release manifest](docs/release-manifest.json)에 포함 소스와 설치 검증을 기록하고, [현재 상태](docs/product-status.ko.md)에서 배포된 동작·fixture 근거·owner-pilot 근거·제품 방향을 구분합니다.

<!-- readme-section:conversation -->

## 이 프로젝트가 만들고 싶은 경험

개인 에이전트라면 마지막 질문에 답하는 데서 끝나지 않고, 한 번 꺼낸 일을 이어갈 수 있어야 합니다.

예를 들어 이렇게 말합니다.

> “다음 주 프로젝트 미팅 좀 챙겨줘. 제안서 결론을 내야 해.”

PA는 내가 허용한 맥락을 미팅과 연결하고, 아직 결정되지 않은 일을 남겨 두고, 다음에 필요한 것을 준비하며, 내 권한이 필요한 지점에서 멈추는 방향으로 일해야 합니다. 초안은 발송이 아닙니다. 초대를 받은 것은 약속을 수락한 것이 아닙니다. 모델이 “했다”고 말하는 것만으로 실제 실행의 근거가 되지 않습니다.

<picture>
  <source media="(max-width: 600px)" srcset="docs/assets/readme/presence-overview.ko.narrow.svg">
  <img src="docs/assets/readme/presence-overview.ko.svg" alt="질문에 답하는 어시스턴트, 명시적 장바구니 요청을 처리하는 실행형 에이전트, 미팅의 남은 결정을 이어가는 PA를 비교한 개념 그림. 관찰된 실행이나 배포된 연동이 아닌 제품 방향 예시입니다.">
</picture>

이렇게 이어지는 관계를 이 프로젝트에서는 **Presence**라고 부릅니다. 친근한 말투가 아니라, 여러 turn·도구·worker·실패·AI 교체를 지나도 맥락과 일이 이어지면서 사실성과 소유자의 권한이 유지되는 경험입니다.

그 구조는 [아키텍처와 온톨로지](docs/personal-agentos-architecture.en.md)와 [Presence 경험 계약](docs/presence-experience-contract.en.md)에서 자세히 설명합니다.

## 일상의 짧은 말에도 같은 PA

몇 시간 간격의 짧은 말에도 같은 원리가 필요합니다.

> “커피 거의 다 떨어졌네.”  
> 몇 시간 뒤: “이제 나가려고. 가는 길에 살 만한 데 있을까?”  
> 나중에: “시간 없네. 지난번에 사던 걸로 그냥 사줘.”

바라는 경험은 내가 워크플로를 조립하는 대신 대화를 계속하는 것입니다. PA가 관련 맥락을 이어 받고, 빠진 정보만 묻고, 내 계정이나 권한이 필요한 경계에서 멈춥니다.

아래 그림은 owner-pilot 대화를 바탕으로 압축·비식별화해 재구성한 이미지입니다. **제품 화면 그대로의 캡처나 해당 대화의 증거 기록이 아닙니다.** 그림 속 지도·쇼핑 연동은 배포된 기능이 아니라 제품 방향입니다.

<picture>
  <source media="(max-width: 600px)" srcset="docs/assets/readme/owner-pilot-conversation.ko.png">
  <img src="docs/assets/readme/owner-pilot-conversation.ko.png" alt="위치를 공유해 귀갓길 식당을 찾고, 골프 벨트를 비교한 뒤 계정 로그인을 요청하고, 식당 사진에서 근처 산책으로 이어지는 세 장면의 설명용 재구성입니다.">
</picture>

[한국어 이미지 전체 크기로 보기](docs/assets/readme/owner-pilot-conversation.ko.png) · [원본 참고 이미지 보기](docs/assets/readme/owner-pilot-conversation-reference.jpg)

공통 흐름은 다음과 같습니다.

**내 말과 사진 → 출처·시각이 있는 허용된 맥락 → 필요한 질문과 도구 → 권한의 경계 → 확인된 결과**

<!-- readme-section:try-today -->

## 지금 되는 것과 아직 아닌 것

이 저장소는 **실제로 동작하는 소프트웨어**, **테스트/fixture 근거**, **owner-pilot 관찰**, **제품 방향**을 의도적으로 구분합니다.

현재 공개 배포본에는 설치 가능한 로컬 런타임과 모델 연결, 대화 surface가 있으며, 소스에는 owner context와 Work 연속성, 모델 교체, 브라우저/로그인 handoff, skill routing, Presence 동작 관련 구현이 포함되어 있습니다. 설치 검증은 패키지 설치와 로컬 foreground 실행을 확인합니다.

반면 자율 구매, 임의의 컴퓨터 조작, 모든 웹 정보의 검증, 실시간 재고·결제 확인, 공개 에이전트 마켓플레이스, 그리고 위 미팅·쇼핑 장면 전체가 v1.1.1에서 종단 간 동작한다는 주장은 하지 않습니다.

정확한 현재 경계는 [현재 상태](docs/product-status.ko.md), 배포본별 근거는 [release manifest](docs/release-manifest.json)에서 확인할 수 있습니다.

<!-- readme-section:more -->

## 더 알아보기

- [왜 이 프로젝트를 만드는가](VISION.md) · [누구의 에이전트인가](docs/whitepapers/whose-agent.ko.md) — 개인 에이전트의 연속성을 왜 소유자가 가져야 하는지에 대한 제품·산업 논의.
- [구조와 온톨로지](docs/personal-agentos-architecture.en.md) · [Presence](docs/presence-experience-contract.en.md) · [역할과 위임](docs/research/role-ontology-and-mandate-2026-10-05.ko.md) — 맥락·일·권한·근거가 어떻게 연결되는지에 대한 설계.
- [연구와 참고 자료](docs/acknowledgements.en.md) — 설계에 영향을 준 선행 연구와 프로젝트.
- [문서 지도](docs/README.md) · [기여하기](CONTRIBUTING.md) — 현재 계약과 구현, 기여 경로. 내부 문서의 기준 언어는 영어입니다.

<!-- readme-section:license -->

## 오픈소스

Personal AgentOS는 직접 실행하고, 의문을 제기하고, 함께 고칠 수 있는 탐구입니다. 최종적인 정답이 아니더라도 의미 있는 시작이 될 수 있다고 생각합니다.

코드는 [AGPL-3.0-only](LICENSE)로 공개합니다. Personal AgentOS 이름과 로고에는 [상표 고지](TRADEMARKS.md)가 적용됩니다. 참고한 외부 작업은 [감사의 말과 참고 자료](docs/acknowledgements.en.md)에 기록합니다.
