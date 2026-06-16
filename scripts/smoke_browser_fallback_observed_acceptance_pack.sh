#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

CONTRACT="$TMP_DIR/browser-contract.json"
python3 scripts/kernel_phase2_browser_fallback_contract.py \
  --workspace "$TMP_DIR/workspace" \
  --url https://example.com/app \
  --allow-domain example.com \
  --interactive \
  --json >"$CONTRACT"

BLOCKED_OUT="$TMP_DIR/acceptance-blocked.json"
python3 scripts/kernel_browser_fallback_observed_acceptance.py \
  --workspace "$TMP_DIR/workspace" \
  --contract-json "$CONTRACT" \
  --target-url https://example.com/app \
  --output "$BLOCKED_OUT"
python3 scripts/kernel_browser_fallback_observed_acceptance.py --validate "$BLOCKED_OUT" --json >/dev/null

python3 - "$BLOCKED_OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-browser-fallback-observed-acceptance.v1", payload
assert payload["proof"]["manual_acceptance_pack_completed"] is True, payload
assert payload["proof"]["live_browser_fallback_completed"] is False, payload
assert payload["proof"]["browser_mutation_executed"] is False, payload
assert payload["proof"]["browser_is_default"] is False, payload
assert payload["proof"]["contract_only_without_observed"] is True, payload
assert payload["blockers"][0]["id"] == "browser-fallback-observed-proof-not-attached", payload
PY

OBSERVED="$TMP_DIR/observed-browser-proof.json"
cat >"$OBSERVED" <<'JSON'
{
  "schema_version": "agentos-observed-proof-intake.v1",
  "proof_surface": "browser fallback",
  "claim": "User-approved browser fallback to https://example.com/app was observed without mutation",
  "status": "observed",
  "observed_by": "manual tester",
  "observed_at_utc": "2026-06-16T00:00:00Z",
  "evidence": [
    {
      "kind": "sanitized_log",
      "path_or_url": "manual-observed-browser-fallback.log",
      "redaction": "Target URL and result only; no credentials, cookies, tokens, or page secrets retained."
    }
  ],
  "remaining_non_claims": [
    "Browser automation is not the default AgentOS runtime path.",
    "Authenticated sites, form submission, destructive actions, and broad browser replacement remain unclaimed."
  ],
  "blockers": []
}
JSON

python3 scripts/observed_proof_intake_validate.py "$OBSERVED" --json >/dev/null

OBSERVED_OUT="$TMP_DIR/acceptance-observed.json"
python3 scripts/kernel_browser_fallback_observed_acceptance.py \
  --workspace "$TMP_DIR/workspace" \
  --contract-json "$CONTRACT" \
  --observed-proof-json "$OBSERVED" \
  --target-url https://example.com/app \
  --output "$OBSERVED_OUT"
python3 scripts/kernel_browser_fallback_observed_acceptance.py --validate "$OBSERVED_OUT" --require-observed --json >/dev/null

python3 - "$OBSERVED_OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["proof"]["live_browser_fallback_completed"] is True, payload
assert payload["proof"]["contract_only_without_observed"] is False, payload
assert payload["proof"]["browser_is_default"] is False, payload
assert payload["proof"]["secrets_redacted"] is True, payload
assert payload["blockers"] == [], payload
PY

grep -q "browser fallback observed proof acceptance" docs/acceptance/browser-fallback-observed-acceptance.md
grep -q "browser fallback observed proof acceptance epic is closed" TASKS.md
grep -q "browser-fallback-observed-proof-acceptance-epic" docs/next-roadmap.md
grep -q "docs/acceptance/browser-fallback-observed-acceptance.md" docs/index.md

echo "browser fallback observed acceptance pack smoke: PASS"
