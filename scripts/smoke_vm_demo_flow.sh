#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"

OUT="$TMP_DIR/vm-demo.out"
scripts/vm_demo_flow.sh --workspace "$WORKSPACE" --dry-run > "$OUT"

for needle in \
  "AgentOS VM Demo Flow" \
  "vm_appliance_manifest.py --workspace" \
  "Goal: boot AgentOS -> tiny setup -> ai>" \
  "Bootstrap Ubuntu substrate prerequisites" \
  "Run substrate doctor (compatibility preflight)" \
  "Install AgentOS boot integration assets" \
  "Verify kernel boot integration" \
  "Verify managed session health" \
  "Verify managed session status surface" \
  "Boot the default AgentOS appliance path" \
  "Let AgentOS Setup appear" \
  "ai>" \
  "vm demo flow dry-run: PASS"
do
  if ! rg -q --fixed-strings "$needle" "$OUT"; then
    echo "[vm-demo-smoke] missing output: $needle"
    cat "$OUT"
    exit 1
  fi
done

echo "vm demo flow smoke: PASS"
