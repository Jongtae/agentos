# SKILL-EVAL-01 — Supplied-skill coverage, evidence and live-sample protocol

**Issue:** [#964](https://github.com/Jongtae/agentos/issues/964) (child of [SKILL-SUPPLY-01 #959](https://github.com/Jongtae/agentos/issues/959))
**Date:** 2026-10-02
**Status:** coverage map, gap checks and protocol. **No live run has been made.** The live budget stays zero until the owner approves the sample in section 4.
**Code covered:** `main` after #976 (`efb5977`). Upstream fixture `anthropics/skills@8a1541c`. Reference skills `skills/shopping-cart` and `skills/emart-ssg` at that head.

This is not a second test project. Each implementing child already checked its own boundary. This document maps that evidence to the #964 inventory, adds only the checks that were really missing, and states what remains unproven.

**Evidence classes** used below:

- **U:** unit/fixture tests, model-free.
- **I:** model-free integration through a real boundary (MCP bridge process, CLI process with a loopback fake model).
- **P:** live public read, no account.
- **S:** static or structural check.
- **L:** live model or live account. None yet.

## 1. Coverage map

| # | Inventory item | Evidence (class) | Status |
| --- | --- | --- | --- |
| 0 | Off/empty/missing/incompatible skill and supplier outage keep existing functions; a revoked loaded skill stops the Work without replay | `test_skill_supply`: `OffAndEmptyPreserveThePreSkillPath`, `test_source_outage_never_breaks_an_installed_skill`, `RevocationAfterLoading`, `test_a_relayed_call_is_refused_when_a_loaded_skill_was_withdrawn`, `test_a_restarted_bridge_remembers_what_the_work_loaded`, `test_a_delegated_specialist_stops_when_a_loaded_skill_is_withdrawn` (U). Route surfaces unchanged with skills off: `test_capability_profiles`, `test_bounded_execution`, `test_turn_provenance` (U). `test_skill_shop.BrowserPortIsPreserved` (U) | Covered |
| 1 | A fresh user completes a task with supplied knowledge, with no failed first attempt | `test_skill_supply.FreshUserFirstUse` (U). `test_skill_shop.test_supplied_knowledge_is_used_on_the_first_request_with_one_change_and_a_readback` (U, fixture shop) | Covered (fixture) |
| 2 | An externally authored package goes through the real import path | `anthropics/skills` `internal-comms` (Apache-2.0), byte-identical fixture (`ThirdPartyFixtureIsPinned`, U). Real bridge process (`test_the_real_bridge_process_serves_the_pinned_skill`, I). One live public GitHub install into a temporary store on 2026-10-02 (P; #971) | Covered |
| 3 | A repeat with changed products or quantity modes reuses the know-how and re-reads current facts | New `test_skill_shop.test_a_later_request_reuses_the_pinned_revision_without_fetching` (U). Re-reading facts is in the method (content). | Structure covered. **Model behavior: L, pending** |
| 4 | A Main AI change keeps the skill version; unsupported bindings stay explicit; API/Codex/Claude parity | Route snapshot per Work (`test_ai_route_selection.test_switch_during_running_work_does_not_redirect_it`, U). Binding captured once per Work before the attempts loop, refs recorded in turn provenance (S, `quickstart_service`). Host → bridge parity (`test_the_bridge_rebuilds_the_exact_binding_the_host_passed`, U; real bridge, I). Strict/isolated declared unavailable (U). Codex `CODEX_HOME` skills kept out (`test_codex_trusted_local_keeps_codex_home_skills_out`, I, opt-in) | Covered |
| 5 | Management setters separate requested/configured/effective/observed; family setup-ready versus paired | `test_skill_manage` (U). Existing `test_owner_settings_conversation`, family tests (U) | Covered |
| 6 | UI drift, expired login, unavailable item, partial result, duplicate request, interruption and restart recover without unverified replay | Host side: `test_browser_session` login continuation, unknown-effect and `tool_incomplete` handling, payment guard (U). Withdrawal mid-flow stops the next click (`test_withdrawing_the_method_mid_flow_…`, U). Model side: method steps 4 and 6 (content) | Host covered. **Model behavior on drift: L, pending** |
| 7 | A concurrent shared-cart change is not falsely attributed or claimed exactly-once | Method step 6 (content). Cookie sharing boundary: `test_family_share` (U) | **Model behavior: L, pending.** Not observable in fixtures |
| 8 | Disabled/removed skill after load, unavailable supplier, tampering, permission-expanding update and rollback | `RevocationAfterLoading`, `test_tampered_content_is_refused`, `ReviewRemediations`, `ManifestDeclarations` (a skill package cannot declare tools, so no update can widen permissions) (U). New `test_a_rollback_restores_the_older_revision_without_reviving_a_newer_works_binding` (U) | Covered |
| 9 | A second site fixture uses the common contract without core edits | `fixture-mart` flow and the published `emart-ssg` package installed and loaded (`test_skill_shop`, U). No core literal names a skill or compares a skill identity (`test_no_scenario_code`: `CoreNamesNoSkill`, `CoreSelectsNoSkill`, `CoreReadsNoSkillFiles`, S) | Covered (fixture). Held-out live site: L, not planned |
| 10 | One voice, no new rituals, confirmations or compulsory specialist/verifier calls | New assertion: the fresh-user run makes exactly one model call per scripted step (U). Skill reads need no confirmation; adding one uses the existing settings draft (U). Transcript quality: eval scenario `skill-add-reference-by-name` (rubric-judged) | Structure covered. **Transcript: L, pending** |

**Gaps closed by this child.** Each is a new model-free check named in the table:

- item 3: repeat without a supplier call;
- item 8: rollback;
- item 10: no hidden model calls.

**Gaps that remain open** all need a live model, and some an account:

- whether a model actually follows the shopping method on the real Emart site (items 3, 6 and 7);
- whether the transcript is natural (item 10).

These remain **pending**. They do not block fixture-based closure of #961–#963. They do block any claim about real-site quality or savings.

## 2. Comparison protocol (A / A-off / B)

Defined before any tuning. Conditions run **sequentially, never in parallel against a real account**.

| Condition | Definition | Source of evidence |
| --- | --- | --- |
| **A** (existing baseline) | The AgentOS behavior before skills existed, on the same route | The 12 earlier Works with redacted SSG browser records (#963 section 14): observed URLs, titles and outcomes only. No new run |
| **A-off** | The current code with skills off (the default) | Unit/route tests showing the surface identical to A; a live sample only if the owner approves (section 4) |
| **B** | The current code with `shopping-cart` + `emart-ssg` installed and skills on | The fixture runs (section 1). A live sample only if the owner approves (section 4) |
| C | Learned or replayed procedures | Not implemented; out of scope |

Rules:

- A fresh fixture store per run.
- An explicit package set.
- A cart change already made does not count as a new execution.
- One evidence class per row in any report.

The eval harness (`evals/`) cannot run cart flows, because its sandboxes have no browser by design. It covers the conversation part with the new scenario `evals/scenarios/skills.json` (`skill-add-reference-by-name`). Per the #887 on-demand policy, run it only as `--scenarios skill-add-reference-by-name --epochs 1` after an approved batch.

## 3. Metrics recorded for any live sample

- **Outcome:** goal satisfaction supported by a cart read-back reference; false completions; duplicate or unrequested cart effects; owner interventions.
- **Cost:** end-to-end latency; model calls and tool calls (from Work events); token or usage data where the route exposes it (unknown otherwise; a subscription route is not "free").
- **Change cost:** core files changed to add a site (expected 0).
- **Context:** sample size, exact code and skill revisions, model and route.

No target percentage. An inconclusive result stays inconclusive.

## 4. Proposed live sample (needs the owner's approval; not run)

| Item | Proposal |
| --- | --- |
| Route | The owner's main AgentOS, current Main AI (trusted-local Codex), the owner's signed-in browser profile |
| Condition | **B** only (skills on with `shopping-cart` + `emart-ssg`). A is the existing redacted records; no second, shadow mutation |
| Cases (sequential) | **L1 ensure:** "이마트몰 장바구니에 서울우유 1L 하나 담아줘". **L2 add:** "그 우유 하나 더 담아줘". **L3 set:** "그 우유 1개로 맞춰줘". **L4 cleanup:** "그 우유 장바구니에서 빼줘" |
| Permitted effects | Add, change quantity or remove **that one product line** only. No checkout and no payment (the host refuses it anyway). No other line may change |
| Caps | At most 4 Works; each Work within the existing `WorkBudget` (9 model turns, 40 tool attempts, 600 s); total wall clock 30 min |
| Stop condition | The first false completion, any unrequested cart effect, a sign-in prompt, or a usage limit. Stop, report, do not retry automatically |
| Cleanup | L4. If L4 does not leave the line removed, the owner removes it by hand and the result is reported as a failure |
| Decision use | Pass/fail per case with the cart read-back reference. A run either supports or does not support the claim "the method is followed on the real site for these 3 quantity modes", nothing broader |

## 5. What may be claimed now

- **Structural:** skill supply, pinning, revocation, route parity, the off path, management content and the shopping/site packages behave as specified on fixtures and through a real bridge process. One live public GitHub install also worked (#971).
- **Not claimed:**
  - real-site cart success rates;
  - model adherence to the method;
  - transcript quality;
  - token or time savings;
  - any "frontier" advantage.

  Those wait for section 4 or later approved samples.
