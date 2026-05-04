#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$(mktemp)"
trap 'rm -f "$OUT"' EXIT

python3 "$ROOT_DIR/scripts/kernel_vm_e2e_scenario.py" --workspace "$ROOT_DIR/workspaces/default" --output "$OUT"
python3 "$ROOT_DIR/scripts/kernel_vm_e2e_scenario.py" --validate "$OUT" --json >/dev/null
echo "kernel vm e2e scenario smoke: PASS"
