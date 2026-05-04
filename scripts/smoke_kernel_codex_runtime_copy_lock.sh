#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

out="$(mktemp)"
trap 'rm -f "$out"' EXIT

python3 "$ROOT_DIR/scripts/kernel_codex_runtime_copy_lock.py" --output "$out"
python3 "$ROOT_DIR/scripts/kernel_codex_runtime_copy_lock.py" --validate "$out" --json >/dev/null

echo "codex runtime copy lock smoke: PASS"
