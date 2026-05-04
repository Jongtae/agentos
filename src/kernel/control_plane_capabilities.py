from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from kernel.broker.daemon import broker_activity_summary, brokerd_report
from kernel.broker.schema import broker_contract
from kernel.event_fabric.correlation import normalize_correlation_context
from kernel.event_fabric.report import query_events, query_session_timeline
from kernel.policies.approval_rules import PolicyEngine
from kernel.service_governance import build_service_governance_report

SERVICE_CAPABILITY_SCHEMA = "agentos-service-capability.v1"
PERMISSION_CAPABILITY_SCHEMA = "agentos-permission-capability.v1"
EXECUTION_OWNERSHIP_SCHEMA = "agentos-capability-execution-ownership.v1"
VM_E2E_PROOF_SCHEMA = "agentos-vm-e2e-proof.v1"

PERMISSION_STATES = (
    "available",
    "approval_required",
    "temporarily_blocked",
    "escalated_only",
    "unsupported_or_deferred",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _artifact_root(workspace_dir: str | Path) -> Path:
    root = Path(workspace_dir).resolve() / "artifacts" / "control-plane-capabilities"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_manifest(workspace_dir: str | Path, name: str, payload: dict) -> str:
    path = _artifact_root(workspace_dir) / name
    path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return str(path)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_service_capability_report(workspace_dir: str | Path, *, write_manifest: bool = True) -> dict:
    workspace = Path(workspace_dir).resolve()
    governance = build_service_governance_report(workspace)
    broker = brokerd_report(workspace)
    inventory = list(governance.get("inventory", []) or [])
    summary = dict(governance.get("summary", {}) or {})
    operator_actions = list((governance.get("evidence", {}) or {}).get("operator_control_actions", []) or [])

    payload = {
        "schema_version": SERVICE_CAPABILITY_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "service_permission",
        "capability": "service_capability",
        "native_capability_broker_path": True,
        "escalated_app_interface_path": "manual_operator_or_external_service_interface",
        "service_inventory": inventory,
        "broker_contract": broker_contract(),
        "broker_status": {
            "ok": bool(broker.get("ok", False)),
            "artifacts_ready": bool(broker.get("artifacts_ready", False)),
            "managed_paths": list(broker.get("managed_paths", []) or []),
        },
        "evidence": {
            "operator_control_actions": operator_actions[-20:],
            "mandatory_broker_units": list(summary.get("mandatory_broker_units", []) or []),
            "approval_gated_units": list(summary.get("approval_gated_units", []) or []),
        },
        "proof": {
            "ok": True,
            "native_service_handled": bool(summary.get("mandatory_broker_units")),
            "native_service_units": list(summary.get("mandatory_broker_units", []) or []),
            "approval_gated_units": list(summary.get("approval_gated_units", []) or []),
            "escalated_control_path": "manual_operator_or_external_service_interface",
            "control_escalation_reason": "service_not_yet_mapped_to_broker_capability" if not summary.get("mandatory_broker_units") else "",
            "control_mediation_cost": "medium",
        },
        "artifacts": {},
    }
    if write_manifest:
        payload["artifacts"]["latest_service_capability_manifest_json"] = _write_manifest(
            workspace,
            "latest-service-capability.json",
            payload,
        )
    return payload


def build_permission_capability_report(workspace_dir: str | Path, *, write_manifest: bool = True) -> dict:
    workspace = Path(workspace_dir).resolve()
    activity = broker_activity_summary(workspace, limit=20)
    approval_requests = query_events(workspace, kind="broker.approval_request", limit=20)
    approval_decisions = query_events(workspace, kind="broker.approval_decision", limit=20)
    operator_decisions = query_events(workspace, kind="broker.exec_decision", limit=20)

    policy_targets: dict[str, dict] = {}
    for event in (approval_requests.get("events", []) or []) + (approval_decisions.get("events", []) or []):
        obj = dict(event.get("object") or {})
        decision = dict(event.get("decision") or {})
        target = str(obj.get("policy_target", "")).strip() or "unspecified"
        entry = policy_targets.setdefault(
            target,
            {
                "policy_target": target,
                "permission_state": "approval_required",
                "approval_requests": 0,
                "approval_decisions": 0,
                "last_reason": "",
                "path_available": "broker_mediated",
            },
        )
        if str(event.get("kind", "")) == "broker.approval_request":
            entry["approval_requests"] += 1
            entry["last_reason"] = str(decision.get("reason", "")) or str(obj.get("risk_reason", ""))
        else:
            entry["approval_decisions"] += 1
            state = str(decision.get("state", "")).strip()
            if state == "approved":
                entry["permission_state"] = "available"
            elif state == "denied":
                entry["permission_state"] = "temporarily_blocked"
            entry["last_reason"] = str(decision.get("reason", ""))

    for event in operator_decisions.get("events", []) or []:
        obj = dict(event.get("object") or {})
        decision = dict(event.get("decision") or {})
        target = str(obj.get("policy_target", "")).strip()
        if not target:
            continue
        entry = policy_targets.setdefault(
            target,
            {
                "policy_target": target,
                "permission_state": "available",
                "approval_requests": 0,
                "approval_decisions": 0,
                "last_reason": "",
                "path_available": "broker_mediated",
            },
        )
        state = str(decision.get("state", "")).strip()
        if state == "override":
            entry["permission_state"] = "escalated_only"
        elif state == "blocked":
            entry["permission_state"] = "temporarily_blocked"
        entry["last_reason"] = str(decision.get("reason", ""))

    payload = {
        "schema_version": PERMISSION_CAPABILITY_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "capability_family": "service_permission",
        "capability": "permission_capability",
        "permission_states_supported": list(PERMISSION_STATES),
        "native_capability_broker_path": True,
        "escalated_app_interface_path": "manual_operator_or_external_service_interface",
        "permission_targets": sorted(policy_targets.values(), key=lambda item: item["policy_target"]),
        "broker_activity": activity,
        "proof": {
            "ok": True,
            "native_permission_handled": bool(policy_targets),
            "broker_mediated_targets": sorted(policy_targets.keys()),
            "escalated_control_path": "manual_operator_or_external_service_interface",
            "control_escalation_reason": "",
            "control_mediation_cost": "medium",
        },
        "artifacts": {},
    }
    if write_manifest:
        payload["artifacts"]["latest_permission_capability_manifest_json"] = _write_manifest(
            workspace,
            "latest-permission-capability.json",
            payload,
        )
    return payload


def execution_resolution_contract() -> dict:
    return {
        "schema_version": EXECUTION_OWNERSHIP_SCHEMA,
        "resolution_order": [
            "native_capability_handler",
            "broker_mediated_privileged_path",
            "external_adapter",
        ],
        "permission_states": list(PERMISSION_STATES),
        "compatibility_policy": "existing tool paths remain valid but are described through capability-selected paths",
    }


def classify_execution_path(step, policy: PolicyEngine) -> dict:
    tool_name = str(getattr(step, "tool_name", "")).strip()
    capability = "tool_execution"
    selected_path = "native_capability_handler"
    external_adapter_required = False
    escalation_reason = ""

    if tool_name in {"file_read"}:
        capability = "document_access"
    elif tool_name in {"web_fetch"}:
        capability = "web_access"
    elif tool_name in {"browser_run"}:
        capability = "web_access"
        selected_path = "external_adapter"
        external_adapter_required = True
        escalation_reason = "browser_navigation_required"
    elif tool_name in {"bash", "file_write"}:
        capability = "brokered_tool_execution"
        selected_path = "broker_mediated_privileged_path"
    elif tool_name.startswith("service_") or tool_name in {"operator_control", "install_control"}:
        capability = "service_capability"
        selected_path = "broker_mediated_privileged_path"

    if policy.is_blocked(step):
        permission_state = "temporarily_blocked"
        capability_execution_ready = False
    elif policy.requires_approval(step):
        permission_state = "approval_required"
        capability_execution_ready = False
        if selected_path == "native_capability_handler":
            selected_path = "broker_mediated_privileged_path"
    else:
        permission_state = "available" if selected_path != "external_adapter" else "escalated_only"
        capability_execution_ready = selected_path != "external_adapter"

    broker_mediated = selected_path == "broker_mediated_privileged_path"
    if selected_path == "external_adapter" and not escalation_reason:
        escalation_reason = "external_adapter_required"

    return {
        "capability": capability,
        "capability_selected_path": selected_path,
        "permission_state": permission_state,
        "broker_mediated": broker_mediated,
        "external_adapter_required": external_adapter_required,
        "capability_execution_ready": capability_execution_ready,
        "control_escalation_reason": escalation_reason,
        "control_mediation_cost": "high" if external_adapter_required else ("medium" if broker_mediated else "low"),
    }


def build_execution_ownership_report(workspace_dir: str | Path, *, samples: list[dict] | None = None, write_manifest: bool = True) -> dict:
    workspace = Path(workspace_dir).resolve()
    payload = {
        "schema_version": EXECUTION_OWNERSHIP_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "contract": execution_resolution_contract(),
        "sampled_execution_paths": samples or [],
        "summary": {
            "native_capability_handler_count": sum(1 for item in samples or [] if item.get("capability_selected_path") == "native_capability_handler"),
            "broker_mediated_count": sum(1 for item in samples or [] if item.get("broker_mediated")),
            "external_adapter_count": sum(1 for item in samples or [] if item.get("external_adapter_required")),
            "approval_required_count": sum(1 for item in samples or [] if item.get("permission_state") == "approval_required"),
        },
        "artifacts": {},
    }
    if write_manifest:
        payload["artifacts"]["latest_execution_ownership_manifest_json"] = _write_manifest(
            workspace,
            "latest-execution-ownership.json",
            payload,
        )
    return payload


def build_vm_e2e_proof_report(
    workspace_dir: str | Path,
    *,
    runtime_report: dict | None = None,
    capability_proof: dict | None = None,
    service_capability: dict | None = None,
    permission_capability: dict | None = None,
    execution_ownership: dict | None = None,
    session_id: str = "",
    write_manifest: bool = True,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    runtime_report = runtime_report or {}
    capability_proof = capability_proof or {}
    service_capability = service_capability or {}
    permission_capability = permission_capability or {}
    execution_ownership = execution_ownership or {}
    sessions = query_session_timeline(workspace, session_id=session_id, limit=20)
    correlation = normalize_correlation_context(dict(sessions.get("correlation_evidence") or {}))

    service_schema = str(service_capability.get("schema_version", ""))
    permission_schema = str(permission_capability.get("schema_version", ""))
    service_ok = bool(service_capability.get("proof", {}).get("ok", False))
    if service_schema == "agentos-service-capability.v1":
        service_ok = "broker_mediated_control_units" in (service_capability.get("summary") or {})
    permission_ok = bool(permission_capability.get("proof", {}).get("ok", False))
    if permission_schema == "agentos-permission-capability.v1":
        permission_ok = "approval_requested" in (permission_capability.get("summary") or {})

    summary = {
        "vm_e2e_runtime_ok": bool(runtime_report.get("ok", False)),
        "vm_e2e_capability_ok": bool((capability_proof.get("summary") or {}).get("document_native_handled", False))
        and bool(
            (capability_proof.get("summary") or {}).get("web_native_handled", False)
            or (capability_proof.get("summary") or {}).get("web_escalated_handled", False)
        ),
        "vm_e2e_intake_ok": bool((capability_proof.get("intake_surface") or {}).get("summary", {}).get("ok", False)),
        "vm_e2e_service_permission_ok": service_ok and permission_ok,
        "vm_e2e_escalation_integrity_ok": all(
            not item.get("external_adapter_required") or str(item.get("control_escalation_reason", "")).strip()
            for item in (execution_ownership.get("sampled_execution_paths") or [])
        ),
    }
    failure_classes: list[str] = []
    if not summary["vm_e2e_runtime_ok"]:
        failure_classes.append("runtime_entry_failure")
    if not summary["vm_e2e_capability_ok"]:
        failure_classes.append("capability_native_regression")
    if not summary["vm_e2e_service_permission_ok"]:
        failure_classes.append("broker_mediation_regression")
    if not summary["vm_e2e_intake_ok"] or not any(correlation.values()):
        failure_classes.append("session_correlation_regression")
    if not summary["vm_e2e_escalation_integrity_ok"]:
        failure_classes.append("escalated_path_without_reason")

    payload = {
        "schema_version": VM_E2E_PROOF_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "scenario_contract": [
            "boot_to_agentos",
            "managed_codex_session",
            "native_document_access",
            "native_or_escalated_web_access_with_reason",
            "inspect_intake_surface",
            "governed_service_permission_action",
            "integrated_proof_export",
        ],
        "runtime_report": runtime_report,
        "capability_proof": capability_proof,
        "service_capability": service_capability,
        "permission_capability": permission_capability,
        "execution_ownership": execution_ownership,
        "session_correlation": correlation,
        "summary": summary,
        "failure_classes": failure_classes,
        "artifacts": {},
    }
    if write_manifest:
        payload["artifacts"]["latest_vm_e2e_proof_manifest_json"] = _write_manifest(
            workspace,
            "latest-vm-e2e-proof.json",
            payload,
        )
    return payload


def load_latest_control_plane_manifests(workspace_dir: str | Path) -> dict:
    root = _artifact_root(workspace_dir)
    return {
        "service_capability": _read_json(root / "latest-service-capability.json"),
        "permission_capability": _read_json(root / "latest-permission-capability.json"),
        "execution_ownership": _read_json(root / "latest-execution-ownership.json"),
        "vm_e2e_proof": _read_json(root / "latest-vm-e2e-proof.json"),
    }
