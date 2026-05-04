#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/src"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

OUT_FILE="$TMP_DIR/result.json"
TREND_FILE="$TMP_DIR/trend.jsonl"
python3 scripts/memory_recall_benchmark.py --top-k 2 --output "$OUT_FILE" --trend-output "$TREND_FILE" > "$TMP_DIR/run.out"

if ! rg -q '"query": "what did I work on yesterday\?"' "$OUT_FILE"; then
  echo "[memory-recall] missing expected query in output"
  cat "$OUT_FILE"
  exit 1
fi

if ! rg -q '"precision_at_k": 1.0' "$OUT_FILE"; then
  echo "[memory-recall] expected precision_at_k=1.0"
  cat "$OUT_FILE"
  exit 1
fi

if ! rg -q '"recall_at_k": 1.0' "$OUT_FILE"; then
  echo "[memory-recall] expected recall_at_k=1.0"
  cat "$OUT_FILE"
  exit 1
fi

if ! rg -q '"threshold_status": "pass"' "$OUT_FILE"; then
  echo "[memory-recall] expected threshold_status=pass"
  cat "$OUT_FILE"
  exit 1
fi

if [ ! -s "$TREND_FILE" ]; then
  echo "[memory-recall] expected non-empty trend artifact"
  exit 1
fi

echo "memory recall benchmark smoke: PASS"
