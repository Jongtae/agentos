#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
USER_HOME="$TMP_DIR/home"
mkdir -p "$WORKSPACE" "$USER_HOME/.config/agentos"

cat > "$WORKSPACE/spec.yaml" <<'EOF'
name: "kernel-firstrun-reset-smoke"
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
EOF

cat > "$USER_HOME/.config/agentos/env" <<'EOF'
AGENTOS_PROVIDER="ollama"
EOF

OUT_JSON="$TMP_DIR/reset.json"
"$ROOT_DIR/scripts/agentos-kernelctl" firstrun-reset --workspace "$WORKSPACE" --user-home "$USER_HOME" --json > "$OUT_JSON"

python3 - "$OUT_JSON" "$WORKSPACE/spec.yaml" "$USER_HOME/.config/agentos/env" <<'PY'
import json
import sys
from pathlib import Path
import yaml

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if not payload.get("ok", False):
    raise SystemExit("firstrun-reset expected ok=true")
if payload.get("kernel_engine_provider") != "":
    raise SystemExit("kernel_engine.provider should be reset to empty")
if not payload.get("setup_required", False):
    raise SystemExit("setup_required should be true")

spec = yaml.safe_load(Path(sys.argv[2]).read_text(encoding="utf-8"))
provider = str(spec.get("kernel_engine", {}).get("provider", ""))
if provider != "":
    raise SystemExit("spec kernel_engine.provider not reset")

if Path(sys.argv[3]).exists():
    raise SystemExit("expected env file removed")
PY

echo "kernelctl firstrun-reset smoke: PASS"
