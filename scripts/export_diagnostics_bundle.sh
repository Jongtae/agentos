#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/src"

WORKSPACE_DIR="${1:-$ROOT_DIR/workspaces/default}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_DIR="${2:-$ROOT_DIR/artifacts/diagnostics/$STAMP}"

mkdir -p "$OUT_DIR"

run_capture() {
  local name="$1"
  shift

  set +e
  "$@" >"$OUT_DIR/${name}.stdout" 2>"$OUT_DIR/${name}.stderr"
  local rc=$?
  set -e

  printf "%s" "$rc" > "$OUT_DIR/${name}.exit"
}

run_capture doctor python3 src/main.py --workspace "$WORKSPACE_DIR" --doctor --json --doctor-file "$OUT_DIR/doctor.json"
run_capture status python3 src/main.py --workspace "$WORKSPACE_DIR" --status --json --status-file "$OUT_DIR/status.json"
run_capture snapshot python3 src/main.py --workspace "$WORKSPACE_DIR" --snapshot --snapshot-file "$OUT_DIR/snapshot.json"

DOCTOR_EXIT="$(cat "$OUT_DIR/doctor.exit")"
STATUS_EXIT="$(cat "$OUT_DIR/status.exit")"
SNAPSHOT_EXIT="$(cat "$OUT_DIR/snapshot.exit")"

OVERALL_EXIT=0
if [ "$DOCTOR_EXIT" -ne 0 ] || [ "$STATUS_EXIT" -ne 0 ] || [ "$SNAPSHOT_EXIT" -ne 0 ]; then
  OVERALL_EXIT=1
fi

python3 - "$OUT_DIR" "$WORKSPACE_DIR" "$DOCTOR_EXIT" "$STATUS_EXIT" "$SNAPSHOT_EXIT" "$OVERALL_EXIT" <<'PY'
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from kernel.runtime.autoremediation_scheduler import autoremediation_scheduler_report
from kernel.runtime.governance import governance_report
from kernel.runtime.policy_actions import policy_actions_report
from kernel.runtime.policy_executor import execute_policy_actions
from kernel.runtime.remediation_orchestrator import remediation_orchestration_report
from kernel.runtime.retention import retention_health_summary, retention_policy_from_env
from kernel.event_fabric.policy_evidence import policy_evidence_report
from kernel.event_fabric.report import event_coverage_summary, query_events, query_process_lineage, query_session_timeline
from kernel_approval_forensics import build_approval_forensics
from workspace.manager import WorkspaceManager

out_dir = Path(sys.argv[1])
workspace = sys.argv[2]
doctor_exit = int(sys.argv[3])
status_exit = int(sys.argv[4])
snapshot_exit = int(sys.argv[5])
overall_exit = int(sys.argv[6])

def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _trace_parse_summary(trace_file: str) -> dict:
    p = Path(trace_file) if trace_file else Path("")
    if not trace_file:
        return {"parse_ok": False, "parse_errors": 0}
    if not p.exists():
        return {"parse_ok": False, "parse_errors": 0}

    errors = 0
    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                errors += 1
                continue
            if not isinstance(obj, dict):
                errors += 1
                continue
            if "timestamp_utc" not in obj or "event" not in obj:
                errors += 1
    except Exception:
        return {"parse_ok": False, "parse_errors": 1}

    return {"parse_ok": errors == 0, "parse_errors": errors}

def _approval_health(status_obj: dict, snapshot_obj: dict) -> dict:
    status_counters = status_obj.get("approval_counters", {}) or {}
    snapshot_counters = snapshot_obj.get("approval_counters", {}) or {}

    trace_file = str(status_counters.get("trace_file") or snapshot_counters.get("trace_file") or "")
    trace_exists = bool(trace_file) and Path(trace_file).exists()

    base = status_counters if status_counters else snapshot_counters
    counters = {
        "requested": int(base.get("requested", 0)),
        "approved": int(base.get("approved", 0)),
        "denied": int(base.get("denied", 0)),
        "blocked": int(base.get("blocked", 0)),
        "trace_events": int(base.get("trace_events", 0)),
    }
    anomaly = {
        "anomaly_detected": bool(base.get("anomaly_detected", False)),
        "reason": str(base.get("reason", "")),
        "details": str(base.get("details", "")),
    }

    consistency_keys = ["requested", "approved", "denied", "blocked", "trace_events", "trace_file"]
    consistent = all(status_counters.get(k) == snapshot_counters.get(k) for k in consistency_keys)

    parse_summary = _trace_parse_summary(trace_file)
    return {
        "trace_file": trace_file,
        "trace_exists": trace_exists,
        "event_count": counters["trace_events"],
        "parse_ok": parse_summary["parse_ok"],
        "parse_errors": parse_summary["parse_errors"],
        "status_snapshot_consistent": bool(consistent),
        "approval_counters": counters,
        "approval_anomaly": anomaly,
    }

def _autoremediation_cycle_preview(workspace: str) -> dict:
    cmd = [
        "python3",
        "scripts/runtime_autoremediation_cycle.py",
        "--workspace",
        workspace,
        "--dry-run",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except Exception as exc:
        return {
            "command": " ".join(cmd),
            "exit_code": 1,
            "parse_ok": False,
            "error": str(exc),
        }

    payload = {}
    parse_ok = False
    if proc.stdout.strip():
        try:
            payload = json.loads(proc.stdout.strip())
            parse_ok = isinstance(payload, dict)
        except Exception:
            parse_ok = False

    return {
        "command": " ".join(cmd),
        "exit_code": int(proc.returncode),
        "parse_ok": bool(parse_ok),
        "payload": payload if isinstance(payload, dict) else {},
    }

def _autoremediation_supervisor_preview(workspace: str) -> dict:
    cmd = [
        "python3",
        "scripts/runtime_autoremediation_supervisor.py",
        "--workspace",
        workspace,
        "--dry-run",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except Exception as exc:
        return {
            "command": " ".join(cmd),
            "exit_code": 1,
            "parse_ok": False,
            "error": str(exc),
        }

    payload = {}
    parse_ok = False
    if proc.stdout.strip():
        try:
            payload = json.loads(proc.stdout.strip())
            parse_ok = isinstance(payload, dict)
        except Exception:
            parse_ok = False

    return {
        "command": " ".join(cmd),
        "exit_code": int(proc.returncode),
        "parse_ok": bool(parse_ok),
        "payload": payload if isinstance(payload, dict) else {},
    }

status_obj = _load_json(out_dir / "status.json")
snapshot_obj = _load_json(out_dir / "snapshot.json")
policy = retention_policy_from_env(default_days=7, default_keep_archives=1)
trace_file_for_retention = str(
    (status_obj.get("approval_counters", {}) or {}).get("trace_file")
    or (snapshot_obj.get("approval_counters", {}) or {}).get("trace_file")
    or ""
)
retention_health = retention_health_summary(
    trace_file=Path(trace_file_for_retention) if trace_file_for_retention else (Path(workspace) / "artifacts" / "runtime_trace.jsonl"),
    retention_days=int(policy["retention_days"]),
    keep_archives=int(policy["keep_archives"]),
)
gov = governance_report(workspace_dir=Path(workspace))
actions = policy_actions_report(workspace_dir=Path(workspace))
execution = execute_policy_actions(
    actions=actions.get("actions", []),
    workspace_dir=Path(workspace),
    apply=False,
    max_actions=10,
)
orchestration = remediation_orchestration_report(
    workspace_dir=Path(workspace),
    apply=False,
    max_actions=10,
)
autoremediation_scheduler = autoremediation_scheduler_report(
    workspace_dir=Path(workspace),
    trace_file=Path(trace_file_for_retention) if trace_file_for_retention else None,
)
autoremediation_cycle_preview = _autoremediation_cycle_preview(workspace)
cycle_payload = autoremediation_cycle_preview.get("payload", {}) or {}
cycle_scheduler = cycle_payload.get("scheduler", {}) or {}
cycle_decision = (cycle_scheduler.get("decision", {}) or {}) if isinstance(cycle_scheduler, dict) else {}
cycle_cadence = cycle_payload.get("cadence", {}) or {}
cycle_escalation = cycle_payload.get("escalation", {}) or {}
autoremediation_supervisor_preview = _autoremediation_supervisor_preview(workspace)
supervisor_payload = autoremediation_supervisor_preview.get("payload", {}) or {}
supervisor_governance = supervisor_payload.get("governance", {}) or {}
supervisor_handoff = supervisor_payload.get("handoff", {}) or {}

manifest = {
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "workspace": workspace,
    "bundle_dir": str(out_dir),
    "overall_exit": overall_exit,
    "commands": {
        "doctor": {"exit_code": doctor_exit, "json_file": "doctor.json"},
        "status": {"exit_code": status_exit, "json_file": "status.json"},
        "snapshot": {"exit_code": snapshot_exit, "json_file": "snapshot.json"},
    },
    "trace_health": _approval_health(status_obj, snapshot_obj),
    "kernel_policy_ready": kernel_policy_ready,
    "kernel_policy_shadow": kernel_policy_shadow,
    "kernel_policy_bridge": kernel_policy_bridge,
    "event_fabric": event_fabric,
    "retention_health": retention_health,
    "governance_slo": {
        "overall_state": gov.get("overall_state", "WARN"),
        "policy_pressure": gov.get("policy_pressure", {}),
        "slo": gov.get("slo", {}),
    },
    "policy_actions": {
        "overall_state": actions.get("overall_state", "WARN"),
        "action_count": int(actions.get("action_count", 0)),
        "severity_counts": actions.get("severity_counts", {}),
        "actions": actions.get("actions", []),
    },
    "policy_execution": {
        "mode": "dry-run",
        "apply": bool(execution.get("apply", False)),
        "action_total": int(execution.get("action_total", 0)),
        "would_execute": int(execution.get("would_execute", 0)),
        "executed": int(execution.get("executed", 0)),
        "skipped": int(execution.get("skipped", 0)),
        "errors": int(execution.get("errors", 0)),
        "results": execution.get("results", []),
    },
    "remediation_orchestration": {
        "mode": orchestration.get("mode", "dry-run"),
        "plan": orchestration.get("plan", {}),
        "execution": orchestration.get("execution", {}),
        "rollback": orchestration.get("rollback", {}),
    },
    "autoremediation": {
        "scheduler": {
            "cooldown_sec": int((autoremediation_scheduler.get("scheduler", {}) or {}).get("cooldown_sec", 0)),
            "max_consecutive_applies": int((autoremediation_scheduler.get("scheduler", {}) or {}).get("max_consecutive_applies", 0)),
        },
        "decision": autoremediation_scheduler.get("decision", {}),
        "summary": autoremediation_scheduler.get("summary", {}),
        "state": autoremediation_scheduler.get("state", {}),
        "preview": {
            "command": str(autoremediation_cycle_preview.get("command", "")),
            "exit_code": int(autoremediation_cycle_preview.get("exit_code", 1)),
            "parse_ok": bool(autoremediation_cycle_preview.get("parse_ok", False)),
            "execution_mode": str(cycle_payload.get("execution_mode", "")),
            "decision_status": str(cycle_decision.get("status", "")),
            "decision_reason": str(cycle_decision.get("reason", "")),
        },
    },
    "autoremediation_cadence": {
        "status": str(cycle_cadence.get("status", "")),
        "reason": str(cycle_cadence.get("reason", "")),
        "next_allowed_epoch": int(cycle_cadence.get("next_allowed_epoch", 0) or 0),
        "limits": cycle_cadence.get("limits", {}),
        "counts": cycle_cadence.get("counts", {}),
    },
    "autoremediation_escalation": {
        "should_escalate": bool(cycle_escalation.get("should_escalate", False)),
        "reason": str(cycle_escalation.get("reason", "")),
        "severity": str(cycle_escalation.get("severity", "")),
        "cooldown": cycle_escalation.get("cooldown", {}),
        "event": cycle_escalation.get("event", {}),
    },
    "autoremediation_governance": {
        "decision": str(supervisor_governance.get("decision", "")),
        "reason": str(supervisor_governance.get("reason", "")),
        "inputs": supervisor_governance.get("inputs", {}),
        "preview": {
            "command": str(autoremediation_supervisor_preview.get("command", "")),
            "exit_code": int(autoremediation_supervisor_preview.get("exit_code", 1)),
            "parse_ok": bool(autoremediation_supervisor_preview.get("parse_ok", False)),
        },
    },
    "autoremediation_handoff": {
        "handoff_required": bool(supervisor_handoff.get("handoff_required", False)),
        "run_id": str(supervisor_handoff.get("run_id", "")),
        "summary": supervisor_handoff.get("summary", {}),
        "recommended_actions": supervisor_handoff.get("recommended_actions", []),
    },
}

(out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=True) + "\n", encoding="utf-8")
PY

cat <<MSG
Diagnostics bundle written: $OUT_DIR
- doctor.json   (exit: $DOCTOR_EXIT)
- status.json   (exit: $STATUS_EXIT)
- snapshot.json (exit: $SNAPSHOT_EXIT)
- manifest.json
MSG

exit "$OVERALL_EXIT"
