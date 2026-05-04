#!/usr/bin/env bash
set -euo pipefail

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This bootstrap script is intended for Ubuntu/Debian (apt-get required)."
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export DEBIAN_FRONTEND=noninteractive

echo "[1/4] apt-get update"
sudo apt-get update

echo "[2/4] install system prerequisites"
sudo apt-get install -y --no-install-recommends \
  apparmor \
  apparmor-utils \
  ca-certificates \
  curl \
  git \
  jq \
  python3 \
  python3-pip \
  python3-venv \
  ripgrep \
  build-essential

echo "[3/4] install Python dependencies"
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

echo "[4/4] verify toolchain"
python3 --version
git --version
rg --version
jq --version

echo "Optional next step:"
echo "  scripts/install_kernel_boot_integration.sh"

echo "Ubuntu bootstrap: PASS"
