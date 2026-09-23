# AgentOS UX v1.1 — 개인 에이전트 DM

추적 에픽: [#149](https://github.com/Jongtae/agentos/issues/149)  
마일스톤: [AgentOS UX v1.1](https://github.com/Jongtae/agentos/milestone/5)

## 제품 기준

AgentOS는 사용자가 설정을 관리하는 콘솔이 아니라, 한 명의 개인 에이전트와 대화하는 로컬 우선 DM이다. 웹과 Telegram은 하나의 개인 대화와 작업 기록을 공유한다. 조사·기록·검토 역할은 내부에서 협업할 수 있지만, 사용자는 결과와 필요한 짧은 상태만 본다.

UI는 텍스트, 여백, 한 개의 입력창을 중심으로 한 절제된 현대적 스타일을 유지한다. 모델 이름, API 키, 도구 로그, 내부 역할, 진단은 기본 화면에 노출하지 않는다.

## 사용자 흐름

1. **첫 사용:** 사용자는 AI 연결 없이 메모를 남긴다. 대화형 추론이 필요한 순간에만 AI 연결을 제안받는다.
2. **일상 요청:** 사용자는 웹이나 Telegram에서 자연어로 요청한다. 에이전트는 필요할 때만 `조사하고 있어요` 같은 상태를 보이고 결과를 돌려준다.
3. **장기 업무:** 대화와 결과가 쌓이면 에이전트가 작업공간 저장을 제안한다. 사용자가 수락할 때만 저장한다.
4. **결과 확인:** 조사·계획·정리는 대화 속 결과로 읽고 저장하거나 후속 요청을 이어간다.
5. **개인정보:** 결과에는 `공개 웹 3곳 참고`, `내 컴퓨터의 문서 2개 사용` 같은 짧은 정보 경계를 표시한다. 외부 AI 전송은 기존 승인 규칙을 따른다.
6. **복구:** 재시작·전달 불확실성은 자동 재실행하지 않고, 사용자가 할 다음 행동을 명확히 안내한다.

## Telegram 말풍선 경험

Telegram은 단순 알림 채널이 아니라 같은 개인 에이전트 DM의 원격 화면이다. UX-03은 Telegram의 기본 말풍선 문법 안에서 다음을 보장한다.

- 요청을 받은 뒤 한 번만 짧게 응답하고, 긴 작업은 하나의 수정되는 진행 말풍선으로 표현한다.
- 완료는 답변을 먼저 읽히게 하고, 필요할 때만 짧은 근거 줄과 웹에서 이어보기 행동을 붙인다.
- 버튼은 진행 보기, 대기 중 취소, 승인, 거절, 웹에서 이어보기처럼 현재 작업에 필요한 행동만 제공한다.
- 모델명, 도구명, 내부 역할 대화, 문서 원문·경로·식별자는 말풍선에 표시하지 않는다.
- 실패·재시작·전달 불확실성은 자동 재시도를 암시하지 않고 사용자의 다음 행동을 한 문장으로 안내한다.
- 자연어가 기본 입력이다. 현재의 전문가용 컨텍스트 명령은 보안상 명시 선택을 유지하되, UX-03에서 안내형 선택 흐름으로 감싼다.

## 이터레이션

| 순서 | 이슈 | 결과 |
| --- | --- | --- |
| UX-01 | [#150](https://github.com/Jongtae/agentos/issues/150) | 대화 중심 웹 홈과 점진적 관리 화면 |
| UX-02 | [#151](https://github.com/Jongtae/agentos/issues/151) | 사용자 수락형 작업공간과 저장 결과 |
| UX-03 | [#152](https://github.com/Jongtae/agentos/issues/152) | 같은 대화로 느껴지는 Telegram DM |
| UX-04 | [#153](https://github.com/Jongtae/agentos/issues/153) | 사람의 언어로 표현한 정보 경계와 복구 · 완료 |
| UX-03a | [#159](https://github.com/Jongtae/agentos/issues/159) | 명령어 없이 고르는 Telegram 컨텍스트 선택 |
| UX-05 | [#154](https://github.com/Jongtae/agentos/issues/154) | 웹·Telegram 인수 검증과 릴리스 |

## 참고 기준

- [ChatGPT Projects](https://help.openai.com/ko-kr/articles/10169521-projects-in-chatgpt): 지속되는 대화·자료·지시의 작업 단위
- [ChatGPT Tasks](https://help.openai.com/en/articles/10291617-tasks-inchatgpt): 대화에서 시작해 상태와 결과로 이어지는 작업
- [Home Assistant dashboards](https://www.home-assistant.io/dashboards): 로컬 연결은 필요할 때만 관리하는 경험
- [Claude Artifacts](https://support.anthropic.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them): 대화에서 분리해 다시 쓰는 결과물

AgentOS는 이 제품들의 화면을 복제하지 않는다. 개인 소유, 로컬 데이터 경계, Telegram 연속성이라는 차별점을 DM 경험에 적용한다.
