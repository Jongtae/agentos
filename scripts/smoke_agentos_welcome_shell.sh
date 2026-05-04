#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WELCOME="$ROOT_DIR/image-assets/live/bin/agentos-welcome-shell"
RECOVERY="$ROOT_DIR/image-assets/live/bin/agentos-recovery-shell"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

CONTINUE_OUT="$TMP_DIR/continue.out"
INSTALL_OUT="$TMP_DIR/install.out"
RECOVERY_OUT="$TMP_DIR/recovery.out"
RECOVERY_SHIM="$TMP_DIR/recovery-shim.sh"
FIRSTRUN_SHIM="$TMP_DIR/firstrun-shim.sh"
SHELL_SHIM="$TMP_DIR/shell-shim.sh"
SETUP_MARKER="$TMP_DIR/setup.marker"
SHELL_MARKER="$TMP_DIR/shell.marker"

cat > "$RECOVERY_SHIM" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' 'shim recovery'
EOF
chmod +x "$RECOVERY_SHIM"

cat > "$FIRSTRUN_SHIM" <<EOF
#!/usr/bin/env bash
printf '%s\n' "shim firstrun workspace=\$2"
printf '%s\n' "\$2" > "$SETUP_MARKER"
EOF
chmod +x "$FIRSTRUN_SHIM"

cat > "$SHELL_SHIM" <<EOF
#!/usr/bin/env bash
printf '%s\n' "shim shell \$*"
printf '%s\n' "\$*" > "$SHELL_MARKER"
EOF
chmod +x "$SHELL_SHIM"

AGENTOS_FIRSTRUN_BIN="$FIRSTRUN_SHIM" \
AGENTOS_SHELL_BIN="$SHELL_SHIM" \
AGENTOS_WELCOME_WORKSPACE="$TMP_DIR/workspace" \
  bash "$WELCOME" continue >"$CONTINUE_OUT"
install_code=0
if bash "$WELCOME" install >"$INSTALL_OUT"; then
  install_code=0
else
  install_code=$?
fi
AGENTOS_RECOVERY_SHELL_BIN="$RECOVERY_SHIM" bash "$WELCOME" recovery >"$RECOVERY_OUT"
bash "$RECOVERY" return >>"$RECOVERY_OUT"

rg -q 'Continue to AgentOS' "$CONTINUE_OUT"
rg -q 'Launching managed Codex CLI session through AgentOS Setup' "$CONTINUE_OUT"
rg -q 'shim firstrun workspace=' "$CONTINUE_OUT"
rg -q 'shim shell --kernel-mode --workspace' "$CONTINUE_OUT"
test -f "$SETUP_MARKER"
test -f "$SHELL_MARKER"
test "$install_code" -eq 10
rg -q 'Install AgentOS selected' "$INSTALL_OUT"
rg -q 'Recovery selected' "$RECOVERY_OUT"
rg -q 'shim recovery' "$RECOVERY_OUT"
rg -q 'Returning to AgentOS' "$RECOVERY_OUT"
rg -q '^Exec=/usr/local/bin/agentos-welcome-shell continue$' "$ROOT_DIR/image-assets/live/session/agentos-welcome.desktop"

echo "agentos welcome shell smoke: PASS"
