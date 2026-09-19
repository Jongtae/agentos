# USE-01 evaluation evidence

This file records the executable development boundary for USE-01. The frozen rubric is `evals/owner-usefulness-rubric-v0.1.json`; synthetic material is in `evals/use01-fixtures.json`. The runner executes all 24 seed cases with three isolated fixture trials (72 rows), reports every row, and keeps held-out paraphrases in the rubric rather than in runtime prompts.

## Reproducible commands

```sh
python3 scripts/evaluate_use01.py --mode deterministic --label candidate --json
python3 scripts/evaluate_use01.py --mode live --label owner-authorized-live --json
```

The deterministic command drives `AgentService.run_one` with a scripted test provider that responds to returned native-tool evidence. It is service-path state/security and artifact-boundary evidence, not model-quality evidence. The live command has an explicit authorization configuration and bounded transport gate; without all owner-supplied provider/model, destination allowlist, data classification, budget, timeout and `--execute-live`, it reports `implemented_but_unrun/owner_authorization_required` and makes no provider call.

## Current observed run

The evaluator executes 24 cases × 3 clean-state trials = 72 rows and retains every result. The current deterministic service-path run is 72 passed / 0 failed, and all 3 held-out paraphrases are executed and passed. This includes native tool calls, owner-scoped public-page approval and redirect denial, substantive TXT/MD/XLSX artifacts, original preservation, restart/reuse, denied memory persistence, provider-bound approval invalidation and latest-intent behavior. This proves only the implemented synthetic service boundary. It does not prove a live provider, browser behavior, inventory, payable total, production safety or natural-language model quality.

The mandatory repository validation must be rerun on the final PR head and record the observed pytest/unittest counts there. Canonical-document/source-layout/AgentPackage checks, root/package delivery-plan equality, ledger JSON parsing and `git diff --check` remain required. Live provider quality, real browser observation and owner acceptance remain pending and are reported separately.

## Owner live procedure

1. Configure one selected provider/model in the local settings UI; do not paste credentials into a report or repository.
2. Declare the exact provider destination, data class, allowed public URLs, request/token or cost ceiling and timeout. Keep local document sharing disabled unless the owner explicitly approves that exact destination and scope. For the runner, pass the same values to `--provider`, `--endpoint`, `--model`, one or more `--destination`, `--data-class`, `--budget`, and `--timeout`; omit `--execute-live` for a configuration-only dry run.
3. After separately authorizing execution, set the API key through an environment reference (never in the command or report) and add `--execute-live`. The bounded transport enforces the declared deadline, destination scope and maximum request count; stop and report if the provider does not expose a trustworthy cost boundary.
4. Repeat each case three times, retain first-attempt and repeat outcomes, latency/usage/cost only when observed, and report failures plus denominator.
5. Separately exercise the browser UI against a simulated provider. HTTP fixture results must not be described as browser observations.

No live credentials, paid request, login, OAuth, cart, booking, message or payment action was performed for the development evidence above.
