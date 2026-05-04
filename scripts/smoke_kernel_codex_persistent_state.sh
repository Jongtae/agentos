#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

export PYTHONPATH="$ROOT_DIR/src"
export AGENTOS_STATE_ROOT="$tmpdir/state-root"
export AGENTOS_INSTALL_REQUEST_FILE="$tmpdir/install.env"
export AGENTOS_INSTALLED_BOOT_FILE="$tmpdir/boot.env"

bash "$ROOT_DIR/image-assets/live/bin/agentos-state-root-init" >/dev/null
bash "$ROOT_DIR/image-assets/live/bin/agentos-install-appliance" >/dev/null 2>&1 || test "$?" = 10
bash "$ROOT_DIR/image-assets/live/bin/agentos-installed-boot" >/dev/null

out="$tmpdir/codex-persistent-state.json"
python3 "$ROOT_DIR/scripts/kernel_codex_persistent_state.py" --workspace ./workspaces/default --output "$out"
python3 "$ROOT_DIR/scripts/kernel_codex_persistent_state.py" --validate "$out" --json >/dev/null

echo "codex persistent state smoke: PASS"
