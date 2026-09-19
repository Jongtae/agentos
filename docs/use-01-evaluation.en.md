# USE-01 evaluation evidence

This file records the executable development boundary for USE-01. The frozen rubric is `evals/owner-usefulness-rubric-v0.1.json`; synthetic material is in `evals/use01-fixtures.json`. The runner executes all 24 seed cases with three isolated fixture trials (72 rows), reports every row, and keeps held-out paraphrases in the rubric rather than in runtime prompts.

## Reproducible commands

```sh
python3 scripts/evaluate_use01.py --mode deterministic --label candidate --json
python3 scripts/evaluate_use01.py --mode live --label owner-authorized-live --json
```

The deterministic command exercises the bounded public reader and managed file workspace with synthetic pages/files. It is state/security and artifact-boundary evidence, not model-quality evidence. The live command intentionally reports `live_quality: not_run/pending_owner_operation` until the owner supplies an explicit provider/model, destination allowlist, data classification, request/token or cost ceiling and timeout.

## Current observed run

The evaluator executes 24 cases × 3 trials = 72 rows and retains every result. The current deterministic run is 72 passed / 0 failed. This includes restart/reuse, corrected artifact constraints, revoked reads, interrupted-work recovery, provider-bound approval invalidation, latest-intent no-tool behavior, redacted receipts and owner-authorized superseding memory. The held-out paraphrase inventory is 3. This proves only the implemented fixture boundary. It does not prove a live provider, browser behavior, inventory, payable total, production safety or natural-language model quality.

The mandatory repository validation observed 344 pytest tests with 232 subtests, 309 unittest tests, canonical-document/source-layout/AgentPackage checks, root/package delivery-plan equality, ledger JSON parsing and `git diff --check` successfully. Live provider quality, real browser observation and owner acceptance remain pending and are reported separately.

## Owner live procedure

1. Configure one selected provider/model in the local settings UI; do not paste credentials into a report or repository.
2. Declare the exact provider destination, data class, allowed public URLs, request/token or cost ceiling and timeout. Keep local document sharing disabled unless the owner explicitly approves that exact destination and scope.
3. Run the evaluator in a clean state with the selected configuration and save the redacted JSON report outside the repository if it contains private evidence.
4. Repeat each case three times, retain first-attempt and repeat outcomes, latency/usage/cost only when observed, and report failures plus denominator.
5. Separately exercise the browser UI against a simulated provider. HTTP fixture results must not be described as browser observations.

No live credentials, paid request, login, OAuth, cart, booking, message or payment action was performed for the development evidence above.
