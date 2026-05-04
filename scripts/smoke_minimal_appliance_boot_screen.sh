#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

VERSION="vsmoke-boot-visuals-$(date +%s)-$$"
ASSET_OUT_DIR="$TMP_DIR/iso-assets"
PREPARE_OUT="$($ROOT_DIR/scripts/prepare_iso_assets.sh --version "$VERSION" --output-dir "$ASSET_OUT_DIR")"
BUNDLE_PATH="$(printf '%s\n' "$PREPARE_OUT" | sed -n 's/^bundle:[[:space:]]*//p' | tail -n1)"
MANIFEST_PATH="$(printf '%s\n' "$PREPARE_OUT" | sed -n 's/^manifest:[[:space:]]*//p' | tail -n1)"

if [ ! -f "$BUNDLE_PATH" ]; then
  echo "[boot-visual-smoke] missing asset bundle"
  exit 1
fi

if [ ! -f "$MANIFEST_PATH" ]; then
  echo "[boot-visual-smoke] missing asset manifest"
  exit 1
fi

for path in \
  'iso-assets/boot/shared/agentos-wordmark.png' \
  'iso-assets/boot/shared/agentos-dark-background.png' \
  'iso-assets/boot/grub/theme.txt' \
  'iso-assets/boot/grub/00_agentos_theme.cfg' \
  'iso-assets/boot/plymouth/agentos-minimal.plymouth' \
  'iso-assets/boot/plymouth/agentos-minimal.script' \
  'iso-assets/bin/install_agentos_boot_visuals.sh' \
  'iso-assets/live/bin/agentos-welcome-shell' \
  'iso-assets/live/bin/agentos-recovery-shell' \
  'iso-assets/live/session/agentos-welcome.desktop'
do
  if ! tar -tzf "$BUNDLE_PATH" | rg -q "^${path}$"; then
    echo "[boot-visual-smoke] asset bundle missing ${path}"
    exit 1
  fi
done

if ! rg -q 'boot/grub/theme.txt' "$MANIFEST_PATH"; then
  echo "[boot-visual-smoke] asset manifest missing grub theme entry"
  exit 1
fi

if ! rg -q 'boot/plymouth/agentos-minimal.plymouth' "$MANIFEST_PATH"; then
  echo "[boot-visual-smoke] asset manifest missing plymouth theme entry"
  exit 1
fi

if ! rg -q 'live/session/agentos-welcome.desktop' "$MANIFEST_PATH"; then
  echo "[boot-visual-smoke] asset manifest missing welcome session entry"
  exit 1
fi

echo "minimal appliance boot screen smoke: PASS"
