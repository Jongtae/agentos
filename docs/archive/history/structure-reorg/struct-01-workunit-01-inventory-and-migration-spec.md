# STRUCT-01 Work Unit 01 — 구조 확정과 이동 명세

Issue: [#285](https://github.com/Jongtae/personal-agentos/issues/285)
Branch: `codex/struct-01-repo-structure`
Goal: `STRUCT-01 — AgentOS 저장소 구조 정리`

## 1) 이동 범위 (현재 위치)

본 하위 작업은 WU-01에서 실제 이동 전 구조 확정/추적을 정리한다.

- 보존 대상(운영/검증 코드):
  - `AGENTS.md`
  - `.githooks`, `.github`
  - `pyproject.toml`, `Dockerfile*`, `compose.yaml`, `.dockerignore`
  - `agentos/` (독립 Git 저장소로 관리)
  - `.runtime/` (개인 실행 데이터)
- 대상 코드 집합:
  - `personal_agent/*.py`, `personal_agent/web/*`
  - `scripts/*.py`, `scripts/*.sh`
  - `tests/*.py`
  - `docs/*.md`, `docs/archive/*`, `docs/validation/*`
  - `deploy/*`

## 2) 예외/보존 규칙

- `agentos/`
  - 별도 Git 저장소(내부 `.git` 보유).
  - 현재 goal에서는 `agentos/`를 파일 수준으로 이동하지 않는다.
  - 이력/브랜치 확인은 `git -C agentos status --short --branch`로 보존 상태만 검증한다.
- `.runtime/`
  - 개인정보/개인 런타임 데이터 포함 가능.
  - 구조 정리에서 이동하지 않으며, 필요 시 별도 마이그레이션 하위 작업으로 분리한다.
- `__pycache__`, `*.pyc`
  - 생성물(컴파일 캐시)은 이동 스캔/정렬 대상에서 제외하고, 변경 시 `.gitignore` 정책으로 정리 유지.

## 3) WU-01 단계별 이동명세(안)

| 현재 위치 | 목표 위치(안) | 보존 방식 | 비고 |
| --- | --- | --- | --- |
| `personal_agent/*.py`, `personal_agent/web/*` | `src/personal_agent/*.py`, `src/personal_agent/web/*` | `git mv` | 패키지명을 `personal_agent`로 유지하고, 소스 루트만 `src/` 아래로 이동해 통일된 역할별 패키지 구조 기반으로 재배치 준비 |
| `tests/*.py` | `tests/*.py` (1차 유지) | 없음 | 초기 1차 산출물은 참조/명세 확정용. 이동은 WU-03 또는 WU-04에서 필요 시 결정 |
| `scripts/*.py`, `scripts/*.sh` | `scripts/*.py`, `scripts/*.sh` (1차 유지) | 없음 | WU-01에서 이동 경로 추적만 생성, 실제 재배치는 WU-03/04에서 판단 |
| `docs/*` | `docs/*` (구조 링크 정리 후 필요 시 하위 폴더 정리) | 없음 | 우선 문서 링크 유효성 확보를 WU-02로 연계 |
| `deploy/*` | `deploy/*` | 없음 | WU-04에서 경로 바인딩 점검/업데이트 전제 |

## 4) 관련 참조(변경 필요 항목) 선별

이 항목들은 `personal_agent/`를 `src/personal_agent/`로 이동할 경우 우선 수정해야 하는 경로 의존성이다.

- `pyproject.toml`
  - `[project.scripts]`
  - `[tool.setuptools.packages.find]`
  - `[tool.setuptools.package-data]`
- `Dockerfile.egress`
  - `COPY personal_agent/...`
- `personal_agent/delivery-plan.yaml` 및 `delivery-plan.yaml`
  - 코드 패키지 경로와 검증 스크립트 경로의 정합성
- `scripts/agentos_doctor.py`
- `scripts/operating_preflight.py`
- `scripts/product_validate.py`, `scripts/quickstart_install_check.py`
- `tests/test_delivery.py`, `tests/test_product_validation.py`, `tests/test_master_plan_traceability.py`
- `README*` 문서의 설치/실행/링크 언급
- `docs/roadmap.md`, `docs/issue-branch-ledger.jsonl`, `TASKS.md`

## 5) 추적 기준(본 하위 작업 종료 조건)

- 목표 위치 대상/예외/보존 방법이 명시되고, 본문 기준의 예외가 문서화되어야 한다.
- 각 카테고리별 이동 명세가 누락 없이 표로 남아야 한다.
- 위 파일/경로에서 추적 대상이 아닌 항목을 본문에서 제거하고 사유를 남긴다.

## 6) WU-01 상태 로그

- 2026-09-08: Issue #285 생성, branch `codex/struct-01-repo-structure`로 전환 완료.
- 2026-09-08: `agentos/` 및 `.runtime/` 분리 보존 규칙 선별 완료.
