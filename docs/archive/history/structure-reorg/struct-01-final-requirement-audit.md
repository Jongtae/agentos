# STRUCT-01 — 최종 요구사항-증거 감사

Issue: [#295](https://github.com/Jongtae/personal-agentos/issues/295)

Audit date: 2026-09-08

## 감사 기준

상위 Goal의 사용자 결과, 변경 범위, 유지 조건, 제외 범위, 보호 대상을 현재 main의 파일·merged PR·CI·로컬 실행 증거와 대조했다. 과거 검증 기록은 원문을 덮어쓰지 않고 현재 closeout record에서 참조했다.

## 요구사항 매핑

| 요구사항 | 현재 증거 | 판정 |
| --- | --- | --- |
| 구조 확정과 이동 명세 | `struct-01-workunit-01-inventory-and-migration-spec.md`, issue #285, ledger issue #285 record | 충족 |
| 문서·산출물 분리 및 링크 도달성 | `struct-01-workunit-02-document-and-evidence-organization.md`, recorded `broken_links=0`, PR #290 closeout CI | 충족 |
| 제품 패키지 `src/personal_agent/` 전환 | PR #288, merge `1699bbc`, WU-03 record, `pyproject.toml`, web assets | 충족 |
| 설치와 CLI 유지 | editable install, `agentos --help`, `package_data_ok`, PR #288 CI run `34217734559` | 충족 |
| 도구·Docker·CI·테스트 경로 정렬 | PR #292, merge `dc73ff8`, `scripts/verify_src_layout.py`, WU-04 CI run `34218738406` | 충족 |
| Compose 및 기존 테스트 | local Compose acceptance, pytest `248 passed` plus `46 subtests`, unittest `219 tests OK`, required CI; test-only stability fix merged in PR #300 | 충족 |
| CLI·저장 데이터·승인·격리·복구 경계 보존 | WU-01 exception rules, WU-03/WU-04 scope records, independent review artifact | 충족 |
| nested `agentos/`와 `.runtime/` 보호 | WU-01 inventory/exception rules and every implementation issue non-goal | 충족 |
| 새 기능·OP-03·외부 연결·운영 배포 제외 | issues #285/#287/#291/#295 non-goals, PR bodies, ledger operating limitations | 충족 |
| issue → branch → validation → PR → merge → record | issues #285, #286, #287, #291, #293, #295; merged PRs #288, #290, #292, #294 | 충족 |

## 역할별 구조 판단

`src/personal_agent/`는 `quickstart_*`, `isolated_*`, `telegram_*`, `portable_state`, `providers`, `plugins`, `delivery` 등 기존 역할별 모듈 경계를 유지한다. `quickstart_service.py`의 내부 책임 분리는 동작 보존을 위해 수행하지 않았고, Goal의 명시적 non-goal로 기록했다.

## 독립 검토 결론

- [x] 이동 대상과 예외가 문서화되어 있다.
- [x] 현재 설치·CLI·web resource·Docker·Compose·pytest·unittest·CI 증거가 있다.
- [x] tracker, roadmap, ledger가 동일한 WU 상태와 merge evidence를 가리킨다.
- [x] 운영 배포나 외부 provider 성공을 주장하지 않는다.
- [x] 중요한 미해결 finding 없음.

결론: STRUCT-01의 선언된 개발 범위는 충족되었다. 상위 issue #285는 이 audit artifact를 포함한 closeout PR merge 후 닫을 수 있다.
