#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

GOOD="$TMP_DIR/good.jsonl"
BAD="$TMP_DIR/bad.jsonl"

cat > "$GOOD" <<'EOS'
{"timestamp_utc":"2026-01-01T00:00:00Z","event":"run_start","payload":{}}
{"timestamp_utc":"2026-01-01T00:00:01Z","event":"plan_generated","payload":{"steps":1}}
{"timestamp_utc":"2026-01-01T00:00:02Z","event":"run_end","payload":{"result_count":1}}
EOS

cat > "$BAD" <<'EOS'
{"timestamp_utc":"2026-01-01T00:00:02Z","event":"run_end","payload":{}}
{"timestamp_utc":"2026-01-01T00:00:01Z","event":"run_start","payload":{}}
EOS

python3 scripts/validate_runtime_trace.py "$GOOD" >/dev/null
if python3 scripts/validate_runtime_trace.py "$BAD" >/dev/null 2>&1; then
  echo "trace validator smoke: expected bad fixture failure"
  exit 1
fi

echo "runtime trace validator smoke: PASS"
