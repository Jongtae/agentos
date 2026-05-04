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
name: preview-evaluation-kit-smoke
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
{"timestamp_utc":"2026-04-14T00:00:01+00:00","source":"broker","kind":"broker.approval_request","actor":{"component":"agentos-runtime"},"object":{"tool_name":"bash","policy_target":"destructive_action_approval"},"action":"approval_gate","decision":{"state":"requested","request_kind":"approval"},"correlation":{"approval_id":"approval:req-1","request_id":"req-1","session_id":"agentos:tty1"},"raw_ref":{"component":"broker"}}
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

OUT_JSON="$TMP_DIR/preview-evaluation-kit.json"
python3 scripts/kernel_preview_evaluation_kit.py \
  --workspace "$WORKSPACE" \
  --report-dir "$REPORT_DIR" \
  --history-dir "$HISTORY_DIR" \
  --session-id agentos:tty1 \
  --snapshot-label preview \
  --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("schema_version") != "agentos-preview-evaluation-kit.v1":
    raise SystemExit("expected preview evaluation kit schema")
kit_root = Path(payload["kit_root"])
kit_dir = Path(payload["kit_dir"])
if kit_root.name != "preview-evaluation-kits":
    raise SystemExit("expected preview-evaluation-kits layout root")
for name in ["evaluator-guide.md", "preview-kit-manifest.json"]:
    if not (kit_dir / name).exists():
        raise SystemExit(f"missing preview kit artifact: {name}")
if not (kit_root / "latest-preview-kit-manifest.json").exists():
    raise SystemExit("missing latest preview kit manifest")
milestone_dir = Path(payload["artifacts"]["milestone_bundle_dir"])
if not milestone_dir.exists():
    raise SystemExit("missing nested milestone bundle")
guide = (kit_dir / "evaluator-guide.md").read_text(encoding="utf-8")
if "Boot AgentOS through the default appliance path" not in guide:
    raise SystemExit("expected appliance-first evaluator guidance")
print("kernel preview evaluation kit smoke: PASS")
PY
