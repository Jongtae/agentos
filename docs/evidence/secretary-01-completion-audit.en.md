# SECRETARY-01 phase 1 completion audit (template)

SEC-EVAL-01 [#660](https://github.com/Jongtae/agentos/issues/660) · Program [#662](https://github.com/Jongtae/agentos/issues/662) · Contract: [Secretary Agency Contract](../secretary-agency-contract.en.md), "Completion rule" · Owner procedure: [probe runbook (ko)](secretary-01-probe-runbook.ko.md)

**Status: template.** This file maps each completion-rule item to the evidence that exists on `main` today and marks what is still owed. It is not a completion claim. The program is complete only when every row below is satisfied **on one closeout head**, recorded here with that head's commit id and its required CI.

Closeout head: `pending` · Required CI on that head: `pending`

## Evidence classes used here

| Class | Meaning |
| --- | --- |
| unit | Focused tests with injected model/tool transports, fake clocks and temporary stores (#612). Proves code behavior under scripted inputs, not live model behavior. |
| model-free integration | A real `run_agent` / `AgentService.run_one` / bridge / Playwright path with only the model or remote wire replaced. |
| static structural | A source scan (`tests/test_no_scenario_code.py`). Proves what the scanned source contains, not runtime behavior. |
| owner-installation record | A redacted record of one Work on the owner's installation, produced by `scripts/prepare_owner_smoke.py record-probe`, plus the owner's own check of the external state. The only class that satisfies item 6. |
| review | A reviewer's confirmation on a named head. |

A fixture pass, a merged PR or this template never counts as an owner-installation record.

## Item-to-evidence map

| # | Completion-rule item | Evidence on `main` now (class) | Still owed | Status |
| --- | --- | --- | --- | --- |
| 1 | **Alternatives observed** — the loop moves to a different provider, query or route after a failed path, without repeating the same path. | PR #669: `tests/test_agency_loop.py` `test_irrelevant_results_then_the_same_search_is_refused_and_a_provider_switch_runs`, `test_a_rewritten_query_is_a_different_path`, `test_an_omitted_provider_is_the_default_so_naming_it_is_a_repeat`, `test_alternative_nudges_are_bounded_by_the_work_budget`, `test_a_missing_authority_is_not_nudged_toward_another_path` (unit). PR #668/#669: `tests/test_browser_session.py` `test_the_same_step_on_the_same_page_is_refused_and_on_a_changed_page_runs` (unit). PR #660: `tests/test_prepare_owner_smoke.py` `test_record_of_a_real_loop_run` (model-free integration: provider switch and refused repeat survive into the record). | At least one owner-installation record whose `tool_calls` show an `alternative` after a failed or irrelevant path and whose `checks.repeat_paths_refused` or distinct paths show no repetition. | automated: present · live: `pending owner run` |
| 2 | **Evidence-based completion enforced** — `succeeded` is never emitted without matching observed state; a tool that "succeeds" without the goal being reached does not succeed. | PR #669: `test_a_tool_that_succeeds_without_showing_the_goal_never_succeeds`, `test_a_plain_reply_after_tools_is_checked_once_and_never_succeeds_without_a_claim`, `test_a_claim_citing_a_failed_or_unknown_observation_is_rejected`, `test_a_done_claim_without_evidence_is_rejected`, `test_a_judged_done_finish_succeeds_through_the_service` (unit / model-free integration). PR #668: `test_login_required_keeps_the_turn_from_claiming_success` (unit). | Owner-installation records with `checks.succeeded_iff_judged_done_claim: true`. Known limitation carried from #669/#670: the subscription-CLI route has no `finish`/judgment, so probe runs must use the direct API route. | automated: present · live: `pending owner run` |
| 3 | **Reports match observation** — requested / observed / failed / unknown stated correctly. | PR #669: `tests/test_agency_loop.py` `test_a_partial_finish_reaches_the_owner_as_a_typed_report`, `test_a_empty_rule_read_is_rejudged_by_the_loop` (model-free integration through the service and the Telegram terminal text). PR #660: `test_report_sections_are_parsed_from_the_owner_report` (unit). | For each probe record, the owner confirms the `report` (reply, observed, failed, unknown, next) against the external state: the cart page, the stored reminder and its delivery, the lunch sources. | automated: present · live: `pending owner run` |
| 4 | **Execution environment enforces only the allowed set** — payment blocked without approval; secrets absent from prompts, logs and Evidence; cart add, provider choice and page reads proceed without re-asking. | Negative, PR #668: `test_card_fields_and_their_form_button_need_approval_whatever_the_label_says`, `test_password_fields_are_guarded_too`, `test_a_refused_card_number_leaves_no_trace_in_the_store`, `test_password_otp_values_and_a_rendered_token_never_leave_the_driver`, `test_durable_records_never_carry_page_secrets`, `test_browser_type_text_is_never_recorded` (unit); PR #669: `test_secrets_and_saved_private_values_are_redacted_before_the_judgment`, `test_the_service_redacts_its_stored_secrets_before_the_judgment` (unit / model-free integration); PR #666: `test_keys_round_trip_into_the_secret_store_and_are_never_returned`, `test_http_401_and_429_are_typed_failures_without_the_body_or_key` (unit); PR #664: `test_the_owner_sees_a_secret_like_value_but_the_prompt_never_does` (unit). Positive, PR #668: `test_ordinary_fields_and_buttons_proceed_and_the_label_can_only_add`, `test_product_to_cart_through_the_loop_with_repeated_reads` (unit), `test_product_page_cart_button_and_cart_page_through_the_real_driver` (model-free integration; skips without Playwright/Chromium, observed passing in #668's isolated venv); PR #666: `test_the_model_choice_is_honored_regardless_of_the_query_language` (unit); PR #665: `test_api_route_sends_a_book_title_request_as_the_worker_composed_it`, `test_cli_route_sends_a_book_title_request_as_the_worker_composed_it` (unit). PR #660: `test_record_never_carries_secrets_cookies_typed_text_or_saved_private_values` (unit, for the evidence records themselves). | Probe A record shows the cart step ran without an owner re-ask and no payment step ran. Known limitation from #668: a stored-payment purchase button outside a card-field form is not detected; the owner does not connect payment. | automated: present · live: `pending owner run` |
| 5 | **No scenario-specific code** — no site, provider or category branch in decision/runtime code. | PR #660: `tests/test_no_scenario_code.py` (static structural): scans `agent_runtime.py`, `conversation_handoff.py`, `current_context.py`, `browser_session.py`, `local_tools.py`, `quickstart_service.py`, `decision*.py` and `preparations.py` once it exists; `search_providers.py` is the allowlisted registry. Every PR #664–#670 states "generalizes the loop". | Owner disposition of the three **open findings** below, and a review confirmation on the closeout head that no new branch was added (the guard fails on any new hit). | automated: present, 3 open findings · review: `pending` |
| 6 | **Probes A, B, C and the held-out scenario** complete on the owner's installation with evidence recorded. | None. Fixture runs do not satisfy this item. The recorder and runbook exist (PR #660). | Records `secretary-01-probe-A-<date>.json`, `-B-`, `-C-`, `-D-` from the owner's installation on the closeout head, each with the owner's check below. Probe B and the preparation part of probe C depend on SEC-ATTN-01 #659. | `pending owner run` |
| 7 | **Phase 2** delegation completes its own audit, or the owner explicitly closes the program at phase 1 and records phase 2 as the successor. | None. SEC-A2A-01 is a later ordered substep. | Either the SEC-A2A-01 audit or an owner decision recorded through a governance PR. | `pending owner decision` |

## Open findings from the no-scenario-code guard (item 5)

The guard found these on `main` at `49b4fac`. They predate SECRETARY-01 and were **not changed** by #660. Each is a deterministic keyword rule that classifies the request type before the model; none names a probe's site or provider. They are listed in `CLASSIFIED` in `tests/test_no_scenario_code.py` as `open-finding`.

| Module | Literal | Where | Nature |
| --- | --- | --- | --- |
| `conversation_handoff.py` | `'book'` | `_CALENDAR_VERBS`, used by `_rule_calendar` | English verb "book (a meeting)" in the calendar-create cue list; not the book category, but a keyword rule. |
| `conversation_handoff.py` | `'google it'` | `_RESEARCH_CUES`, used by `_rule_research` | Names a provider as a verb in the research cue list. |
| `quickstart_service.py` | `'google drive'` | `AgentService.requests_drive_access` | Keyword rule that classifies a request as a Drive request and offers the Drive connection. |

Owner disposition: `pending` (accept as pre-existing capability routing outside this rule, or open a bounded removal issue).

Also classified by the guard as **allowed** (not a scenario branch): `metadata.google.internal` in `local_tools.DENIED_PUBLIC_HOSTS` (SSRF denylist), and the connector ids `google-drive-read`, `google-gmail-read`, `google-calendar`, `google-calendar-write` in `quickstart_service.py` (connector registry identity and display labels).

## Probe records

One row per probe, filled after the owner run. Ids come from the record file.

| Probe | Record file | Work id | Head | Key call ids (provider/action) | `finish.evidence_refs` | `goal_judgment` | `final_outcome` | Owner check of external state | Report matches? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A book → cart | `pending` | | | search, product page, cart click, cart page | | | | item in the Kyobo cart: | |
| B reminder | `pending` (after #659) | | | calendar read, reminder stored, delivery | | | | reminder time / delivered at / event start: | |
| C lunch | `pending` | | | search, page read, location source | | | | allergens absent, distance/hours correct: | |
| D held-out | `pending` (closeout head only) | | | | | | | request chosen at closeout: | |

Held-out D verdict: `pending`. If D fails for a reason that would require site-, provider- or category-specific code, completion is rejected.

Re-runs: none recorded. Any additional live run states its reason here (#612).
