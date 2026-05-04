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
name: review-packet-smoke
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
{"timestamp_utc":"2026-04-14T00:00:01+00:00","source":"broker","kind":"broker.exec_decision","actor":{"component":"kernel_policy_bridge.py"},"object":{"workspace_root":"./"},"action":"policy_bridge_reload","decision":{"state":"allowed","request_kind":"operator_control","reason":"profile reload succeeded"},"correlation":{"session_id":"agentos:tty1"},"raw_ref":{"component":"broker"}}
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

OUT_MD="$TMP_DIR/review-packet.md"
python3 scripts/kernel_operator_review_packet.py --workspace "$WORKSPACE" --history-dir "$HISTORY_DIR" --session-id agentos:tty1 --output "$OUT_MD"

grep -q "AgentOS Operator Review Packet" "$OUT_MD"
grep -q "Session phase:" "$OUT_MD"
grep -q "Validation Drift" "$OUT_MD"
echo "kernel operator review packet smoke: PASS"
