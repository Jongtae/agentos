#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE/artifacts"
cat > "$WORKSPACE/spec.yaml" <<'YAML'
name: case-export-smoke
kernel_engine:
  provider: none
  mode: single
runtime:
  workspace_root: ./
YAML
cat > "$WORKSPACE/artifacts/runtime_trace.jsonl" <<'JSONL'
{"timestamp_utc":"2026-04-14T00:00:00+00:00","event":"run_start","payload":{}}
{"timestamp_utc":"2026-04-14T00:00:01+00:00","event":"approval_requested","payload":{"tool_name":"bash","risk_reason":"destructive command","broker":{"correlation":{"request_id":"req-1","approval_id":"approval:req-1"}}}}
{"timestamp_utc":"2026-04-14T00:00:02+00:00","event":"approval_decision","payload":{"tool_name":"bash","approved":false,"broker":{"correlation":{"request_id":"req-1","approval_id":"approval:req-1"}}}}
JSONL
cat > "$WORKSPACE/artifacts/os_events.jsonl" <<'JSONL'
{"timestamp_utc":"2026-04-14T00:00:00+00:00","source":"journald","kind":"session.login","actor":{"uid":1000},"object":{"session_id":"agentos:tty1"},"action":"login","decision":{"state":"observed"},"correlation":{"session_id":"agentos:tty1","boot_id":"boot-1","session_origin":"local_managed_tty1","next_managed_entry":"ai_shell"},"raw_ref":{"collector":"journald"}}
{"timestamp_utc":"2026-04-14T00:00:01+00:00","source":"broker","kind":"broker.approval_request","actor":{"component":"agentos-runtime"},"object":{"tool_name":"bash","policy_target":"destructive_action_approval"},"action":"approval_gate","decision":{"state":"requested","request_kind":"approval"},"correlation":{"approval_id":"approval:req-1","request_id":"req-1","session_id":"agentos:tty1"},"raw_ref":{"component":"broker"}}
{"timestamp_utc":"2026-04-14T00:00:02+00:00","source":"broker","kind":"broker.approval_decision","actor":{"component":"agentos-runtime"},"object":{"tool_name":"bash","policy_target":"destructive_action_approval"},"action":"decision","decision":{"state":"denied","reason":"approval denied by approver","request_kind":"approval"},"correlation":{"approval_id":"approval:req-1","request_id":"req-1","session_id":"agentos:tty1"},"raw_ref":{"component":"broker"}}
JSONL
OUT="$TMP_DIR/case.json"
scripts/agentos-kernelctl case-export --workspace "$WORKSPACE" --session-id agentos:tty1 --output "$OUT"
python3 - <<'PY' "$OUT"
import json, pathlib, sys
obj = json.loads(pathlib.Path(sys.argv[1]).read_text())
if obj.get('schema_version') != 'agentos-operator-case.v1':
    raise SystemExit('expected schema_version')
summary = obj.get('summary', {})
if summary.get('approval_requested') != 1:
    raise SystemExit('expected approval_requested=1')
if summary.get('approval_denied') != 1:
    raise SystemExit('expected approval_denied=1')
if 'evidence' not in obj or 'replay' not in obj or 'approval_forensics' not in obj:
    raise SystemExit('expected evidence/replay/approval_forensics sections')
print('kernel operator case export smoke: PASS')
PY
