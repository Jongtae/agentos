#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

BUNDLE_A="$TMP_DIR/review-bundle-a"
BUNDLE_B="$TMP_DIR/review-bundle-b"
mkdir -p "$BUNDLE_A" "$BUNDLE_B"

cat > "$BUNDLE_A/bundle-manifest.json" <<'JSON'
{"schema_version":"agentos-operator-review-bundle.v1","generated_at_utc":"2026-04-13T00:00:00Z","workspace":"/tmp/ws","snapshot_label":"a","summary":{"session_phase":"setup_session","approval_forensic_status":"pending","validation_stable":false}}
JSON
echo '{}' > "$BUNDLE_A/review-pack.json"
echo '# a' > "$BUNDLE_A/review-packet.md"

cat > "$BUNDLE_B/bundle-manifest.json" <<'JSON'
{"schema_version":"agentos-operator-review-bundle.v1","generated_at_utc":"2026-04-14T00:00:00Z","workspace":"/tmp/ws","snapshot_label":"b","summary":{"session_phase":"ai_shell","approval_forensic_status":"quiet","validation_stable":true}}
JSON
echo '{}' > "$BUNDLE_B/review-pack.json"
echo '# b' > "$BUNDLE_B/review-packet.md"

OUT_JSON="$TMP_DIR/review-bundle-history.json"
python3 scripts/kernel_operator_review_bundle_history.py --history-dir "$TMP_DIR" --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("schema_version") != "agentos-operator-review-bundle-history.v1":
    raise SystemExit("expected review bundle history schema")
summary = payload.get("summary", {})
if int(summary.get("review_bundle_count", 0)) != 2:
    raise SystemExit("expected review_bundle_count=2")
if summary.get("stable") is not False:
    raise SystemExit("expected stable=false")
if "session_phase" not in summary.get("changed_fields", []):
    raise SystemExit("expected session_phase drift")
print("kernel operator review bundle history smoke: PASS")
PY
