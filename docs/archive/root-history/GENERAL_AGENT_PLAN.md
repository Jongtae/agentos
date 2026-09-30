# AgentOS 0.2 — general personal-agent runtime

## Product intent

설치한 개인 AgentOS가 사용자의 발화에 따라 필요한 도구를 선택하고,
호스트에서 실행한 결과를 모델에 돌려주어 답변을 완성한다.
배포 방식(Homebrew, 컨테이너, Kubernetes)은 이 동작과 분리한다.

## Implementation

- 모든 일반 발화에 같은 도구 목록을 제공하고 native tool calling의 `auto` 선택을 사용한다.
- 웹 검색, 날씨, 연결 폴더 검색·읽기, 메모, 조사·검토 에이전트 위임을 공통 루프로 실행한다.
- OpenRouter/호환 API, Ollama, Anthropic의 도구 호출과 결과를 공통 형식으로 변환한다.
- 무료 라우터에서 선택된 모델은 작업 동안 유지한다. 429일 때만 무료 라우터로 한 번 재시도하며 완료된 도구 결과를 유지한다.
- 도구 이름·인수·호출 ID를 검증하고 실행 횟수를 제한한다. 호출 실패와 부분 완료를 기록한다.
- 파일은 사용자가 연결한 폴더 안의 UTF-8 텍스트만 읽는다. 경로 이탈과 숨김 파일 접근을 거부한다.
- 전문 에이전트는 별도 모델 대화로 실행하며, 제공된 작업과 최근 로컬 도구 증거를 받는다. 재귀 위임과 메모 쓰기는 허용하지 않는다.
- 웹에서 실제 도구의 시작·완료·실패 기록을 확인할 수 있다. 모델 내부 추론을 표시하는 기능은 아니다.

## Completion checks

1. 같은 대화에서 웹 검색 → 로컬 파일 검색 및 읽기 → 검토 위임 → 일반 대화 → 메모 저장이 각각 올바른 도구로 처리된다.
2. 일반 대화로 전환하면 이전 검색/날씨 도구가 강제 실행되지 않는다.
3. 파일 답변은 합성 검증 문서의 정확한 날짜를 포함한다.
4. 위임은 실제 별도 모델 호출과 결과 반환으로 확인한다.
5. 허용 폴더 이탈, 중복 메모, 제공자별 도구 결과 변환, 호출 제한 복구를 자동 테스트한다.
6. Homebrew로 설치한 실행 파일에서도 임시 데이터로 설치·설정·기록 유지 및 실제 모델 호출을 검증한다.

Live results: `GENERAL_AGENT_ACCEPTANCE.json`. A successful run proves those prompts and
provider conditions, not all possible requests or guaranteed free-provider availability.

## Remaining scope

외부 Codex/Claude Code 등 에이전트 엔진 연결, 플러그인 설치, PDF/Office 추출,
파일 편집, 셸 실행, 이메일/캘린더 연동은 아직 구현하지 않았다.
현재 전문 에이전트는 같은 모델 제공자를 사용하는 내장 역할이다.
Ollama·Anthropic은 프로토콜 자동 테스트 대상으로, 실제 설치/키를 이용한 검증은 별도다.
웹 검색은 검색 결과 요약과 링크를 반환하며 전체 페이지를 읽는 도구는 아직 없다.
