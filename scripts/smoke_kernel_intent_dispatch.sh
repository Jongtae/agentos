#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$(mktemp -d)"
trap 'rm -rf "$WORKSPACE"' EXIT

PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" "$ROOT_DIR/scripts/kernel_intent_dispatch.py" \
  --workspace "$WORKSPACE" \
  --source telegram \
  --message hi \
  --chat-id 1001 \
  --json >"$WORKSPACE/intent.json"

python3 - "$WORKSPACE/intent.json" "$WORKSPACE/artifacts/os_events.jsonl" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-intent-dispatch.v1"
assert payload["intent"] == "greeting"
assert payload["web_search_used"] is False
assert payload["proof"]["ok"] is True
events = Path(sys.argv[2]).read_text()
assert "telegram.message_received" in events
assert "intent.classified" in events
assert "Replied without web search" in events
PY

echo "smoke_kernel_intent_dispatch: PASS"
