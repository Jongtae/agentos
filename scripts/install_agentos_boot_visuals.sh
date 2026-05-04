#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ASSET_ROOT="$ROOT_DIR/image-assets/boot"
GRUB_THEME_DIR="/boot/grub/themes/agentos-minimal"
PLYMOUTH_THEME_DIR="/usr/share/plymouth/themes/agentos-minimal"
GRUB_DEFAULTS_DIR="/etc/default/grub.d"
GRUB_THEME_CONF="$GRUB_DEFAULTS_DIR/90-agentos-visuals.cfg"
PLYMOUTH_DEFAULT="/usr/share/plymouth/themes/default.plymouth"

if [ ! -d "$ASSET_ROOT" ]; then
  echo "[agentos-boot-visuals] asset root missing: $ASSET_ROOT" >&2
  exit 1
fi

install -d -m 0755 "$GRUB_THEME_DIR" "$PLYMOUTH_THEME_DIR" "$GRUB_DEFAULTS_DIR"
install -m 0644 "$ASSET_ROOT/shared/agentos-dark-background.png" "$GRUB_THEME_DIR/agentos-dark-background.png"
install -m 0644 "$ASSET_ROOT/shared/agentos-wordmark.png" "$PLYMOUTH_THEME_DIR/agentos-wordmark.png"
install -m 0644 "$ASSET_ROOT/grub/theme.txt" "$GRUB_THEME_DIR/theme.txt"
install -m 0644 "$ASSET_ROOT/grub/00_agentos_theme.cfg" "$GRUB_THEME_CONF"
install -m 0644 "$ASSET_ROOT/plymouth/agentos-minimal.plymouth" "$PLYMOUTH_THEME_DIR/agentos-minimal.plymouth"
install -m 0644 "$ASSET_ROOT/plymouth/agentos-minimal.script" "$PLYMOUTH_THEME_DIR/agentos-minimal.script"
ln -sf "$PLYMOUTH_THEME_DIR/agentos-minimal.plymouth" "$PLYMOUTH_DEFAULT"

if command -v update-alternatives >/dev/null 2>&1; then
  update-alternatives --install /usr/share/plymouth/themes/default.plymouth default.plymouth "$PLYMOUTH_THEME_DIR/agentos-minimal.plymouth" 200 || true
  update-alternatives --set default.plymouth "$PLYMOUTH_THEME_DIR/agentos-minimal.plymouth" || true
fi

if command -v update-initramfs >/dev/null 2>&1; then
  update-initramfs -u || true
fi

if command -v update-grub >/dev/null 2>&1; then
  update-grub || true
elif command -v grub-mkconfig >/dev/null 2>&1; then
  grub-mkconfig -o /boot/grub/grub.cfg || true
fi

echo "[agentos-boot-visuals] installed AgentOS minimal GRUB + Plymouth themes"
