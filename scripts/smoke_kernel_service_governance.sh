#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE/artifacts"

cat > "$WORKSPACE/artifacts/os_events.jsonl" <<'JSONL'
{"timestamp_utc":"2026-04-14T00:00:00+00:00","source":"journald","kind":"systemd.unit_state","actor":{"uid":1000},"object":{"unit":"agentos-kernel.service","state":"started"},"action":"started","decision":{"state":"observed"},"correlation":{"session_id":"agentos:tty1"},"raw_ref":{"collector":"journald"}}
{"timestamp_utc":"2026-04-14T00:00:01+00:00","source":"broker","kind":"broker.exec_decision","actor":{"component":"systemctl"},"object":{"unit":"agentos-kernel.service"},"action":"service_restart","decision":{"state":"allowed","request_kind":"operator_control"},"correlation":{"session_id":"agentos:tty1"},"raw_ref":{"component":"broker"}}
JSONL

OUT="$TMP_DIR/service-governance.json"
python3 "$ROOT_DIR/scripts/kernel_service_governance.py" --workspace "$WORKSPACE" --output "$OUT"
python3 "$ROOT_DIR/scripts/kernel_service_governance.py" --validate "$OUT" --json >/dev/null
python3 - "$OUT" <<'PY'
import json, sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
if payload.get('schema_version') != 'agentos-service-governance.v1':
    raise SystemExit('expected service governance schema version')
summary = payload.get('summary', {})
if 'agentos-kernel.service' not in summary.get('mandatory_broker_units', []):
    raise SystemExit('expected managed session unit in mandatory_broker_units')
if summary.get('operator_control_actions') != 1:
    raise SystemExit('expected one operator control action')
print('kernel service governance smoke: PASS')
PY
