#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_ROOT_EMBED="${AGENTOS_RUNTIME_ROOT_EMBED:-$ROOT_DIR}"
INSTALL_ROOT="${AGENTOS_INSTALL_ROOT:-/}"
AGENTOS_USER="${AGENTOS_USER:-${SUDO_USER:-$(id -un)}}"
AGENTOS_USER_HOME="${AGENTOS_USER_HOME:-}"
WORKSPACE="${DEFAULT_WORKSPACE:-$ROOT_DIR/workspaces/default}"
ENABLE_SYSTEMD="${AGENTOS_ENABLE_SYSTEMD:-1}"
BROKER_EMIT_CMD="${AGENTOS_BROKER_EMIT_CMD:-$ROOT_DIR/src/broker_emit.py}"

if [ -z "$AGENTOS_USER_HOME" ] && command -v getent >/dev/null 2>&1; then
  AGENTOS_USER_HOME="$(getent passwd "$AGENTOS_USER" 2>/dev/null | cut -d: -f6 || true)"
fi

if [ -z "$AGENTOS_USER_HOME" ]; then
  AGENTOS_USER_HOME="/home/$AGENTOS_USER"
fi

if [ "$INSTALL_ROOT" != "/" ]; then
  ENABLE_SYSTEMD=0
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
    --component install_kernel_boot_integration.sh \
    --object-field "install_root=$INSTALL_ROOT" \
    --object-field "enable_systemd=$ENABLE_SYSTEMD" \
    --object-field "agentos_user=$AGENTOS_USER" >/dev/null 2>&1 || true
}

bindir="$INSTALL_ROOT/usr/local/bin"
etc_systemd="$INSTALL_ROOT/etc/systemd/system"
getty_dropin="$etc_systemd/getty@tty1.service.d"
profile_dir="$INSTALL_ROOT/etc/profile.d"

mkdir -p "$bindir" "$etc_systemd" "$getty_dropin" "$profile_dir"

install -m 0755 "$ROOT_DIR/scripts/agentos-shell" "$bindir/agentos-shell"
install -m 0755 "$ROOT_DIR/scripts/agentos-operator-console" "$bindir/agentos-operator-console"
install -m 0755 "$ROOT_DIR/scripts/agentos-kernelctl" "$bindir/agentos-kernelctl"
install -m 0755 "$ROOT_DIR/scripts/agentos-firstrun" "$bindir/agentos-firstrun"
install -m 0755 "$ROOT_DIR/scripts/agentos-live-firstrun-service" "$bindir/agentos-live-firstrun-service"
install -m 0755 "$ROOT_DIR/scripts/agentos-eventd" "$bindir/agentos-eventd"
install -m 0755 "$ROOT_DIR/scripts/agentos-brokerd" "$bindir/agentos-brokerd"
install -m 0755 "$ROOT_DIR/image-assets/live/bin/agentos-state-root-init" "$bindir/agentos-state-root-init"
install -m 0755 "$ROOT_DIR/image-assets/live/bin/agentos-installed-boot" "$bindir/agentos-installed-boot"
install -m 0755 "$ROOT_DIR/image-assets/live/bin/agentos-slot-metadata-init" "$bindir/agentos-slot-metadata-init"

sed \
  -e "s|__AGENTOS_USER__|$AGENTOS_USER|g" \
  -e "s|__AGENTOS_REPO_ROOT__|$RUNTIME_ROOT_EMBED|g" \
  -e "s|__AGENTOS_WORKSPACE__|$WORKSPACE|g" \
  "$ROOT_DIR/deploy/systemd/agentos-eventd.service" > "$etc_systemd/agentos-eventd.service"

sed \
  -e "s|__AGENTOS_USER__|$AGENTOS_USER|g" \
  -e "s|__AGENTOS_REPO_ROOT__|$RUNTIME_ROOT_EMBED|g" \
  -e "s|__AGENTOS_WORKSPACE__|$WORKSPACE|g" \
  "$ROOT_DIR/deploy/systemd/agentos-brokerd.service" > "$etc_systemd/agentos-brokerd.service"

sed \
  -e "s|__AGENTOS_USER__|$AGENTOS_USER|g" \
  -e "s|__AGENTOS_REPO_ROOT__|$RUNTIME_ROOT_EMBED|g" \
  -e "s|__AGENTOS_WORKSPACE__|$WORKSPACE|g" \
  "$ROOT_DIR/deploy/systemd/agentos-kernel.service" > "$etc_systemd/agentos-kernel.service"

sed \
  -e "s|__AGENTOS_USER__|$AGENTOS_USER|g" \
  -e "s|__AGENTOS_USER_HOME__|$AGENTOS_USER_HOME|g" \
  -e "s|__AGENTOS_REPO_ROOT__|$RUNTIME_ROOT_EMBED|g" \
  -e "s|__AGENTOS_WORKSPACE__|$WORKSPACE|g" \
  "$ROOT_DIR/deploy/systemd/agentos-firstrun.service" > "$etc_systemd/agentos-firstrun.service"

sed \
  -e "s|__AGENTOS_USER__|$AGENTOS_USER|g" \
  "$ROOT_DIR/deploy/systemd/getty-tty1-autologin.conf" > "$getty_dropin/override.conf"

sed \
  -e "s|__AGENTOS_REPO_ROOT__|$RUNTIME_ROOT_EMBED|g" \
  -e "s|__AGENTOS_WORKSPACE__|$WORKSPACE|g" \
  "$ROOT_DIR/deploy/profile/agentos-kernel-autostart.sh" > "$profile_dir/agentos-kernel-autostart.sh"
chmod 0644 "$profile_dir/agentos-kernel-autostart.sh"

emit_install_control "install_kernel_boot_integration" "managed boot integration assets installed"

cat <<MSG
AgentOS managed session assets installed.
- agentos-shell:              $bindir/agentos-shell
- agentos-operator-console:   $bindir/agentos-operator-console
- agentos-kernelctl:          $bindir/agentos-kernelctl
- agentos-firstrun:           $bindir/agentos-firstrun
- agentos-live-firstrun:      $bindir/agentos-live-firstrun-service
- agentos-eventd:             $bindir/agentos-eventd
- agentos-brokerd:            $bindir/agentos-brokerd
- agentos-state-root-init:     $bindir/agentos-state-root-init
- agentos-installed-boot:      $bindir/agentos-installed-boot
- agentos-slot-metadata-init:  $bindir/agentos-slot-metadata-init
- event fabric service:       $etc_systemd/agentos-eventd.service
- broker control service:     $etc_systemd/agentos-brokerd.service
- managed shell service:      $etc_systemd/agentos-kernel.service
- setup session service:      $etc_systemd/agentos-firstrun.service
- tty1 autologin override:    $getty_dropin/override.conf
- tty1 session profile:       $profile_dir/agentos-kernel-autostart.sh

Recovery quick reference:
- AgentOS Recovery:           AgentOS Recovery -> Return to AgentOS -> ai>
- detailed recovery rejoin:   AgentOS Recovery -> AgentOS Setup -> AgentOS Managed Session -> ai>
- AGENTOS_BOOT_AUTOSTART=0       keep tty1 on the normal login shell
- AGENTOS_BROKER_BYPASS=1        bypass broker hooks during recovery sessions
- AGENTOS_BROKER_OVERRIDE=1      emit override events while keeping AgentOS entry active
- local tty1 banner contract:    "AgentOS Managed Session" prints before setup/ai>
- install identity path:         AgentOS Setup -> AgentOS Managed Session -> ai>
- installed boot identity:      Installed AgentOS Boot -> AgentOS Setup -> AgentOS Managed Session -> ai>
- install-later contract:        Continue to AgentOS -> Install AgentOS -> AgentOS Setup -> AgentOS Managed Session -> ai>
- persistence target origin:     installed_appliance_boot (Stage 7 baseline)
- sudo scripts/uninstall_kernel_boot_integration.sh

Recovery ladder:
1. normal shell fallback         AGENTOS_BOOT_AUTOSTART=0
2. managed entry + broker bypass AGENTOS_BROKER_BYPASS=1
3. managed entry + override      AGENTOS_BROKER_OVERRIDE=1
4. full uninstall                sudo scripts/uninstall_kernel_boot_integration.sh
MSG

if [ "$ENABLE_SYSTEMD" = "1" ] && command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload
  systemctl enable agentos-kernel.service
  systemctl enable agentos-firstrun.service
  echo "systemd daemon reloaded and AgentOS managed shell/setup session services are enabled"
  echo "agentos-eventd.service and agentos-brokerd.service stay disabled until event fabric and broker control paths are explicitly enabled"
else
  echo "systemd apply skipped (AGENTOS_ENABLE_SYSTEMD=$ENABLE_SYSTEMD, install_root=$INSTALL_ROOT)"
fi

emit_install_control "install_kernel_boot_systemd_apply" "systemd integration phase completed"
