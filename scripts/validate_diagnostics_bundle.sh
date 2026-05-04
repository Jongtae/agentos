#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/src"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE_DIR="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE_DIR"

FAKE_CODEX="$TMP_DIR/fake-codex.sh"
cat > "$FAKE_CODEX" <<'EOS'
#!/bin/sh
set -eu

out_file=""
prompt=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --output-last-message)
      shift
      out_file="$1"
      ;;
    *)
      prompt="$1"
      ;;
  esac
  shift
done

if printf "%s" "$prompt" | grep -q "Reply with exactly: HEALTH_OK"; then
  msg="HEALTH_OK"
else
  msg='{"summary":"noop","steps":[]}'
fi

if [ -n "$out_file" ]; then
  printf "%s" "$msg" > "$out_file"
fi
printf "%s\n" "$msg"
EOS
chmod +x "$FAKE_CODEX"

cat > "$WORKSPACE_DIR/spec.yaml" <<EOS
name: "bundle-validate"
ai_model:
  provider: "openai"
  model: "gpt-4o-mini"
kernel_engine:
  provider: "codex"
  mode: "single"
  codex:
    command: "$FAKE_CODEX"
    timeout_sec: 10
    model: ""
tools:
  bash: true
  file: true
  web: true
permissions:
  require_approval: true
memory:
  checkpointer: "sqlite"
  db_path: "./data/session.sqlite"
  store_path: "./data/memory.sqlite"
runtime:
  max_steps: 12
  max_message_window: 20
  workspace_root: "./"
EOS

OUT_DIR="$TMP_DIR/out"
OPENAI_API_KEY=dummy scripts/export_diagnostics_bundle.sh "$WORKSPACE_DIR" "$OUT_DIR"

for f in doctor.json status.json snapshot.json manifest.json; do
  if [ ! -f "$OUT_DIR/$f" ]; then
    echo "missing bundle file: $f"
    exit 1
  fi
done

python3 - "$OUT_DIR/manifest.json" <<'PY'
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
obj = json.loads(p.read_text(encoding="utf-8"))
if obj.get("overall_exit") != 0:
    raise SystemExit("overall_exit is not zero")
for key in ["doctor", "status", "snapshot"]:
    code = obj.get("commands", {}).get(key, {}).get("exit_code")
    if code != 0:
        raise SystemExit(f"{key} exit_code expected 0, got {code}")

status = json.loads((p.parent / "status.json").read_text(encoding="utf-8"))
snapshot = json.loads((p.parent / "snapshot.json").read_text(encoding="utf-8"))

required_browser_fields = [
    "backend_requested",
    "backend_selected",
    "backend_fallback_reason",
    "policy_allowlist",
    "policy_denylist",
    "policy_current_url",
    "last_policy_decision",
    "last_policy_reason",
]

browser_status = status.get("browser_runtime", {})
for field in required_browser_fields:
    if field not in browser_status:
        raise SystemExit(f"status.browser_runtime missing: {field}")

browser_snapshot = snapshot.get("browser_runtime", {})
for field in required_browser_fields:
    if field not in browser_snapshot:
        raise SystemExit(f"snapshot.browser_runtime missing: {field}")

required_approval_fields = ["requested", "approved", "denied", "blocked", "trace_events", "trace_file"]
for field in required_approval_fields:
    if field not in status.get("approval_counters", {}):
        raise SystemExit(f"status.approval_counters missing: {field}")
    if field not in snapshot.get("approval_counters", {}):
        raise SystemExit(f"snapshot.approval_counters missing: {field}")

trace_health = obj.get("trace_health", {})
required_trace_health_fields = [
    "trace_file",
    "trace_exists",
    "event_count",
    "parse_ok",
    "parse_errors",
    "status_snapshot_consistent",
    "approval_counters",
    "approval_anomaly",
]
for field in required_trace_health_fields:
    if field not in trace_health:
        raise SystemExit(f"manifest.trace_health missing: {field}")

for field in ["requested", "approved", "denied", "blocked", "trace_events"]:
    if field not in trace_health.get("approval_counters", {}):
        raise SystemExit(f"manifest.trace_health.approval_counters missing: {field}")

for field in ["anomaly_detected", "reason", "details"]:
    if field not in trace_health.get("approval_anomaly", {}):
        raise SystemExit(f"manifest.trace_health.approval_anomaly missing: {field}")

status_trace_file = str(status.get("approval_counters", {}).get("trace_file", ""))
snapshot_trace_file = str(snapshot.get("approval_counters", {}).get("trace_file", ""))
if trace_health.get("trace_file", "") not in (status_trace_file, snapshot_trace_file):
    raise SystemExit("manifest.trace_health.trace_file mismatch against status/snapshot")

if int(trace_health.get("event_count", -1)) != int(status.get("approval_counters", {}).get("trace_events", -2)):
    raise SystemExit("manifest.trace_health.event_count mismatch against status.approval_counters.trace_events")

kernel_policy_ready = obj.get("kernel_policy_ready", {})
required_kernel_policy_ready_fields = [
    "command",
    "exit_code",
    "parse_ok",
    "available",
    "overall_status",
    "operator_state",
    "blocking_checks",
    "warning_checks",
    "drift_checks",
    "summary",
    "recommended_actions",
]
for field in required_kernel_policy_ready_fields:
    if field not in kernel_policy_ready:
        raise SystemExit(f"manifest.kernel_policy_ready missing: {field}")

if not isinstance(kernel_policy_ready.get("overall_status", ""), str):
    raise SystemExit("manifest.kernel_policy_ready.overall_status must be a string")

if int(kernel_policy_ready.get("exit_code", -1)) < 0:
    raise SystemExit("manifest.kernel_policy_ready.exit_code must be >= 0")
if not isinstance(kernel_policy_ready.get("blocking_checks", []), list):
    raise SystemExit("manifest.kernel_policy_ready.blocking_checks must be a list")
if not isinstance(kernel_policy_ready.get("warning_checks", []), list):
    raise SystemExit("manifest.kernel_policy_ready.warning_checks must be a list")
if not isinstance(kernel_policy_ready.get("drift_checks", []), list):
    raise SystemExit("manifest.kernel_policy_ready.drift_checks must be a list")
if not isinstance(kernel_policy_ready.get("recommended_actions", []), list):
    raise SystemExit("manifest.kernel_policy_ready.recommended_actions must be a list")

readiness_summary = kernel_policy_ready.get("summary", {})
for field in ["total_checks", "passing_checks", "blocking_count", "warning_count", "drift_count"]:
    if field not in readiness_summary:
        raise SystemExit(f"manifest.kernel_policy_ready.summary missing: {field}")

kernel_policy_bridge = obj.get("kernel_policy_bridge", {})
required_kernel_policy_bridge_fields = [
    "available",
    "policy_dir",
    "profile_path",
    "profile_exists",
    "state_path",
    "state_exists",
    "lifecycle_path",
    "lifecycle_exists",
    "lifecycle_summary",
    "workspace_root_runtime",
    "workspace_root_state",
    "workspace_root_match",
    "browser_allowlist",
    "web_allowlist",
    "network_allowlist",
    "destructive_action_approval_required",
]
for field in required_kernel_policy_bridge_fields:
    if field not in kernel_policy_bridge:
        raise SystemExit(f"manifest.kernel_policy_bridge missing: {field}")

if not isinstance(kernel_policy_bridge.get("browser_allowlist", []), list):
    raise SystemExit("manifest.kernel_policy_bridge.browser_allowlist must be a list")
if not isinstance(kernel_policy_bridge.get("web_allowlist", []), list):
    raise SystemExit("manifest.kernel_policy_bridge.web_allowlist must be a list")
if not isinstance(kernel_policy_bridge.get("network_allowlist", []), list):
    raise SystemExit("manifest.kernel_policy_bridge.network_allowlist must be a list")
if not isinstance(kernel_policy_bridge.get("destructive_action_approval_required", True), bool):
    raise SystemExit("manifest.kernel_policy_bridge.destructive_action_approval_required must be bool")
lifecycle_summary = kernel_policy_bridge.get("lifecycle_summary", {})
for field in ["bridge_state", "drift_state", "reload_state", "disable_state", "operator_state"]:
    if field not in lifecycle_summary:
        raise SystemExit(f"manifest.kernel_policy_bridge.lifecycle_summary missing: {field}")

kernel_policy_shadow = obj.get("kernel_policy_shadow", {})
required_kernel_policy_shadow_fields = [
    "available",
    "command",
    "exit_code",
    "parse_ok",
    "policy_target",
    "runtime_trace_file",
    "shadow_event_file",
    "user_space_blocked_count",
    "shadow_detected_count",
    "comparison",
]
for field in required_kernel_policy_shadow_fields:
    if field not in kernel_policy_shadow:
        raise SystemExit(f"manifest.kernel_policy_shadow missing: {field}")

comparison = kernel_policy_shadow.get("comparison", {})
if not isinstance(comparison, dict):
    raise SystemExit("manifest.kernel_policy_shadow.comparison must be object")
if "aligned" not in comparison or "delta" not in comparison:
    raise SystemExit("manifest.kernel_policy_shadow.comparison missing aligned/delta")

event_fabric = obj.get("event_fabric", {})
required_event_fabric_fields = [
    "available",
    "event_file",
    "archive_file",
    "event_file_exists",
    "archive_file_exists",
    "total_events",
    "recent_kinds",
    "session_timeline",
    "process_lineage",
    "policy_evidence",
    "approval_forensics",
    "collector_coverage",
]
for field in required_event_fabric_fields:
    if field not in event_fabric:
        raise SystemExit(f"manifest.event_fabric missing: {field}")

session_timeline = event_fabric.get("session_timeline", {})
for field in ["matched_events", "returned_events", "recent_summaries"]:
    if field not in session_timeline:
        raise SystemExit(f"manifest.event_fabric.session_timeline missing: {field}")
for field in ["ownership_summary", "correlation_evidence"]:
    if field not in session_timeline:
        raise SystemExit(f"manifest.event_fabric.session_timeline missing: {field}")

process_lineage = event_fabric.get("process_lineage", {})
for field in ["matched_process_events", "returned_process_events", "root_pids", "node_count"]:
    if field not in process_lineage:
        raise SystemExit(f"manifest.event_fabric.process_lineage missing: {field}")

policy_evidence = event_fabric.get("policy_evidence", {})
for field in ["overall_aligned", "policy_targets"]:
    if field not in policy_evidence:
        raise SystemExit(f"manifest.event_fabric.policy_evidence missing: {field}")

approval_forensics = event_fabric.get("approval_forensics", {})
for field in ["summary", "correlation_evidence", "recent_events"]:
    if field not in approval_forensics:
        raise SystemExit(f"manifest.event_fabric.approval_forensics missing: {field}")

for field in [
    "approval_requested",
    "approval_approved",
    "approval_denied",
    "approval_blocked",
    "broker_override_count",
    "operator_control_count",
    "install_control_count",
    "recovery_bypass_active",
    "approval_ids_observed",
    "request_ids_observed",
    "forensic_status",
]:
    if field not in approval_forensics.get("summary", {}):
        raise SystemExit(f"manifest.event_fabric.approval_forensics.summary missing: {field}")

collector_coverage = event_fabric.get("collector_coverage", {})
for field in ["sample_limit", "sampled_events", "observed_sources", "source_counts", "observed_kinds", "kind_counts", "gaps", "retention"]:
    if field not in collector_coverage:
        raise SystemExit(f"manifest.event_fabric.collector_coverage missing: {field}")

gaps = collector_coverage.get("gaps", {})
for field in ["missing_expected_sources", "missing_systemd_unit_state", "missing_dbus_classification"]:
    if field not in gaps:
        raise SystemExit(f"manifest.event_fabric.collector_coverage.gaps missing: {field}")

retention_health = obj.get("retention_health", {})
required_retention_fields = [
    "policy",
    "archive_count",
    "archive_bytes",
    "oldest_archive_age_days",
    "pending_delete_count",
    "pending_delete_paths",
]
for field in required_retention_fields:
    if field not in retention_health:
        raise SystemExit(f"manifest.retention_health missing: {field}")

policy = retention_health.get("policy", {})
for field in ["retention_days", "keep_archives"]:
    if field not in policy:
        raise SystemExit(f"manifest.retention_health.policy missing: {field}")

if int(retention_health.get("archive_count", -1)) < 0:
    raise SystemExit("manifest.retention_health.archive_count must be >= 0")
if int(retention_health.get("pending_delete_count", -1)) < 0:
    raise SystemExit("manifest.retention_health.pending_delete_count must be >= 0")

governance_slo = obj.get("governance_slo", {})
for field in ["overall_state", "policy_pressure", "slo"]:
    if field not in governance_slo:
        raise SystemExit(f"manifest.governance_slo missing: {field}")

policy_pressure = governance_slo.get("policy_pressure", {})
for field in ["approval_requested", "approval_denied", "approval_blocked", "denied_rate", "approval_anomaly"]:
    if field not in policy_pressure:
        raise SystemExit(f"manifest.governance_slo.policy_pressure missing: {field}")

slo = governance_slo.get("slo", {})
for field in ["ok", "thresholds", "checks"]:
    if field not in slo:
        raise SystemExit(f"manifest.governance_slo.slo missing: {field}")

policy_actions = obj.get("policy_actions", {})
for field in ["overall_state", "action_count", "severity_counts", "actions"]:
    if field not in policy_actions:
        raise SystemExit(f"manifest.policy_actions missing: {field}")

if int(policy_actions.get("action_count", -1)) < 0:
    raise SystemExit("manifest.policy_actions.action_count must be >= 0")

severity_counts = policy_actions.get("severity_counts", {})
for field in ["info", "warn", "critical"]:
    if field not in severity_counts:
        raise SystemExit(f"manifest.policy_actions.severity_counts missing: {field}")

for action in policy_actions.get("actions", []):
    for field in ["id", "severity", "title", "reason", "recommended_command", "category", "auto_safe"]:
        if field not in action:
            raise SystemExit(f"manifest.policy_actions.actions[] missing: {field}")

policy_execution = obj.get("policy_execution", {})
for field in ["mode", "apply", "action_total", "would_execute", "executed", "skipped", "errors", "results"]:
    if field not in policy_execution:
        raise SystemExit(f"manifest.policy_execution missing: {field}")

for field in ["action_total", "would_execute", "executed", "skipped", "errors"]:
    if int(policy_execution.get(field, -1)) < 0:
        raise SystemExit(f"manifest.policy_execution.{field} must be >= 0")

for item in policy_execution.get("results", []):
    for field in ["action_id", "status", "reason", "command", "exit_code"]:
        if field not in item:
            raise SystemExit(f"manifest.policy_execution.results[] missing: {field}")

orchestration = obj.get("remediation_orchestration", {})
for field in ["mode", "plan", "execution", "rollback"]:
    if field not in orchestration:
        raise SystemExit(f"manifest.remediation_orchestration missing: {field}")

for field in ["action_total", "auto_safe_count", "manual_review_count", "critical_count", "sequence"]:
    if field not in orchestration.get("plan", {}):
        raise SystemExit(f"manifest.remediation_orchestration.plan missing: {field}")

for field in ["apply", "action_total", "executed", "would_execute", "skipped", "errors", "results"]:
    if field not in orchestration.get("execution", {}):
        raise SystemExit(f"manifest.remediation_orchestration.execution missing: {field}")

for field in ["required", "candidate_count", "candidates"]:
    if field not in orchestration.get("rollback", {}):
        raise SystemExit(f"manifest.remediation_orchestration.rollback missing: {field}")

autoremediation = obj.get("autoremediation", {})
for field in ["scheduler", "decision", "summary", "state", "preview"]:
    if field not in autoremediation:
        raise SystemExit(f"manifest.autoremediation missing: {field}")

for field in ["cooldown_sec", "max_consecutive_applies"]:
    if field not in autoremediation.get("scheduler", {}):
        raise SystemExit(f"manifest.autoremediation.scheduler missing: {field}")

for field in ["status", "reason", "next_allowed_epoch", "eligible_action_ids"]:
    if field not in autoremediation.get("decision", {}):
        raise SystemExit(f"manifest.autoremediation.decision missing: {field}")

for field in ["action_total", "auto_safe_action_count", "manual_review_count", "critical_count"]:
    if field not in autoremediation.get("summary", {}):
        raise SystemExit(f"manifest.autoremediation.summary missing: {field}")

for field in ["last_apply_epoch", "consecutive_applies"]:
    if field not in autoremediation.get("state", {}):
        raise SystemExit(f"manifest.autoremediation.state missing: {field}")

for field in ["command", "exit_code", "parse_ok", "execution_mode", "decision_status", "decision_reason"]:
    if field not in autoremediation.get("preview", {}):
        raise SystemExit(f"manifest.autoremediation.preview missing: {field}")

if int(autoremediation.get("preview", {}).get("exit_code", 99)) != 0:
    raise SystemExit("manifest.autoremediation.preview.exit_code must be 0")

autoremediation_cadence = obj.get("autoremediation_cadence", {})
for field in ["status", "reason", "next_allowed_epoch", "limits", "counts"]:
    if field not in autoremediation_cadence:
        raise SystemExit(f"manifest.autoremediation_cadence missing: {field}")

for field in ["min_interval_sec", "max_applies_per_hour", "max_applies_per_day"]:
    if field not in autoremediation_cadence.get("limits", {}):
        raise SystemExit(f"manifest.autoremediation_cadence.limits missing: {field}")

for field in ["applies_last_hour", "applies_last_day", "history_count"]:
    if field not in autoremediation_cadence.get("counts", {}):
        raise SystemExit(f"manifest.autoremediation_cadence.counts missing: {field}")

autoremediation_escalation = obj.get("autoremediation_escalation", {})
for field in ["should_escalate", "reason", "severity", "cooldown", "event"]:
    if field not in autoremediation_escalation:
        raise SystemExit(f"manifest.autoremediation_escalation missing: {field}")

for field in ["min_escalation_interval_sec", "last_escalation_epoch", "next_allowed_epoch"]:
    if field not in autoremediation_escalation.get("cooldown", {}):
        raise SystemExit(f"manifest.autoremediation_escalation.cooldown missing: {field}")

for field in [
    "title",
    "severity",
    "reason",
    "cadence_status",
    "cadence_reason",
    "scheduler_reason",
    "execution_errors",
    "hold_streak",
    "failure_streak",
    "timestamp_epoch",
]:
    if field not in autoremediation_escalation.get("event", {}):
        raise SystemExit(f"manifest.autoremediation_escalation.event missing: {field}")

autoremediation_governance = obj.get("autoremediation_governance", {})
for field in ["decision", "reason", "inputs", "preview"]:
    if field not in autoremediation_governance:
        raise SystemExit(f"manifest.autoremediation_governance missing: {field}")

for field in [
    "cycle_mode",
    "scheduler_status",
    "scheduler_reason",
    "cadence_status",
    "cadence_reason",
    "escalation_required",
    "escalation_reason",
    "hold_streak",
    "failure_streak",
]:
    if field not in autoremediation_governance.get("inputs", {}):
        raise SystemExit(f"manifest.autoremediation_governance.inputs missing: {field}")

for field in ["command", "exit_code", "parse_ok"]:
    if field not in autoremediation_governance.get("preview", {}):
        raise SystemExit(f"manifest.autoremediation_governance.preview missing: {field}")

if int(autoremediation_governance.get("preview", {}).get("exit_code", 99)) not in [0, 3, 5]:
    raise SystemExit("manifest.autoremediation_governance.preview.exit_code must be one of 0/3/5")

autoremediation_handoff = obj.get("autoremediation_handoff", {})
for field in ["handoff_required", "run_id", "summary", "recommended_actions"]:
    if field not in autoremediation_handoff:
        raise SystemExit(f"manifest.autoremediation_handoff missing: {field}")

for field in [
    "decision",
    "reason",
    "scheduler_status",
    "scheduler_reason",
    "cadence_status",
    "cadence_reason",
    "escalation_reason",
    "hold_streak",
    "failure_streak",
]:
    if field not in autoremediation_handoff.get("summary", {}):
        raise SystemExit(f"manifest.autoremediation_handoff.summary missing: {field}")

print("diagnostics bundle validation: PASS")
PY
