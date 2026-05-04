#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_ROOT="$(mktemp -d /tmp/agentos-public-preview-launch-XXXXXX)"
trap 'rm -rf "$TMP_ROOT"' EXIT
WORKSPACE="$TMP_ROOT/w"
REPORT_DIR="$TMP_ROOT/r"
mkdir -p "$WORKSPACE"
OUTPUT_JSON="$TMP_ROOT/public-preview-launch-readiness-review.json"
PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR/scripts" python3 "$ROOT_DIR/scripts/kernel_public_preview_launch_readiness_review.py" --workspace "$WORKSPACE" --report-dir "$REPORT_DIR" --snapshot-label c --output "$OUTPUT_JSON" --json >/dev/null
PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR/scripts" python3 - "$OUTPUT_JSON" <<'PY'
import json, sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
assert payload['schema_version'] == 'agentos-public-preview-launch-readiness-review.v1'
assert payload['summary']['launch_readiness'] in {'ready', 'not_ready'}
print('kernel public preview launch readiness review smoke: PASS')
PY
