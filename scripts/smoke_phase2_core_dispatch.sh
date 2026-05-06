#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"
printf 'phase 2 dispatch fixture\n' >"$WORKSPACE/notes.txt"

run_dispatch() {
  local message="$1"
  local output="$2"
  shift 2
  PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 scripts/kernel_intent_dispatch.py \
    --workspace "$WORKSPACE" \
    --source operator \
    --message "$message" \
    --request-id "phase2-core-dispatch-${output}" \
    --json \
    "$@" >"$TMP_DIR/${output}.json"
}

run_dispatch "AgentOS status" status
run_dispatch "list files in this workspace" workspace
run_dispatch "search https://example.com and summarize" web --allow-domain example.com

python3 - "$TMP_DIR" "$WORKSPACE" <<'PY'
import json
import sys
from pathlib import Path

tmp_dir = Path(sys.argv[1])
workspace = Path(sys.argv[2])

expected = {
    "status": ("runtime_status", "runtime_status", False),
    "workspace": ("local_workspace_search", "local_workspace_search", False),
    "web": ("web_search_summary", "research_brief_response", True),
}

for name, (intent, capability, web_used) in expected.items():
    payload = json.loads((tmp_dir / f"{name}.json").read_text())
    assert payload["proof"]["ok"] is True, payload
    assert payload["intent"] == intent, payload
    assert payload["capability_executed"] == capability, payload
    assert payload["web_search_used"] is web_used, payload
    assert payload["activity_events_written"] >= 3, payload
    assert payload["summary"]["capability"] == capability, payload
    assert payload["response"].strip(), payload

activity_path = workspace / "artifacts" / "os_events.jsonl"
events = [json.loads(line) for line in activity_path.read_text().splitlines() if line.strip()]
kinds = {event["kind"] for event in events}
for required in {"operator.request_received", "intent.classified", "capability.started", "capability.completed"}:
    assert required in kinds, kinds
PY

echo "phase2 core dispatch smoke: PASS"
