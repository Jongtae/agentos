#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WELCOME="$ROOT_DIR/image-assets/live/bin/agentos-welcome-shell"
INSTALLER="$ROOT_DIR/image-assets/live/bin/agentos-install-appliance"
HANDOFF="$ROOT_DIR/image-assets/live/bin/agentos-handoff"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

REQ_FILE="$TMP_DIR/install.env"
HANDOFF_FILE="$TMP_DIR/handoff.env"
OUT_FILE="$TMP_DIR/install.out"

install_code=0
if AGENTOS_INSTALL_APPLIANCE_BIN="$INSTALLER" \
  AGENTOS_INSTALL_REQUEST_FILE="$REQ_FILE" \
  AGENTOS_HANDOFF_BIN="$HANDOFF" \
  AGENTOS_HANDOFF_FILE="$HANDOFF_FILE" \
  bash "$WELCOME" install >"$OUT_FILE"; then
  install_code=0
else
  install_code=$?
fi

test "$install_code" -eq 10
rg -q '^action_label=Install AgentOS$' "$REQ_FILE"
rg -q '^persistence_goal=make_this_appliance_persistent$' "$REQ_FILE"
rg -q '^target_origin=installed_appliance_boot$' "$REQ_FILE"
rg -q '^installer_ui_hidden=true$' "$REQ_FILE"
rg -q '^installer_semantics=agentos_persistence$' "$REQ_FILE"
rg -q '^route=install_agentos$' "$HANDOFF_FILE"
rg -q '^next_step=persistent_install$' "$HANDOFF_FILE"
rg -q 'AgentOS will make this appliance persistent on disk' "$OUT_FILE"
rg -q 'Post-install identity: AgentOS Setup -> AgentOS Managed Session -> ai>' "$OUT_FILE"

echo "agentos install-later productization smoke: PASS"
