#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

INSTALL_ROOT="$TMP_DIR/root"
WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"

cat > "$WORKSPACE/spec.yaml" <<'EOF'
name: "installed-launcher-smoke"
ai_model:
  provider: "openai"
  model: "gpt-4o-mini"
kernel_engine:
  provider: "none"
  mode: "single"
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

AGENTOS_INSTALL_ROOT="$INSTALL_ROOT" \
AGENTOS_ENABLE_SYSTEMD=0 \
DEFAULT_WORKSPACE="$WORKSPACE" \
"$ROOT_DIR/scripts/install_kernel_boot_integration.sh" >/dev/null

PROFILE_FILE="$INSTALL_ROOT/etc/profile.d/agentos-kernel-autostart.sh"
if ! rg -q 'AGENTOS_REPO_ROOT=' "$PROFILE_FILE"; then
  echo "missing AGENTOS_REPO_ROOT export in profile autostart"
  exit 1
fi

SHELL_BIN="$INSTALL_ROOT/usr/local/bin/agentos-shell"
KERNELCTL_BIN="$INSTALL_ROOT/usr/local/bin/agentos-kernelctl"

OUT_STATUS="$TMP_DIR/status.txt"
AGENTOS_REPO_ROOT="$ROOT_DIR" \
DEFAULT_WORKSPACE="$WORKSPACE" \
"$SHELL_BIN" --workspace "$WORKSPACE" --status > "$OUT_STATUS"

if ! rg -q "AgentOS Status" "$OUT_STATUS"; then
  echo "installed agentos-shell did not produce status output"
  exit 1
fi

OUT_JSON="$TMP_DIR/kernelctl-status.json"
AGENTOS_REPO_ROOT="$ROOT_DIR" \
DEFAULT_WORKSPACE="$WORKSPACE" \
"$KERNELCTL_BIN" status --workspace "$WORKSPACE" --json > "$OUT_JSON" || true

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
runtime = payload.get("runtime_status", {}) or {}
if "ok" not in runtime:
    raise SystemExit("missing runtime_status.ok")
if payload.get("service", {}).get("name", "") == "":
    raise SystemExit("missing service name")
PY

echo "installed launcher repo-root smoke: PASS"
