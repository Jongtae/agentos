from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from kernel.capability_substrate import (
    build_capability_proof_surface,
    build_document_access_report,
    build_intake_surface_report,
    build_web_access_report,
)
from kernel.control_plane_capabilities import build_execution_ownership_report
from kernel.event_fabric.collectors import append_events_jsonl
from kernel.event_fabric.schema import build_os_event_record
from kernel.policies.approval_rules import PolicyEngine
from kernel.planner.planner import Step
from kernel.runtime.trace import resolve_runtime_trace_path
from kernel.service_permission_capability import (
    build_permission_capability_report,
    build_service_capability_report,
)

VM_E2E_SCENARIO_SCHEMA = "agentos-vm-e2e-scenario.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_document_fixture(workspace: Path) -> str:
    fixture = workspace / "documents" / "agentos-first-run.md"
    fixture.parent.mkdir(parents=True, exist_ok=True)
    if not fixture.exists():
        fixture.write_text(
            "# AgentOS VM E2E\n\nThis document is used to prove native document handling.\n",
            encoding="utf-8",
        )
    return str(fixture.relative_to(workspace))


def _ensure_intake_fixture(workspace: Path, *, session_id: str, boot_id: str) -> dict[str, str]:
    artifacts = workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    append_events_jsonl(
        artifacts / "os_events.jsonl",
        [
            build_os_event_record(
                source="vm_e2e_scenario",
                kind="session.login",
                action="managed_session_entry",
                object={"session_id": session_id, "path": "ai_shell"},
                correlation={"session_id": session_id, "boot_id": boot_id},
                timestamp_utc=_utc_now(),
            ),
            build_os_event_record(
                source="vm_e2e_scenario",
                kind="broker.exec_request",
                action="service_capability_probe",
                object={"request_kind": "install_control", "tool_name": "service_capability"},
                correlation={"session_id": session_id, "boot_id": boot_id, "request_id": "vm-e2e-request-1"},
                timestamp_utc=_utc_now(),
            ),
        ],
    )
    feedback_root = artifacts / "feedback-intake"
    feedback_root.mkdir(parents=True, exist_ok=True)
    feedback_manifest = feedback_root / "latest-feedback-intake-manifest.json"
    feedback_manifest.write_text(
        json.dumps(
            {
                "generated_at_utc": _utc_now(),
                "feedback_packet": {
                    "channel": "vm_e2e",
                    "summary": "Observed VM scenario refresh completed.",
                    "recommendation": "continue",
                },
            },
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "events_jsonl": str(artifacts / "os_events.jsonl"),
        "feedback_manifest": str(feedback_manifest),
    }


def run_vm_e2e_scenario(
    workspace_dir: str | Path,
    *,
    session_id: str = "agentos:tty1",
    boot_id: str = "vm-e2e-boot",
    web_url: str = "https://example.com",
) -> dict:
    from kernel.control_plane_capabilities import classify_execution_path

    workspace = Path(workspace_dir).resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    document_rel_path = _ensure_document_fixture(workspace)
    intake_artifacts = _ensure_intake_fixture(workspace, session_id=session_id, boot_id=boot_id)

    document_access = build_document_access_report(workspace, document_rel_path, write_manifest=True)
    web_access = build_web_access_report(workspace, web_url, domain_allowlist=["example.com"], write_manifest=True)
    if not web_access.get("native_handled", False) and not web_access.get("escalated_handled", False):
        web_access = build_web_access_report(
            workspace,
            web_url,
            domain_allowlist=["example.com"],
            requires_authentication=True,
            write_manifest=True,
        )

    intake_surface = build_intake_surface_report(
        workspace,
        report_dir=str(workspace / "artifacts"),
        session_id=session_id,
        write_manifest=True,
    )
    service_capability = build_service_capability_report(workspace, write_manifest=True)
    permission_capability = build_permission_capability_report(workspace, session_id=session_id, write_manifest=True)

    policy = PolicyEngine(require_approval=True)
    execution_samples = []
    for step in (
        Step(tool_name="file_read", description="Read scenario document", args={"path": document_rel_path}),
        Step(tool_name="web_fetch", description="Fetch a public page", args={"url": web_url}),
        Step(tool_name="browser_run", description="Open interactive page", args={"action": "navigate", "url": web_url + "/login"}),
        Step(tool_name="operator_control", description="Probe service control", args={"unit": "agentos-kernel.service", "action": "restart"}),
    ):
        execution_samples.append(classify_execution_path(step, policy))
    execution_ownership = build_execution_ownership_report(workspace, samples=execution_samples, write_manifest=True)
    capability_proof = build_capability_proof_surface(workspace)

    return {
        "schema_version": VM_E2E_SCENARIO_SCHEMA,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace),
        "document_access": document_access,
        "web_access": web_access,
        "intake_surface": intake_surface,
        "service_capability": service_capability,
        "permission_capability": permission_capability,
        "execution_ownership": execution_ownership,
        "capability_proof": capability_proof,
        "runtime_trace_path": str(resolve_runtime_trace_path(workspace)),
        "artifacts": {
            "document_fixture": str(workspace / document_rel_path),
            "intake_events_jsonl": intake_artifacts["events_jsonl"],
            "feedback_manifest": intake_artifacts["feedback_manifest"],
        },
        "summary": {
            "document_native_handled": bool(document_access.get("native_handled", False)),
            "web_handled": bool(web_access.get("native_handled", False) or web_access.get("escalated_handled", False)),
            "intake_ok": bool((intake_surface.get("summary") or {}).get("ok", False)),
            "service_permission_ready": bool(service_capability) and bool(permission_capability),
            "execution_samples": len(execution_samples),
        },
    }
