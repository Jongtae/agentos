#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/src"

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
elif echo "$prompt" | grep -q 'planning engine for AgentOS'; then
  msg='{"summary":"noop","steps":[]}'
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
name: "kernel-boot-smoke"
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

INSTALL_OUT="$TMP_DIR/install.out"
AGENTOS_INSTALL_ROOT="$INSTALL_ROOT" \
AGENTOS_ENABLE_SYSTEMD=0 \
DEFAULT_WORKSPACE="$WORKSPACE" \
"$ROOT_DIR/scripts/install_kernel_boot_integration.sh" > "$INSTALL_OUT"

[ -x "$INSTALL_ROOT/usr/local/bin/agentos-shell" ]
[ -x "$INSTALL_ROOT/usr/local/bin/agentos-kernelctl" ]
[ -x "$INSTALL_ROOT/usr/local/bin/agentos-live-firstrun-service" ]
[ -f "$INSTALL_ROOT/etc/systemd/system/agentos-kernel.service" ]
[ -f "$INSTALL_ROOT/etc/systemd/system/getty@tty1.service.d/override.conf" ]
[ -f "$INSTALL_ROOT/etc/profile.d/agentos-kernel-autostart.sh" ]

if ! rg -q "Recovery quick reference:" "$INSTALL_OUT"; then
  echo "[kernel-smoke] install output missing recovery quick reference"
  cat "$INSTALL_OUT"
  exit 1
fi
if ! rg -q 'AgentOS Managed Session' "$INSTALL_ROOT/etc/profile.d/agentos-kernel-autostart.sh"; then
  echo "[kernel-smoke] profile missing managed session banner contract"
  exit 1
fi
if ! rg -q 'path: AgentOS Setup -> AgentOS Managed Session -> ai>' "$INSTALL_ROOT/etc/profile.d/agentos-kernel-autostart.sh"; then
  echo "[kernel-smoke] profile missing install identity path"
  exit 1
fi
if ! rg -q "AGENTOS_BOOT_AUTOSTART=0" "$INSTALL_OUT"; then
  echo "[kernel-smoke] install output missing tty bypass hint"
  cat "$INSTALL_OUT"
  exit 1
fi
if ! rg -q 'install identity path:' "$INSTALL_OUT"; then
  echo "[kernel-smoke] install output missing install identity path"
  cat "$INSTALL_OUT"
  exit 1
fi
if ! rg -q 'local tty1 banner contract:' "$INSTALL_OUT"; then
  echo "[kernel-smoke] install output missing banner contract note"
  cat "$INSTALL_OUT"
  exit 1
fi

if ! rg -q -- "--autologin" "$INSTALL_ROOT/etc/systemd/system/getty@tty1.service.d/override.conf"; then
  echo "[kernel-smoke] missing autologin profile"
  exit 1
fi

if ! rg -q "agentos-shell --workspace" "$INSTALL_ROOT/etc/systemd/system/agentos-kernel.service"; then
  echo "[kernel-smoke] missing service ExecStart"
  exit 1
fi

if ! rg -q "Description=AgentOS Managed Shell Bootstrap Service" "$INSTALL_ROOT/etc/systemd/system/agentos-kernel.service"; then
  echo "[kernel-smoke] missing managed shell service description"
  exit 1
fi

if ! rg -q "Description=AgentOS Setup Session Service" "$INSTALL_ROOT/etc/systemd/system/agentos-firstrun.service"; then
  echo "[kernel-smoke] missing setup session service description"
  exit 1
fi
if ! rg -q "agentos-live-firstrun:" "$INSTALL_OUT"; then
  echo "[kernel-smoke] install output missing live firstrun wrapper"
  cat "$INSTALL_OUT"
  exit 1
fi

OUT="$TMP_DIR/shell.out"
OPENAI_API_KEY=dummy "$ROOT_DIR/scripts/agentos-shell" --workspace "$WORKSPACE" --status > "$OUT"
if ! rg -q "AgentOS Status" "$OUT"; then
  echo "[kernel-smoke] agentos-shell status failed"
  cat "$OUT"
  exit 1
fi

FAKE_SYSTEMCTL="$TMP_DIR/fake-systemctl.sh"
cat > "$FAKE_SYSTEMCTL" <<'EOS'
#!/bin/sh
set -eu
case "$1" in
  is-active)
    echo active
    ;;
  is-enabled)
    echo enabled
    ;;
  restart)
    echo restarted "$2"
    ;;
  *)
    exit 1
    ;;
esac
EOS
chmod +x "$FAKE_SYSTEMCTL"

CTL_OUT="$TMP_DIR/kernelctl.out"
OPENAI_API_KEY=dummy AGENTOS_SYSTEMCTL_CMD="$FAKE_SYSTEMCTL" "$ROOT_DIR/scripts/agentos-kernelctl" status --workspace "$WORKSPACE" > "$CTL_OUT"
if ! rg -q "managed_session_service: agentos-kernel.service" "$CTL_OUT"; then
  echo "[kernel-smoke] kernelctl status missing managed session service header"
  cat "$CTL_OUT"
  exit 1
fi
if ! rg -q "Setup status:" "$CTL_OUT"; then
  echo "[kernel-smoke] kernelctl status missing setup transition summary"
  cat "$CTL_OUT"
  exit 1
fi
if ! rg -q "Recovery hints:" "$CTL_OUT"; then
  echo "[kernel-smoke] kernelctl status missing recovery hints section"
  cat "$CTL_OUT"
  exit 1
fi
if ! rg -q "Recovery ladder:" "$CTL_OUT"; then
  echo "[kernel-smoke] kernelctl status missing recovery ladder section"
  cat "$CTL_OUT"
  exit 1
fi
if ! rg -q "AGENTOS_BOOT_AUTOSTART=0 keeps tty1 on the normal login shell" "$CTL_OUT"; then
  echo "[kernel-smoke] kernelctl status missing tty recovery hint"
  cat "$CTL_OUT"
  exit 1
fi
if ! rg -q "1. normal shell fallback -> AGENTOS_BOOT_AUTOSTART=0" "$CTL_OUT"; then
  echo "[kernel-smoke] kernelctl status missing recovery ladder level 1"
  cat "$CTL_OUT"
  exit 1
fi
if ! rg -q "AgentOS Status" "$CTL_OUT"; then
  echo "[kernel-smoke] kernelctl status missing runtime status"
  cat "$CTL_OUT"
  exit 1
fi

GUIDED_OUT="$TMP_DIR/guided-operator.json"
OPENAI_API_KEY=dummy AGENTOS_SESSION_MANAGED=1 AGENTOS_SESSION_ENTRY=local_tty1 \
  "$ROOT_DIR/scripts/agentos-kernelctl" guided-operator --workspace "$WORKSPACE" --json > "$GUIDED_OUT"
python3 - "$GUIDED_OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["runtime_entry_mode"] == "tty"
assert payload["state_summary"]["session_origin"] == "local_managed_tty1"
assert payload["operator_context"]["session_origin"] == "local_managed_tty1"
assert payload["guided_operator_surface_reachable"] is True
PY

echo "kernel boot integration smoke: PASS"
