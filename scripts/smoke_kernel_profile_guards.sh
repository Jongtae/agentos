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
name: "kernel-profile-guards-smoke"
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

PROFILE_SCRIPT="$INSTALL_ROOT/etc/profile.d/agentos-kernel-autostart.sh"
[ -f "$PROFILE_SCRIPT" ]

rg -q 'case "\$-" in' "$PROFILE_SCRIPT"
rg -q '\*i\*\) ;;\s*$' "$PROFILE_SCRIPT"
rg -q '\*\) return ;;\s*$' "$PROFILE_SCRIPT"
rg -q 'id -u' "$PROFILE_SCRIPT"
rg -q 'SSH_TTY' "$PROFILE_SCRIPT"
rg -q '/dev/tty1' "$PROFILE_SCRIPT"
rg -q 'AGENTOS_SHELL_STARTED' "$PROFILE_SCRIPT"
rg -q 'AGENTOS_SESSION_MANAGED=1' "$PROFILE_SCRIPT"
rg -q 'AGENTOS_SESSION_ENTRY=local_tty1' "$PROFILE_SCRIPT"
rg -q 'AGENTOS_SESSION_BANNER_VERSION=phase49-v1' "$PROFILE_SCRIPT"
rg -q '=== AgentOS Managed Session ===' "$PROFILE_SCRIPT"
rg -q 'recovery: AGENTOS_BOOT_AUTOSTART=0 keeps tty1 on the normal login shell' "$PROFILE_SCRIPT"
rg -q 'agentos_print_managed_session_banner' "$PROFILE_SCRIPT"
rg -q '/usr/local/bin/agentos-firstrun' "$PROFILE_SCRIPT"
rg -q 'exec /usr/local/bin/agentos-shell --kernel-mode' "$PROFILE_SCRIPT"

firstrun_line="$(rg -n '/usr/local/bin/agentos-firstrun' "$PROFILE_SCRIPT" | head -n1 | cut -d: -f1)"
exec_line="$(rg -n 'exec /usr/local/bin/agentos-shell --kernel-mode' "$PROFILE_SCRIPT" | head -n1 | cut -d: -f1)"
if [ -z "$firstrun_line" ] || [ -z "$exec_line" ] || [ "$firstrun_line" -ge "$exec_line" ]; then
  echo "[kernel-profile-guards-smoke] firstrun must run before shell exec"
  exit 1
fi

banner_line="$(rg -n 'agentos_print_managed_session_banner' "$PROFILE_SCRIPT" | tail -n1 | cut -d: -f1)"
if [ -z "$banner_line" ] || [ "$banner_line" -ge "$firstrun_line" ]; then
  echo "[kernel-profile-guards-smoke] managed session banner must print before firstrun"
  exit 1
fi

echo "kernel profile guards smoke: PASS"
