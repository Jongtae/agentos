#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/agentos-browser-fallback.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

run_case() {
  local name="$1"
  shift
  PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR/scripts" python3 "$ROOT_DIR/scripts/kernel_phase2_browser_fallback_contract.py" \
    --workspace "$TMP_DIR/workspace-$name" \
    "$@" \
    --json >"$TMP_DIR/$name.json"
  PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR/scripts" python3 "$ROOT_DIR/scripts/kernel_phase2_browser_fallback_contract.py" \
    --validate "$TMP_DIR/$name.json" \
    --json >"$TMP_DIR/$name.validate.json"
}

run_case native --url https://example.com --allow-domain example.com
run_case fallback --url https://example.com/app --allow-domain example.com --interactive
run_case blocked --url https://blocked.example --allow-domain example.com
run_case graduate --url https://example.com/app --allow-domain example.com --interactive --repeated-pattern

python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

tmp_dir = Path(sys.argv[1])
expected = {
    "native": "internal_capability",
    "fallback": "allowed_browser_fallback",
    "blocked": "blocked_external_state",
    "graduate": "graduate_to_capability",
}
for name, decision in expected.items():
    payload = json.loads((tmp_dir / f"{name}.json").read_text(encoding="utf-8"))
    validation = json.loads((tmp_dir / f"{name}.validate.json").read_text(encoding="utf-8"))
    assert validation["ok"], validation
    assert payload["schema_version"] == "agentos-phase2-browser-fallback-contract.v1"
    assert payload["routing"]["decision"] == decision, payload
    assert payload["routing"]["internal_capability_preferred"] is True
    assert payload["routing"]["browser_is_default"] is False
    assert payload["proof"]["contract_only"] is True
    assert payload["proof"]["live_browser_executed"] is False
    assert payload["proof"]["third_party_auth_used"] is False
    assert Path(payload["artifacts"]["latest_browser_fallback_contract_json"]).exists()

blocked = json.loads((tmp_dir / "blocked.json").read_text(encoding="utf-8"))
assert blocked["blockers"][0]["id"] == "browser-fallback-blocked"
graduate = json.loads((tmp_dir / "graduate.json").read_text(encoding="utf-8"))
assert graduate["graduation"]["candidate"] is True
PY

echo "phase2 browser fallback contract smoke: PASS"
