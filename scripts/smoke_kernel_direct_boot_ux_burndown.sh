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
name: direct-boot-ux-burndown-smoke
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
{"evaluator_id":"smoke-evaluator","channel":"guided_eval","session_label":"smoke-session","recommendation":"hold","summary":"Need one more walkthrough.","findings":[{"title":"Boot wording","severity":"high","area":"boot","detail":"Clarify the boot story.","artifact_ref":""},{"title":"Setup wording","severity":"medium","area":"setup","detail":"Clarify the setup path.","artifact_ref":""},{"title":"Recovery wording","severity":"medium","area":"recovery","detail":"Clarify one step.","artifact_ref":""}],"follow_up_requests":[]}
JSON

OUT_JSON="$TMP_DIR/direct-boot-ux-burndown.json"
python3 scripts/kernel_direct_boot_ux_burndown.py \
  --workspace "$WORKSPACE" \
  --report-dir "$REPORT_DIR" \
  --history-dir "$HISTORY_DIR" \
  --feedback-file "$WORKSPACE/feedback.json" \
  --session-id agentos:tty1 \
  --snapshot-label burndown \
  --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("schema_version") != "agentos-direct-boot-ux-burndown.v1":
    raise SystemExit("expected direct-boot ux burndown schema")
run_root = Path(payload["burndown_root"])
run_dir = Path(payload["burndown_dir"])
if run_root.name != "direct-boot-ux-burndown":
    raise SystemExit("expected direct-boot-ux-burndown layout root")
for name in ["direct-boot-ux-burndown.md", "direct-boot-ux-burndown.json"]:
    if not (run_dir / name).exists():
        raise SystemExit(f"missing direct-boot ux burn-down artifact: {name}")
if payload["summary"].get("burn_down_state") != "blocked":
    raise SystemExit("expected blocked burn-down state")
if payload["summary"].get("outstanding_fix_targets") != ["boot_clarity", "setup_clarity", "recovery_clarity"]:
    raise SystemExit("unexpected outstanding fix targets")
print("kernel direct-boot ux burndown smoke: PASS")
PY
