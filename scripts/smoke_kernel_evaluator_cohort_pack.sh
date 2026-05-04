#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
REPORT_DIR="$TMP_DIR/reports"
HISTORY_DIR="$TMP_DIR/history"
POLICY_DIR="$WORKSPACE/artifacts/kernel-policy"
mkdir -p "$HISTORY_DIR" "$POLICY_DIR"

cat > "$WORKSPACE/spec.yaml" <<'YAML'
name: evaluator-cohort-pack-smoke
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
{"timestamp_utc":"2026-04-14T00:00:00+00:00","source":"journald","kind":"session.login","actor":{"uid":1000},"object":{"session_id":"agentos:tty1"},"action":"login","decision":{"state":"observed"},"correlation":{"session_id":"agentos:tty1","session_origin":"live_appliance_boot","next_managed_entry":"ai_shell"},"raw_ref":{"collector":"journald"}}
{"timestamp_utc":"2026-04-14T00:00:01+00:00","source":"broker","kind":"broker.approval_request","actor":{"component":"agentos-runtime"},"object":{"tool_name":"bash","policy_target":"destructive_action_approval"},"action":"approval_gate","decision":{"state":"requested","request_kind":"approval"},"correlation":{"approval_id":"approval:req-1","request_id":"req-1","session_id":"agentos:tty1"},"raw_ref":{"component":"broker"}}
JSONL

cat > "$POLICY_DIR/profile-lifecycle.json" <<'JSON'
{"bridge_state":"reloaded","reload_state":"applied","disable_state":"inactive","operator_state":"ready"}
JSON
cat > "$POLICY_DIR/enforced-pilot.json" <<'JSON'
{"enabled":true,"policy_target":"destructive_action_approval"}
JSON

cat > "$HISTORY_DIR/window-1.json" <<'JSON'
{"schema_version":"agentos-validation-window.v1","label":"window-1","generated_at_utc":"2026-04-13T00:00:00Z","summary":{"runtime_ok":true,"session_phase":"ai_shell","session_origin":"live_appliance_boot","install_validation_ok":true,"audit_ok":true,"diagnostics_ok":true,"diagnostics_readiness_status":"ready","approval_forensic_status":"requested","policy_targets":{"destructive_action_approval":"candidate"},"overall_state":"ready"}}
JSON

cat > "$WORKSPACE/feedback.json" <<'JSON'
{"evaluator_id":"smoke-evaluator","channel":"guided_eval","session_label":"smoke-session","recommendation":"hold","summary":"Need one more walkthrough.","findings":[{"title":"Recovery wording","severity":"medium","area":"recovery","detail":"Clarify one step.","artifact_ref":""}],"follow_up_requests":[]}
JSON

OUT_JSON="$TMP_DIR/evaluator-cohort-pack.json"
python3 scripts/kernel_evaluator_cohort_pack.py \
  --workspace "$WORKSPACE" \
  --report-dir "$REPORT_DIR" \
  --history-dir "$HISTORY_DIR" \
  --feedback-file "$WORKSPACE/feedback.json" \
  --session-id agentos:tty1 \
  --snapshot-label cohort \
  --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("schema_version") != "agentos-evaluator-cohort-pack.v1":
    raise SystemExit("expected evaluator cohort pack schema")
cohort_root = Path(payload["cohort_root"])
cohort_dir = Path(payload["cohort_dir"])
if cohort_root.name != "evaluator-cohort-packs":
    raise SystemExit("expected evaluator-cohort-packs layout root")
for name in ["cohort-guide.md", "evaluator-cohort-pack.json"]:
    if not (cohort_dir / name).exists():
        raise SystemExit(f"missing cohort pack artifact: {name}")
if not (cohort_root / "latest-evaluator-cohort-pack.json").exists():
    raise SystemExit("missing latest cohort pack manifest")
if payload["summary"].get("delivery_scope") != "limited_preview_extension":
    raise SystemExit("expected limited preview extension scope")
guide = (cohort_dir / "cohort-guide.md").read_text(encoding="utf-8")
if "bounded, operator-guided limited preview cohort" not in guide:
    raise SystemExit("expected bounded cohort guidance")
print("kernel evaluator cohort pack smoke: PASS")
PY
