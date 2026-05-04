from __future__ import annotations

import os
from pathlib import Path

from kernel.runtime.retention import retention_health_summary, retention_policy_from_env
from kernel.runtime.trace import (
    approval_anomaly_from_counters,
    approval_counters_from_trace,
    resolve_runtime_trace_path,
)


def governance_report(workspace_dir: Path, trace_file: Path | None = None) -> dict:
    workspace = Path(workspace_dir)
    trace_path = Path(trace_file) if trace_file else resolve_runtime_trace_path(workspace)

    counters = approval_counters_from_trace(trace_path)
    anomaly = approval_anomaly_from_counters(counters)
    policy = retention_policy_from_env(default_days=7, default_keep_archives=1)
    retention = retention_health_summary(
        trace_file=trace_path,
        retention_days=int(policy["retention_days"]),
        keep_archives=int(policy["keep_archives"]),
    )

    requested = int(counters.get("requested", 0))
    denied = int(counters.get("denied", 0))
    blocked = int(counters.get("blocked", 0))
    denied_rate = float(denied / requested) if requested > 0 else 0.0

    slo = _slo_summary(
        denied_rate=denied_rate,
        blocked=blocked,
        pending_delete_count=int(retention.get("pending_delete_count", 0)),
    )

    pressure = {
        "approval_requested": requested,
        "approval_denied": denied,
        "approval_blocked": blocked,
        "denied_rate": round(denied_rate, 4),
        "approval_anomaly": anomaly,
    }

    overall_state = "PASS" if slo["ok"] and not anomaly.get("anomaly_detected", False) else "WARN"
    return {
        "ok": True,
        "workspace": str(workspace.resolve()),
        "trace_file": str(trace_path),
        "policy_pressure": pressure,
        "retention_health": retention,
        "slo": slo,
        "overall_state": overall_state,
    }


def _slo_summary(denied_rate: float, blocked: int, pending_delete_count: int) -> dict:
    thresholds = {
        "max_denied_rate": _env_float("AGENTOS_SLO_MAX_DENIED_RATE", 0.50),
        "max_blocked_steps": _env_int("AGENTOS_SLO_MAX_BLOCKED_STEPS", 5),
        "max_retention_pending": _env_int("AGENTOS_SLO_MAX_RETENTION_PENDING", 3),
    }
    checks = {
        "denied_rate_ok": denied_rate <= thresholds["max_denied_rate"],
        "blocked_steps_ok": blocked <= thresholds["max_blocked_steps"],
        "retention_pending_ok": pending_delete_count <= thresholds["max_retention_pending"],
    }
    return {
        "ok": bool(all(checks.values())),
        "thresholds": thresholds,
        "checks": checks,
    }


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except Exception:
        return default
