#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

INSTALL_ROOT="$TMP_DIR/root"
WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"

FAKE_CODEX="$TMP_DIR/fake-codex.sh"
cat > "$FAKE_CODEX" <<'EOS'
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
if echo "$prompt" | grep -q 'Reply with exactly: HEALTH_OK'; then
  msg='HEALTH_OK'
else
  msg='{"summary":"noop","steps":[]}'
fi
if [ -n "$out_file" ]; then
  printf "%s" "$msg" > "$out_file"
fi
printf "%s\n" "$msg"
EOS
chmod +x "$FAKE_CODEX"

cat > "$WORKSPACE/spec.yaml" <<EOS
name: "kernel-rollback-smoke"
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
  max_steps: 4
  max_message_window: 20
  workspace_root: "./"
EOS

AGENTOS_INSTALL_ROOT="$INSTALL_ROOT" \
AGENTOS_ENABLE_SYSTEMD=0 \
DEFAULT_WORKSPACE="$WORKSPACE" \
"$ROOT_DIR/scripts/install_kernel_boot_integration.sh"

AGENTOS_INSTALL_ROOT="$INSTALL_ROOT" "$ROOT_DIR/scripts/uninstall_kernel_boot_integration.sh"

if [ -e "$INSTALL_ROOT/usr/local/bin/agentos-shell" ] || [ -e "$INSTALL_ROOT/etc/systemd/system/agentos-kernel.service" ]; then
  echo "[kernel-rollback-smoke] uninstall did not remove assets"
  exit 1
fi

# Reinstall should still work after uninstall.
AGENTOS_INSTALL_ROOT="$INSTALL_ROOT" \
AGENTOS_ENABLE_SYSTEMD=0 \
DEFAULT_WORKSPACE="$WORKSPACE" \
"$ROOT_DIR/scripts/install_kernel_boot_integration.sh"

[ -x "$INSTALL_ROOT/usr/local/bin/agentos-kernelctl" ]

# Validate kernelctl diagnostics bundle shortcut via exporter.
OUT_DIR="$TMP_DIR/diag"
OPENAI_API_KEY=dummy "$ROOT_DIR/scripts/agentos-kernelctl" bundle --workspace "$WORKSPACE" --out-dir "$OUT_DIR"
[ -f "$OUT_DIR/doctor.json" ]
[ -f "$OUT_DIR/status.json" ]
[ -f "$OUT_DIR/snapshot.json" ]
[ -f "$OUT_DIR/manifest.json" ]

echo "kernel boot rollback smoke: PASS"
