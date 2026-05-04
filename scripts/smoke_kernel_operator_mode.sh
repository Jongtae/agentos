#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

python3 "$ROOT_DIR/scripts/kernel_operator_mode.py" \
  --session-origin local_managed_tty1 \
  --setup-status configured \
  --output "$TMP_DIR/user.json"
AGENTOS_BROKER_BYPASS=1 python3 "$ROOT_DIR/scripts/kernel_operator_mode.py" \
  --session-origin local_managed_tty1 \
  --setup-status configured \
  --output "$TMP_DIR/recovery.json"
python3 "$ROOT_DIR/scripts/kernel_operator_mode.py" --validate "$TMP_DIR/user.json" --json > "$TMP_DIR/validate.json"

python3 - "$TMP_DIR/user.json" "$TMP_DIR/recovery.json" "$TMP_DIR/validate.json" <<'PY'
import json
import sys
from pathlib import Path

user = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
recovery = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
validate = json.loads(Path(sys.argv[3]).read_text(encoding='utf-8'))
if user.get('current_mode') != 'user_mode':
    raise SystemExit('expected default managed session to be user_mode')
if recovery.get('current_mode') != 'recovery_mode':
    raise SystemExit('expected bypass session to be recovery_mode')
if validate.get('ok') is not True:
    raise SystemExit('expected operator mode validation to pass')
PY

echo "operator mode smoke: PASS"
