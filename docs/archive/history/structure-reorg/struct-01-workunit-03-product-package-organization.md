# STRUCT-01 Work Unit 03 — 제품 패키지 정리

Issue: [#287](https://github.com/Jongtae/personal-agentos/issues/287)
Branch: `codex/struct-01-workunit-03-product-packages`
Goal: `STRUCT-01 — AgentOS 저장소 구조 정리`

## 1) WU-03 범위(현재 라운드)

- `personal_agent/` 패키지 루트를 `src/personal_agent/`로 이동.
- 이동 후 최초 1차 범위: 모듈별 세분화는 보류하고, 기존 파일의 경로만 변경해 동작성 유지.
- `tests/`, `scripts/`, `Dockerfile*`, `pyproject.toml`은 WU-03에서 참조 경로만 정합성 정리.
- 외부 동작(기능 수정/결함 수정)은 WU-03 범위 밖.
- `agentos/`, `.runtime/`은 기존 WU-01 규칙 유지(현재 라운드에서 이동하지 않음).

## 2) 패키지 이동 명세(안)

### 이동 대상

| 현재 위치 | 목표 위치 | 보존 방법 | 목적 |
| --- | --- | --- | --- |
| `personal_agent/*.py` | `src/personal_agent/*.py` | `git mv` | 소스 루트 통일 및 패키지 역할별 분리 기반 확보 |
| `personal_agent/web/*` | `src/personal_agent/web/*` | `git mv` | 정적 자원 포함 패키지 데이터 경로 일치 |

### 보존 대상(현재 이동 제외)

- `agentos/` (독립 Git 저장소)
- `.runtime/` (개인 실행 데이터)
- 외부 서비스 연결, 배포 아티팩트, 설치 스크립트 실행 동작의 기능 로직

## 3) 선행 의존 경로 수정 우선순위

이 항목은 WU-03 착수 직후 순차 반영한다.

1) `pyproject.toml`
- `[project.scripts]`: `agentos = "personal_agent.quickstart:main"`에서 루트 이동이 필요 없도록 `src` 기반 패키지 빌드 설정 재확인
- `[tool.setuptools.packages.find]`: `src` 전역 인식(`where`) 여부 확인
- `[tool.setuptools.package-data]`: `web/*.html`, `web/*.css`, `web/*.js`, `delivery-plan.yaml` 패키지 데이터 경로 보존

2) 실행/테스트/도커 진입 경로
- `Dockerfile.egress`: `COPY src/personal_agent/...` 및 `python -m personal_agent.limited_egress_proxy`
- `Dockerfile.engine`: `python -m personal_agent.isolated_engine_sidecar`
- `scripts/*` 실행 커맨드 (`-m personal_agent...`) 및 수동 문자열 매칭
- `tests/test_compose_isolated_engine_contract.py`의 텍스트 기반 도커 명령 비교

3) 구성/설치 문서
- `QUICKSTART.md`의 `python3 -m personal_agent.quickstart` 형태
- README 계열의 CLI/스크립트 실행 예시

## 4) WU-03 종료 체크리스트(완료 조건)

- [x] `personal_agent` 코드 트리와 정적 자원 트리를 `src/` 아래로 이동 완료
- [x] 패키지 데이터 경로(`web/*`, `delivery-plan.yaml`)가 설치/실행 환경에서 정상 탐색됨(`package_data_ok` 확인)
- [x] `pyproject.toml`, `Dockerfile`, `scripts`, `tests`, `docs`에서 경로 참조가 변경 후 정합
- [x] `agentos` CLI 엔트리포인트가 패키지 경로 이동 후에도 정상 실행(`agentos --help` 확인)
- [x] 역할별 모듈 배치는 기존 모듈 파일 경계를 유지하고, 내부 책임 분리는 범위 밖으로 명시해 별도 기능 WU로 확대하지 않음
- [x] 소스 체크아웃에서 실행되는 검증 스크립트가 `src/` 패키지 루트를 직접 찾도록 정렬
- [x] Docker 컨텍스트 예외와 CI editable 설치 경로를 `src/personal_agent/` 구조에 맞춤

## 5) WU-03 상태 로그

- 2026-09-08: Issue #287 생성, WU-03 브랜치 `codex/struct-01-workunit-03-product-packages`로 전환.
- 2026-09-08: WU-01/02 산출물 기준으로 패키지 이동 의존 항목 목록 확정.
- 2026-09-08: WU-03에서 `personal_agent` → `src/personal_agent/` 우선 이동과 경로 정합 순서를 기록.
- 2026-09-08: `personal_agent/` 이동 실행 및 패키지 메타데이터, Dockerfile, 검증 경로 참조 정합을 반영.
- 2026-09-08: 소스 체크아웃 스크립트의 `src/` 부트스트랩, `.dockerignore`, CI editable 설치, egress Docker 복사 경로를 정렬. 패키지 데이터와 CLI 실제 설치 검증은 보류.
- 2026-09-08: editable 설치, `agentos --help`, 설치 패키지 데이터 탐색, 문서 검증, pytest(248 passed, 46 subtests), unittest(219 passed), Compose acceptance를 통과시켰다. Dockerfile의 남은 `COPY personal_agent` 경로도 수정했다.
