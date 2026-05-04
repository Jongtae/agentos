#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INSTALL_ROOT="${AGENTOS_INSTALL_ROOT:-/}"
DISABLE_SYSTEMD="${AGENTOS_DISABLE_SYSTEMD:-1}"
WORKSPACE="${DEFAULT_WORKSPACE:-$ROOT_DIR/workspaces/default}"
BROKER_EMIT_CMD="${AGENTOS_BROKER_EMIT_CMD:-$ROOT_DIR/src/broker_emit.py}"
SERVICE_PATH="$INSTALL_ROOT/etc/systemd/system/agentos-kernel.service"
EVENTD_SERVICE_PATH="$INSTALL_ROOT/etc/systemd/system/agentos-eventd.service"
BROKERD_SERVICE_PATH="$INSTALL_ROOT/etc/systemd/system/agentos-brokerd.service"
FIRSTRUN_SERVICE_PATH="$INSTALL_ROOT/etc/systemd/system/agentos-firstrun.service"
GETTY_OVERRIDE="$INSTALL_ROOT/etc/systemd/system/getty@tty1.service.d/override.conf"
PROFILE_AUTOSTART="$INSTALL_ROOT/etc/profile.d/agentos-kernel-autostart.sh"
BIN_SHELL="$INSTALL_ROOT/usr/local/bin/agentos-shell"
BIN_CTL="$INSTALL_ROOT/usr/local/bin/agentos-kernelctl"
BIN_FIRSTRUN="$INSTALL_ROOT/usr/local/bin/agentos-firstrun"
BIN_EVENTD="$INSTALL_ROOT/usr/local/bin/agentos-eventd"
BIN_BROKERD="$INSTALL_ROOT/usr/local/bin/agentos-brokerd"

if [ "$INSTALL_ROOT" != "/" ]; then
  DISABLE_SYSTEMD=0
fi

emit_install_control() {
  if [ ! -f "$BROKER_EMIT_CMD" ]; then
    return 0
  fi
  if [ "${AGENTOS_BROKER_BYPASS:-0}" = "1" ]; then
    return 0
  fi
  local emit_state="allowed"
  local emit_reason="$2"
  if [ "${AGENTOS_BROKER_OVERRIDE:-0}" = "1" ]; then
    emit_state="override"
    emit_reason="operator override active: $1"
  fi
  python3 "$BROKER_EMIT_CMD" \
    --workspace "$WORKSPACE" \
    --kind install_control \
    --action "$1" \
    --state "$emit_state" \
    --reason "$emit_reason" \
    --component uninstall_kernel_boot_integration.sh \
    --object-field "install_root=$INSTALL_ROOT" \
    --object-field "disable_systemd=$DISABLE_SYSTEMD" >/dev/null 2>&1 || true
}

if [ "$DISABLE_SYSTEMD" = "1" ] && command -v systemctl >/dev/null 2>&1; then
  systemctl disable agentos-kernel.service >/dev/null 2>&1 || true
  systemctl disable agentos-eventd.service >/dev/null 2>&1 || true
  systemctl disable agentos-brokerd.service >/dev/null 2>&1 || true
  systemctl disable agentos-firstrun.service >/dev/null 2>&1 || true
fi

rm -f "$SERVICE_PATH"
rm -f "$EVENTD_SERVICE_PATH"
rm -f "$BROKERD_SERVICE_PATH"
rm -f "$FIRSTRUN_SERVICE_PATH"
rm -f "$GETTY_OVERRIDE"
rm -f "$PROFILE_AUTOSTART"
rm -f "$BIN_SHELL"
rm -f "$BIN_CTL"
rm -f "$BIN_FIRSTRUN"
rm -f "$BIN_EVENTD"
rm -f "$BIN_BROKERD"

if [ "$DISABLE_SYSTEMD" = "1" ] && command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload
fi

echo "Kernel boot integration assets removed."
emit_install_control "uninstall_kernel_boot_integration" "managed boot integration assets removed"
