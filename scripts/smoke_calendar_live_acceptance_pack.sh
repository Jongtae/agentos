#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$TMP_DIR/status.json" <<'JSON'
{
  "schema_version": "agentos-calendar-readonly-status.v1",
  "current_route": "calendar_fixture",
  "fixture_ready": true,
  "live_oauth_ready": false,
  "mutation_allowed": false,
  "proof": {
    "read_only": true,
    "live_calendar_oauth_completed": false,
    "mutation_executed": false
  }
}
JSON

cat > "$TMP_DIR/read-fixture.json" <<'JSON'
{
  "schema_version": "agentos-phase2-calendar-fixture.v1",
  "adapter": "calendar_fixture",
  "matched_count": 1,
  "events": [{"id": "event-1", "title": "Roadmap"}],
  "proof": {
    "ok": true,
    "blocker": "real_calendar_oauth_not_configured",
    "read_only": true,
    "mutation_executed": false
  }
}
JSON

OUT="$TMP_DIR/acceptance.json"
python3 scripts/kernel_calendar_live_acceptance.py \
  --workspace "$TMP_DIR/workspace" \
  --status-json "$TMP_DIR/status.json" \
  --read-json "$TMP_DIR/read-fixture.json" \
  --query roadmap \
  --output "$OUT"

python3 scripts/kernel_calendar_live_acceptance.py --validate "$OUT" --json >/dev/null

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-calendar-live-acceptance.v1", payload
assert payload["proof"]["manual_acceptance_pack_completed"] is True, payload
assert payload["proof"]["live_calendar_oauth_completed"] is False, payload
assert payload["proof"]["calendar_mutation_executed"] is False, payload
assert payload["validation"]["fixture_or_mock_used"] is True, payload
assert payload["blockers"][0]["id"] == "calendar-live-oauth-proof-not-observed", payload
assert "refresh_token" not in json.dumps(payload, ensure_ascii=True), payload
assert "access_token" not in json.dumps(payload, ensure_ascii=True), payload
PY

cat > "$TMP_DIR/status-live.json" <<'JSON'
{
  "schema_version": "agentos-calendar-readonly-status.v1",
  "current_route": "calendar_oauth_readonly",
  "fixture_ready": true,
  "live_oauth_ready": true,
  "mutation_allowed": false,
  "proof": {
    "read_only": true,
    "live_calendar_oauth_completed": true,
    "mutation_executed": false
  }
}
JSON

cat > "$TMP_DIR/read-live.json" <<'JSON'
{
  "schema_version": "agentos-phase2-calendar-fixture.v1",
  "adapter": "calendar_oauth_readonly",
  "matched_count": 1,
  "events": [{"id": "live-event-1", "title": "Roadmap"}],
  "proof": {
    "ok": true,
    "blocker": "calendar_live_read_ok",
    "read_only": true,
    "mutation_executed": false
  }
}
JSON

LIVE_OUT="$TMP_DIR/acceptance-live.json"
python3 scripts/kernel_calendar_live_acceptance.py \
  --workspace "$TMP_DIR/workspace" \
  --status-json "$TMP_DIR/status-live.json" \
  --read-json "$TMP_DIR/read-live.json" \
  --query roadmap \
  --output "$LIVE_OUT"
python3 scripts/kernel_calendar_live_acceptance.py --validate "$LIVE_OUT" --require-live --json >/dev/null

echo "calendar live acceptance pack smoke: PASS"
