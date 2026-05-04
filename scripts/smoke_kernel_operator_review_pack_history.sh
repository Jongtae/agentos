#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$TMP_DIR/pack-1.json" <<'JSON'
{"schema_version":"agentos-operator-review-pack.v1","generated_at_utc":"2026-04-13T00:00:00Z","workspace":"/tmp/ws","summary":{"session_phase":"setup_session","approval_forensic_status":"pending","validation_stable":false,"control_categories":["bridge"]}}
JSON

cat > "$TMP_DIR/pack-2.json" <<'JSON'
{"schema_version":"agentos-operator-review-pack.v1","generated_at_utc":"2026-04-14T00:00:00Z","workspace":"/tmp/ws","summary":{"session_phase":"ai_shell","approval_forensic_status":"quiet","validation_stable":true,"control_categories":["bridge","operator_control"]}}
JSON

OUT_JSON="$TMP_DIR/review-pack-history.json"
python3 scripts/kernel_operator_review_pack_history.py --history-dir "$TMP_DIR" --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("schema_version") != "agentos-operator-review-pack-history.v1":
    raise SystemExit("expected review pack history schema")
summary = payload.get("summary", {})
if int(summary.get("review_pack_count", 0)) != 2:
    raise SystemExit("expected review_pack_count=2")
if summary.get("stable") is not False:
    raise SystemExit("expected stable=false")
if "session_phase" not in summary.get("changed_fields", []):
    raise SystemExit("expected session_phase drift")
print("kernel operator review pack history smoke: PASS")
PY
