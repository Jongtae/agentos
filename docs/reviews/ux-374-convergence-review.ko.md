# UX-REPAIR-01 수렴 검토 기록

## 범위

Issue #371의 UX 진단과 #374의 수용 기준을 기준으로 현재 변경 diff, 정적 회귀 테스트, 로컬 브라우저 관찰을 대조했다. 외부 모델 호출, 소유자 인증정보, 개인 폴더와 실제 Telegram은 사용하지 않았다.

## 확인 결과

- 모델 변경은 저장된 모델을 덮어쓰기 전에 `/api/model/test`에 현재 draft를 전달하고, 성공한 draft fingerprint만 적용 버튼을 활성화한다. HTTP 경로는 provider/endpoint 변경 시 새 키가 없으면 거부한다. 실패한 draft가 현재 모델을 바꾸지 않는 것은 service의 저장 순서와 테스트 대상 분리로 확인했다.
- `refresh()`는 context 체크박스의 dirty 상태와 기록 검색어/포커스를 복원한다. conversation settings의 내부 lifecycle 화면은 owner-facing 설정에서 렌더링하지 않는다.
- 화면 IA는 `AI 연결`, `파일 · 저장`, `외부 연결`, `내 기록`, `개인정보 · 진단`, `프로젝트`로 정리했다. 참고 폴더·결과 저장 폴더·프로젝트를 서로 다른 문장으로 설명한다.
- 메모·기억·임시 자료·저장된 결과를 구분해 표시하고, 목록의 각 메모/기억/결과에 삭제 버튼과 내용 미리보기를 둔다.
- Playwright 로컬 관찰: 390px viewport에서 `scrollWidth=390`, horizontal overflow 없음, checkbox computed width `13px`, apply button은 테스트 전 disabled. 검색어와 체크박스는 5초 polling 뒤 유지됐다. 포커스 유지는 별도 3.5초 관찰에서 확인했다.
- 전체 pytest `373 passed, 264 subtests passed`; canonical 문서와 src layout 검증도 통과했다.

## 제한 및 후속

- 실제 provider 연결, 실제 응답 모델, live Telegram, 개인 자료 전송은 관찰하지 않았다. 따라서 live external operation 완료를 주장하지 않는다.
- Playwright 관찰은 로컬 synthetic state의 브라우저 evidence이며, 사용자 연구나 실제 모바일 기기 evidence가 아니다.
- 기존 backend의 conversation-settings 계약은 호환성을 위해 남아 있으나 owner-facing 화면에서는 숨겼다. pending lifecycle confirmation의 실제 live journey는 후속 운영 검증 범위다.

## 결론

P0/P1 UX 결함 수정 범위는 현재 자동화·브라우저 evidence와 일치한다. live provider/Telegram 증거가 필요한 항목은 이 PR의 완료 주장에 포함하지 않고 후속 운영 검증으로 남긴다.
