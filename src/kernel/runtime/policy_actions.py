from __future__ import annotations

from pathlib import Path

from kernel.runtime.governance import governance_report


def policy_actions_report(workspace_dir: Path, trace_file: Path | None = None) -> dict:
    gov = governance_report(workspace_dir=workspace_dir, trace_file=trace_file)
    actions = generate_policy_actions(gov)
    severity_counts = {"info": 0, "warn": 0, "critical": 0}
    for item in actions:
        sev = str(item.get("severity", "info"))
        if sev not in severity_counts:
            severity_counts[sev] = 0
        severity_counts[sev] += 1

    return {
        "ok": True,
        "workspace": gov.get("workspace", str(Path(workspace_dir).resolve())),
        "overall_state": gov.get("overall_state", "WARN"),
        "action_count": len(actions),
        "severity_counts": severity_counts,
        "actions": actions,
    }


def generate_policy_actions(governance_payload: dict) -> list[dict]:
    actions: list[dict] = []
    pressure = governance_payload.get("policy_pressure", {}) or {}
    slo = governance_payload.get("slo", {}) or {}
    checks = slo.get("checks", {}) or {}
    anomaly = pressure.get("approval_anomaly", {}) or {}

    if bool(anomaly.get("anomaly_detected", False)):
        actions.append(
            _action(
                action_id="approval_anomaly_triage",
                severity="critical",
                title="Approval anomaly detected",
                reason=f"{anomaly.get('reason', '')}: {anomaly.get('details', '')}".strip(": "),
                recommended_command="python3 scripts/runtime_governance_report.py --workspace ./workspaces/default",
                category="approval",
                auto_safe=False,
            )
        )

    if not bool(checks.get("denied_rate_ok", True)):
        actions.append(
            _action(
                action_id="reduce_denied_rate",
                severity="warn",
                title="Denied-rate SLO breached",
                reason="approval denied rate is above threshold",
                recommended_command="python src/main.py --status --json",
                category="slo",
                auto_safe=False,
            )
        )

    if not bool(checks.get("blocked_steps_ok", True)):
        actions.append(
            _action(
                action_id="reduce_blocked_steps",
                severity="warn",
                title="Blocked-steps SLO breached",
                reason="blocked tool invocations exceeded threshold",
                recommended_command="python src/main.py --trace-status --json",
                category="slo",
                auto_safe=False,
            )
        )

    if not bool(checks.get("retention_pending_ok", True)):
        actions.append(
            _action(
                action_id="run_retention_apply",
                severity="warn",
                title="Retention backlog above threshold",
                reason="pending trace retention deletes exceeded threshold",
                recommended_command="python3 scripts/runtime_trace_retention.py --workspace ./workspaces/default --apply",
                category="retention",
                auto_safe=True,
            )
        )

    if not actions:
        actions.append(
            _action(
                action_id="no_action_required",
                severity="info",
                title="No remediation action required",
                reason="governance and SLO checks are within thresholds",
                recommended_command="python3 scripts/runtime_governance_report.py --workspace ./workspaces/default",
                category="summary",
                auto_safe=True,
            )
        )

    return actions


def _action(
    action_id: str,
    severity: str,
    title: str,
    reason: str,
    recommended_command: str,
    category: str,
    auto_safe: bool,
) -> dict:
    return {
        "id": action_id,
        "severity": severity,
        "title": title,
        "reason": reason,
        "recommended_command": recommended_command,
        "category": category,
        "auto_safe": bool(auto_safe),
    }
