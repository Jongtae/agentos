#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE_DIR="$TMP_DIR/workspace"
ARTIFACTS_DIR="$WORKSPACE_DIR/artifacts"
mkdir -p "$ARTIFACTS_DIR"

TRACE_FILE="$ARTIFACTS_DIR/runtime_trace.jsonl"
ARCHIVE_1="$ARTIFACTS_DIR/runtime_trace.jsonl.1"
ARCHIVE_2="$ARTIFACTS_DIR/runtime_trace.jsonl.2"

printf "{}\n" > "$TRACE_FILE"
printf "a1\n" > "$ARCHIVE_1"
printf "a2\n" > "$ARCHIVE_2"

python3 - "$ARCHIVE_1" "$ARCHIVE_2" <<'PY'
import os
import sys
import time

recent = time.time()
old = recent - (10 * 24 * 3600)
os.utime(sys.argv[1], (recent, recent))
os.utime(sys.argv[2], (old, old))
PY

DRY_JSON="$(python3 scripts/runtime_trace_retention.py --workspace "$WORKSPACE_DIR" --retention-days 7 --keep-archives 1 --dry-run)"
python3 - "$DRY_JSON" "$ARCHIVE_2" <<'PY'
import json
import os
import sys

obj = json.loads(sys.argv[1])
if obj.get("mode") != "dry-run":
    raise SystemExit("dry-run mode mismatch")
if int(obj.get("summary", {}).get("deleted", -1)) != 0:
    raise SystemExit("dry-run must not delete files")

target_name = os.path.basename(sys.argv[2])
action_names = [os.path.basename(a.get("path", "")) for a in obj.get("actions", [])]
if target_name not in action_names:
    raise SystemExit("expected archive candidate not found in dry-run actions")
PY

if [ ! -f "$ARCHIVE_2" ]; then
  echo "archive unexpectedly deleted during dry-run"
  exit 1
fi

APPLY_JSON="$(python3 scripts/runtime_trace_retention.py --workspace "$WORKSPACE_DIR" --retention-days 7 --keep-archives 1 --apply)"
python3 - "$APPLY_JSON" <<'PY'
import json
import sys

obj = json.loads(sys.argv[1])
if obj.get("mode") != "apply":
    raise SystemExit("apply mode mismatch")
if int(obj.get("summary", {}).get("deleted", -1)) < 1:
    raise SystemExit("apply mode expected at least one deletion")
PY

if [ -f "$ARCHIVE_2" ]; then
  echo "archive was not deleted in apply mode"
  exit 1
fi

echo "runtime trace retention smoke: PASS"
