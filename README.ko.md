# Personal AgentOS

[English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

<!-- readme-parity:v1 -->
<!-- readme-section:hero -->

## 우리가 바라던 개인 비서

어제 나눈 이야기를 오늘 이어가고, 생각이 다 정리되지 않아도 편하게 말하고, 하던 일을 함께 끝내고 싶습니다. 매번 나를 처음부터 설명하지 않아도 되는 비서, 그리고 그 비서가 나에 대해 아는 것을 믿고 맡길 수 있는 환경을 바랍니다.

**Personal AgentOS는 내가 설치하고 통제하는 환경에서 그런 개인 비서(PA)를 만들어보는 프로젝트입니다.**

어시스턴트는 질문에 답하고, 컴퓨터 에이전트는 명령을 실행합니다. 개인 에이전트라면 대화와 작업이 바뀌고 AI가 교체되어도 나와 함께 이어갈 수 있어야 합니다. 이 지속성을 **Presence**라고 부릅니다.

<!-- readme-section:ownership -->

## 내 비서가 내 환경에 있어야 하는 이유

비서가 내 일상을 더 잘 알수록, 그 기억을 누가 갖고 무엇을 할 수 있는지 누가 결정하는지가 중요해집니다. 비서와 쌓은 관계가 특정 회사나 모델, 한 번의 대화에 묶여 있지는 않았으면 합니다.

AgentOS는 기억과 진행 중인 일, 권한을 내 환경에 둡니다. 어떤 AI를 쓸지, 어떤 정보를 사용하고 어디까지 접근하게 할지 내가 정합니다. 더 좋은 AI가 나와도 처음부터 다시 시작하는 대신, 내 비서의 능력이 좋아지는 방향입니다.

로컬 우선(local-first)은 로컬 전용(local-only)이 아닙니다. 로컬 모델과 외부 모델을 선택할 수 있고, 외부 모델을 쓰면 요청에 사용되는 맥락은 그 제공자로 전송됩니다.

<!-- readme-section:presence -->

## 대화가 이어지려면 무엇이 필요할까

Presence에는 긴 대화 기록 이상의 구조가 필요합니다. 나에 대해 아는 것, 지금 상황, 진행 중인 일, 내가 허락한 범위, 실제로 일어난 일이 서로 연결되어야 합니다.

AgentOS는 이것을 공통된 개념과 관계로 표현합니다. 이 구조가 **온톨로지**입니다. 하나의 일에 관련된 맥락·권한·결과·근거를 연결하고, 새로 생긴 일이나 정정된 내용을 다음 판단에 반영할 수 있게 합니다. 그래서 AI가 바뀌거나 일이 중단돼도 무엇을 알고 있었고 어디서 이어가야 하는지가 남습니다.

<picture>
  <source media="(max-width: 600px)" srcset="docs/assets/readme/presence-overview.ko.narrow.svg">
  <img src="docs/assets/readme/presence-overview.ko.svg" alt="개념 설명 일러스트: NVIDIA 질문에 답하는 어시스턴트, Amazon 명령을 실행하는 컴퓨터 에이전트, 시간에 걸친 대화를 이어가는 Personal AgentOS. 나는 하나의 PA와 대화하고, 맥락·일·권한은 교체 가능한 AI와 도구 위의 AgentOS에 남습니다. 이 예시는 제품 방향을 설명하며 실제 관찰 실행이나 배포된 통합 기능을 뜻하지 않습니다.">
</picture>

AgentOS의 판단 계층이 필요한 AI와 도구를 고르고 결과를 확인합니다. 나는 PA와 이야기하고, AgentOS가 대화 아래에서 이 구조를 이어갑니다. **같은 PA, 다른 AI.**

<!-- readme-section:conversation -->

## 말은 짧아도, 맥락은 이어지도록

*제품 방향을 설명하는 예시이며, 실제 관찰 실행이나 배포된 구매 기능을 뜻하지 않습니다.*

아래 이미지는 제공하신 한국어 화면을 바탕으로 대화를 짧게 각색한 것입니다. 귀갓길 식사를 찾기 위한 위치 공유, 골프 벨트 비교와 장바구니 작업 전 계정 로그인 요청, 식당 사진에서 이어지는 근처 산책 대화를 보여줍니다. 설명을 위해 편집한 재구성 화면이며, 제품을 그대로 캡처한 기록이나 해당 연동 기능의 배포 증거는 아닙니다.

<picture>
  <source media="(max-width: 600px)" srcset="docs/assets/readme/owner-pilot-conversation-edited.png">
  <img src="docs/assets/readme/owner-pilot-conversation-edited.png" alt="제공된 한국어 화면을 각색한 PA 대화 세 장면: 위치를 공유해 귀갓길 식당을 찾고, 골프 벨트를 비교한 뒤 계정 로그인을 요청하고, 식당 사진에서 근처 산책으로 이어갑니다. 설명용 재구성이며 제품 화면 그대로의 캡처는 아닙니다.">
</picture>

[이미지 원본 크기로 보기](docs/assets/readme/owner-pilot-conversation-edited.png) · [제공하신 원본 화면 보기](docs/assets/readme/owner-pilot-conversation-reference.jpg).

그림 속 대화는 이렇게 이어집니다.

1. **퇴근길 저녁:** “퇴근하는 길인데, 저녁 먹고 갈까?” PA가 현재 위치를 물은 뒤 거리와 영업 여부가 표시된 세 곳을 제안합니다. 나는 두 번째를 고릅니다.
2. **이런 벨트 찾아줘:** 사진을 보내자 PA가 세 가지 벨트를 비교합니다. 첫 번째를 장바구니에 담아달라고 하자, PA는 진행 전에 쇼핑 계정 로그인이 필요하다고 말합니다.
3. **여기서 저녁 먹는 중:** 식당 사진을 보내고 다음에 뭘 할지 묻습니다. PA는 근처 산책·카페·바를 제안합니다. 산책을 고르면 길과 운영 시간을 확인하겠다고 답합니다.

몇 시간 간격으로 건네는 짧은 말에도 같은 연속성이 필요합니다.

> “커피 거의 다 떨어졌네.”<br>
> 몇 시간 뒤: “이제 나가려고. 가는 길에 살 만한 데 있을까?”<br>
> 나중에: “시간 없네. 지난번에 사던 걸로 그냥 사줘.”

바라는 모습은 단순합니다. PA가 무엇을 사려는지, 지난번 선택이 무엇인지 이어서 이해하고, 관련된 맥락을 활용하며, 빠진 정보나 권한은 필요해진 순간에 묻는 것입니다. 나는 대화를 이어갑니다. 워크플로를 직접 조립할 필요는 없습니다.

<!-- readme-section:try-today -->

## 가볍게 시작하기

macOS에서 [Homebrew](https://brew.sh)를 사용한다면:

```sh
brew install jongtae/agentos/agentos
agentos start
```

1. 브라우저에서 [http://127.0.0.1:8787](http://127.0.0.1:8787/) 설정 화면이 열리면 **바로 시작하기**를 누릅니다.
2. 내 모델을 연결하고 연결 테스트를 마칩니다. 도구 호출을 지원하는 로컬 Ollama 모델이나 내 API 접근 권한으로 OpenAI·OpenAI 호환 서비스·Anthropic을 사용할 수 있습니다. 설정 화면은 현재 한국어입니다.
3. **설정 → 외부 연결**에서 BotFather로 만든 내 봇의 토큰을 입력해 연결합니다. 표시된 연결 링크를 Telegram에서 열고 **시작**을 누릅니다.
4. 그 Telegram 대화에서 **“이번 주에 무엇에 집중하면 좋을지 같이 정리해보자.”** 하고 말을 걸어보세요.

Python은 Homebrew가 함께 설치하며, 모델 이용 권한은 별도로 준비합니다. 대화하는 동안 `agentos start`를 실행한 상태로 둡니다. 모델 설정, 파일 작업, Telegram, 최신 소스 실행은 [QUICKSTART](QUICKSTART.md)에 안내되어 있습니다.

**현재 단계:** Homebrew는 이전 프리뷰인 **v1.1.0**(2026-09-23)을 설치합니다. 이후 `main`의 Presence 구현은 이 배포판에 포함되지 않습니다. 해당 배포판에서는 일정 생성이 불가능하고 조사는 부분 지원입니다. 자세한 범위는 [release manifest](docs/release-manifest.json)를 보세요. [현재 상태](docs/product-status.ko.md)에서 사용할 수 있는 것, 검증한 것, 앞으로의 목표를 구분해 설명합니다.

<!-- readme-section:more -->

## 더 알아보기

- [왜 이 프로젝트를 만드는가](VISION.md) — 컴퓨터와 어떤 관계를 만들고 싶은지 설명합니다.
- [구조와 온톨로지](docs/personal-agentos-architecture.en.md) · [Presence](docs/presence-experience-contract.en.md) — 개인 상태·일·통제를 하나의 지속되는 비서로 연결하는 방법입니다.
- [연구와 참고 자료](docs/acknowledgements.en.md) — 개인 에이전트, 기억, 사용자 모델, 정보의 출처에 관한 설계 배경을 모았습니다.
- [문서 지도](docs/README.md) · [기여하기](CONTRIBUTING.md) — 현재 계약과 구현을 찾아보고 함께 발전시킬 수 있습니다. 내부 문서의 기준 언어는 영어입니다.

<!-- readme-section:license -->

## 오픈소스

직접 실행하고, 의문을 제기하고, 함께 고칠 수 있는 실험입니다. 최종적인 정답이 아니더라도 의미 있는 시작이 될 수 있다고 생각합니다.

코드는 [AGPL-3.0-only](LICENSE)로 공개합니다. Personal AgentOS 이름과 로고에는 [상표 고지](TRADEMARKS.md)가 적용됩니다. 참고한 외부 작업은 [감사의 말과 참고 자료](docs/acknowledgements.en.md)에 기록합니다.
