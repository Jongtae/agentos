#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VERSION=""
OUT_DIR="$ROOT_DIR/build-output/iso-assets"

usage() {
  cat <<USAGE
Usage:
  scripts/prepare_iso_assets.sh --version <v> [--output-dir <dir>]

Outputs:
  <output-dir>/<version>/agentos-iso-assets.tar.gz
  <output-dir>/<version>/asset-manifest.txt
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --version)
      shift
      VERSION="${1:-}"
      ;;
    --output-dir)
      shift
      OUT_DIR="${1:-}"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift || true
done

if [ -z "$VERSION" ]; then
  echo "--version is required." >&2
  usage >&2
  exit 2
fi

if ! [[ "$VERSION" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "Invalid --version '$VERSION'. Allowed: letters, numbers, dot, underscore, hyphen." >&2
  exit 2
fi

required=(
  "$ROOT_DIR/scripts/agentos-shell"
  "$ROOT_DIR/scripts/agentos-kernelctl"
  "$ROOT_DIR/scripts/agentos-firstrun"
  "$ROOT_DIR/scripts/agentos-terminal-qr"
  "$ROOT_DIR/scripts/agentos-live-firstrun-service"
  "$ROOT_DIR/scripts/agentos-telegram-live-loop-daemon"
  "$ROOT_DIR/scripts/agentos-telegram-webhook-daemon"
  "$ROOT_DIR/scripts/agentos-eventd"
  "$ROOT_DIR/scripts/agentos-brokerd"
  "$ROOT_DIR/scripts/install_kernel_boot_integration.sh"
  "$ROOT_DIR/scripts/uninstall_kernel_boot_integration.sh"
  "$ROOT_DIR/scripts/install_agentos_boot_visuals.sh"
  "$ROOT_DIR/src/main.py"
  "$ROOT_DIR/requirements.txt"
  "$ROOT_DIR/deploy/systemd/agentos-brokerd.service"
  "$ROOT_DIR/deploy/systemd/agentos-eventd.service"
  "$ROOT_DIR/deploy/systemd/agentos-kernel.service"
  "$ROOT_DIR/deploy/systemd/agentos-firstrun.service"
  "$ROOT_DIR/deploy/systemd/agentos-telegram-live-loop.service"
  "$ROOT_DIR/deploy/systemd/agentos-telegram-webhookd.service"
  "$ROOT_DIR/deploy/systemd/getty-tty1-autologin.conf"
  "$ROOT_DIR/deploy/profile/agentos-kernel-autostart.sh"
  "$ROOT_DIR/image-assets/boot/shared/agentos-wordmark.png"
  "$ROOT_DIR/image-assets/boot/shared/agentos-dark-background.png"
  "$ROOT_DIR/image-assets/boot/grub/theme.txt"
  "$ROOT_DIR/image-assets/boot/grub/00_agentos_theme.cfg"
  "$ROOT_DIR/image-assets/boot/plymouth/agentos-minimal.plymouth"
  "$ROOT_DIR/image-assets/boot/plymouth/agentos-minimal.script"
  "$ROOT_DIR/image-assets/live/bin/agentos-welcome-shell"
  "$ROOT_DIR/image-assets/live/bin/agentos-live-session-bootstrap"
  "$ROOT_DIR/image-assets/live/bin/agentos-recovery-shell"
  "$ROOT_DIR/image-assets/live/bin/agentos-handoff"
  "$ROOT_DIR/image-assets/live/bin/agentos-install-appliance"
  "$ROOT_DIR/image-assets/live/bin/agentos-state-root-init"
  "$ROOT_DIR/image-assets/live/bin/agentos-installed-boot"
  "$ROOT_DIR/image-assets/live/bin/agentos-slot-switch-evidence"
  "$ROOT_DIR/image-assets/live/bin/agentos-slot-metadata-init"
  "$ROOT_DIR/image-assets/live/session/agentos-welcome.desktop"
  "$ROOT_DIR/image-assets/postinstall/agentos-postinstall.sh"
  "$ROOT_DIR/image-assets/postinstall/apt-packages.policy"
)

for f in "${required[@]}"; do
  if [ ! -f "$f" ]; then
    echo "Required asset missing: $f" >&2
    exit 1
  fi
done

version_dir="$OUT_DIR/$VERSION"
stage_dir="$version_dir/stage"
bundle_path="$version_dir/agentos-iso-assets.tar.gz"
manifest_path="$version_dir/asset-manifest.txt"
operator_tui_bin="$version_dir/agentos-operator-tui"

operator_tui_bin="$("$ROOT_DIR/scripts/build_agentos_operator_tui.sh" "$operator_tui_bin")"

rm -rf "$stage_dir"
mkdir -p \
  "$stage_dir/iso-assets/bin" \
  "$stage_dir/iso-assets/systemd" \
  "$stage_dir/iso-assets/profile" \
  "$stage_dir/iso-assets/postinstall" \
  "$stage_dir/iso-assets/boot/shared" \
  "$stage_dir/iso-assets/boot/grub" \
  "$stage_dir/iso-assets/boot/plymouth" \
  "$stage_dir/iso-assets/live/bin" \
  "$stage_dir/iso-assets/live/session" \
  "$stage_dir/iso-assets/runtime/agentos/image-assets" \
  "$stage_dir/iso-assets/runtime/agentos"

install -m 0755 "$ROOT_DIR/scripts/agentos-shell" "$stage_dir/iso-assets/bin/agentos-shell"
install -m 0755 "$ROOT_DIR/scripts/agentos-kernelctl" "$stage_dir/iso-assets/bin/agentos-kernelctl"
install -m 0755 "$operator_tui_bin" "$stage_dir/iso-assets/bin/agentos-operator-tui"
install -m 0755 "$ROOT_DIR/scripts/agentos-firstrun" "$stage_dir/iso-assets/bin/agentos-firstrun"
install -m 0755 "$ROOT_DIR/scripts/agentos-terminal-qr" "$stage_dir/iso-assets/bin/agentos-terminal-qr"
install -m 0755 "$ROOT_DIR/scripts/agentos-live-firstrun-service" "$stage_dir/iso-assets/bin/agentos-live-firstrun-service"
install -m 0755 "$ROOT_DIR/scripts/agentos-telegram-live-loop-daemon" "$stage_dir/iso-assets/bin/agentos-telegram-live-loop-daemon"
install -m 0755 "$ROOT_DIR/scripts/agentos-telegram-webhook-daemon" "$stage_dir/iso-assets/bin/agentos-telegram-webhook-daemon"
install -m 0755 "$ROOT_DIR/scripts/agentos-eventd" "$stage_dir/iso-assets/bin/agentos-eventd"
install -m 0755 "$ROOT_DIR/scripts/agentos-brokerd" "$stage_dir/iso-assets/bin/agentos-brokerd"
install -m 0755 "$ROOT_DIR/scripts/install_kernel_boot_integration.sh" "$stage_dir/iso-assets/bin/install_kernel_boot_integration.sh"
install -m 0755 "$ROOT_DIR/scripts/uninstall_kernel_boot_integration.sh" "$stage_dir/iso-assets/bin/uninstall_kernel_boot_integration.sh"
install -m 0755 "$ROOT_DIR/scripts/install_agentos_boot_visuals.sh" "$stage_dir/iso-assets/bin/install_agentos_boot_visuals.sh"

install -m 0644 "$ROOT_DIR/deploy/systemd/agentos-brokerd.service" "$stage_dir/iso-assets/systemd/agentos-brokerd.service"
install -m 0644 "$ROOT_DIR/deploy/systemd/agentos-eventd.service" "$stage_dir/iso-assets/systemd/agentos-eventd.service"
install -m 0644 "$ROOT_DIR/deploy/systemd/agentos-kernel.service" "$stage_dir/iso-assets/systemd/agentos-kernel.service"
install -m 0644 "$ROOT_DIR/deploy/systemd/agentos-firstrun.service" "$stage_dir/iso-assets/systemd/agentos-firstrun.service"
install -m 0644 "$ROOT_DIR/deploy/systemd/agentos-telegram-live-loop.service" "$stage_dir/iso-assets/systemd/agentos-telegram-live-loop.service"
install -m 0644 "$ROOT_DIR/deploy/systemd/agentos-telegram-webhookd.service" "$stage_dir/iso-assets/systemd/agentos-telegram-webhookd.service"
install -m 0644 "$ROOT_DIR/deploy/systemd/getty-tty1-autologin.conf" "$stage_dir/iso-assets/systemd/getty-tty1-autologin.conf"
install -m 0644 "$ROOT_DIR/deploy/profile/agentos-kernel-autostart.sh" "$stage_dir/iso-assets/profile/agentos-kernel-autostart.sh"

install -m 0644 "$ROOT_DIR/image-assets/boot/shared/agentos-wordmark.png" "$stage_dir/iso-assets/boot/shared/agentos-wordmark.png"
install -m 0644 "$ROOT_DIR/image-assets/boot/shared/agentos-dark-background.png" "$stage_dir/iso-assets/boot/shared/agentos-dark-background.png"
install -m 0644 "$ROOT_DIR/image-assets/boot/grub/theme.txt" "$stage_dir/iso-assets/boot/grub/theme.txt"
install -m 0644 "$ROOT_DIR/image-assets/boot/grub/00_agentos_theme.cfg" "$stage_dir/iso-assets/boot/grub/00_agentos_theme.cfg"
install -m 0644 "$ROOT_DIR/image-assets/boot/plymouth/agentos-minimal.plymouth" "$stage_dir/iso-assets/boot/plymouth/agentos-minimal.plymouth"
install -m 0644 "$ROOT_DIR/image-assets/boot/plymouth/agentos-minimal.script" "$stage_dir/iso-assets/boot/plymouth/agentos-minimal.script"

install -m 0755 "$ROOT_DIR/image-assets/live/bin/agentos-welcome-shell" "$stage_dir/iso-assets/live/bin/agentos-welcome-shell"
install -m 0755 "$ROOT_DIR/image-assets/live/bin/agentos-live-session-bootstrap" "$stage_dir/iso-assets/live/bin/agentos-live-session-bootstrap"
install -m 0755 "$ROOT_DIR/image-assets/live/bin/agentos-recovery-shell" "$stage_dir/iso-assets/live/bin/agentos-recovery-shell"
install -m 0755 "$ROOT_DIR/image-assets/live/bin/agentos-handoff" "$stage_dir/iso-assets/live/bin/agentos-handoff"
install -m 0755 "$ROOT_DIR/image-assets/live/bin/agentos-install-appliance" "$stage_dir/iso-assets/live/bin/agentos-install-appliance"
install -m 0755 "$ROOT_DIR/image-assets/live/bin/agentos-state-root-init" "$stage_dir/iso-assets/live/bin/agentos-state-root-init"
install -m 0755 "$ROOT_DIR/image-assets/live/bin/agentos-installed-boot" "$stage_dir/iso-assets/live/bin/agentos-installed-boot"
install -m 0755 "$ROOT_DIR/image-assets/live/bin/agentos-slot-switch-evidence" "$stage_dir/iso-assets/live/bin/agentos-slot-switch-evidence"
install -m 0755 "$ROOT_DIR/image-assets/live/bin/agentos-slot-metadata-init" "$stage_dir/iso-assets/live/bin/agentos-slot-metadata-init"
install -m 0644 "$ROOT_DIR/image-assets/live/session/agentos-welcome.desktop" "$stage_dir/iso-assets/live/session/agentos-welcome.desktop"

install -m 0755 "$ROOT_DIR/image-assets/postinstall/agentos-postinstall.sh" "$stage_dir/iso-assets/postinstall/agentos-postinstall.sh"
install -m 0644 "$ROOT_DIR/image-assets/postinstall/apt-packages.policy" "$stage_dir/iso-assets/postinstall/apt-packages.policy"

cp -R "$ROOT_DIR/src" "$stage_dir/iso-assets/runtime/agentos/src"
cp -R "$ROOT_DIR/scripts" "$stage_dir/iso-assets/runtime/agentos/scripts"
cp -R "$ROOT_DIR/deploy" "$stage_dir/iso-assets/runtime/agentos/deploy"
cp -R "$ROOT_DIR/image-assets/boot" "$stage_dir/iso-assets/runtime/agentos/image-assets/boot"
mkdir -p "$stage_dir/iso-assets/runtime/agentos/image-assets/live"
cp -R "$ROOT_DIR/image-assets/live/bin" "$stage_dir/iso-assets/runtime/agentos/image-assets/live/bin"
install -m 0644 "$ROOT_DIR/requirements.txt" "$stage_dir/iso-assets/runtime/agentos/requirements.txt"
if [ -f "$ROOT_DIR/README.md" ]; then
  install -m 0644 "$ROOT_DIR/README.md" "$stage_dir/iso-assets/runtime/agentos/README.md"
fi

mkdir -p "$version_dir"
(
  cd "$stage_dir"
  tar -czf "$bundle_path" iso-assets
)

{
  echo "version=$VERSION"
  echo "bundle=$bundle_path"
  echo "utc_prepared=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "assets:"
  echo "  - bin/agentos-shell"
  echo "  - bin/agentos-kernelctl"
  echo "  - bin/agentos-operator-tui"
  echo "  - bin/agentos-firstrun"
  echo "  - bin/agentos-live-firstrun-service"
  echo "  - bin/agentos-telegram-live-loop-daemon"
  echo "  - bin/agentos-telegram-webhook-daemon"
  echo "  - bin/agentos-eventd"
  echo "  - bin/agentos-brokerd"
  echo "  - bin/install_kernel_boot_integration.sh"
  echo "  - bin/uninstall_kernel_boot_integration.sh"
  echo "  - bin/install_agentos_boot_visuals.sh"
  echo "  - systemd/agentos-brokerd.service"
  echo "  - systemd/agentos-eventd.service"
  echo "  - systemd/agentos-kernel.service"
  echo "  - systemd/agentos-firstrun.service"
  echo "  - systemd/agentos-telegram-live-loop.service"
  echo "  - systemd/agentos-telegram-webhookd.service"
  echo "  - systemd/getty-tty1-autologin.conf"
  echo "  - profile/agentos-kernel-autostart.sh"
  echo "  - boot/shared/agentos-wordmark.png"
  echo "  - boot/shared/agentos-dark-background.png"
  echo "  - boot/grub/theme.txt"
  echo "  - boot/grub/00_agentos_theme.cfg"
  echo "  - boot/plymouth/agentos-minimal.plymouth"
  echo "  - boot/plymouth/agentos-minimal.script"
  echo "  - live/bin/agentos-welcome-shell"
  echo "  - live/bin/agentos-live-session-bootstrap"
  echo "  - live/bin/agentos-recovery-shell"
  echo "  - live/bin/agentos-handoff"
  echo "  - live/bin/agentos-install-appliance"
  echo "  - live/bin/agentos-state-root-init"
  echo "  - live/bin/agentos-installed-boot"
  echo "  - live/bin/agentos-slot-switch-evidence"
  echo "  - live/bin/agentos-slot-metadata-init"
  echo "  - live/session/agentos-welcome.desktop"
  echo "  - postinstall/agentos-postinstall.sh"
  echo "  - postinstall/apt-packages.policy"
  echo "  - runtime/agentos/src/main.py"
  echo "  - runtime/agentos/scripts/install_kernel_boot_integration.sh"
  echo "  - runtime/agentos/deploy/systemd/agentos-kernel.service"
  echo "  - runtime/agentos/image-assets/boot/shared/agentos-wordmark.png"
  echo "  - runtime/agentos/image-assets/live/bin/agentos-state-root-init"
  echo "  - runtime/agentos/requirements.txt"
} > "$manifest_path"

rm -rf "$stage_dir"

echo "Prepared ISO asset bundle:"
echo "bundle:   $bundle_path"
echo "manifest: $manifest_path"
