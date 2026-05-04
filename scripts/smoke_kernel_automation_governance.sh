#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE/artifacts"

cat > "$WORKSPACE/artifacts/os_events.jsonl" <<'JSONL'
{"timestamp_utc":"2026-04-14T00:00:00+00:00","source":"broker","kind":"broker.exec_decision","actor":{"component":"runtime_autoremediation_stage_orchestrator.py"},"object":{"policy_target":"destructive_action_approval"},"action":"scheduled_stage_apply","decision":{"state":"allowed","request_kind":"operator_control"},"correlation":{"session_id":"agentos:tty1"},"raw_ref":{"component":"broker"}}
{"timestamp_utc":"2026-04-14T00:00:01+00:00","source":"broker","kind":"broker.exec_decision","actor":{"component":"runtime_autoremediation_loop.py"},"object":{"status":"override_active"},"action":"forced_resume","decision":{"state":"override","request_kind":"override"},"correlation":{"session_id":"agentos:tty1"},"raw_ref":{"component":"broker"}}
JSONL

OUT="$TMP_DIR/automation-governance.json"
python3 "$ROOT_DIR/scripts/kernel_automation_governance.py" --workspace "$WORKSPACE" --output "$OUT"
python3 "$ROOT_DIR/scripts/kernel_automation_governance.py" --validate "$OUT" --json >/dev/null
python3 - "$OUT" <<'PY'
import json, sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
if payload.get('schema_version') != 'agentos-automation-governance.v1':
    raise SystemExit('expected automation governance schema version')
summary = payload.get('summary', {})
if summary.get('scheduled_task_count') != 3:
    raise SystemExit('expected three scheduled tasks in baseline inventory')
if summary.get('override_events') != 1:
    raise SystemExit('expected one override event')
print('kernel automation governance smoke: PASS')
PY
