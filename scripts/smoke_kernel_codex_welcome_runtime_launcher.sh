#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

export PYTHONPATH="$ROOT_DIR/src"

out="$tmpdir/codex-welcome-runtime-launcher.json"
python3 "$ROOT_DIR/scripts/kernel_codex_welcome_runtime_launcher.py" --workspace ./workspaces/default --output "$out"
python3 "$ROOT_DIR/scripts/kernel_codex_welcome_runtime_launcher.py" --validate "$out" --json >/dev/null

echo "codex welcome runtime launcher smoke: PASS"
