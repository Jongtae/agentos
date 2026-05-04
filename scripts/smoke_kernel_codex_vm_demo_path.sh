#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

export PYTHONPATH="$ROOT_DIR/src"

out="$tmpdir/codex-vm-demo-path.json"
python3 "$ROOT_DIR/scripts/kernel_codex_vm_demo_path.py" --workspace ./workspaces/default --output "$out"
python3 "$ROOT_DIR/scripts/kernel_codex_vm_demo_path.py" --validate "$out" --json >/dev/null

echo "codex vm demo path smoke: PASS"
