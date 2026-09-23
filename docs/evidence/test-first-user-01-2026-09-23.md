# TEST-FIRST-USER-01 / #472 — synthetic first-user usability audit (2026-09-23)

Head under test: `0d6e4c7`. Evidence class: automated synthetic execution with injected transports (fixture Telegram, Gmail, Google token endpoints, Calendar provider, public-web egress, scripted model). Live operating evidence: not run. No product code was changed by this audit.

The unedited transcripts and the run metadata are preserved as comments on https://github.com/Jongtae/personal-agentos/issues/472. This file records the journey matrix and triage so the record survives outside GitHub.

### Journey matrix

| Journey | Result | What the synthetic user experienced |
| --- | --- | --- |
| install/start | **pass** | `agentos start` printed the address and the setup-link file; a second start on the same data folder refused with "이미 실행 중입니다"; Ctrl-C stopped cleanly; restart printed the address only; the browser auto-claimed on loopback and auto-logged-in after restart. `agentos service status` reported `not_installed` truthfully. Real launchd install / login-service restart: **not run**. |
| Telegram | **pass-with-friction** | Pairing via BotFather token → link → `/start` worked and greeted in Korean. First natural message before a model exists fails with jargon and no pointer (#477). Four bubbles per request, English-only failure strings, raw ids (#480). |
| files | **pass-with-friction** | Folder connection in Settings, summary through the model, the documented quoted phrase saved `9월 출장 정리.md`, the original stayed intact, "저장한 결과에서 출장 찾아줘" reused it after restart. The natural "그걸 파일로 저장해줘" wrote nothing (#481). |
| Gmail | **pass-with-friction** | Disconnected → parked with a one-step link → connect → resumed exactly once; revoked credential → re-auth link → resumed once. But a single interjection while connecting cancels the parked request silently (#473, see contextual row); a found mail cannot be read and a reply request runs a search (#478). |
| Calendar | **pass-with-friction** | Natural create → exact preview → "아니 4시로" → "취소" → restart → "제목은 …으로" → "승인" created exactly one event; English create + "yes" worked; expired preview and unknown provider outcome executed nothing and were not retried. Query "내일 일정 뭐 있어?" was blocked until the user found the raw-id `google-calendar` row in Settings (#475); the model-made cancel draft could not be approved from the conversation (#482); expired/stale "승인" was silent (#483). |
| research | **pass-with-friction** | Product comparison on a clean conversation returned the fixture's observed/unknown split with the source URL. Travel research phrased with "추천해줘" was hijacked into the recommendation rule (#474). Right after a file read, every research request was refused and the owner still received the model's text as if it were the answer (#448 reproduced, #476). Discrimination quality (#459) was not measurable with the fixture page: **not exercised**. |
| Memory | **pass-with-friction** | Remember, inspect from chat, correct (superseded, one current value), model-initiated memory stayed a candidate visible on the web. Delete only works on the web; counts on the receipt are confusing (#479). |
| contextual setup/resume | **blocked** (on the realistic path) | Uninterrupted connect-then-return resumes exactly once for Gmail, Calendar and re-auth. The moment the owner writes anything ("알겠어, 지금 연결할게", "잠깐만, 연결하고 올게") before finishing the connection, the parked request is cancelled, the callback page still says "Return to Telegram", the card still says "연결 대기", and nothing runs (#473). |
| restart/recovery | **pass-with-friction** | Interrupted Work marked "확인 필요" and not re-run; uncertain Telegram delivery not re-sent across restart; grants, pairing, memory and artifacts survived; a post-restart mail search needed no second authorization. The Telegram owner receives no message about the interruption (#483); the first revoked-credential failure reads "Gmail request rejected" (#480). |

### New issues created (materially new, bounded)

- #473 P1 — any unrelated message cancels a parked connector request; nothing resumes after the connection
- #474 P1 — "…추천해줘" hijacks travel/product requests into the capability-recommendation rule (internal outcome tags shown)
- #475 P1 — calendar query fails in English with no way to connect the read grant (raw `google-calendar` row)
- #476 P1 — failed/partial tool turns still deliver the model's answer as the final Telegram bubble
- #482 P1 — model-made cancel/update drafts have no owner-reachable approval; "승인" does nothing
- #477 P2 — before a model is connected, Telegram fails every message with "모델 또는 구독 엔진" jargon
- #478 P2 — a found mail cannot be read; a reply request runs a search
- #479 P2 — memory cannot be deleted from the conversation; web receipt counts confuse
- #481 P2 — natural "그걸 파일로 저장해줘" writes nothing; only the exact quoted phrase saves
- #480 P3 — English-only failure texts, raw connector ids, four status bubbles per request
- #483 P3 — expired preview, stale "승인" and restart-interrupted requests are silent in Telegram

### Known issues reproduced

- **known defect reproduced: #448** — scenario B turns 21–24: four consecutive research requests refused after one file read, with the "문서와 무관한 … 새 요청" wording that does not lead anywhere.
- #447 — not reproduced (the fixture provider never returned 409; no live provider).
- #459 — not exercised (fixture page content; discrimination recall not measurable here).
- #465/#466 — the natural-language create path now works end to end in this run (scenario C); recorded as verified, not as a finding.

### P0 / P1 blockers

- **P0: none observed.** No duplicate external effect (one provider `create` per approval, replays refused), no cross-identity approval, no false claim of an external effect by the product itself. The closest case is #476, where the *model's* sentence asserts an outcome the product did not produce.
- **P1:** #473, #474, #475, #476, #482.

### Internal terminology that reached the user

`private-document-research` / `specialist-research` / `local-specialist-processing`; `google-calendar` (settings row); "구독 엔진"; `/note`, `/notes`, `/summarize`; "Calendar request could not be completed."; "Gmail request rejected"; "Return to Telegram." pages; "Google Calendar 일정 만들기을(를)".

### Unnecessary repetition / setup

- Four Telegram bubbles per request, three of them status lines.
- Two separate Google Calendar authorizations (read and write) with only the write one ever offered by the conversation.
- The exact quoted phrase required to save a file result.
- Re-asking a parked request after any interjection (#473).

### Evidence boundary

- Repository/static: `CONNECTOR_LABELS`, `CONNECTOR_BY_INTENT`, `_RECOMMENDATION_CUES`, `run_one` — consulted only for the root-cause lines after each observation.
- Automated synthetic execution: all journeys above, through `configured_service` + `make_handler`.
- Simulated provider behaviour: Telegram Bot API, Gmail REST (metadata only), Google token endpoints, Calendar provider (query/create, injected timeout), public-web egress, and a scripted model whose tool choices and sentences the harness set per turn.
- Live operating evidence: **not run** — no real Telegram bot, Google account, model provider, web fetch, Homebrew install or launchd service.

### Completion against the contract

1. all independent journeys executed as far as safely possible — yes (nine rows, none `not-run`; live legs stated as not run);
2. original owner-visible evidence preserved — yes (four unedited transcript comments above);
3. known defects distinguished from new findings — yes (#448 reproduced; #447/#459 not reproduced/not exercised);
4. new findings have bounded issues — yes (#473–#483);
5. no implementation fixes mixed in — yes (working tree untouched on main; scripts lived under `/tmp`);
6. journey matrix recorded truthfully — this comment;
7. no successor activated — yes; this comment selects nothing.
