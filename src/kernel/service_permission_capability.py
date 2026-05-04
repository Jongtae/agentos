from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from kernel.service_governance import build_service_governance_report
from scripts.kernel_approval_forensics import build_approval_forensics

CAPABILITY_ARTIFACT_DIRNAME = "capability-substrate"
SERVICE_CAPABILITY_SCHEMA_VERSION = "agentos-service-capability.v1"
PERMISSION_CAPABILITY_SCHEMA_VERSION = "agentos-permission-capability.v1"
SERVICE_PERMISSION_CAPABILITY_SURFACE_SCHEMA_VERSION = "agentos-service-permission-capability-surface.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def capability_artifact_root(workspace_dir: str | Path) -> Path:
    return Path(workspace_dir).resolve() / "artifacts" / CAPABILITY_ARTIFACT_DIRNAME


def _manifest_path(workspace_dir: str | Path, name: str) -> Path:
    root = capability_artifact_root(workspace_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / name


def _write_manifest(workspace_dir: str | Path, name: str, payload: dict) -> str:
    path = _manifest_path(workspace_dir, name)
    path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return str(path)


def _service_control_mode(item: dict) -> str:
    requirement = str(item.get("mediation_requirement", "")).strip()
    if requirement == "mandatory_broker":
        return "broker_mediated"
    if requirement == "approval_gated":
        return "broker_escalated_approval"
    return "native_direct"


def _permission_control_mode(event: dict) -> str:
    source = str(event.get("source", "")).strip()
    kind = str(event.get("kind", "")).strip()
    request_kind = str(event.get("request_kind", "")).strip()
    state = str(event.get("state", "")).strip()
    if source == "runtime_trace":
        return "native_policy_signal"
    if request_kind == "override" or state == "override":
        return "broker_override"
    if kind in {"broker.approval_request", "broker.approval_decision"} or request_kind == "approval":
        return "broker_approval_gate"
    if request_kind == "operator_control":
        return "broker_operator_control"
    return "broker_mediated"


def build_service_capability_report(workspace: str | Path, *, write_manifest: bool = True) -> dict:
    workspace_path = Path(workspace).resolve()
    governance = build_service_governance_report(workspace_path)
    inventory = governance.get("inventory") or []
    unit_counts = ((governance.get("evidence") or {}).get("unit_state_events") or {}).get("unit_counts") or {}
    operator_actions = (governance.get("evidence") or {}).get("operator_control_actions") or []

    units: list[dict] = []
    for item in inventory:
        control_mode = _service_control_mode(item)
        unit_name = str(item.get("unit", "")).strip()
        units.append(
            {
                "unit": unit_name,
                "role": str(item.get("role", "")).strip(),
                "actions": list(item.get("actions") or []),
                "approval_policy": str(item.get("approval_policy", "")).strip(),
                "evidence_sources": list(item.get("evidence_sources") or []),
                "native_status_handled": True,
                "native_control_available": control_mode == "native_direct",
                "broker_mediated_control": control_mode != "native_direct",
                "escalated_control_required": control_mode == "broker_escalated_approval",
                "control_handling": control_mode,
                "observed_unit_state_events": int(unit_counts.get(unit_name, 0)),
            }
        )

    actions_with_modes: list[dict] = []
    for event in operator_actions:
        unit_name = str(event.get("unit", "")).strip()
        unit = next((item for item in units if item.get("unit") == unit_name), None)
        actions_with_modes.append(
            {
                "timestamp_utc": str(event.get("timestamp_utc", "")),
                "action": str(event.get("action", "")),
                "state": str(event.get("state", "")),
                "unit": unit_name,
                "policy_target": str(event.get("policy_target", "")),
                "broker_mediated_control": True,
                "escalated_control_required": bool(unit and unit.get("escalated_control_required")),
                "control_handling": str((unit or {}).get("control_handling", "broker_mediated")),
            }
        )

    control_mode_counts: dict[str, int] = {}
    for item in units:
        control_mode = str(item.get("control_handling", "")).strip()
        control_mode_counts[control_mode] = control_mode_counts.get(control_mode, 0) + 1

    payload = {
        "schema_version": SERVICE_CAPABILITY_SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace_path),
        "capability_family": "service",
        "capability": "service_control",
        "native_status_visibility": True,
        "native_first_rule": "service state is visible natively while control is broker-mediated",
        "control_units": units,
        "governance_rule_ids": [str(rule.get("rule_id", "")) for rule in governance.get("governance_rules") or []],
        "evidence": {
            "observed_units": list(((governance.get("evidence") or {}).get("unit_state_events") or {}).get("observed_units") or []),
            "operator_control_actions": actions_with_modes[-20:],
        },
        "summary": {
            "total_units": len(units),
            "native_status_visible_units": len(units),
            "native_control_units": sum(1 for item in units if item.get("native_control_available")),
            "broker_mediated_control_units": sum(1 for item in units if item.get("broker_mediated_control")),
            "escalated_control_units": sum(1 for item in units if item.get("escalated_control_required")),
            "observed_unit_state_units": len((governance.get("evidence") or {}).get("unit_state_events", {}).get("observed_units", [])),
            "observed_operator_control_actions": len(actions_with_modes),
            "control_mode_counts": control_mode_counts,
        },
        "artifacts": {},
    }
    if write_manifest:
        payload["artifacts"]["latest_service_capability_manifest_json"] = _write_manifest(
            workspace_path,
            "latest-service-capability.json",
            payload,
        )
    return payload


def build_permission_capability_report(
    workspace: str | Path,
    *,
    session_id: str = "",
    limit: int = 50,
    write_manifest: bool = True,
) -> dict:
    workspace_path = Path(workspace).resolve()
    forensics = build_approval_forensics(workspace_path, session_id=session_id, limit=limit)
    recent_events = list(forensics.get("recent_events") or [])
    control_mode_counts: dict[str, int] = {}
    events: list[dict] = []
    for event in recent_events:
        control_mode = _permission_control_mode(event)
        control_mode_counts[control_mode] = control_mode_counts.get(control_mode, 0) + 1
        events.append(
            {
                "timestamp_utc": str(event.get("timestamp_utc", "")),
                "source": str(event.get("source", "")),
                "kind": str(event.get("kind", "")),
                "decision": str(event.get("decision", event.get("state", ""))),
                "request_kind": str(event.get("request_kind", "")),
                "approval_id": str(event.get("approval_id", "")),
                "request_id": str(event.get("request_id", "")),
                "reason": str(event.get("reason", "")),
                "broker_mediated_control": control_mode != "native_policy_signal",
                "escalated_control_required": control_mode in {"broker_approval_gate", "broker_override"},
                "control_handling": control_mode,
            }
        )

    summary = dict(forensics.get("summary") or {})
    payload = {
        "schema_version": PERMISSION_CAPABILITY_SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace_path),
        "capability_family": "permission",
        "capability": "approval_control",
        "session_filter": str(session_id),
        "native_policy_signal_supported": True,
        "broker_mediated_control_supported": True,
        "default_control_handling": "broker_approval_gate",
        "evidence": {
            "forensic_status": str(summary.get("forensic_status", "")),
            "recent_permission_events": events[-limit:],
            "correlation_evidence": dict(forensics.get("correlation_evidence") or {}),
        },
        "summary": {
            "approval_requested": int(summary.get("approval_requested", 0)),
            "approval_approved": int(summary.get("approval_approved", 0)),
            "approval_denied": int(summary.get("approval_denied", 0)),
            "approval_blocked": int(summary.get("approval_blocked", 0)),
            "broker_override_count": int(summary.get("broker_override_count", 0)),
            "operator_control_count": int(summary.get("operator_control_count", 0)),
            "install_control_count": int(summary.get("install_control_count", 0)),
            "native_policy_signal_events": int(control_mode_counts.get("native_policy_signal", 0)),
            "broker_mediated_events": sum(
                count for mode, count in control_mode_counts.items() if mode != "native_policy_signal"
            ),
            "escalated_permission_events": int(control_mode_counts.get("broker_approval_gate", 0))
            + int(control_mode_counts.get("broker_override", 0)),
            "control_mode_counts": control_mode_counts,
            "forensic_status": str(summary.get("forensic_status", "")),
        },
        "artifacts": {},
    }
    if write_manifest:
        payload["artifacts"]["latest_permission_capability_manifest_json"] = _write_manifest(
            workspace_path,
            "latest-permission-capability.json",
            payload,
        )
    return payload


def build_service_permission_capability_surface(
    workspace: str | Path,
    *,
    session_id: str = "",
    limit: int = 50,
    write_manifest: bool = True,
) -> dict:
    workspace_path = Path(workspace).resolve()
    service = build_service_capability_report(workspace_path, write_manifest=write_manifest)
    permission = build_permission_capability_report(
        workspace_path,
        session_id=session_id,
        limit=limit,
        write_manifest=write_manifest,
    )
    payload = {
        "schema_version": SERVICE_PERMISSION_CAPABILITY_SURFACE_SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace_path),
        "service_capability": service,
        "permission_capability": permission,
        "summary": {
            "service_broker_mediated_control_units": int((service.get("summary") or {}).get("broker_mediated_control_units", 0)),
            "service_escalated_control_units": int((service.get("summary") or {}).get("escalated_control_units", 0)),
            "permission_approval_requested": int((permission.get("summary") or {}).get("approval_requested", 0)),
            "permission_broker_override_count": int((permission.get("summary") or {}).get("broker_override_count", 0)),
            "permission_escalated_events": int((permission.get("summary") or {}).get("escalated_permission_events", 0)),
        },
        "artifacts": {},
    }
    if write_manifest:
        payload["artifacts"]["latest_service_permission_capability_surface_json"] = _write_manifest(
            workspace_path,
            "latest-service-permission-capability-surface.json",
            payload,
        )
    return payload
