#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"

OUT="$TMP_DIR/vm-utmctl-observation.out"
scripts/vm_demo_flow.sh \
  --workspace "$WORKSPACE" \
  --utm-vm-name "AgentOS Preview" \
  --dry-run > "$OUT"

for needle in \
  "UTM VM name: AgentOS Preview" \
  "Observation helper:" \
  "vm_utmctl_observation.py --vm-name AgentOS Preview --workspace $WORKSPACE" \
  "kernel_vm_e2e_scenario.py" \
  "kernel_vm_e2e_proof.py" \
  "utmctl vm observation dry-run: PASS" \
  "vm demo flow dry-run: PASS"
do
  if ! rg -q --fixed-strings "$needle" "$OUT"; then
    echo "[vm-utmctl-observation-smoke] missing output: $needle"
    cat "$OUT"
    exit 1
  fi
done

echo "vm utmctl observation smoke: PASS"
