#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"

OUT="$TMP_DIR/vm-appliance-launch.out"
scripts/vm_appliance_launch.sh \
  --workspace "$WORKSPACE" \
  --snapshot-label "agentos-demo-smoke" \
  --dry-run > "$OUT"

for needle in \
  "AgentOS VM Appliance Launch" \
  "\"schema_version\": \"agentos-vm-appliance.v1\"" \
  "\"snapshot_label\": \"agentos-demo-smoke\"" \
  "Hand-off:" \
  "scripts/vm_demo_flow.sh --workspace $WORKSPACE --dry-run" \
  "vm demo flow dry-run: PASS"
do
  if ! rg -q "$needle" "$OUT"; then
    echo "[vm-appliance-launch-smoke] missing output: $needle"
    cat "$OUT"
    exit 1
  fi
done

echo "vm appliance launch smoke: PASS"
