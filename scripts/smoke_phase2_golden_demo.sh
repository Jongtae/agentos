#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

OUT="$TMP_DIR/golden-demo.json"
PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 scripts/phase2_golden_demo_runner.py --output "$OUT"

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-phase2-golden-demo.v1"
assert payload["practical_smoke_count"] >= 10
assert payload["practical_smokes_passed"] == payload["practical_smoke_count"], payload
assert payload["proof"]["docker_local_smoke_completed"] is True
assert payload["proof"]["gmail_oauth_live_completed"] is False
assert payload["proof"]["vm_iso_proof_completed"] is False
smoke_names = {result["name"] for result in payload["results"]}
assert "scripts/smoke_release_manifest_checksum_preflight.sh" in smoke_names
blocker_ids = {blocker["id"] for blocker in payload["explicit_blockers"]}
assert {"gmail-oauth-live", "vm-iso-proof"} <= blocker_ids
PY

echo "phase2 golden demo smoke: PASS"
