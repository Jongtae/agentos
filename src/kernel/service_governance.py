from __future__ import annotations

from pathlib import Path

from kernel.event_fabric.report import query_events

SERVICE_GOVERNANCE_SCHEMA_VERSION = "agentos-service-governance.v1"


def _service_inventory() -> list[dict]:
    return [
        {
            "unit": "agentos-kernel.service",
            "role": "managed_session",
            "actions": ["start", "stop", "restart", "enable", "disable"],
            "mediation_requirement": "mandatory_broker",
            "approval_policy": "operator_control_change",
            "evidence_sources": ["journald", "dbus", "broker"],
        },
        {
            "unit": "agentos-firstrun.service",
            "role": "setup_session",
            "actions": ["start", "stop", "restart", "enable", "disable"],
            "mediation_requirement": "mandatory_broker",
            "approval_policy": "operator_control_change",
            "evidence_sources": ["journald", "dbus", "broker"],
        },
        {
            "unit": "agentos-eventd.service",
            "role": "event_fabric",
            "actions": ["start", "stop", "restart", "enable", "disable"],
            "mediation_requirement": "approval_gated",
            "approval_policy": "operator_control_change",
            "evidence_sources": ["journald", "dbus", "broker"],
        },
        {
            "unit": "agentos-brokerd.service",
            "role": "control_plane",
            "actions": ["start", "stop", "restart", "enable", "disable"],
            "mediation_requirement": "mandatory_broker",
            "approval_policy": "operator_control_change",
            "evidence_sources": ["journald", "dbus", "broker"],
        },
        {
            "unit": "getty@tty1.service",
            "role": "entry_boundary",
            "actions": ["override", "restart", "disable_override"],
            "mediation_requirement": "approval_gated",
            "approval_policy": "operator_control_change",
            "evidence_sources": ["journald", "dbus", "manual"],
        },
    ]


def _governance_rules() -> list[dict]:
    return [
        {
            "rule_id": "managed-session-services-mandatory-broker",
            "scope": ["agentos-kernel.service", "agentos-firstrun.service", "agentos-brokerd.service"],
            "actions": ["start", "stop", "restart", "enable", "disable"],
            "requirement": "mandatory_broker",
            "approval": "operator_control_change",
            "reason": "session and control-plane services define AgentOS entry and mediation ownership",
        },
        {
            "rule_id": "event-fabric-service-approval-gated",
            "scope": ["agentos-eventd.service"],
            "actions": ["start", "stop", "restart", "enable", "disable"],
            "requirement": "approval_gated",
            "approval": "operator_control_change",
            "reason": "event collection should remain operator-visible before broader mandatory mediation",
        },
        {
            "rule_id": "tty1-entry-boundary-approval",
            "scope": ["getty@tty1.service"],
            "actions": ["override", "restart", "disable_override"],
            "requirement": "approval_gated",
            "approval": "operator_control_change",
            "reason": "entry-boundary changes alter the managed session handoff path",
        },
    ]


def build_service_governance_report(workspace: str | Path) -> dict:
    workspace_path = Path(workspace).resolve()
    inventory = _service_inventory()
    rules = _governance_rules()
    unit_events = query_events(workspace_path, kind="systemd.unit_state", limit=100)
    broker_events = query_events(workspace_path, source="broker", limit=100)
    unit_counts: dict[str, int] = {}
    observed_units: list[str] = []
    for event in unit_events.get("events", []):
        unit = str((event.get("object") or {}).get("unit", "")).strip()
        if not unit:
            continue
        unit_counts[unit] = unit_counts.get(unit, 0) + 1
        if unit not in observed_units:
            observed_units.append(unit)
    operator_control_actions = []
    for event in broker_events.get("events", []):
        decision = event.get("decision") or {}
        if str(decision.get("request_kind", "")) != "operator_control":
            continue
        operator_control_actions.append(
            {
                "timestamp_utc": event.get("timestamp_utc", ""),
                "action": event.get("action", ""),
                "state": decision.get("state", ""),
                "unit": (event.get("object") or {}).get("unit", ""),
                "policy_target": (event.get("object") or {}).get("policy_target", ""),
            }
        )
    mandatory_units = sorted({item["unit"] for item in inventory if item["mediation_requirement"] == "mandatory_broker"})
    approval_gated_units = sorted({item["unit"] for item in inventory if item["mediation_requirement"] == "approval_gated"})
    coverage = {
        "inventory_units": len(inventory),
        "observed_units": len(observed_units),
        "operator_control_actions": len(operator_control_actions),
        "mandatory_broker_units": mandatory_units,
        "approval_gated_units": approval_gated_units,
    }
    return {
        "schema_version": SERVICE_GOVERNANCE_SCHEMA_VERSION,
        "workspace": str(workspace_path),
        "inventory": inventory,
        "governance_rules": rules,
        "evidence": {
            "unit_state_events": {
                "matched_events": unit_events.get("matched_events", 0),
                "observed_units": observed_units,
                "unit_counts": unit_counts,
            },
            "operator_control_actions": operator_control_actions[-20:],
        },
        "summary": coverage,
    }
