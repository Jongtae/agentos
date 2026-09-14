# D-AP-01 — 코어 프리미티브와 AgentPackage v0.1 안내

> 이 문서는 소유자용 한국어 설명입니다. 규범적 기준은 영어 원문
> [Core Primitives and AgentPackage v0.1](core-primitives-agentpackage-v0.1.en.md)입니다.
> 번역이 다르게 해석될 경우 영어 원문과 상위 헌법·아키텍처가 우선합니다.

## 무엇이 정해졌나

v0.1은 Owner, Context, Memory, Artifact, Capability, Runtime, Grant, Work,
Event, Evidence와 AgentPackage가 어떤 데이터를 주고받는지 검토 가능한
계약으로 고정합니다. AgentOS는 소유자의 영구 상태, 권한, 승인, 작업 상태,
복구와 증거의 최종 권위자입니다. 패키지와 런타임은 필요한 권한을 요청할
수는 있지만 스스로 발급하거나 확대할 수 없습니다.

이 작업은 명세·JSON Schema·결정적 fixture입니다. 패키지 다운로드, 설치,
실행, Registry, Marketplace, OAuth/자격 증명, 외부 연결, Ruflo, MCP/OpenAI/
Claude 가져오기를 구현하거나 실제로 작동한다고 주장하지 않습니다.

## 소유자가 알아야 할 경계

- `다운로드됨 != 설치됨 != 활성화됨 != 연결됨 != 행동 권한 있음`입니다.
- 설치 후 기본 상태는 `installed-disabled`이며 설치는 Grant를 만들지 않습니다.
- ContextSnapshot은 한 Work에 제한된 입력이며 영구 Memory가 아닙니다.
- 외부 패키지의 영구 기억 출력은 기본적으로 MemoryCandidate입니다. AgentOS가
  별도 정책으로 검토·수락해야 새로운 정식 MemoryRecord가 생기며, 양쪽은
  동일한 봉인된 결정 Evidence를 참조해야 합니다.
- 파일, 네트워크 목적지, 비밀 참조, 백그라운드 Event, 비용·시간 예산,
  결과 행동과 승인이 manifest에 명시되어야 합니다. 생략되거나 모호하면
  허용하는 대신 거부합니다.
- 위임된 Grant는 모든 상위 Grant의 최신 revision이 활성·유효해야 하며,
  상위 Grant가 취소되거나 만료되면 하위 권한도 즉시 무효가 됩니다.
- 구독 Event를 패키지에 전달하려면 현재 Work와 그 행동·범위·예산 전체를
  포함하는 유효 Grant가 있어야 합니다.
- 비밀 값, 루트/홈 전체 경로, 와일드카드 네트워크, 직접 정식 Memory 쓰기,
  자체 Grant 발급, 버전이 고정되지 않은 의존성은 유효한 v0.1 manifest로
  표현할 수 없습니다.
- Artifact와 Evidence에는 해당 Work와 정확한 package/runtime revision 및
  digest가 남습니다. 패키지를 제거해도 소유자 산출물과 보존 대상 증거는
  정책에 따라 유지됩니다.

## 버전과 변경

v0.1 객체는 알 수 없는 필드를 거부합니다. 새 필드나 의미 변경은 명시적인
새 schema 버전과 검토가 필요하며, 소비자가 모르는 권한을 추측해서 허용하면
안 됩니다. 마이그레이션은 기존 기록을 보존한 채 복사 → 검증 → 원자적 선택
순서로 수행해야 하며, 실패 시 기존 기록이 계속 권위 있는 상태로 남습니다.
마이그레이션 자체는 Grant 발급, MemoryCandidate 수락, Work 완료 또는 증거
등급 상승을 할 수 없습니다.

## 이번 증거가 의미하는 것

저장소의 schema 검증은 구조와 권한 선언이 fail-closed인지, 정상 fixture가
통과하고 잘못된 fixture가 거부되는지를 증명합니다. 이는 명세·정적 schema·
결정적 테스트·CI 증거이며 실제 패키지 설치/실행이나 외부 Registry/
Marketplace 운영 증거가 아닙니다. 과거 D-MP2-02의 권한도 기존의 로컬
읽기 전용 추천 범위 그대로 유지됩니다.
