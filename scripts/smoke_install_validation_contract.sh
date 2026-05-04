#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
INSTALL_ROOT="$TMP_DIR/root"
mkdir -p "$WORKSPACE"

cat > "$WORKSPACE/spec.yaml" <<'EOF'
name: "install-validation-contract-smoke"
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

OUT_JSON="$TMP_DIR/report.json"
python3 "$ROOT_DIR/scripts/verify_install_validation_contract.py" \
  --install-root "$INSTALL_ROOT" \
  --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("ok") is not True:
    raise SystemExit("expected install validation contract to pass")
install_root = payload.get("install_root", {})
if install_root.get("ok") is not True:
    raise SystemExit("expected install_root.ok=true")
assets = install_root.get("assets", {})
for key in ("agentos_shell", "agentos_kernelctl", "agentos_firstrun", "managed_shell_service", "setup_session_service", "tty1_override", "tty1_profile"):
    if assets.get(key) is not True:
        raise SystemExit(f"missing required install asset: {key}")
PY

echo "install validation contract smoke: PASS"
