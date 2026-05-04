#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WELCOME="$ROOT_DIR/image-assets/live/bin/agentos-welcome-shell"
RECOVERY="$ROOT_DIR/image-assets/live/bin/agentos-recovery-shell"
HANDOFF="$ROOT_DIR/image-assets/live/bin/agentos-handoff"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

CONTINUE_FILE="$TMP_DIR/continue.env"
INSTALL_FILE="$TMP_DIR/install.env"
RECOVERY_FILE="$TMP_DIR/recovery.env"
RETURN_FILE="$TMP_DIR/return.env"
RECOVERY_SHIM="$TMP_DIR/recovery-shim.sh"
FIRSTRUN_SHIM="$TMP_DIR/firstrun-shim.sh"
SHELL_SHIM="$TMP_DIR/shell-shim.sh"

cat > "$RECOVERY_SHIM" <<'EOS'
#!/usr/bin/env bash
printf '%s\n' 'shim recovery'
EOS
chmod +x "$RECOVERY_SHIM"

cat > "$FIRSTRUN_SHIM" <<'EOS'
#!/usr/bin/env bash
exit 0
EOS
chmod +x "$FIRSTRUN_SHIM"

cat > "$SHELL_SHIM" <<'EOS'
#!/usr/bin/env bash
exit 0
EOS
chmod +x "$SHELL_SHIM"

AGENTOS_HANDOFF_BIN="$HANDOFF" AGENTOS_HANDOFF_FILE="$CONTINUE_FILE" AGENTOS_FIRSTRUN_BIN="$FIRSTRUN_SHIM" AGENTOS_SHELL_BIN="$SHELL_SHIM" bash "$WELCOME" continue >/dev/null
install_code=0
if AGENTOS_HANDOFF_BIN="$HANDOFF" AGENTOS_HANDOFF_FILE="$INSTALL_FILE" bash "$WELCOME" install >/dev/null; then
  install_code=0
else
  install_code=$?
fi
AGENTOS_HANDOFF_BIN="$HANDOFF" AGENTOS_HANDOFF_FILE="$RECOVERY_FILE" AGENTOS_RECOVERY_SHELL_BIN="$RECOVERY_SHIM" bash "$WELCOME" recovery >/dev/null
AGENTOS_HANDOFF_BIN="$HANDOFF" AGENTOS_HANDOFF_FILE="$RETURN_FILE" bash "$RECOVERY" return >/dev/null

test "$install_code" -eq 10
rg -q '^route=continue_to_agentos$' "$CONTINUE_FILE"
rg -q '^next_step=agentos_setup$' "$CONTINUE_FILE"
rg -q 'AgentOS Setup -> Codex CLI Managed Session -> ai>' "$CONTINUE_FILE"
rg -q '^runtime_target=codex_cli_managed_session$' "$CONTINUE_FILE"
rg -q '^supervision_target=codex_launch_supervision$' "$CONTINUE_FILE"
rg -q '^route=install_agentos$' "$INSTALL_FILE"
rg -q '^next_step=persistent_install$' "$INSTALL_FILE"
rg -q '^route=recovery$' "$RECOVERY_FILE"
rg -q '^next_step=agentos_recovery$' "$RECOVERY_FILE"
rg -q '^route=return_to_agentos$' "$RETURN_FILE"
rg -q '^next_step=agentos_setup$' "$RETURN_FILE"

echo "agentos welcome handoff smoke: PASS"
