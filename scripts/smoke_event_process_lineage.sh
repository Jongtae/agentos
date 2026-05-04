#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"

WORKSPACE="$WORKSPACE" PYTHONPATH="$ROOT_DIR/src" python3 - <<'PY'
import os
from pathlib import Path

from kernel.event_fabric.collectors import ProcessSnapshot, append_events_jsonl, process_exec_exit_events

workspace = Path(os.environ["WORKSPACE"])
events = process_exec_exit_events(
    {10: ProcessSnapshot(pid=10, ppid=1, comm="root", exe="/sbin/init")},
    {
        11: ProcessSnapshot(pid=11, ppid=1, comm="bash", exe="/bin/bash"),
        12: ProcessSnapshot(pid=12, ppid=11, comm="python3", exe="/usr/bin/python3"),
    },
    correlation={"request_id": "req-lineage"},
)
append_events_jsonl(workspace / "artifacts" / "os_events.jsonl", events)
PY

OUT_JSON="$TMP_DIR/lineage.json"
scripts/agentos-kernelctl events \
  --workspace "$WORKSPACE" \
  --lineage \
  --correlation-key request_id \
  --correlation-value req-lineage \
  --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("matched_process_events") != 3:
    raise SystemExit("expected three matched process events")
nodes = {node["pid"]: node for node in payload.get("nodes", [])}
if payload.get("root_pids") != [11]:
    raise SystemExit(f"unexpected root set: {payload.get('root_pids')}")
if nodes.get(11, {}).get("children") != [12]:
    raise SystemExit("expected pid 11 to own pid 12 as child")
if nodes.get(12, {}).get("ppid") != 11:
    raise SystemExit("expected pid 12 parent to be 11")
PY

echo "event process lineage smoke: PASS"
