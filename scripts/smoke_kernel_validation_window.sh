#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
HISTORY_DIR="$TMP_DIR/history"
mkdir -p "$WORKSPACE/artifacts" "$HISTORY_DIR"

cat > "$WORKSPACE/spec.yaml" <<'YAML'
name: validation-window-smoke
kernel_engine:
  provider: none
  mode: single
runtime:
  workspace_root: ./
YAML

cat > "$WORKSPACE/artifacts/runtime_trace.jsonl" <<'JSONL'
{"timestamp_utc":"2026-04-14T00:00:00+00:00","event":"run_start","payload":{}}
JSONL

cat > "$WORKSPACE/artifacts/os_events.jsonl" <<'JSONL'
{"timestamp_utc":"2026-04-14T00:00:00+00:00","source":"journald","kind":"session.login","actor":{"uid":1000},"object":{"session_id":"agentos:tty1"},"action":"login","decision":{"state":"observed"},"correlation":{"session_id":"agentos:tty1","boot_id":"boot-1","session_origin":"local_managed_tty1","next_managed_entry":"ai_shell"},"raw_ref":{"collector":"journald"}}
{"timestamp_utc":"2026-04-14T00:00:01+00:00","source":"broker","kind":"broker.approval_request","actor":{"component":"agentos-runtime"},"object":{"tool_name":"bash","policy_target":"destructive_action_approval"},"action":"approval_gate","decision":{"state":"requested","request_kind":"approval"},"correlation":{"approval_id":"approval:req-1","request_id":"req-1","session_id":"agentos:tty1"},"raw_ref":{"component":"broker"}}
JSONL

cat > "$HISTORY_DIR/window-1.json" <<'JSON'
{"schema_version":"agentos-validation-window.v1","label":"window-1","generated_at_utc":"2026-04-13T00:00:00Z","summary":{"runtime_ok":true,"session_phase":"setup_session","session_origin":"local_managed_tty1","install_validation_ok":false,"audit_ok":null,"diagnostics_ok":null,"diagnostics_readiness_status":"","approval_forensic_status":"pending","policy_targets":{"destructive_action_approval":"candidate"},"overall_state":"policy_drift"}}
JSON

OUT_JSON="$TMP_DIR/validation-window.json"
scripts/agentos-kernelctl validation-window \
  --workspace "$WORKSPACE" \
  --report-dir "$HISTORY_DIR" \
  --snapshot-label current-window \
  --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("schema_version") != "agentos-validation-window.v1":
    raise SystemExit("expected validation window schema_version")
summary = payload.get("summary", {})
if int(summary.get("history_count", 0)) != 1:
    raise SystemExit("expected history_count=1")
if summary.get("stable") is not False:
    raise SystemExit("expected stable=false")
if "session_phase" not in summary.get("changed_fields", []):
    raise SystemExit("expected session_phase drift")
if "policy_targets" not in summary.get("changed_fields", []):
    raise SystemExit("expected policy_targets drift")
print("kernel validation window smoke: PASS")
PY
