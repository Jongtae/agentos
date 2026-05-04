#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
HOME_DIR="$TMP_DIR/home"
mkdir -p "$WORKSPACE" "$HOME_DIR"

OUT="$TMP_DIR/reset.out"
scripts/vm_demo_reset.sh \
  --workspace "$WORKSPACE" \
  --user-home "$HOME_DIR" \
  --snapshot-label "agentos-demo-smoke" \
  --dry-run > "$OUT"

for needle in \
  "AgentOS VM Demo Reset" \
  "vm_appliance_manifest.py --workspace" \
  "Reset AgentOS setup state" \
  "scripts/agentos-kernelctl firstrun-reset" \
  "Remove AgentOS boot integration assets" \
  "scripts/uninstall_kernel_boot_integration.sh" \
  "Reinstall AgentOS boot integration assets" \
  "scripts/install_kernel_boot_integration.sh" \
  "Recommended snapshot label: agentos-demo-smoke" \
  "scripts/vm_demo_flow.sh --workspace" \
  "vm demo reset dry-run: PASS"
do
  if ! rg -q "$needle" "$OUT"; then
    echo "[vm-demo-reset-smoke] missing output: $needle"
    cat "$OUT"
    exit 1
  fi
done

echo "vm demo reset smoke: PASS"
