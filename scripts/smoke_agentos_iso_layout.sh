#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ISO_PATH=""

usage() {
  cat <<USAGE
Usage:
  scripts/smoke_agentos_iso_layout.sh [--iso <path>]

Checks:
  - Required autoinstall/image-assets files exist
  - postinstall script is executable
  - Optional ISO filename contract (agentos-*-amd64.iso)
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --iso)
      shift
      ISO_PATH="${1:-}"
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

required_files=(
  "$ROOT_DIR/autoinstall/user-data"
  "$ROOT_DIR/autoinstall/meta-data"
  "$ROOT_DIR/image-assets/boot/shared/agentos-wordmark.png"
  "$ROOT_DIR/image-assets/boot/shared/agentos-dark-background.png"
  "$ROOT_DIR/image-assets/boot/grub/theme.txt"
  "$ROOT_DIR/image-assets/boot/plymouth/agentos-minimal.plymouth"
  "$ROOT_DIR/image-assets/postinstall/agentos-postinstall.sh"
  "$ROOT_DIR/image-assets/postinstall/apt-packages.policy"
  "$ROOT_DIR/src/main.py"
  "$ROOT_DIR/scripts/install_kernel_boot_integration.sh"
  "$ROOT_DIR/scripts/install_agentos_boot_visuals.sh"
  "$ROOT_DIR/scripts/prepare_iso_assets.sh"
  "$ROOT_DIR/scripts/build_agentos_iso.sh"
)

for f in "${required_files[@]}"; do
  if [ ! -f "$f" ]; then
    echo "[iso-layout] missing required file: $f" >&2
    exit 1
  fi
done

if [ ! -x "$ROOT_DIR/image-assets/postinstall/agentos-postinstall.sh" ]; then
  echo "[iso-layout] postinstall script is not executable." >&2
  exit 1
fi

if [ -n "$ISO_PATH" ]; then
  if [ ! -f "$ISO_PATH" ]; then
    echo "[iso-layout] ISO not found: $ISO_PATH" >&2
    exit 1
  fi
  iso_name="$(basename "$ISO_PATH")"
  if ! [[ "$iso_name" =~ ^agentos-[A-Za-z0-9._-]+-amd64\.iso$ ]]; then
    echo "[iso-layout] invalid ISO filename contract: $iso_name" >&2
    exit 1
  fi
fi

echo "ISO layout smoke: PASS"
