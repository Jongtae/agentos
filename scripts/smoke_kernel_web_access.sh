#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"

OUT_JSON="$TMP_DIR/web.json"
python3 "$ROOT_DIR/scripts/kernel_web_access.py" \
  --workspace "$WORKSPACE" \
  --url https://example.com \
  --compatibility-required \
  --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json, sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-web-access.v1"
assert payload["escalated_handled"] is True
assert payload["escalation_reason"] == "compatibility_required"
assert Path(payload["artifacts"]["latest_web_access_manifest_json"]).exists()
print("kernel web access smoke: PASS")
PY
