#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$(mktemp -d)"
trap 'rm -rf "$WORKSPACE"' EXIT

PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" "$ROOT_DIR/scripts/kernel_intent_dispatch.py" \
  --workspace "$WORKSPACE" \
  --source operator \
  --message "workspace file list" \
  --json >/dev/null

PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" "$ROOT_DIR/scripts/kernel_activity_feed.py" \
  --workspace "$WORKSPACE" \
  --limit 10 \
  --json >"$WORKSPACE/activity.json"

python3 - "$WORKSPACE/activity.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-operator-activity-feed.v1"
assert payload["activity_feed_ready"] is True
assert payload["event_count"] >= 3
messages = [event["human_message"] for event in payload["events"]]
assert any("Operator received" in message for message in messages)
assert any("Understood as: local_workspace_search" in message for message in messages)
PY

echo "smoke_kernel_activity_feed: PASS"
