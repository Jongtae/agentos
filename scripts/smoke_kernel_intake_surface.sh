#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
ARTIFACTS="$WORKSPACE/artifacts"
mkdir -p "$ARTIFACTS/feedback-intake"

cat > "$ARTIFACTS/os_events.jsonl" <<'JSON'
{"timestamp_utc":"2026-04-19T00:00:00Z","source":"journald","kind":"session.login","actor":{"uid":1000},"object":{"session_id":"agentos:tty1"},"action":"login","decision":{"state":"observed"},"correlation":{"session_id":"agentos:tty1","boot_id":"boot-1"},"raw_ref":{"collector":"journald"}}
JSON

cat > "$ARTIFACTS/feedback-intake/latest-feedback-intake-manifest.json" <<'JSON'
{"generated_at_utc":"2026-04-19T00:00:02Z","feedback_packet":{"channel":"internal_preview","summary":"Looks good.","recommendation":"advance"}}
JSON

OUT_JSON="$TMP_DIR/intake.json"
python3 "$ROOT_DIR/scripts/kernel_intake_surface.py" \
  --workspace "$WORKSPACE" \
  --report-dir "$ARTIFACTS" \
  --session-id agentos:tty1 \
  --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json, sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-intake-surface.v1"
assert payload["summary"]["total_items"] == 2
assert payload["summary"]["native_intake_items"] == 2
assert Path(payload["artifacts"]["latest_intake_surface_manifest_json"]).exists()
print("kernel intake surface smoke: PASS")
PY
