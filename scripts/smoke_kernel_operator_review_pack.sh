#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
HISTORY_DIR="$TMP_DIR/history"
POLICY_DIR="$WORKSPACE/artifacts/kernel-policy"
mkdir -p "$HISTORY_DIR" "$POLICY_DIR"

cat > "$WORKSPACE/spec.yaml" <<'YAML'
name: review-pack-smoke
kernel_engine:
  provider: none
  mode: single
runtime:
  workspace_root: ./
YAML

cat > "$WORKSPACE/artifacts/runtime_trace.jsonl" <<'JSONL'
{"timestamp_utc":"2026-04-14T00:00:00+00:00","event":"run_start","payload":{}}
{"timestamp_utc":"2026-04-14T00:00:01+00:00","event":"approval_requested","payload":{"tool_name":"bash","broker":{"correlation":{"request_id":"req-1","approval_id":"approval:req-1"}}}}
JSONL

cat > "$WORKSPACE/artifacts/os_events.jsonl" <<'JSONL'
{"timestamp_utc":"2026-04-14T00:00:00+00:00","source":"journald","kind":"session.login","actor":{"uid":1000},"object":{"session_id":"agentos:tty1"},"action":"login","decision":{"state":"observed"},"correlation":{"session_id":"agentos:tty1","session_origin":"local_managed_tty1","next_managed_entry":"ai_shell"},"raw_ref":{"collector":"journald"}}
{"timestamp_utc":"2026-04-14T00:00:01+00:00","source":"broker","kind":"broker.approval_request","actor":{"component":"agentos-runtime"},"object":{"tool_name":"bash","policy_target":"destructive_action_approval"},"action":"approval_gate","decision":{"state":"requested","request_kind":"approval"},"correlation":{"approval_id":"approval:req-1","request_id":"req-1","session_id":"agentos:tty1"},"raw_ref":{"component":"broker"}}
{"timestamp_utc":"2026-04-14T00:00:02+00:00","source":"broker","kind":"broker.exec_decision","actor":{"component":"kernel_policy_bridge.py"},"object":{"workspace_root":"./"},"action":"policy_bridge_reload","decision":{"state":"allowed","request_kind":"operator_control","reason":"profile reload succeeded"},"correlation":{"session_id":"agentos:tty1"},"raw_ref":{"component":"broker"}}
JSONL

cat > "$POLICY_DIR/profile-lifecycle.json" <<'JSON'
{"bridge_state":"reloaded","reload_state":"applied","disable_state":"inactive","operator_state":"ready"}
JSON
cat > "$POLICY_DIR/enforced-pilot.json" <<'JSON'
{"enabled":true,"policy_target":"network_allowlist"}
JSON

cat > "$HISTORY_DIR/window-1.json" <<'JSON'
{"schema_version":"agentos-validation-window.v1","label":"window-1","generated_at_utc":"2026-04-13T00:00:00Z","summary":{"runtime_ok":true,"session_phase":"setup_session","session_origin":"local_managed_tty1","install_validation_ok":false,"audit_ok":null,"diagnostics_ok":null,"diagnostics_readiness_status":"","approval_forensic_status":"pending","policy_targets":{"destructive_action_approval":"candidate"},"overall_state":"policy_drift"}}
JSON

OUT_JSON="$TMP_DIR/review-pack.json"
python3 scripts/kernel_operator_review_pack.py --workspace "$WORKSPACE" --history-dir "$HISTORY_DIR" --session-id agentos:tty1 --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("schema_version") != "agentos-operator-review-pack.v1":
    raise SystemExit("expected review pack schema")
summary = payload.get("summary", {})
if summary.get("validation_stable") is not False:
    raise SystemExit("expected validation_stable=false")
if "bridge" not in summary.get("control_categories", []):
    raise SystemExit("expected bridge category")
if "case_export" not in payload or "validation_window" not in payload or "control_history" not in payload:
    raise SystemExit("expected packaged sections")
print("kernel operator review pack smoke: PASS")
PY
