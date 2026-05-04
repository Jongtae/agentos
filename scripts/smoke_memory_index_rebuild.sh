#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/src"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

MEM_DB="$TMP_DIR/memory.sqlite"
INDEX_FILE="$TMP_DIR/token-index.json"

python3 - <<PY
from kernel.memory.store import MemoryStore
store = MemoryStore("$MEM_DB")
store.save_fact("worked on kernel runtime and codex setup", importance=0.9)
store.save_fact("implemented memory index backend", importance=0.9)
store.save_fact("read weather news", importance=0.2)
PY

FIRST_OUT="$TMP_DIR/first.json"
python3 scripts/rebuild_memory_index.py --memory-db "$MEM_DB" --output "$INDEX_FILE" > "$FIRST_OUT"

if ! rg -q '"parity_ok": true' "$FIRST_OUT"; then
  echo "[index-rebuild] first parity check failed"
  cat "$FIRST_OUT"
  exit 1
fi

printf 'corrupted-json' > "$INDEX_FILE"

SECOND_OUT="$TMP_DIR/second.json"
python3 scripts/rebuild_memory_index.py --memory-db "$MEM_DB" --output "$INDEX_FILE" > "$SECOND_OUT"

if ! rg -q '"parity_ok": true' "$SECOND_OUT"; then
  echo "[index-rebuild] second parity check failed"
  cat "$SECOND_OUT"
  exit 1
fi

if ! rg -q '"recovered_from_corrupt_index": true' "$SECOND_OUT"; then
  echo "[index-rebuild] expected corruption recovery flag"
  cat "$SECOND_OUT"
  exit 1
fi

echo "memory index rebuild smoke: PASS"
