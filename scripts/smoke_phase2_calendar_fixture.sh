#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

FIXTURE="$TMP_DIR/calendar-fixture.json"
cat >"$FIXTURE" <<'JSON'
{
  "events": [
    {
      "id": "cal-1",
      "title": "AgentOS roadmap review",
      "start": "2026-06-16T09:00:00+09:00",
      "end": "2026-06-16T09:30:00+09:00",
      "location": "local VM",
      "description": "Review Phase 2 closeout and choose the next completion track.",
      "attendees": ["operator@example.com"]
    },
    {
      "id": "cal-2",
      "title": "Unrelated focus block",
      "start": "2026-06-16T11:00:00+09:00",
      "end": "2026-06-16T12:00:00+09:00",
      "description": "Deep work.",
      "attendees": []
    }
  ]
}
JSON

OUT="$TMP_DIR/calendar-result.json"
PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 scripts/kernel_phase2_calendar_fixture.py \
  --fixture "$FIXTURE" \
  --query roadmap \
  --action summarize \
  --json >"$OUT"

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-phase2-calendar-fixture.v1", payload
assert payload["adapter"] == "calendar_fixture", payload
assert payload["real_calendar_credentials_used"] is False, payload
assert payload["matched_count"] == 1, payload
assert payload["events"][0]["id"] == "cal-1", payload
assert payload["proof"]["ok"] is True, payload
assert payload["proof"]["read_only"] is True, payload
assert payload["proof"]["mutation_executed"] is False, payload
assert "delete" in payload["blocked_actions"], payload
PY

set +e
PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 scripts/kernel_phase2_calendar_fixture.py \
  --fixture "$FIXTURE" \
  --query roadmap \
  --action delete \
  --json >"$TMP_DIR/calendar-blocked.json"
RC=$?
set -e
if [ "$RC" -ne 0 ]; then
  echo "calendar fixture blocked action should still return a safe fixture payload"
  exit 1
fi
python3 - "$TMP_DIR/calendar-blocked.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["proof"]["ok"] is False, payload
assert payload["proof"]["blocker"] == "calendar_delete_requires_confirmation", payload
assert payload["proof"]["mutation_executed"] is False, payload
PY

echo "phase2 calendar fixture smoke: PASS"
