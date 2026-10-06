# STRUCT-01 Work Unit 02 — 문서·산출물 정리

Issue: [#286](https://github.com/Jongtae/personal-agentos/issues/286)
Branch: `codex/struct-01-workunit-02-docifacts`
Goal: `STRUCT-01 — AgentOS 저장소 구조 정리`

## 1) 분류 규칙(작성 전 정합)

- 활성 실행 가능 계약/규약: `docs/*-contract.*`, `docs/goal-execution-contract.*`, `docs/development-governance.*`, `docs/operating-*/**`, `docs/top-level-specification-completion.*`, `docs/master-plan-*.{en,ko}.md`, `docs/v1-*`, `docs/vps-compose.md`
- 라우팅/로드맵: `docs/roadmap.md`, `docs/agentos-hub-v2.ko.md`
- 기록·이력: `docs/archive/*`, `docs/validation/*`, `docs/first-milestone-report.ko.md`
- 작업 참조(운영 추적): `docs/structure-reorg/*`, `docs/issue-branch-ledger.jsonl`, `TASKS.md` (상위/하위 트래커)

## 2) `README` 접근점 및 현재 링크 점검

### 접근 링크

- `README.md` / `README.ko.md` / `README.ja.md` / `README.zh-CN.md`
  - [AGENTS.md](AGENTS.md)
  - [PRD.md](PRD.md)
  - [TASKS.md](TASKS.md)
  - [docs/roadmap.md](docs/roadmap.md)
  - [docs/goal-execution-contract.en.md](docs/goal-execution-contract.en.md)
  - [docs/goal-execution-contract.ko.md](docs/goal-execution-contract.ko.md)

### 링크 검증 근거(현재)

명령: 

```sh
python3 - <<'PY'
from pathlib import Path
import re, urllib.parse, json

root = Path('.')
files = list(root.glob('README*.md')) + list(root.glob('docs/**/*.md'))
pattern = re.compile(r'\[[^\]]*\]\(([^)]+)\)')
errors = []
for p in files:
    text = p.read_text(encoding='utf-8')
    for m in pattern.finditer(text):
        link = m.group(1).strip()
        if link.startswith(('http://', 'https://', 'mailto:', '#')):
            continue
        path = urllib.parse.urlparse(link).path
        target = (p.parent / path).resolve() if path else None
        if path and target and not target.exists():
            errors.append((str(p), link))
print(f"checked_files={len(files)}")
print(f"broken_links={len(errors)}")
if errors:
    for e in errors:
        print(json.dumps({'file': e[0], 'link': e[1]}))
PY
```

실행 결과(2026-09-08):

- `checked_files=59`
- `broken_links=0`

## 3) WU-02 종료 체크리스트

- [x] 문서 카테고리(계약/계획/역사/증거/활용) 구분 규칙 확정
- [x] README 경로 도달성(필수 문서) 정합성 확인
- [x] 로컬 Markdown 링크 검증 기준 산출물 작성
- [x] WU-02 추적 항목 등록

## 4) WU-02 상태 로그

- 2026-09-08: Issue #286 생성, 브랜치 `codex/struct-01-workunit-02-docifacts`에서 산출 시작
- 2026-09-08: WU-01 하위 작업 산출물 [docs/structure-reorg/struct-01-workunit-01-inventory-and-migration-spec.md]를 기준 문서 분류에 반영
- 2026-09-08: `README*.md`와 docs 전체 링크 스캔 기준/실행 결과를 문서화
