#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE/artifacts"

cat > "$WORKSPACE/artifacts/runtime_trace.jsonl" <<'JSONL'
{"timestamp_utc":"2026-04-14T00:00:01+00:00","event":"approval_requested","payload":{"tool_name":"bash","risk_reason":"destructive command","broker":{"correlation":{"request_id":"req-1","approval_id":"approval:req-1"}}}}
{"timestamp_utc":"2026-04-14T00:00:02+00:00","event":"approval_decision","payload":{"tool_name":"bash","approved":false,"broker":{"correlation":{"request_id":"req-1","approval_id":"approval:req-1"}}}}
JSONL

cat > "$WORKSPACE/artifacts/os_events.jsonl" <<'JSONL'
{"timestamp_utc":"2026-04-14T00:00:00+00:00","source":"journald","kind":"session.login","actor":{"component":"logind"},"object":{"session_id":"tty1","user":"agent"},"action":"login","decision":{"state":"observed"},"correlation":{"session_id":"tty1","boot_id":"boot-1","session_origin":"local_managed_tty1","next_managed_entry":"ai_shell"},"raw_ref":{"component":"journald"}}
{"timestamp_utc":"2026-04-14T00:00:01+00:00","source":"broker","kind":"broker.approval_request","actor":{"component":"agentos-runtime"},"object":{"tool_name":"bash","policy_target":"destructive_action_approval"},"action":"approval_gate","decision":{"state":"requested","request_kind":"approval"},"correlation":{"request_id":"req-1","approval_id":"approval:req-1","session_id":"tty1"},"raw_ref":{"component":"broker"}}
{"timestamp_utc":"2026-04-14T00:00:02+00:00","source":"broker","kind":"broker.approval_decision","actor":{"component":"agentos-runtime"},"object":{"tool_name":"bash","policy_target":"destructive_action_approval"},"action":"decision","decision":{"state":"denied","reason":"approval denied by approver","request_kind":"approval"},"correlation":{"request_id":"req-1","approval_id":"approval:req-1","session_id":"tty1"},"raw_ref":{"component":"broker"}}
{"timestamp_utc":"2026-04-14T00:00:03+00:00","source":"broker","kind":"broker.exec_decision","actor":{"component":"install_kernel_boot_integration.sh"},"object":{"status":"override_active"},"action":"install_kernel_boot_integration","decision":{"state":"override","reason":"operator override active: install_kernel_boot_integration","request_kind":"override"},"correlation":{"request_id":"req-override","session_id":"tty1"},"raw_ref":{"component":"broker"}}
JSONL

OUTPUT="$(scripts/agentos-kernelctl approval-forensics --workspace "$WORKSPACE" --json)"
python3 - <<'PY' "$OUTPUT"
import json, sys
obj = json.loads(sys.argv[1])
summary = obj.get('summary', {})
if summary.get('approval_requested') != 1:
    raise SystemExit('expected approval_requested=1')
if summary.get('approval_denied') != 1:
    raise SystemExit('expected approval_denied=1')
if summary.get('broker_override_count') != 1:
    raise SystemExit('expected broker_override_count=1')
if summary.get('forensic_status') != 'override_active':
    raise SystemExit('expected forensic_status=override_active')
if summary.get('approval_ids_observed', 0) < 1:
    raise SystemExit('expected approval_ids_observed')
print('kernel approval forensics smoke: PASS')
PY
