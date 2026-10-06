# STRUCT-01 Work Unit 04 — 도구·배포·테스트 정리

Goal: `STRUCT-01 — AgentOS 저장소 구조 정리`

Issue: [#291](https://github.com/Jongtae/personal-agentos/issues/291)

Branch: `codex/struct-01-workunit-04-tool-deployment-tests`

## 1) 범위

- `scripts/`, Docker/Compose, service 설정, CI, 테스트 진입점의 `src/personal_agent/` 참조 정합성을 유지한다.
- 구조 회귀를 조기에 발견할 수 있도록 `scripts/verify_src_layout.py`를 CI에 연결한다.
- 기존 CLI, 저장 데이터 형식, 승인·격리·복구 경계는 변경하지 않는다.

## 2) 제외 범위

- 새 제품 기능, OP-03 결함 수정, 외부 서비스 연결, 운영 배포
- `quickstart_service.py` 내부 책임 분리
- 중첩 Git 저장소 `agentos/` 및 개인 실행 데이터 `.runtime/` 이동

## 3) 완료 조건

- [x] `src` 패키지, Docker 복사 경로, `.dockerignore`, 패키지 데이터 선언을 검사하는 verifier를 추가한다.
- [x] verifier를 필수 `validate` CI 단계에 연결한다.
- [ ] verifier, CLI, package install, Compose, pytest, unittest, 문서 검증이 clean checkout에서 통과한다.
- [x] 독립 검토 기록을 추가한다.
- [ ] PR merge 후 TASKS/roadmap/ledger를 closeout한다.

## 4) 상태 로그

- 2026-09-08: Issue #291 및 matching branch 생성.
- 2026-09-08: src-layout/Docker/CI/script bootstrap 회귀를 검사하는 verifier를 추가하고 validate workflow에 연결.
- 2026-09-08: 로컬 `operating_preflight.py --root .` 실행에서 `state=ready`, recovery action 없음, owner 운영 게이트 deferred를 재확인했다. 원격 CI의 단발성 preflight probe 실패는 검증 완화 없이 새 run에서 재확인한다.
