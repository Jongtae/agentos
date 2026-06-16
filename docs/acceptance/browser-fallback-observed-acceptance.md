# Browser Fallback Observed Acceptance

Status: Phase 2 active browser fallback observed proof acceptance pack

Browser automation is still a fallback path, not the default AgentOS runtime
interface. This acceptance pack defines how a future user-approved browser
fallback run can be recorded as observed proof without making unobserved local
smokes claim live browser execution.

## Proof Boundary

`scripts/kernel_browser_fallback_observed_acceptance.py` exports
`agentos-browser-fallback-observed-acceptance.v1`.

The pack combines:

- a browser fallback routing contract from
  `agentos-phase2-browser-fallback-contract.v1`
- an optional sanitized `agentos-observed-proof-intake.v1` record
- explicit blockers when no observed browser proof has been attached

Without a sanitized observed proof record, the pack remains useful but blocked.
It must report `live_browser_fallback_completed=false`,
`browser_mutation_executed=false`, `browser_is_default=false`, and
`contract_only_without_observed=true`.

## Manual Commands

```bash
python3 scripts/kernel_phase2_browser_fallback_contract.py \
  --workspace <workspace> \
  --url <url> \
  --allow-domain <domain> \
  --interactive \
  --json > browser-contract.json

python3 scripts/observed_proof_intake_validate.py observed-browser-proof.json --json

python3 scripts/kernel_browser_fallback_observed_acceptance.py \
  --contract-json browser-contract.json \
  --observed-proof-json observed-browser-proof.json \
  --target-url <url> \
  --json
```

The observed proof record must contain only sanitized evidence. Cookies,
session tokens, credentials, page secrets, and destructive browser actions stay
outside repo, workspace, and build artifacts.

## Acceptance

The focused smoke is:

```bash
scripts/smoke_browser_fallback_observed_acceptance_pack.sh
```

The smoke covers both:

- blocked/no-observed proof, which keeps live browser proof unclaimed
- synthetic observed proof, which proves the acceptance pack can validate a
  sanitized user-approved browser fallback record

## Exit Condition

This slice is complete when the acceptance script, smoke, documentation, golden
runner coverage, and roadmap state make observed browser fallback proof
attachable while preserving these non-claims:

- browser automation is not the default runtime path
- authenticated sites, mutations, broad browser replacement, and external app
  dependence remain unclaimed until separate observed proof exists
- repeated browser fallback patterns should graduate into internal AgentOS
  capabilities before browser mediation expands
