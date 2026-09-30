# Historical execution plan

> 이 문서는 Kubernetes 기반 초기 프로토타입의 historical 기록이다. 현재 제품 방향과 활성 실행 순서는 [제품 비전](../concepts/PRODUCT_VISION.ko.md), [파일 작업공간 계약](../../file-workspace-first-experience-contract.ko.md), `delivery-plan.yaml`의 FILE-WS 프로그램을 기준으로 한다. 아래 내용은 현재 구현 지시가 아니다.

제품 단위: 개인별 에이전트 환경. 원본 agentos는 변경하지 않는 참고 checkout.

1. 개인 환경 기반: Namespace, 개인 PVC/Secret/ServiceAccount, 제한된 runtime, 관리자 CLI.
2. 지속성 수직 구현: 개인 기억 저장, 파일 목록, 영속 작업 큐, 예약 작업, 중지/재개.
3. 실제 kind 검증: 두 사용자, 잘못된 인증 거부, 데이터 분리, Pod 재생성, 오프라인 예약 실행.
4. 후속: 사용자 로그인/관리 API, LLM 및 원본 도구 adapter, 실행 Job 격리, 중앙 wake-up scheduler.
5. 운영: NetworkPolicy를 집행하는 CNI, 타 tenant 네트워크 차단 실증, 백업/복원, sandbox, 배포 자동화.

이번 구현은 1–3의 로컬 개발 MVP. 테스트용 결정적 도구만 실행하며 LLM 에이전트 완성을 주장하지 않는다.
개인 런타임당 단일 writer SQLite/PVC로 시작한다. 다중 replica 공용 API를 만들 때 PostgreSQL을 도입한다.
중지한 환경은 자동으로 깨우지 않는다. 예약 작업은 환경이 실행 중이면 처리하고 중지 중 만료된 작업은 재개 후 처리한다.
관리자 CLI는 kubeconfig 권한을 가진 운영 도구이며 사용자에게 배포하지 않는다.
검증: HTTP 인증, 입력 제한, SQL 영속성, 작업 중복 방지, 두 namespace/PVC 및 재시작 수용 테스트.

## 이번 실행 상태

- 1–3 구현 및 실제 kind 수용 테스트 통과. 상세 결과는 E2E_RESULT.json.
- 원본 코드는 수정하지 않았으며 별도 저장소의 로컬 브랜치에서 작업했다.
- 다음 구현 단위: 로그인과 개인 환경을 연결하는 관리 API, 실제 LLM adapter 및 대화 기록.
- 이후 실행 Job과 자동 깨우기를 추가한다. 네트워크 격리 실증 전 외부 사용자 공개는 범위 밖이다.
