<div align="center">

<pre>
          P E R S O N A L           
                                    
   ___                __  ____  ____
  / _ |___ ____ ___  / /_/ __ \/ __/
 / __ / _ `/ -_) _ \/ __/ /_/ /\ \  
/_/ |_\_, /\__/_//_/\__/\____/___/  
     /___/                          
</pre>

**내 컴퓨터에서 돌아가는 나의 개인 에이전트.<br>아래의 AI는 바꿔도, 기억과 진행 중인 일과 권한은 그대로 남습니다.**

[![CI](https://github.com/Jongtae/agentos/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/Jongtae/agentos/actions/workflows/validate.yml) [![Full test suite](https://github.com/Jongtae/agentos/actions/workflows/full-validate.yml/badge.svg?branch=main)](https://github.com/Jongtae/agentos/actions/workflows/full-validate.yml) [![Latest release](https://img.shields.io/github/v/release/Jongtae/agentos?sort=semver&label=release)](https://github.com/Jongtae/agentos/releases) [![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](../../pyproject.toml) [![macOS | Linux | WSL2 limited](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20WSL2%20limited-555)](../../docs/QUICKSTART.md) [![License: AGPL 3.0](https://img.shields.io/badge/license-AGPL--3.0--only-blue)](../../LICENSE)

[English](../../README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

[빠른 시작](#빠른-시작) · [나에게 남는 것](#나에게-남는-것) · [동작 방식](#동작-방식) · [문서](#문서)

</div>

<!-- readme-parity:v1 -->
<!-- readme-section:hero -->

## 자비스의 두뇌가 내 것이 아니어도, 나만의 자비스를 가질 수 있을까?

**The brain can be borrowed. The assistant should remain yours.**

토니 스타크에게는 자비스(J.A.R.V.I.S.)가 있었습니다. 자신의 맥락을 이해하고 언제든 대화할 수 있으며 컴퓨터와 다양한 시스템에서 실제 일을 수행하는 개인 AI 비서였습니다. 토니는 그 두뇌까지 직접 소유했지만, 우리는 대부분 가장 뛰어난 AI 두뇌를 직접 소유하지 않습니다. 외부 기업의 모델을 사용하고, 그 모델의 성능과 가격, 정책, 접근 조건은 바뀔 수 있습니다.

그렇다면 질문은 단순히 *우리도 자비스를 만들 수 있을까?*에서 끝나지 않습니다. **외부 AI 두뇌를 빌려 쓰면서도 나의 기억과 맥락, 끝내지 못한 일과 통제권을 유지하는 진정한 개인 비서를 가질 수 있을까?** 더 좋은 AI를 쓰기 위해 지금까지의 관계를 포기해야 할까요?

Personal AgentOS는 *그럴 필요가 없다*는 가능성을 탐구합니다. 내가 설치하고 통제하는 오픈소스 환경에서 하나의 개인 에이전트(PA)가 내 맥락과 진행 중인 일과 권한을 유지하고, 실제 일을 하는 AI는 바꿀 수 있게 합니다.

<p align="center">
  <img src="../../docs/assets/readme/demo/demo-v2.ko.gif" width="360" alt="데모: PA와 나눈 한국어 Telegram 대화. 저녁 약속의 경로와 식당을 정리하고, 장바구니에 작은 상품 하나를 담은 뒤 결제 전에 멈추며, 확인하지 못한 할인 단계를 밝힙니다. 개인 정보는 흐리게 처리했습니다.">
</p>
<p align="center"><sub>데모 · Telegram 한국어 화면, 한국어 자막. 대기 시간은 줄이고 개인 정보는 흐리게 처리했습니다. · <a href="../../docs/assets/readme/demo/demo-v2.ko.gif">전체 크기로 보기</a></sub></p>

**주요 기능**

- **원하는 AI를 연결.** 로컬 Ollama 모델, OpenAI 호환·Anthropic API, Codex나 Claude Code 구독이 실제 일을 합니다.
- **대화가 바뀌어도 같은 PA.** 기억, 저장한 결과와 열린 일의 상태는 다음 대화와 재시작 뒤에도 남습니다. 중단된 실행은 몰래 다시 돌리지 않고 중단으로 보고합니다.
- **경계는 내가 정합니다.** 내가 연결한 폴더·계정·도구에서 접근이 시작됩니다. 지원되는 결제 흐름은 행동마다 승인을 요구하며, [현재 브라우저 한계](https://github.com/Jongtae/agentos/issues/758)는 공개합니다. [비밀값](../../.github/SECURITY.md)은 모델 프롬프트·로그·Evidence에 넣지 않습니다.
- **숨기지 않고 알립니다.** AI가 무언가를 기억하면 그 사실을 알리고 정확히 되돌릴 수 있게 합니다. 맡긴 일마다 내 정보 중 무엇을 썼고 어디로 보냈는지 기록합니다.
- **늘 쓰는 곳에서 대화.** 휴대폰의 Telegram이나 macOS·Linux의 브라우저에서 대화합니다. Windows는 [현재 제약이 있는 WSL2](../../docs/QUICKSTART.md#windows-wsl2)에서 동작합니다.

<!-- readme-section:principles -->

## Personal AgentOS의 다섯 가지 핵심 원칙

그런데 네가 이야기한 핵심은 특정 AI의 기능이 아니잖아.

- **Presence:** 내가 별도로 앱을 찾아가서 일을 시키는 게 아니라, 평소 소통하는 공간에서 지속적으로 함께하는 비서.
- **Portable Memory:** 내 기억과 맥락이 특정 AI 서비스에 종속되지 않는 구조.
- **Model Independence:** AI 모델은 교체할 수 있지만, 나의 비서와 관계는 유지되는 구조.
- **Execution:** 대답만 하는 것이 아니라 실제 서비스와 컴퓨터에서 일을 수행하는 능력.
- **Owner Control:** 내 데이터, 권한, 실행 결과에 대한 통제권을 내가 갖는 구조.

이 다섯 가지는 완성된 기능을 모두 제공한다는 선언이 아니라, 프로젝트의 설계와 실제 사용 경험을 평가하는 기준입니다. [현재 상태](../../docs/product-status.ko.md), 위의 실제 데모, [브라우저의 알려진 한계](https://github.com/Jongtae/agentos/issues/758)를 통해 구현된 것과 검증 중인 것을 구분합니다.

<!-- readme-section:try-today -->

## 빠른 시작

macOS나 Linux에서는 명령 하나로 설치하고 바로 시작합니다. Homebrew, Python, Docker가 없어도 됩니다.

```sh
curl -LsSf https://raw.githubusercontent.com/Jongtae/agentos/94776134546ed400ab1573d171c0bca2975a5f22/scripts/install.sh | sh
```

URL은 설치 스크립트 자체도 특정 커밋에 고정합니다. 실행 전에 [고정된 스크립트 내용을 확인](https://github.com/Jongtae/agentos/blob/94776134546ed400ab1573d171c0bca2975a5f22/scripts/install.sh)할 수 있고, 스크립트는 공개 AgentOS 아카이브와 내려받는 uv 설치 프로그램의 체크섬을 검증합니다.

macOS에서 [Homebrew](https://brew.sh)를 쓴다면:

```sh
brew install jongtae/agentos/agentos
agentos start
```

1. 브라우저에서 [http://127.0.0.1:8787](http://127.0.0.1:8787/)이 열립니다. 화면은 영어가 기본이며 왼쪽 아래에서 한국어, 중국어 간체, 일본어로 바꿀 수 있습니다. 일부 고정 Telegram 상태·진행 표시와 연결 검증 오류는 아직 한국어입니다.
2. AI를 연결합니다. 도구 호출을 지원하는 Ollama 모델, OpenAI·OpenAI 호환·Anthropic API 키, 또는 Codex나 Claude Code 구독을 쓸 수 있습니다.
3. 선택: **설정 → 외부 연결**에서 내 Telegram 봇 토큰을 넣고 페어링 링크를 엽니다.
4. 이렇게 말해 보세요. **“이번 주에 제안서를 끝내야 해. 다음 할 일 몇 단계로 나눠 줘.”**

Windows에서는 PowerShell에서 `wsl --install`을 실행하고 재시작한 뒤, Ubuntu를 열어 첫 번째 명령을 실행하세요. Windows 안내, 설치 스크립트가 하는 일, 소스 실행, 모든 설정은 [QUICKSTART](../../docs/QUICKSTART.md)에 있습니다. 대화하는 동안 `agentos start`를 켜 두세요.

**배포 상태:** 두 설치 방법 모두 태그가 붙은 main 커밋의 **v1.3.0**(2026-10-10)을 설치합니다. 데모와 일상 사용 화면은 실제 사용 세션을 바탕으로 한 것으로 이 배포본의 종단 간 검증은 아니며, 구조 그림은 제품 방향 예시입니다. [release manifest](../../docs/release-manifest.json)는 배포본마다 포함 범위를 기록하고, [현재 상태](../../docs/product-status.ko.md)는 제공 기능과 테스트 근거와 방향을 구분합니다.

<!-- readme-section:ownership -->

## 나에게 남는 것

| 바뀔 수 있는 것 | 나에게 남는 것 |
| --- | --- |
| 모델과 제공자 | 나에 대한 기억과 맥락 |
| 일을 맡은 CLI 에이전트나 API | 진행 중인 일과 다음 단계 |
| 도구와 커넥터 | 권한과 승인 |
| | 실제로 실행된 일의 기록 |

더 좋은 AI가 나오면 에이전트가 아니라 일하는 AI만 바꿉니다. [누구의 에이전트인가?](../../docs/whitepapers/whose-agent.ko.md) 백서가 이 질문을 더 깊게 다룹니다.

로컬 우선(local-first)은 로컬 전용(local-only)이 아닙니다. 로컬 모델과 외부 모델을 선택할 수 있고, 외부 모델을 쓰면 요청에 사용되는 맥락은 그 제공자로 전송됩니다.

<!-- readme-section:presence -->

## 동작 방식

<picture>
  <source media="(max-width: 600px)" srcset="../../docs/assets/readme/presence-overview.ko.narrow.svg">
  <img src="../../docs/assets/readme/presence-overview.ko.svg" alt="개념 그림: NVIDIA 질문에 답하는 어시스턴트, Amazon 장바구니라는 명시적 요청을 처리하는 실행형 에이전트, 미팅의 남은 결정을 이어가는 PA. AgentOS는 허용된 일정·제안서·메모의 출처를 연결하고, 미결정 일을 남기며, 메일 초안과 실제 발송을 권한·결과로 구분합니다. AI와 도구는 교체 가능합니다. 관찰 실행이나 배포 기능이 아닌 제품 방향 예시입니다.">
</picture>

- **PA**는 내가 대화하는 에이전트이고, **AgentOS**는 그 PA의 맥락·남은 일·권한·근거를 지키는 환경입니다.
- **판단 계층**이 요청마다 AI와 도구를 고르고, 지시를 쓰고, 결과를 확인해 부족하면 다시 맡깁니다.
- **온톨로지**는 출처가 있는 대상(미팅, 계좌 잔액 등)을 그 주변의 일·역할·권한과 연결합니다. 초안을 발송으로, 초대를 수락으로 여기지 않습니다.

그림은 설계 방향이며 관찰된 실행이 아닙니다. 자세히: [아키텍처와 온톨로지](../../docs/personal-agentos-architecture.en.md) · [Presence](../../docs/presence-experience-contract.en.md)

<!-- readme-section:ai-switch -->

## AI를 바꿔도 이어지는 대화

<p align="center">
  <img src="../../docs/assets/readme/ai-switch/ai-switch-conversation.png" alt="한국어 Telegram 화면 세 장을 잘라 붙인 이미지. 1: Claude Code로 바꾼 뒤 어제 스팸을 넣었는지 뺐는지 묻자, PA가 이전 장바구니 대화를 이어받고 로그인을 요청합니다. 2: 로그인 후 CJ 스팸 클래식 200g 1개가 장바구니에 있다고 답하고, 일부 단계는 확인하지 못했다고 알립니다. 3: Codex로 바꾼 뒤 스팸을 빼 달라고 하자, 뺐고 나머지 22개 상품은 그대로라고 답합니다.">
</p>
<p align="center"><sub>실제 대화에서 발췌한 화면입니다. 로그인 링크는 잘라내고 이름은 가렸습니다. · <a href="../../docs/assets/readme/ai-switch/ai-switch-conversation.png">크게 보기</a></sub></p>

① **Claude Code로 전환.** “어제 스팸을 넣었나, 뺐나?”라는 질문에 이전 쇼핑 대화를 이어받습니다.

② **현재 장바구니 확인.** 다시 로그인한 뒤, 스팸 클래식 200g 한 개가 장바구니에 있다고 답합니다.

③ **Codex로 전환해 다음 행동 요청.** “스팸 빼줘.” 같은 대화에서 제거 결과와 나머지 22개 상품을 안내합니다.

<!-- readme-section:conversation -->

## 일상에서 쓰는 모습

*PA와 실제로 나눈 대화를 압축해 다시 그린 화면입니다. 실제 Telegram에서는 카드가 아니라 텍스트와 링크로 답합니다.*

<picture>
  <source media="(max-width: 600px)" srcset="../../docs/assets/readme/owner-pilot-conversation.ko.png">
  <img src="../../docs/assets/readme/owner-pilot-conversation.ko.png" alt="실제 사용을 바탕으로 다시 구성한 PA 대화 세 장면: 위치를 공유해 귀갓길 식당을 찾고, 골프 벨트를 비교한 뒤 장바구니 단계 전에 로그인을 요청하고, 식당 사진에서 근처 산책으로 이어갑니다. 압축한 화면이며 원본 그대로의 캡처는 아닙니다.">
</picture>

귀갓길에는 식당을 제안하기 전에 현재 위치를 묻습니다. 사진 속 벨트와 비슷한 상품은 비교한 뒤 장바구니 단계 전에 로그인을 요청합니다. 식당 사진을 보내면 지금 있는 곳에서 이어 다음에 할 일을 제안합니다. **내가 말하거나 보여 준 것 → 출처와 시각이 있는 허락된 맥락 → 필요한 질문이나 도구 → 행동의 경계 → 확인된 결과.** 장바구니에 담기와 결제는 서로 다른 행동입니다.

**다음 목표:** 몇 시간이 지나도 “그거”와 “같은 걸로”가 무엇인지 따라오는 것. 나는 대화만 이어 가고 워크플로를 조립하지 않습니다.

> “커피가 거의 떨어졌네.” · *몇 시간 뒤* · “나가는 길에 살 데 있어?” · *그 뒤* · “시간 없다. 지난번이랑 같은 걸로.”

<!-- readme-section:more -->

## 문서

| 문서 | 내용 |
| --- | --- |
| [QUICKSTART](../../docs/QUICKSTART.md) | 설치, 모델 연결, 파일, Telegram, 소스 실행 |
| [현재 상태](../../docs/product-status.ko.md) | 되는 것, 아직 불편한 것, 영역별 근거 |
| [왜 만드는가](../../docs/VISION.md) | 프로젝트의 동기 |
| [아키텍처와 온톨로지](../../docs/personal-agentos-architecture.en.md) | 커널 기본 개념, 패키지, 런타임, 소유자 통제 |
| [문서 지도](../../docs/README.md) | 현재 계약과 가이드 전체 |
| [참고한 연구와 프로젝트](../../docs/acknowledgements.en.md) | 설계에 영향을 준 연구와 프로젝트 |

**기여하기.** 이슈와 PR을 환영합니다. [CONTRIBUTING](../../.github/CONTRIBUTING.md)부터 읽어 주세요. 개발 흐름은 [AGENTS.md](../../AGENTS.md)에 있습니다. 써 보셨다면 [피드백 양식](https://github.com/Jongtae/agentos/issues/new?template=feedback.yml)이나 [Discussions](https://github.com/Jongtae/agentos/discussions)에 좋았던 점과 아쉬운 점을 남겨 주세요.

<!-- readme-section:license -->

## 라이선스

[AGPL-3.0-only](../../LICENSE). Personal AgentOS 이름과 로고는 [상표 안내](../../docs/TRADEMARKS.md)를 따릅니다.
