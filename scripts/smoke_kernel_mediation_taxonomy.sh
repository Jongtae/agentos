#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

python3 "$ROOT_DIR/scripts/kernel_mediation_taxonomy.py" \
  --workspace ./workspaces/default \
  --output "$TMP_DIR/taxonomy.json"
python3 "$ROOT_DIR/scripts/kernel_mediation_taxonomy.py" --validate "$TMP_DIR/taxonomy.json" --json > "$TMP_DIR/validate.json"

python3 - "$TMP_DIR/taxonomy.json" "$TMP_DIR/validate.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
validate = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
if payload.get('schema_version') != 'agentos-mediation-taxonomy.v1':
    raise SystemExit('expected mediation taxonomy schema')
if payload.get('summary', {}).get('user_intent_class_count') != 3:
    raise SystemExit('expected three user intent execution classes')
if validate.get('ok') is not True:
    raise SystemExit('expected mediation taxonomy validation to pass')
PY

echo "mediation taxonomy smoke: PASS"
