#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_ROOT="$(mktemp -d /tmp/agentos-public-preview-messaging-XXXXXX)"
trap 'rm -rf "$TMP_ROOT"' EXIT

WORKSPACE="$TMP_ROOT/w"
REPORT_DIR="$TMP_ROOT/r"
mkdir -p "$WORKSPACE"

OUTPUT_JSON="$TMP_ROOT/public-preview-messaging-review.json"
PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR/scripts" python3 "$ROOT_DIR/scripts/kernel_public_preview_messaging_review.py" \
  --workspace "$WORKSPACE" \
  --report-dir "$REPORT_DIR" \
  --snapshot-label c \
  --output "$OUTPUT_JSON" \
  --json >/dev/null

PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR/scripts" python3 - "$OUTPUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["schema_version"] == "agentos-public-preview-messaging-review.v1"
assert payload["summary"]["review_state"] in {"aligned", "needs_review"}
print("kernel public preview messaging review smoke: PASS")
PY
