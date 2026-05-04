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
name: evaluator-feedback-intake-smoke
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
{"timestamp_utc":"2026-04-14T00:00:00+00:00","source":"journald","kind":"session.login","actor":{"uid":1000},"object":{"session_id":"agentos:tty1"},"action":"login","decision":{"state":"observed"},"correlation":{"session_id":"agentos:tty1","session_origin":"local_managed_tty1","next_managed_entry":"ai_shell"},"raw_ref":{"collector":"journald"}}
JSONL

cat > "$POLICY_DIR/profile-lifecycle.json" <<'JSON'
{"bridge_state":"reloaded","reload_state":"applied","disable_state":"inactive","operator_state":"ready"}
JSON
cat > "$POLICY_DIR/enforced-pilot.json" <<'JSON'
{"enabled":true,"policy_target":"destructive_action_approval"}
JSON

cat > "$HISTORY_DIR/window-1.json" <<'JSON'
{"schema_version":"agentos-validation-window.v1","label":"window-1","generated_at_utc":"2026-04-13T00:00:00Z","summary":{"runtime_ok":true,"session_phase":"ai_shell","session_origin":"local_managed_tty1","install_validation_ok":true,"audit_ok":true,"diagnostics_ok":true,"diagnostics_readiness_status":"ready","approval_forensic_status":"requested","policy_targets":{"destructive_action_approval":"candidate"},"overall_state":"ready"}}
JSON

cat > "$TMP_DIR/feedback.json" <<'JSON'
{"evaluator_id":"reviewer-1","channel":"internal_preview","session_label":"session-a","recommendation":"advance","summary":"Preview baseline is coherent.","findings":[{"title":"Guide is readable","severity":"low","area":"docs","detail":"The evaluator guide is usable.","artifact_ref":"artifacts.evaluator_guide_markdown"}]}
JSON

OUT_JSON="$TMP_DIR/feedback-intake.json"
python3 scripts/kernel_evaluator_feedback_intake.py \
  --workspace "$WORKSPACE" \
  --report-dir "$REPORT_DIR" \
  --history-dir "$HISTORY_DIR" \
  --feedback-file "$TMP_DIR/feedback.json" \
  --session-id agentos:tty1 \
  --snapshot-label preview \
  --json > "$OUT_JSON"

python3 scripts/kernel_evaluator_feedback_intake.py --validate "$OUT_JSON" --json >/dev/null
python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("schema_version") != "agentos-evaluator-feedback-intake.v1":
    raise SystemExit("expected evaluator feedback intake schema")
if payload.get("feedback_packet", {}).get("recommendation") != "advance":
    raise SystemExit("expected normalized recommendation")
artifacts = payload.get("artifacts", {})
if not Path(artifacts.get("feedback_intake_manifest_json", "")).exists():
    raise SystemExit("missing feedback intake manifest")
if not Path(artifacts.get("feedback_template_json", "")).exists():
    raise SystemExit("missing feedback template")
print("kernel evaluator feedback intake smoke: PASS")
PY
