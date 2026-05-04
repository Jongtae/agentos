#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$(mktemp)"
trap 'rm -f "$OUT"' EXIT

"$ROOT_DIR/scripts/agentos-kernelctl" capability-execution --workspace "$ROOT_DIR/workspaces/default" --json >"$OUT"
python3 "$ROOT_DIR/scripts/kernel_capability_execution.py" --validate "$OUT" --json >/dev/null
echo "kernel capability execution smoke: PASS"
