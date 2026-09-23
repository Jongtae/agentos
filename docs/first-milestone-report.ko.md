# AgentOS 1차 개발 정리 보고서

기준일: 2026-09-08. 정리 이슈: [#282](https://github.com/Jongtae/agentos/issues/282). 1차 마일스톤: [AgentOS 1차 개발 정리](https://github.com/Jongtae/agentos/milestone/6).

## 판단

승인된 MP1·MP2·TOP의 **개발 기준선은 완료**했다. 현재 실행 가능한 후속 목표는 활성화하지 않는다. 실제 구독 로그인, 외부 서비스 연결, Telegram/OAuth 설정, 운영 배포 및 실사용 성공은 이번 완료 판정에 포함하지 않는다. 추가 운영 진단 도구 OP-03은 PR #281에 미완료 상태로 보존한다.

검증된 불변 배포 후보는 `53912eeb1357ced37031234b1e5376f024dd0a96`이다. 해당 SHA의 [main validate 34204797899](https://github.com/Jongtae/agentos/actions/runs/34204797899)가 성공했다. `v1.0.4` 태그의 과거 지원 주장은 이미 철회되었으며, 이번 정리는 새 버전 릴리스가 아니다.

## 지금까지 진행한 작업

| 단계 | 결과 | 근거와 한계 |
| --- | --- | --- |
| v1 / M0–M6 | 제품 저장소 분리, 도구 호출, 실행·재시작 복구, 문서 읽기/공유 승인, Compose/VPS 운영 템플릿, 확장 manifest/plugin, v1 검증 | 기존 ledger의 #3/#5, P1–P6, v1.0.0–v1.0.3 기록. 당시 설치 관찰은 과거 증거이며 현재 외부 서비스 운영 증거가 아님 |
| v1 / P7 | Telegram 작업 카드·승인·연속성 일부 구현 | #76/#77/#78 등 병합 기록. P7-04 #94 릴리스 게이트는 동결된 역사 기록이며 Hub v2 선행 조건이 아님 |
| Hub v2 / H0–H5 | 구독 실행 엔진 연결 경계, 소유자 런타임 격리, BotFather 기반 개인 봇 경로, opt-in 문맥함, 공식 assistant 정책, export/restore | #103–#109 및 후속 V1 구현. 자동 봇 생성이라는 과거 epic 문구는 현행 계약이 아님 |
| V1 / UX | 설치·일상 Telegram 작업·문맥 공유 승인·복구, 개인 DM, 작업공간/저장 결과, 웹/Telegram 대화 설정 경로 | V1-01–05, UX-01–06, #137/#138 등; 현재 claim은 자동화된 개발 증거로 제한 |
| MP1 | Personal Space, capability lifecycle, Drive 읽기, A2A 위임, Calendar 생성 승인, ReAct 정책/복구 및 통합 검증 | #180/#185/#191/#201/#205/#209, 보완 #217–#225. 공급자·A2A 테스트 피어는 mock/fixture 증거 |
| MP2 | 대화 중심 설정, 검토된 capability 추천, 소유자 로컬 지식 검색 | #235/#243/#251. 자동 설치·외부 인덱스·외부 공유 권한을 부여하지 않음 |
| STAB / OP | 구독 엔진 요약 입력·MCP 왕복·중복/재시작 복구, 배포 사전점검, 격리·복원 보완 | #255/#258/#261/#262. OP-01의 잘못된 후보 주장은 후속 보완으로 대체 |
| GOV / TOP | 목표 실행 계약, 명세→증거 추적, 격리 Compose 검증, 통합 회귀, 완료 판정 강화 | #263/#264/#266/#270–#278. 실제 credential-free 로컬 Compose build/health/recreate/restore/cleanup 관찰과 mock 검증을 구분 |
| LEGACY-01 | 레거시 `agentos/PRD.md`를 역사 자료로 유지 | #279에 이미 기록된 소유자 결정 반영. 향후 OS/appliance 방향은 별도 제안·승인·계약 필요 |
| OP-03 | 운영 진단 도구 코드와 문서 초안 | #280 / PR #281 미병합. 격리, 후보 실행 절차, 포트 일치 보완 필요 |

정리 시작 시 일반 이슈 **132개(닫힘 120, 열림 12)**, PR **149개(병합 146, 미병합 종료 2, 열림 1)**를 조사했다. 이 수치는 이번 정리 이슈/PR 생성 전 기준이다. 전체 제목·상태·URL·병합 SHA는 [전체 인벤토리](validation/first-milestone-inventory-2026-09-08.json)에 수록했다. 과거 작업을 삭제하거나 미완료 항목을 완료로 치환하지 않는다.

## 마일스톤과 이슈 정리

정리 PR [#283](https://github.com/Jongtae/agentos/pull/283)이 `0025148e7ab30bd27c4b1ca761b3ba9702b0e0f8`로 병합되었다. 기존 마일스톤 #1–#5 및 이슈 #1/#36/#94/#102/#149/#265/#279의 마감은 실제 적용했다. 신규 마일스톤 #6과 #282는 마지막 증거 PR의 필수 CI·병합 후 마감한다.

| 대상 | 마감 방식 |
| --- | --- |
| #1 / Personal AgentOS v1의 저장소 분리 | #3/#5와 ledger의 태그/Formula 분리 증거로 완료 종료 |
| #36 / 옛 확장 epic | 현행 manifest·MP1 계약으로 대체된 역사 기록으로 종료. 과거 설치 수용 조건을 새로 충족했다고 주장하지 않음 |
| #102 Hub v2, #149 UX 상위 epic | 후속 TOP/현행 계약으로 대체된 역사 기록으로 종료. 옛 자동 봇 생성·live gate 조건의 달성을 주장하지 않음 |
| #94 P7-04 | 동결·대체된 릴리스 작업으로 종료. 미출시 기능 완료로 표시하지 않음 |
| 기존 GitHub 마일스톤 #1–#5 | 완료/대체 사유를 명시하여 역사 마일스톤으로 닫음 |
| #265 TOP | 불변 후보, 요구사항별 근거, 필수 CI, tracker/ledger에 따라 개발 완료 종료 |
| #279 LEGACY-01 | 소유자의 historical 유지 결정을 문서·계획에 반영하여 종료 |
| 신규 마일스톤 #6 | #265/#279/#282의 1차 정리를 묶어 검증·병합·최종 감사 후 닫음 |
| #48/#49/#50/#100 | native companion, 추가 메신저, managed hosting, 광범위 context capture 제안은 보류 상태 유지; 활성화하지 않음 |
| #280 / PR #281 | 후속 보완 대상 유지; 1차 완료 범위에서 제외 |

## 브랜치 정리

정리 전 SHA와 main 조상 관계 또는 GitHub의 **동일 브랜치 head SHA가 병합된 PR**을 대조했다. 복구 가능한 Git bundle을 생성·검증한 뒤 **로컬 브랜치 58개, 원격 브랜치 18개를 삭제**했다. 원격 삭제는 예상 SHA에 대한 lease와 atomic push로 실행했다. 원격 추적용 symbolic HEAD는 브랜치로 세지 않는다.

깨끗하고 병합된 P6/P7 작업 폴더 4개는 디렉터리를 삭제하지 않고 기존 SHA에서 detached HEAD로 보존했다. 다음 작업은 보존한다.

| 브랜치 | 보존 이유 |
| --- | --- |
| `codex/280-owner-operating-doctor` | PR #281 미병합, 실제 보완 필요 |
| `docs/168-github-first-delivery` | 깨끗한 별도 worktree이나 head 병합 동등성이 입증되지 않음 |
| `feature/p1-03-continuity-acceptance` | `agent_runtime.py`, 해당 테스트의 미커밋 수정. 원격 브랜치도 유지 |
| `fix/p6-00e-packaged-plan` | 미추적 build/egg-info 산출물 존재 |
| `release/v1.0.1`, `release/v1.0.2` | 미추적 build/egg-info 산출물 존재 |

백업: 로컬 `.git/branch-archives/2026-09-08-first-closeout/pre-cleanup.bundle`과 같은 폴더의 ref 인벤토리. 미커밋 파일은 bundle에 포함되지 않으므로 원래 작업 폴더를 그대로 보존했다. 이번 정리 브랜치는 자신의 PR 병합 후 제거한다. `main`과 위 보존 대상만 남기는 것이 최종 상태이다.

## 검증·검토와 남은 일

[독립 검토 기록](validation/first-milestone-independent-review-2026-09-08.md)은 PR #281을 제외하고 TOP의 기존 개발 완료 증거를 확인했다. 현재 계획의 TOP 활성 상태를 `development_complete`로 정리하며, 종료된 목표가 다시 선택되거나 GitHub 작업을 시작하지 않는 회귀 검증을 추가했다. 과거 활성 TOP의 지속/마이그레이션 테스트는 명시적 fixture로 유지한다.

필수 검증은 문서 링크/계약 검증, 두 delivery plan 일치, JSON ledger/inventory 파싱, pytest/unittest 전체 CI이다. 최종 PR 및 main CI 결과와 이슈/마일스톤·브랜치 실측 결과는 #282의 완료 감사에 연결한다. 이 보고서 자체는 아직 실행하지 않은 운영 검증을 증명하지 않는다.

다음 개발 보완은 OP-03의 세 발견사항이다. 별도 운영 단계에서는 후보 검토, 정확한 provider DNS allowlist, 로컬 claim, 공식 구독 로그인, 필요한 Telegram/OAuth 설정, health와 실제 작업 1건 관찰이 필요하다. 이번 정리로 운영 단계나 보류 기능을 자동 시작하지 않는다.

## 1차 정리 검증 결과

- 정리 PR #283의 [필수 validate 34213401518](https://github.com/Jongtae/agentos/actions/runs/34213401518)이 성공했다. 요구사항별 개발 근거는 불변 후보의 main CI에 계속 연결된다.
- 로컬 pytest: **241 passed, 46 subtests passed**. unittest 첫 전체 실행은 preflight fixture HTTP400 오류 1건으로 실패했으며, 해당 파일 13개 집중 재검증과 전체 **219개 재검증은 통과**했다. 첫 실패 기록은 지우지 않는다.
- 독립 검토의 한/영 상태 불일치와 미병합 PR 가상 merge SHA 문제는 수정·재검토 완료했다. OP-03 세 발견사항은 미해결 상태로 해당 PR에 남긴다.
- 기존 delivery heartbeat는 PAUSED임을 읽기 확인했다. 새 자동화를 만들거나 후속 기능을 활성화하지 않았다.
- 행정 마감 후 남는 일반 이슈는 OP-03 #280 및 보류 제안 #48/#49/#50/#100의 **5개**다. 미병합 제품 PR은 #281 하나다. 마지막 정리 PR 자체의 마감 결과는 #282에서 확인할 수 있다.
