# USE-01 goal readiness

## State and authority

[USE-01 / #358](https://github.com/Jongtae/personal-agentos/issues/358) is the owner's selected next product goal. This preparation belongs to GOV-USE-01 / #357 and becomes authoritative only after PR #361 merges with required validation and independent review. It does not start implementation. The delivery-plan entry and `next_goal.status` are `owner-activated-goal-ready`, never `active`; the existing heartbeat must return no work. A later explicit owner Goal-mode invocation is the execution delegation. Do not create a second automation or race it with Goal mode.

Predecessors: completed DOGFOOD-01 #351 and merged GOV-USE-01 #357. D-AP-01 #334 remains schema/fixture evidence. USE-01 does not depend on a public Marketplace, Ruflo, OBS-01 #359 or completing the entire distribution epic. #335–#346, #359 and #360 remain inactive.

Read current main, #358, the USE-01 plan entry, [AGENTS](../AGENTS.md), [Development Constitution](development-constitution.en.md), [Goal Execution Contract](goal-execution-contract.en.md), [Owner Control](owner-control-contract.en.md), [Default Agent Usefulness](default-agent-usefulness.en.md), [evaluation seed](../evals/owner-usefulness-v0.1.json) and relevant existing file/provider contracts. The stricter authority/evidence boundary prevails on conflict. No broad historical re-audit without a concrete dependency.

## Outcome and allowed work

Make the actual default assistant useful for public research to a decision-ready brief, approved documents to substantive ordinary-file artifacts, and follow-up correction/restart/reuse. Preserve owner state, originals, managed writes, current Grants, source provenance and external-transmission policy. Natural Korean/English paraphrases must work; no hard-coded event or magic phrase demonstration.

After explicit invocation, work on `codex/358-useful-default-assistant`, not main. Limit product changes to the existing native tool loop/provider/file/work paths, bounded public-page reading, necessary owner browser UX, evaluation/tests and operating guidance. Implement the exact public-reader security contract before any public access: permitted HTTP(S), DNS/address and redirect/rebinding checks, no credentials or private/loopback/link-local/metadata destinations, bounded response/decompression/time, hostile content as data and no private-query leaks. Test transports must not weaken production denial. No shell, cookies carrying identity, authenticated browsing, JS automation or access-control bypass.

## Ordered work units

1. Map requirements and build the minimum runnable evaluator/source/file fixtures and graders **before** measuring a baseline. Freeze/version the rubric before tuning.
2. Run the credential-free baseline through the real application boundary. Record every failure/unsupported case. Add opt-in live mode with explicit provider, destinations, data classification, request/token or cost ceiling and timeout. Existing credentials are not authorization.
3. Implement bounded public-page reading and security-negative tests; snippets do not prove full-page reading, inventory or payable totals.
4. Improve source-grounded research/comparison/briefs, exact dates/timezones/numbers/currencies/fees, decision-critical clarification, uncertainty and approved output saving.
5. Improve real multi-document artifacts, natural paraphrases, correction/topic change and restart/reuse. Preserve file/privacy guards and invalidate non-covering approvals after parameter/scope changes.
6. Execute all 24 cases with three clean-state trials in the declared mode, plus held-out paraphrases inaccessible to runtime code. Grade actual artifacts/state/source support and calibrated human-quality criteria; report all outcomes and denominators.
7. Exercise the real browser with a simulated provider where tooling permits; provide exact install/run/first-task/restart and separately authorized live-owner procedures. HTTP-only evidence must not be called a browser observation.
8. Independent security and utility/convergence review (UI review when affected), full validation, PR merge, main validation and tracker/ledger/issue closeout. Stop without selecting a successor.

## Development versus live-quality gates

All in-scope deterministic implementation/state/security checks and useful positive cases must pass before development closeout. Static seed tests are not an executed evaluator; simulated model replies do not establish real model quality. Correct abstention can pass only where the case expects it; labelling everything unknown cannot pass a task requiring supported facts.

The initial **live-quality promotion target**, not a measured result, is at least 20 of 24 successful trials in each eight-case family at three trials/case. Report first-attempt and repeat consistency, not best-of-three. Any unauthorized effect or private/secret leak in declared negative tests blocks promotion. Report measured latency, owner interventions and available model/usage/cost data; unknown remains unknown. Do not silently change the rubric to manufacture success.

Without explicitly authorized live credentials/scope/budget, record `live_quality: not_run/pending_owner_operation`. Finish safe development and provide a runnable owner command, but do not advertise measured usefulness, production safety, competitor parity or live deployment. Development completion and live promotion are distinct records; a routine owner live test is not an endless development blocker. A strong-model profile is measured or explicitly unvalidated, never invented.

## Validation

Run the existing mandatory commands:

```sh
python3 scripts/verify_master_plan_docs.py
python3 scripts/verify_src_layout.py
cmp -s delivery-plan.yaml src/personal_agent/delivery-plan.yaml
python3 scripts/verify_agentpackage_v01.py
python3 -m pytest -q tests
python3 -m unittest discover -s tests -q
git diff --check
```

Also parse each nonempty ledger line as JSON. Add targeted reader/egress/authority, file/restart and browser tests plus the evaluator's exact command when implemented. Never claim an uncreated command ran. Do not weaken existing verifiers; replace obsolete assumptions only with demonstrated equivalent safety coverage.

## Review, completion and stop

Primary implementer plus independent security and utility/convergence reviewers; add specialized review only when relevant. Exclusive file ownership for parallel writers. Record requested/accepted/observed model and reasoning truthfully. Self-review is not independent review.

Development completes only when every #358 development criterion maps to merged evidence, required CI and main validation pass, no blocking review remains, and TASKS/roadmap/ledger/#358 closeout match the evidence class. Report remaining live-quality/owner actions separately. No successors are activated.

No cart/hold/checkout mutation, booking/payment, message sending, account creation/login/OAuth, personal-data scope expansion, arbitrary browser/shell, new always-on service, package install, Marketplace, Ruflo or other issue implementation. No private screenshots/transcripts in public evidence. For a genuine external tool/permission blocker preserve state and follow the Goal Execution Contract; do not abandon safe remaining work.

Progress: concise English material updates. Final owner summary: Korean, with actual artifacts/checks, limits and exact manual operating steps.
