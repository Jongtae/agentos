# PRESENCE-EVAL-01 — Presence A–J evaluation record

Issue: [#512](https://github.com/Jongtae/agentos/issues/512), final convergence verification child of PRESENCE-01 [#508](https://github.com/Jongtae/agentos/issues/508). Canonical matrix: [Presence Experience Contract](presence-experience-contract.en.md), "Observable acceptance matrix".

## Evidence class and boundary

Everything recorded as a result here is **automated synthetic fixture evidence**: `tests/test_presence_eval_matrix.py`, run in repository CI. Each scenario goes through the shipped owner boundaries:

- Telegram ingest: `AgentService.ingest_update`, `ingest_callback`, `ingest_stop`;
- the single conversation worker, `run_one`;
- durable delivery, `deliver_one`;
- where the contract puts the authority step on the owner's Mac, the real local HTTP handler (`quickstart.make_handler` on loopback, with an owner session).

Only these parts are scripted:

- a fake Telegram Bot API transport, which records every outbound method and body in wire order;
- a scripted `ModelAdapter` transport;
- `FixtureDecisionEngine`, behind the provider-neutral DecisionEngine seam;
- fixture Gmail, Google Calendar (including the real `GoogleCalendar` adapter over a transport that returns HTTP 409), public web and folder-dialog seams.

Nothing in this record is live owner, live provider, live Telegram or live macOS evidence. **The owner reported on 2026-09-25 that the six live Telegram checks for #581 did not behave as the fixture expectations predict. The details have not been captured yet and the cause is unknown. #581 was reopened.** Every native-presence result below is therefore fixture-only. The live Telegram pass is listed as an unmet owner-live item. No owner live observation is cited as evidence.

Owner phrasing varies across cases: Korean and English, direct and indirect. A pass does not depend on one magic phrase. This PR adds no product code and no cue or regex rule. A product gap is recorded as a **finding**: an `unittest.expectedFailure` test named `test_finding_*` that asserts the contract's expected behavior, so it turns into an unexpected success once the product meets it. Evaluation does not fix product code (#512 evaluation rule).

Run: `PYTHONPATH=src python3 -m pytest tests/test_presence_eval_matrix.py -q`. The exact integration head and CI run are recorded in the PR.

## A–J results

| # | Scenario | Tests (`tests/test_presence_eval_matrix.py`) | Owner-visible expected interaction (asserted) | Result |
| --- | --- | --- | --- | --- |
| A | Trivial request | `A_TrivialRequest.*` | 4 phrasings: `setMessageReaction(👍)` → one `sendMessage` (the answer). No card, no controls, no anchor, no lifecycle text. A brief wait adds only `sendChatAction(typing)`. Model Markdown renders as Telegram HTML. | **Pass** |
| B | Failed runtime | `B_FailedRuntime.*` | `👍` (receipt only) → one anchored bubble. It opens with `이 요청은 완료하지 못했습니다.`, states the cause, never carries the model's success sentence, and offers `[다시 시도][상세]`. Tapping 상세 opens an alert and adds no bubble. A CLI worker failure gets the same projection. A missing AI route is a blocked turn with an in-chat next action; a repeat is a one-line reminder with no retry control. | **Pass** |
| C | "try again / does it work now?" | `C_RetryContinuity.*` | 4 phrasings judged `retry` by the DecisionEngine replay the **original** request once, with `relation_kind=retry` and `related_job_id` set to the failed Work. The failed Work stays `failed`. The reply is `👍` then one answer. Retry is refused, not duplicated, in four cases: a second retry, a foreign or duplicate tap, callback-API failure, and a failed Work that attempted an effect. A new topic, or an unavailable judge, never replays. | **Pass** |
| D | Missing Gmail | `D_MissingGmail.*` | 3 phrasings each get `👍` then exactly one guidance bubble (full method sequence asserted). It names Gmail, says nothing ran, and links to `http://127.0.0.1:<port>/google-gmail`. The Work is `awaiting_connection` and the mailbox is not called. The connection runs through `/google-gmail` → `/oauth/gmail/callback` (fixture token exchange). The **original** Work resumes exactly once, gets exactly one `sendMessage` with no second reaction, and triggers one Gmail search. A replayed callback returns 400 and nothing resumes twice. A denied connection fails the Work and grants nothing. Chat in the meantime keeps the request; only a withdrawal the judge detects cancels it. | **Pass**, with generalization finding **D1** |
| E | Missing local folder | `E_MissingFolder.*` | `👍` then one path-free guidance bubble (`Mac에서 계속`, `읽기만`), provenance `setup-required`, nothing granted. Over HTTP, the phone/tunnel host gets 403. On the Mac, the read-only preview shows, then the (fixture) dialog selects: selecting is not granting. Approve grants exactly the picked folder with read only, sends one notice, and the original Work resumes once. A replayed approve returns 409 `no_pending_work`. The original file is unchanged. Read and result-write are two separate approvals, and the write folder never becomes a read folder. A cancelled dialog, a deny, or a path typed in Telegram grants nothing. | **Pass**, with owner-language finding **E1** |
| F | Calendar approval | `F_CalendarApproval.*` | 3 phrasings get an exact preview (title, date/time, zone) with no reaction and no provider call. `승인`/`approve`/`yes` makes exactly one create. A replayed approval, an expired preview (+901 s), another identity (web) or `취소` creates nothing. A correction re-drafts, and only the corrected payload runs. A missing write grant produces one handoff; the resumed Work stops at a preview. | **Pass** |
| G | Long-running research | `G_LongResearch.*` | `👍` → `sendMessageDraft(can_stop)` at 6 s, one refresh at 27 s (9 s and 14 s are no-ops) → one durable anchored answer with observed sources. No card and no scheduler narration. Stop during running Work sends one `STOP_RUNNING_TEXT` notice ("could not cancel"), no further drafts, and the real result once. A repeated Stop sends nothing more. Stop on queued Work cancels it through the state machine and it never runs. | **Pass** |
| H | Partial result | `H_PartialResult.*`, `Inspectability.*` | The Work is `partial`, never collapsed into success. The sequence is `👍` then one bubble; it opens with `일부 단계만 완료했습니다.`, names the failed portion, never asserts the model's "compared both" claim, and offers `[상세]`. The Evidence qualifier is `partial` in the transcript, the card and later model context. The opposing succeeded/failed/partial outcomes read differently and carry different controls. | **Fail**: **H1**, the verified portion is not stated in conversation |
| I | Unknown external effect | `I_UnknownExternalEffect.*` | A 409 on create (#447) gives exactly `OUTCOME_UNKNOWN` ("could not confirm … not retried automatically"), and the draft state is `outcome-unknown`. A repeated `승인` and two judged-retry phrasings make **no** second provider call. | **Pass** on the matrix line, with Work-record finding **I1** |
| J | Memory correction | `J_MemoryCorrection.*` | An owner-stated value becomes canonical Memory. A correction supersedes it (one row, new value) and the Work links the retained item. A model-proposed value the owner did not state stays a pending MemoryCandidate. The Work is `failed`, and the bubble says it was kept as a candidate and never says "remembered". Only owner inspect → request-approval → accept on the Mac changes canonical Memory. Delete works on the Mac. | **Pass**, with generalization finding **J1** |

## Acceptance map (#512)

| Acceptance item | Evidence (tests) | Result |
| --- | --- | --- |
| Every A–J scenario has an owner-visible expected interaction and observed result | Table above; each scenario asserts owner-visible texts, and the method sequence where the next row says so | Met (fixture) |
| Telegram message count and order recorded | Complete outbound `methods()` sequence asserted for A, B, C (retry turn), D (park turn and resumed answer), E (guidance, grant notice and resumed answer), F (preview), G (first/last method, draft count) and H (single and opposing turns). Bubble count and content are asserted everywhere else. | Met (fixture) |
| Owner-visible claims map to Work/Event/Evidence | Each scenario checks job status/relation, `task_events`, `turn_provenance`, `task_progress` qualifier/route, Gmail/Calendar/provider call counts, and canonical Memory rows | Met, except **I1** (unknown effect recorded as `succeeded` Work) |
| Opposing success/failed/partial/unknown covered | `H_PartialResult.test_opposing_outcomes_…`, B, C opposing, `I_*`, `J_…candidate…` | Met (fixture) |
| Short conversation has no lifecycle chatter | `A_*` (`LIFECYCLE_CHATTER` check), G | Met (fixture) |
| Prior-failure retry/correction continuity without duplicate effects | `C_*`, `I_…never_retried`, `F_…correction…` | Met (fixture) |
| Missing capability → contextual handoff → original Work resumes exactly once | `D_…exactly_once`, `E_…resumes_once`, `F_…missing_write_grant…` | Met for cue-bearing phrasing. **D1**: a mail request without a mail cue word gets no handoff |
| Calendar exact preview/approval semantics | `F_*`, `I_*` | Met (fixture) |
| Effective AI route vs observed worker identity distinct and truthful | `RouteAndIdentity.*`, `SettingsLanguage.test_exactly_one_effective_route…` | Mostly met. **R1**: the configured model is stored as the observed response model when the provider reports none |
| Settings uses owner language, not internal ids | `SettingsLanguage.*`; web renderer regression inputs `tests/test_settings_ui.py`, `tests/test_settings_orchestrator.py` | Met for Settings. **X1** and **E1**: raw tool/result ids appear in conversation bubbles |
| Worker/model change keeps one assistant identity | `RouteAndIdentity.test_a_worker_change_…`: the same `CORE_INSTRUCTIONS` on the CLI and API workers; the API worker reads the CLI turn; no worker names itself in any bubble; the same reaction | Met (fixture) |
| Routine turns use native presence (#581), not a lifecycle bubble | A, C, G | Met (**fixture only**; the owner live pass did not match, see below) |
| Noticeable waits use chat action/draft; Stop reconciled with real cancellation state | `A_…brief_wait…`, `G_*` | Met (**fixture only**) |
| Reaction/chat-action/draft/callback failures are best-effort only | `A_…presentation_api_failures…`, `C_…callback_presentation_failures…` | Met (**fixture only**) |
| Reply anchoring and callback controls owner-bound/idempotent; no raw Markdown markers | `B_*`, `C_…owner_bound…`, `G_*`, `A_…markdown…` | Met (**fixture only**) |
| Work/Event/Evidence remain inspectable | `Inspectability.*` (`/api/tasks/<id>`: status, qualifier, error, route, provenance, events; preserved text) | Met (fixture) |
| Synthetic and live evidence reported separately | This document | Met |
| Bounded live owner dogfood pass recorded before promotion | Not done here; see the owner-live checklist | **Not met: owner action** |

The issue's completion rule also requires independent convergence review and the owner-live boundary on the exact integration head. Neither is supplied by this PR.

### Extended regressions (retired narrow issues)

| Issue | Evidence | Result |
| --- | --- | --- |
| #477 AI/provider unavailable first use | `B_…no_ai_route…` | Pass |
| #478 found-item follow-up / unsupported mutation | `D_*` (found item), `tests/test_conversation_connector_handoff.py::MailIntentTests` (regression input) | Pass (found item); unsupported send covered by the existing suite only |
| #479 Memory correction/delete/reference | `J_*` | Pass (J1 noted) |
| #481 reference resolution | `ExtendedRegressions.test_481_…` | Pass: the relation is recorded and the previous request is not replayed |
| #475 missing Calendar capability → one handoff | `F_…missing_write_grant…` | Pass |
| #482/#483 stale/expired/replayed approval | `F_…expired…`, `F_…each_phrasing…` (replay), `F_…another_identity…`, `D_…replayed_callback…`, `E_*` (replayed approve) | Pass |
| #489/#493 typed setup-required/truncated; failed vs partial | `ExtendedRegressions.test_489_493_…`, H | Pass (X1 noted) |
| #490 no generic false-success fallback | `ExtendedRegressions.test_490_…` | Pass |
| Restart/recovery (material) | `ExtendedRegressions.test_restart_recovery_…`; #505 restart in `tests/test_contextual_capability_handoff.py` | Pass |

## Findings (not fixed here; remediation is the owner's decision)

Each finding is an `expectedFailure` test that asserts the contract's expected behavior. When the product meets it, the test becomes an unexpected success and CI fails as a signal to flip it.

| ID | Where | Observed (synthetic) | Contract expectation | Test |
| --- | --- | --- | --- | --- |
| **D1** | Intent routing (`IntentClassifier` literal cue tables in `conversation_handoff.py`) | `집주인한테 답장 왔어?` and `did the landlord write back to me?` contain no mail cue word. They go to the ordinary model route: both Works `succeeded` and no Gmail handoff is offered. The sentinel ingests both phrasings before asserting. | Model-first semantics: a mailbox read by meaning gets the contextual handoff | `test_finding_d1_…` |
| **E1** | Result-saved reply (`quickstart_service`: `저장됨: {name} · {id}`) | The Telegram reply ends with the internal result UUID | Raw ids belong in technical detail; #562 already provides exact-item links | `test_finding_e1_…` |
| **H1** | Partial terminal bubble (`conversation_projection.terminal_text`) | The bubble names the failed portion and points to the web record. The verified portion (page A's fact, `3,000 KRW`, and its source) is not stated in conversation. The sentinel requires the fact itself, not only the source URL. | "State the verified completed portion and the unavailable/failed portion separately"; do not default to "open the web console" | `test_finding_h1_…` |
| **I1** | Calendar approval Work outcome | After a 409, the approving Work is `succeeded` with no qualifier, even though the bubble says unknown. As a result, a later judged "try again" is refused with the misleading reason "the previous request was not failed/interrupted". The refusal still holds: there is no duplicate. | failed/partial/unknown stay distinct in Work/Evidence, not only in prose; the refusal should name the unknown effect and its duplicate risk. The sentinel requires an explicit `unknown` qualifier and the unknown-effect refusal; an ordinary failed/partial outcome does not satisfy it. | `test_finding_i1_…` |
| **J1** | Memory authority cue (`AgentService.explicit_memory_request` regex) | `회의는 오후가 좋다는 거 잊지 마` ("don't forget") is not recognised as a remember request. The owner-stated value is withheld as a candidate and the turn fails. This is truthful, but the owner's explicit instruction is not honoured. | Model-first interpretation of an explicit owner instruction; authority checks stay deterministic | `test_finding_j1_…` |
| **R1** | Model identity recording (`ModelAdapter` fallback → `model/responded` event → `task.observed.model`, route label) | With no provider-reported model, the configured name is recorded as the response model and shown as "observed". `turn_provenance` correctly keeps `requested_model` and `reported_model=None` apart. | Configured identity is not presented as observed execution identity | `test_finding_r1_…` |
| **X1** | Failed/partial bubbles (`완료하지 못한 도구 실행 — <tool_id>: …`) | Owner-visible Telegram text includes `bounded_public_research`, `save_memory` and `find_files` | Raw internal ids are not the default owner language; the tool id stays in Task/Evidence detail (as `Inspectability` shows it does) | `test_finding_x1_…` |

Observation, not scored: the Calendar handoff text reads `Google Calendar 일정 만들기을(를) 연결해 주세요` (particle template).

## Owner-live checklist (not claimed; owner actions)

Do not commit screenshots, raw ids, paths, credentials or personal content. Record each item as a short, redacted outcome note on #512 (pass / differs, plus what differed).

1. **Live Telegram mobile pass (#581, currently reopened).** The owner already observed live behavior that differs from the fixture expectations; the cause is unknown. Run the same checks on a phone once #581 is resolved:
   1. Send an ordinary question (`오늘 저녁은 뭐해 먹을까?`). Expect a 👍 reaction on your message, then one answer bubble, with no "처리가 끝났습니다" and no "결과 상태 보기".
   2. Ask for something that takes a few seconds. Expect "typing…" only, then one answer.
   3. Ask for long research. Expect a draft/"thinking" preview with Stop, then one answer quoted to your message. Tap Stop once during the wait. Expect one "could not cancel, will report the real result" notice, then the real result.
   4. Make the AI route fail (for example, stop the local model). Expect one failure bubble quoted to your message with `다시 시도` / `상세`. Tap `다시 시도` twice. Expect exactly one retry. Tap `상세`. Expect an alert and no new bubble.
   5. Check that formatting renders without literal `**`.
   6. Note the Telegram client/version and anything that differed.
2. **macOS folder dialog (E).** On the Mac, ask in Telegram for a file in a folder you have not granted. Open the linked `#settings/files`, press choose, and confirm the **native macOS folder dialog** opens with the request prompt. Pick one folder and confirm the read-only preview before approving. Then confirm the answer arrives once in Telegram and that the phone/tunnel page cannot approve.
3. **Real DecisionEngine provider judgment (C, D, J semantics).** With the owner-configured decision route (default `gpt-4o-mini` or the selected route), send varied follow-ups after a failure (`이제 돼?`, `한 번 더`, `그건 됐고 …`). Note which were resolved as retry, which as a new request, and any mis-resolution. This measures real judgment quality; the fixture does not.
4. **Live Gmail connection (D).** On the Mac, open the `/google-gmail` link from the guidance bubble, complete Google consent, and confirm the parked request answers exactly once in Telegram.
5. **Live Calendar create (F), optional.** On a test calendar, create one draft, approve it, and confirm exactly one event exists. The HTTP 409/unknown path (I) is not reproducible on demand live; do not force it.
6. **AI route switch (identity).** In Settings, switch between the CLI route and the direct API. Confirm replies read as the same assistant, and that the task technical detail names the route and the reported model (or "not reported").

## Non-claims

This record makes the following non-claims:

- it does not claim live Telegram, Google, provider or macOS behavior;
- it does not measure model quality;
- it does not activate #383 or any successor;
- it makes no product change.

The pre-existing literal cue routing (D1/J1) is recorded as a gap; it is not a new rule. The Calendar approval vocabulary (`승인`, `approve`, `yes`) is deterministic authority by design and is not scored as a generalization gap.
