# AgentOS Kubernetes 전환 아키텍처 초안

> 최신 제품 방향은 [AgentOS 제품 컨셉](PRODUCT_VISION.ko.md)을 기준으로 합니다. 설치형 데스크톱 대화 앱과 개인 에이전트 생태계가 목표이며, 아래 Kubernetes 구성은 실행 기반 프로토타입 기록입니다.

작성일: 2026-09-05. 상태: 초기 설계 기록. 아래 개인 환경 중심 변경안이 우선한다.

## 합의 후 변경: 개인별 AgentOS

사용자와의 후속 합의로 제품 단위를 개별 작업에서 개인 에이전트 환경으로 변경했다.
공용 관리 계층이 개인 환경을 생성·중지·재개하고, 각 개인 환경은 자신의 기억·파일·인증·예약 작업을 소유한다.
초기 구현은 개인별 Namespace + 단일 runtime Deployment + 개인 PVC/SQLite + Secret이다.
공용 PostgreSQL/dispatcher, 실행 Job 분리, LLM 연결, 자동 깨우기는 후속 단계이며 아래 원안의 목표 구성과 현재 구현을 구분한다.
실행 계획과 구현 범위의 최신 정보는 `PLAN.md`, `README.md`, 실제 수용 테스트 결과는 `E2E_RESULT.json`을 기준으로 한다.
분석 기준: Jongtae/agentos-os-prototype(당시 이름 Jongtae/agentos)의 main 커밋 `bf136746e2e623b95e6058bc11e966622389d0b2`.
원본을 `agentos/`에 복제해 주요 런타임·저장소·API·제품 요구사항을 확인했다. 전체 모듈의 동작 검증이나 전수 기능 감사는 아직 수행하지 않았다.

## 1. 제품 정의와 전환 완료 기준

목표는 사용자의 요청을 이해하고, 승인된 도구를 격리된 실행 환경에서 수행하며, 진행 상황·결과·복구 이력을 보존하는 Kubernetes 기반 에이전트 플랫폼이다.

원본의 런타임 우선 원칙, 사용자 데이터 소유권, 명시적 외부 서비스 연동, 실행 근거 기록을 계승한다. 클러스터 내부 저장소와 로컬 모델만으로 운영할 수 있는 self-hosted 배치를 기본 방향으로 제안한다.

완전 전환은 다음을 모두 충족해야 한다.

- 합의한 기존 사용자 기능마다 이식·대체·제외 결정을 기록하고 수용 테스트를 통과한다.
- 정상 실행에 호스트 systemd, TTY 자동 로그인, 호스트 경로, ISO 부팅이 필요하지 않다.
- API나 실행 Pod 재시작 이후 작업 상태·승인·기록을 복원한다.
- 설치, 업그레이드, 백업 복원, 작업 취소, 장애 복구를 실제 클러스터에서 검증한다.
- 원본의 상태 표시·fixture 검증과 실제 외부 서비스 실행을 구분한다.

## 2. 코드에서 확인한 출발점

| 영역 | 확인한 근거 | 전환 의미 |
|---|---|---|
| Web/API | `scripts/docker_runtime_preview.py`: ThreadingHTTPServer, 동기 `/api/prompt`, 다수 제품 상태 API | 비동기 작업 API와 화면을 분리 |
| 도구 실행 | `src/kernel/runtime/executor.py`: 프로세스 내부 `tool.run`; `tools/bash_tool.py`: subprocess | 클러스터 실행 어댑터와 격리된 worker 필요 |
| 기억 저장 | `src/kernel/memory/store.py`: SQLite | 다중 프로세스용 저장 계층 필요 |
| 체크포인트 | `src/kernel/runtime/checkpoint_saver.py`: JSON 파일 | 원자적 갱신·동시 실행 제어·버전 관리 필요 |
| 데이터 | `docker-compose.yml`: workspace/user/state 호스트 bind mount | workspace PVC, 기록 DB, 결과물 저장소로 분리 |
| 수신기 | Docker preview 내부 background worker 및 Telegram polling | 수신기 분리, 중복 수신 방지 필요 |
| 생명주기 | `deploy/systemd/`, TTY 및 ISO 경로 | Deployment와 운영 절차로 의미 재정의 |
| 승인 등 제품 화면 | TASKS·roadmap과 `/api/approvals` 등 | 가시성 제공을 실제 승인 집행 완료로 간주하지 않음 |

기존 Python 도메인 로직과 테스트는 재사용 후보다. 호스트 명령, 전역 환경 변수, 파일 쓰기, subprocess 호출의 의존성을 분리한 뒤 이식한다. 모든 코드를 다른 언어로 재작성할 필요는 없다.

## 3. 제안 구성

```text
Web / CLI / Telegram
        |
        v
AgentOS API + 인증 + 승인 서비스
        |                     |
        v                     v
PostgreSQL              결과물 저장소
작업·승인·이벤트          S3 호환 또는 초기 PVC
        ^
        |
Dispatcher / Reconciler ----> Kubernetes API
                                |
                                v
                           실행 Job / Pod
                           Python runtime
                           도구·모델 adapter
                                |
                       workspace PVC / LLM endpoint
```

- **API Deployment**: 요청 등록, 권한 검사, 조회, 승인·취소, SSE 진행 이벤트. 도구를 API 프로세스 안에서 실행하지 않는다.
- **Dispatcher Deployment**: DB의 실행 대기 작업을 lease로 확보하고 Job을 생성하며 결과를 조정한다. 초기에는 단일 replica, 이후 다중 replica 경쟁과 복구를 검증한다.
- **Runtime Job**: 유한한 실행 단위 하나를 담당한다. 기존 intent/planner/tool/model 코드를 어댑터 뒤에 재사용한다. 장기 대기 승인은 DB에 저장하고 Pod를 종료한다.
- **Connector Deployment**: Telegram 등 외부 입력을 작업으로 변환한다. 초기 polling은 단일 활성 수신자와 영속 cursor를 사용한다.
- **PostgreSQL**: 작업·시도·승인·체크포인트·이벤트·메모리의 기준 저장소. MVP는 클러스터 내부 단일 인스턴스도 허용하지만 HA 완료로 표시하지 않는다.
- **Workspace PVC**: 파일 작업용 POSIX 공간. 초기에는 workspace별 동시 writer를 하나로 제한한다. RWO 볼륨과 재스케줄링·attach 제약을 수용 테스트에 포함한다.
- **결과물 저장소**: MVP에서는 영속 볼륨, 다중 노드 단계에서는 S3 호환 저장소를 사용할 수 있다. 실행 파일시스템과 아카이브의 역할을 분리한다.
- **모델 endpoint**: 외부 LLM 또는 클러스터 내부 Ollama 등을 선택. GPU 할당과 모델 캐시는 선택 배치로 분리한다.

초기에는 서비스 메시·별도 메시지 브로커·벡터 DB를 필수 의존성으로 도입하지 않는다. DB 기반 dispatch로 시작하고 측정된 병목에 따라 확장한다.

### CRD / Operator 도입 시점

MVP는 표준 Deployment/Job/PVC/Secret을 사용한다. 운영자가 AgentOS 설치나 workspace를 선언적으로 관리할 필요가 확인되면 `AgentRuntime`, `AgentWorkspace` CRD와 Operator를 추가한다. 모든 대화·이벤트·작업 기록을 Kubernetes 객체로 만들지는 않는다.

이 설계에서 제품 작업 상태는 PostgreSQL이 소유하고 Kubernetes는 실행 자원의 상태를 소유한다. 향후 CRD를 추가해도 동일한 작업 상태를 두 곳에서 독립적으로 수정하지 않도록 소유권을 명시해야 한다.

## 4. 실행·실패·복구 계약

권장 상태 흐름: `queued → running → succeeded | failed | cancelled`, 중간 승인 필요 시 `awaiting_approval → queued`. 재시도는 별도 attempt로 남긴다.

1. API는 idempotency key와 함께 작업을 DB에 기록한 뒤 작업 ID를 반환한다.
2. Dispatcher는 lease와 attempt 번호를 확보하고 결정적인 이름으로 Job을 생성한다.
3. DB 기록과 Kubernetes 생성 사이에 장애가 생기면 Job 이름·라벨·UID를 조회해 재연결한다. 무조건 새 Job을 생성하지 않는다.
4. Worker는 한정된 자격으로 해당 작업의 이벤트·결과·체크포인트만 기록한다.
5. 승인은 사용자·작업·실행 인자 해시·유효기간에 연결한다. 승인 후 인자가 바뀌면 새 승인이 필요하다.
6. 취소는 Job 종료 요청과 실제 종료 확인을 구분한다. 이미 발생한 외부 효과가 자동 취소되었다고 표시하지 않는다.
7. Kubernetes Job의 재시작과 애플리케이션 재시도를 함께 설계한다. 외부 쓰기는 기본 자동 재시도를 막고, 제공자 idempotency 지원이나 결과 조회로 중복 여부를 확인한다.
8. 결과가 불명확한 외부 작업은 사용자 확인이 필요한 상태로 보존한다. exactly-once 실행을 가정하지 않는다.

실행 timeout, 동시 작업 한도, CPU/메모리 한도, 로그 보존 기간, Job TTL은 설정으로 제공한다. Job 삭제 전에 결과·이벤트를 영속화한다.

## 5. 기존 기능의 대응 범위

| 원본 기능 | Kubernetes 목표 | 범위 |
|---|---|---|
| 요청·intent·계획·도구 실행 | API → 작업 등록 → Runtime Job | MVP 핵심 |
| Runtime Home·상태·설정 | 설치 및 adapter readiness, 작업 현황 | MVP |
| workspace 파일 | workspace PVC와 권한 검사 | MVP |
| 실행 기록·Activity Timeline·메모리 | DB 이벤트·기억, 결과물 아카이브 | MVP 이후 검색 확장 |
| 외부 LLM·로컬 LLM | provider adapter와 모델 endpoint | MVP: 테스트 adapter + 실제 provider 하나 |
| 웹 검색·브라우저 | 웹 도구 이식, 브라우저 전용 이미지 | 검색 우선, 브라우저 후속 |
| Telegram | 별도 수신기, 중복 제거, reply 기록 | 기능 이식 단계 |
| Work Inbox·Gmail·Calendar | connector 계약, OAuth 갱신·권한 관리 | 기존 구현 수준 감사 후 read-only부터 |
| Capability Store | 도구 목록·버전·권한·실행 가능 상태 | 기능 이식 단계 |
| Approval Center | 승인 조회 및 실제 실행 전 강제 검사 | 집행은 신규 개발 포함 |
| Proof·Evidence·Release Trust | 테스트 결과·이미지 digest·실행 provenance | 기존 표시 수준 이식 후 실증 확장 |
| 복구·세션 연속성 | Job 재조정·체크포인트·데이터 복원 | MVP 실패 처리, 후속 복원 검증 |
| TTY·shell 모드 | CLI 및 격리된 workspace shell | 호스트 shell과 권한 의미가 다름 |
| boot/install/reboot/power/ISO | Helm 설치·업데이트·runtime 재시작·복원 | 제품 의미 대체, 동등 기능으로 오인 금지 |
| hardware attestation | 필요 시 별도 노드 신뢰 설계 | 초기 범위 제외, 사용자 합의 필요 |

전체 API 목록, CLI 명령, 도구별로 입력·출력·부작용·현재 검증 수준을 기록하는 기능 대장이 필요하다. 위 표는 주요 영역 설계이며 전수 대장을 대신하지 않는다.

## 6. 권한과 격리

사용자 인증과 workspace 소유권 검사는 API와 저장소 질의에 적용한다. Namespace만으로 사용자 데이터 접근이 해결되지는 않는다.

- API, dispatcher, worker의 ServiceAccount를 분리한다. Worker의 Kubernetes API 토큰 자동 마운트는 기본 비활성화한다.
- Dispatcher는 지정 namespace의 허용된 실행 자원만 관리한다. 사용자 입력으로 임의 image, hostPath, privileged 설정을 주입할 수 없게 한다.
- Worker는 non-root, capability drop, resource limit을 적용하고 필요한 workspace만 마운트한다.
- 외부 네트워크 정책은 이를 지원하는 CNI에서 검증한다. 허용 도메인 제어가 필요하면 egress proxy 등 별도 수단을 설계한다.
- 서로 신뢰하지 않는 사용자의 임의 코드를 실행하는 서비스는 sandbox runtime 또는 별도 노드/클러스터 격리를 추가 검토한다.
- 비밀 값은 Secret 또는 외부 비밀 저장소로 주입하며 사용자 기록에 포함하지 않는다. OAuth 자격 갱신과 암호화 저장은 connector 범위에 포함한다.

## 7. 단계별 개발 범위와 수용 기준

| 단계 | 산출물 | 완료 증거 |
|---|---|---|
| 0. 계약 확정 | 기능 전수 대장, API·상태 모델, ADR, 테스트 시나리오 | 기존 기능마다 보존·대체·제외 및 검증 방식 합의 |
| 1. 수직 MVP | API, DB, dispatcher, worker 이미지, Helm, 최소 Web 화면 | 요청 → Job → 결과·이벤트 조회가 로컬 클러스터에서 성공 |
| 2. 기능 이식 | workspace·메모리·검색·LLM·승인·Telegram, 제품 화면 | 기능별 기존 입력/출력 비교, 실제 연동은 별도 증거 |
| 3. 복구와 확장 | lease 복구, 동시성, 백업/복원, 취소, 중복 실행 제어 | API/dispatcher/worker 강제 종료 후 누락·중복·상태 오류 검사 |
| 4. 운영 배포 | 인증, tenant 격리, 관측, 업그레이드, 운영 문서 | 목표 클러스터에서 설치·업데이트·복원·권한 거부 E2E |

첫 MVP 시나리오는 “사용자가 workspace 파일 목록을 요청 → 독립 Job 실행 → 진행 상황 및 결과 표시 → API 재시작 후에도 결과 조회”로 잡는다. 가짜 adapter로 인프라 흐름을 검증한 결과와 실제 LLM 호출 성공은 따로 기록한다.

주요 회귀 검증: 중복 요청 등록, dispatcher의 Job 생성 직후 종료, worker timeout, workspace 동시 쓰기, 승인 인자 변경, 타 workspace 접근, 비밀 노출, 데이터 복원.

기간과 비용은 기능 대장, 인력, 목표 클러스터 및 동시 실행 규모를 정한 뒤 산정한다.

## 8. 다음 설계 결정

권장 초기 가정은 단일 조직의 self-hosted 클러스터, 로컬 kind 개발 환경, Python runtime 재사용, 단일 workspace writer다. 다음 사항은 아직 확정하지 않았다.

1. 개인/사내 서비스인지, 서로 다른 고객을 받는 멀티테넌트 서비스인지.
2. 목표가 로컬 k3s·사내 Kubernetes·관리형 클라우드 중 무엇인지.
3. 로컬/GPU 모델과 외부 API 중 필수 지원 범위.
4. 기존 저장소 변경인지 별도 프로젝트인지.
5. ISO·호스트 전원 기능의 대체 및 제외 수용 여부.

이 절의 초기 설계 작성 시점에는 구현하지 않았다. 이후 개인 환경 중심의 별도 로컬 MVP를 구현했으며 원본 코드는 변경하지 않았다. 최신 구현 및 검증 상태는 README와 E2E 결과를 참조한다.

## 참고 자료

- [원본 저장소](https://github.com/Jongtae/agentos-os-prototype) (분석 당시 이름 `Jongtae/agentos`; 이후 `Jongtae/agentos`는 현재 주력 제품 저장소로 재사용됨)
- [Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/) — 작업 수명주기와 재시도 특성
- [Kubernetes Operator pattern](https://kubernetes.io/docs/concepts/extend-kubernetes/operator/) — 선언적 애플리케이션 운영
- [Kubernetes Multi-tenancy](https://kubernetes.io/docs/concepts/security/multi-tenancy/) — namespace·권한·격리 설계
