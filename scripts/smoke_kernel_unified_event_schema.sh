#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

OUT="$TMP_DIR/unified-event-schema.json"
python3 "$ROOT_DIR/scripts/kernel_unified_event_schema.py" --output "$OUT"
python3 "$ROOT_DIR/scripts/kernel_unified_event_schema.py" --validate "$OUT" --json >/dev/null
python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
if payload.get('schema_version') != 'agentos-unified-event-schema.v1':
    raise SystemExit('expected unified event schema version')
families = {item['family'] for item in payload.get('event_families', [])}
required = {'process', 'network', 'approval', 'policy', 'recovery', 'service', 'session'}
missing = required - families
if missing:
    raise SystemExit(f'missing families: {sorted(missing)}')
if 'request_id' not in ((payload.get('causal_chain') or {}).get('stable_fields') or []):
    raise SystemExit('expected request_id in causal chain')
print('kernel unified event schema smoke: PASS')
PY
