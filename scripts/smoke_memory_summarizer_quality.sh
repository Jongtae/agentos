#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/src"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

OUT_FILE="$TMP_DIR/summary.json"
python3 scripts/memory_summarizer_benchmark.py --max-chars 180 --max-lines 4 --output "$OUT_FILE" > "$TMP_DIR/run.out"

if ! rg -q '"compaction_ratio":' "$OUT_FILE"; then
  echo "[summarizer-quality] missing compaction_ratio"
  cat "$OUT_FILE"
  exit 1
fi

if ! rg -q '"critical_lines_retained":' "$OUT_FILE"; then
  echo "[summarizer-quality] missing critical retention metric"
  cat "$OUT_FILE"
  exit 1
fi

python3 - <<PY
import json
from pathlib import Path
payload = json.loads(Path("$OUT_FILE").read_text())
metrics = payload["metrics"]
if metrics["compaction_ratio"] > 1.0:
    raise SystemExit("compaction_ratio should be <= 1.0")
if metrics["critical_lines_retained"] < 1:
    raise SystemExit("expected at least one retained critical line")
PY

echo "memory summarizer quality smoke: PASS"
