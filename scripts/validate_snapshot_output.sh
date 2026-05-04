#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/src"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE_DIR="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE_DIR"

FAKE_CODEX="$TMP_DIR/fake-codex.sh"
cat > "$FAKE_CODEX" <<'EOF'
#!/bin/sh
set -eu

out_file=""
prompt=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --output-last-message)
      shift
      out_file="$1"
      ;;
    *)
      prompt="$1"
      ;;
  esac
  shift
done

if printf "%s" "$prompt" | grep -q "Reply with exactly: HEALTH_OK"; then
  msg="HEALTH_OK"
else
  msg="{}"
fi

if [ -n "$out_file" ]; then
  printf "%s" "$msg" > "$out_file"
fi
printf "%s\n" "$msg"
EOF
chmod +x "$FAKE_CODEX"

cat > "$WORKSPACE_DIR/spec.yaml" <<EOF
name: "snapshot-validate"
ai_model:
  provider: "openai"
  model: "gpt-4o-mini"
kernel_engine:
  provider: "codex"
  mode: "single"
  codex:
    command: "$FAKE_CODEX"
    timeout_sec: 10
    model: ""
tools:
  bash: true
  file: true
  web: true
permissions:
  require_approval: true
memory:
  checkpointer: "sqlite"
  db_path: "./data/session.sqlite"
  store_path: "./data/memory.sqlite"
runtime:
  max_steps: 12
  max_message_window: 20
  workspace_root: "./"
EOF

SNAPSHOT_FILE="$TMP_DIR/snapshot.json"
OPENAI_API_KEY=dummy PYTHONPATH=src python3 src/main.py --snapshot --workspace "$WORKSPACE_DIR" > "$SNAPSHOT_FILE"

python3 - "$SNAPSHOT_FILE" <<'PY'
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
obj = json.loads(p.read_text(encoding="utf-8"))
required = ["timestamp_utc", "app_version", "workspace", "ok", "exit_code", "doctor", "status", "browser_runtime", "approval_counters"]
missing = [k for k in required if k not in obj]
if missing:
    raise SystemExit(f"missing keys: {missing}")

git_required = ["is_repo", "root", "branch", "commit", "dirty"]
if "git" not in obj or not isinstance(obj["git"], dict):
    raise SystemExit("missing git object")
git_missing = [k for k in git_required if k not in obj["git"]]
if git_missing:
    raise SystemExit(f"missing git keys: {git_missing}")

if not obj["ok"]:
    raise SystemExit("snapshot ok=false unexpectedly")

for nested in ["doctor", "status"]:
    if not isinstance(obj[nested], dict):
        raise SystemExit(f"{nested} is not an object")
if not isinstance(obj["browser_runtime"], dict):
    raise SystemExit("browser_runtime is not an object")
if not isinstance(obj["approval_counters"], dict):
    raise SystemExit("approval_counters is not an object")

print("snapshot schema validation: PASS")
PY
