from __future__ import annotations

import json
import os
from pathlib import Path

from kernel.event_fabric.schema import os_event_log_path
from kernel.runtime.trace import resolve_runtime_trace_path


def policy_evidence_report(workspace_dir: str | Path, *, trace_file: str | Path = "", event_file: str | Path = "") -> dict:
    workspace = Path(workspace_dir).resolve()
    runtime_trace = Path(trace_file).resolve() if trace_file else resolve_runtime_trace_path(workspace)
    os_events = Path(event_file).resolve() if event_file else os_event_log_path(workspace)

    runtime_rows = _read_jsonl(runtime_trace)
    os_rows = _read_jsonl(os_events)

    user_counts = {
        "fs_workspace_boundary": _count_runtime_workspace_blocks(runtime_rows),
        "network_allowlist": _count_runtime_network_blocks(runtime_rows),
        "destructive_action_approval": _count_runtime_approval_requests(runtime_rows),
    }
    os_counts = {
        "fs_workspace_boundary": _count_os_events(os_rows, "file.outside_workspace_candidate"),
        "network_allowlist": _count_os_events(os_rows, "network.connect_candidate"),
        "destructive_action_approval": _count_os_approval_requests(os_rows),
    }
    enforced_pilot = _load_enforced_pilot(workspace)

    targets = []
    for target in ("fs_workspace_boundary", "network_allowlist", "destructive_action_approval"):
        user_count = user_counts[target]
        os_count = os_counts[target]
        target_enforced = {
            "configured": bool(enforced_pilot.get("configured_enabled", False))
            and str(enforced_pilot.get("policy_target", "")) == target,
            "effective": bool(enforced_pilot.get("effective_enabled", False))
            and str(enforced_pilot.get("policy_target", "")) == target,
        }
        targets.append(
            {
                "policy_target": target,
                "user_space_count": user_count,
                "os_evidence_count": os_count,
                "evidence_kind": _evidence_kind_for_target(target),
                "enforced_pilot": target_enforced,
                "comparison": {
                    "aligned": user_count == os_count,
                    "delta": os_count - user_count,
                    "status": _comparison_status(user_count, os_count),
                },
            }
        )

    return {
        "ok": True,
        "exit_code": 0,
        "workspace": str(workspace),
        "runtime_trace_file": str(runtime_trace),
        "os_event_file": str(os_events),
        "runtime_trace_events": len(runtime_rows),
        "os_event_rows": len(os_rows),
        "enforced_pilot": enforced_pilot,
        "policy_targets": targets,
        "overall_aligned": all(item["comparison"]["aligned"] for item in targets),
    }


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    items: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        row = line.strip()
        if not row:
            continue
        try:
            payload = json.loads(row)
        except Exception:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items


def _count_runtime_workspace_blocks(rows: list[dict]) -> int:
    count = 0
    for row in rows:
        if str(row.get("event", "")) != "step_blocked":
            continue
        payload = row.get("payload", {}) or {}
        reason = str(payload.get("reason", "")).lower()
        detail = str(payload.get("detail", "")).lower()
        if reason == "workspace_boundary" or "../" in detail or "workspace" in reason:
            count += 1
    return count


def _count_runtime_network_blocks(rows: list[dict]) -> int:
    count = 0
    for row in rows:
        if str(row.get("event", "")) != "step_blocked":
            continue
        payload = row.get("payload", {}) or {}
        reason = str(payload.get("reason", "")).lower()
        detail = str(payload.get("detail", "")).lower()
        if reason in {"network_allowlist", "web_domain_blocked", "browser_domain_blocked"}:
            count += 1
            continue
        if "allowlist" in reason or "domain" in reason or "network" in reason or "network" in detail:
            count += 1
    return count


def _count_runtime_approval_requests(rows: list[dict]) -> int:
    return sum(1 for row in rows if str(row.get("event", "")) == "approval_requested")


def _count_os_events(rows: list[dict], kind: str) -> int:
    return sum(1 for row in rows if str(row.get("kind", "")) == kind)


def _count_os_approval_requests(rows: list[dict]) -> int:
    count = 0
    for row in rows:
        if str(row.get("kind", "")) != "broker.approval_request":
            continue
        object_payload = row.get("object", {}) or {}
        decision = row.get("decision", {}) or {}
        request_kind = str(decision.get("request_kind", "")).strip()
        policy_target = str(object_payload.get("policy_target", "")).strip()
        if request_kind == "approval" or policy_target == "destructive_action_approval":
            count += 1
    return count


def _comparison_status(user_count: int, os_count: int) -> str:
    if user_count == os_count:
        return "aligned"
    if user_count == 0 and os_count > 0:
        return "os_only"
    if user_count > 0 and os_count == 0:
        return "userspace_only"
    return "divergent"


def _evidence_kind_for_target(target: str) -> str:
    if target == "fs_workspace_boundary":
        return "file.outside_workspace_candidate"
    if target == "network_allowlist":
        return "network.connect_candidate"
    return "broker.approval_request"


def _load_enforced_pilot(workspace: Path) -> dict:
    path = workspace / "artifacts" / "kernel-policy" / "enforced-pilot.json"
    configured_enabled = False
    policy_target = "fs_workspace_boundary"
    updated_at_utc = ""
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            configured_enabled = bool(payload.get("enabled", False))
            policy_target = str(payload.get("policy_target", policy_target))
            updated_at_utc = str(payload.get("updated_at_utc", ""))
        except Exception:
            pass
    env_disabled = os.environ.get("AGENTOS_KERNEL_POLICY_DISABLE", "").strip().lower() in {"1", "true", "yes", "on"}
    return {
        "config_file": str(path),
        "config_exists": path.exists(),
        "configured_enabled": configured_enabled,
        "effective_enabled": configured_enabled and not env_disabled,
        "env_disable_active": env_disabled,
        "policy_target": policy_target,
        "updated_at_utc": updated_at_utc,
    }
