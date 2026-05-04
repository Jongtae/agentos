#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

STRICT_APPARMOR=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --strict-apparmor)
      STRICT_APPARMOR=1
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
  shift || true
done

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"

cat > "$WORKSPACE/spec.yaml" <<'EOF'
name: "kernel-policy-enforce-require-ready-smoke"
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

OUT_FAIL="$TMP_DIR/not-ready.json"
if scripts/agentos-kernelctl policy-enforce \
  --workspace "$WORKSPACE" \
  --enable \
  --confirm \
  --require-ready \
  --json > "$OUT_FAIL" 2>/dev/null; then
  echo "require-ready should fail before policy profile exists"
  exit 1
fi

python3 - "$OUT_FAIL" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("reason") != "kernel_profile_not_ready":
    raise SystemExit("expected kernel_profile_not_ready before bridge output")
PY

scripts/agentos-kernelctl policy-bridge --workspace "$WORKSPACE" >/dev/null

OUT_OK="$TMP_DIR/ready.json"
PARSER_CMD="sh"
if [ "$STRICT_APPARMOR" = "1" ]; then
  if ! command -v apparmor_parser >/dev/null 2>&1; then
    echo "strict mode requires apparmor_parser on PATH"
    exit 1
  fi
  PARSER_CMD="apparmor_parser"
fi

scripts/agentos-kernelctl policy-enforce \
  --workspace "$WORKSPACE" \
  --enable \
  --confirm \
  --require-ready \
  --policy-target network_allowlist \
  --parser-cmd "$PARSER_CMD" \
  --json > "$OUT_OK"

python3 - "$OUT_OK" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("configured_enabled") is not True:
    raise SystemExit("expected configured_enabled=true")
kernel = payload.get("kernel_mechanism") or {}
if kernel.get("profile_exists") is not True:
    raise SystemExit("expected profile_exists=true")
if kernel.get("parser_available") is not True:
    raise SystemExit("expected parser_available=true")
if kernel.get("ready_for_enforced_pilot") is not True:
    raise SystemExit("expected ready_for_enforced_pilot=true")
if payload.get("policy_target") != "network_allowlist":
    raise SystemExit("expected policy_target=network_allowlist")
PY

echo "kernel policy enforce require-ready smoke: PASS (strict_apparmor=${STRICT_APPARMOR})"
