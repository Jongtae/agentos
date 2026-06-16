#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

OUT="$TMP_DIR/result.json"
PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 scripts/kernel_phase2_capability_result.py \
  --workspace "$TMP_DIR/workspace" \
  --intent status \
  --capability runtime_status \
  --status ok \
  --output "Runtime ready" \
  --json >"$OUT"

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-phase2-capability-result.v1"
assert payload["status"] == "ok"
assert payload["permission"]["level"] == "safe_read"
assert payload["outcome"] == "completed"
assert payload["activity_state"] == "completed"
assert payload["record"]["durable"] is True
assert Path(payload["record"]["path"]).exists()
assert payload["record"]["includes_permission"] is True
assert payload["record"]["secrets_included"] is False
assert payload["recovery"]["required"] is False
assert payload["proof"]["permission_checked"] is True
assert payload["proof"]["outcome_checked"] is True
assert payload["proof"]["secrets_redacted"] is True
PY

BLOCKED_SETUP="$TMP_DIR/blocked-setup.json"
PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 scripts/kernel_phase2_capability_result.py \
  --workspace "$TMP_DIR/workspace" \
  --intent gmail_read_or_draft \
  --capability gmail_read \
  --status blocked \
  --requires-setup \
  --output "Gmail setup required" \
  --json >"$BLOCKED_SETUP"

python3 - "$BLOCKED_SETUP" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["permission"]["level"] == "external_read"
assert payload["permission"]["requires_setup"] is True
assert payload["outcome"] == "blocked_needs_setup"
assert payload["record"]["durable"] is False
assert payload["record"]["path"] == ""
assert payload["recovery"]["required"] is True
assert "setup" in payload["recovery"]["reason"]
assert payload["proof"]["blocked"] is True
PY

BLOCKED_UNSUPPORTED="$TMP_DIR/blocked-unsupported.json"
PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 scripts/kernel_phase2_capability_result.py \
  --workspace "$TMP_DIR/workspace" \
  --intent gmail_read_or_draft \
  --capability gmail_send \
  --status blocked \
  --output "Gmail send is blocked" \
  --json >"$BLOCKED_UNSUPPORTED"

python3 - "$BLOCKED_UNSUPPORTED" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["permission"]["level"] == "destructive_blocked"
assert payload["outcome"] == "blocked_unsupported"
assert payload["needs_confirmation"] is False
assert payload["record"]["secrets_included"] is False
assert payload["recovery"]["required"] is True
assert "destructive_blocked" in payload["recovery"]["reason"]
PY

echo "phase2 capability result smoke: PASS"
