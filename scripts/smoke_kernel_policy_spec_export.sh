#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"

cat > "$WORKSPACE/spec.yaml" <<'EOF'
name: "kernel-policy-spec-smoke"
ai_model:
  provider: "openai"
  model: "gpt-4o-mini"
kernel_engine:
  provider: "ollama"
  mode: "single"
  codex:
    command: "codex"
    timeout_sec: 10
    model: ""
  ollama:
    command: "ollama"
    timeout_sec: 10
    model: "llama3.1:8b"
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
  max_steps: 4
  max_message_window: 20
  workspace_root: "./"
network:
  browser:
    allowlist:
      - "openai.com"
EOF

OUT_JSON="$TMP_DIR/kernel-policy.json"
scripts/export_kernel_policy_spec.py --workspace "$WORKSPACE" --output "$OUT_JSON" --json > /dev/null

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("schema_version") != "kernel-policy-spec.v1":
    raise SystemExit("unexpected schema_version")

targets = {item.get("id") for item in payload.get("policy_targets", [])}
required = {"fs_workspace_boundary", "network_allowlist", "destructive_action_approval"}
missing = sorted(required - targets)
if missing:
    raise SystemExit(f"missing policy target ids: {missing}")

if payload.get("failure_modes", {}).get("kernel_path_default") != "fail_open":
    raise SystemExit("kernel_path_default should be fail_open")
if payload.get("failure_modes", {}).get("user_space_default") != "fail_closed":
    raise SystemExit("user_space_default should be fail_closed")
PY

echo "kernel policy spec export smoke: PASS"
