#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from export_install_verification_manifest import build_manifest as build_install_manifest
from kernel_approval_forensics import build_approval_forensics
from kernel.automation_governance import build_automation_governance_report
from kernel.policy_maturity import build_policy_maturity_report
from kernel.provenance_graph import build_provenance_graph
from kernel.user_space_sovereignty import build_user_space_sovereignty_report
from kernel.mediation_pilot import build_mediation_pilot_report
from kernel_broker_status import run_brokerd_status  # noqa: F401
from kernel_boot_audit import audit_report
from kernel.service_governance import build_service_governance_report
from kernel.event_fabric.policy_evidence import policy_evidence_report
from kernel.event_fabric.report import query_session_timeline
from kernel.broker.daemon import brokerd_report
from kernel.operator_mode import operator_mode_contract
from status import status_report
from workspace.manager import WorkspaceManager


def build_evidence_report(
    *,
    workspace: str,
    install_root: str = "",
    metadata: str = "",
    snapshot_label: str = "agentos-demo-clean",
) -> dict:
    wm = WorkspaceManager(workspace)
    runtime_status = status_report(wm)
    session_timeline = query_session_timeline(wm.workspace_dir, limit=20)
    broker_status = brokerd_report(Path(wm.workspace_dir))
    service_governance = build_service_governance_report(wm.workspace_dir)
    automation_governance = build_automation_governance_report(wm.workspace_dir)
    policy_maturity = build_policy_maturity_report(str(wm.workspace_dir), parser_cmd="python3")
    provenance_graph = build_provenance_graph(workspace=str(wm.workspace_dir), limit=20)
    mediation_pilot = build_mediation_pilot_report(workspace=str(wm.workspace_dir))
    operator_mode = operator_mode_contract(
        session_origin=runtime_status.get("session_origin", {}),
        setup_state=runtime_status.get("setup_state", {}),
    )
    user_space_sovereignty = build_user_space_sovereignty_report(
        session_origin=runtime_status.get("session_origin", {}) or {},
        setup_state=runtime_status.get("setup_state", {}) or {},
        runtime_entry=runtime_status.get("runtime_entry", {}) or {},
        operator_mode=operator_mode,
    )
    policy_correlation = policy_evidence_report(wm.workspace_dir)
    approval_forensics = build_approval_forensics(wm.workspace_dir, limit=20)

    install_validation = {
        "available": False,
        "ok": False,
        "reason": "install_root_not_requested",
    }
    audit_summary = {
        "available": False,
        "ok": False,
        "reason": "install_root_not_requested",
    }
    if install_root:
        install_manifest = build_install_manifest(
            metadata=metadata,
            install_root=install_root,
            workspace=str(wm.workspace_dir),
            snapshot_label=snapshot_label,
            root_dir=ROOT_DIR,
        )
        install_validation = {
            "available": True,
            "ok": bool((install_manifest.get("summary") or {}).get("ok", False)),
            "manifest": install_manifest,
        }
        audit_payload = audit_report(install_root=install_root, workspace=str(wm.workspace_dir))
        audit_summary = {
            "available": True,
            "ok": bool(audit_payload.get("ok", False)),
            "report": audit_payload,
        }

    summary = {
        "runtime_ok": bool(runtime_status.get("ok", False)),
        "session_phase": str((session_timeline.get("ownership_summary") or {}).get("session_phase", "")),
        "session_origin": str((session_timeline.get("ownership_summary") or {}).get("session_origin", "")),
        "runtime_session_origin": str((runtime_status.get("session_origin") or {}).get("category", "")),
        "session_path_family": str((runtime_status.get("session_origin_compatibility") or {}).get("path_family", "")),
        "session_compatibility_label": str((runtime_status.get("session_origin_compatibility") or {}).get("label", "")),
        "broker_recent_actions": list((broker_status.get("activity") or {}).get("recent_actions", []))[:5],
        "policy_targets": [
            {
                "policy_target": str(item.get("policy_target", "")),
                "status": str((item.get("comparison") or {}).get("status", "")),
            }
            for item in (policy_correlation.get("policy_targets") or [])
        ],
        "approval_forensics": approval_forensics.get("summary", {}),
        "service_governance": service_governance.get("summary", {}),
        "automation_governance": automation_governance.get("summary", {}),
        "policy_maturity": policy_maturity.get("summary", {}),
        "provenance_graph": provenance_graph.get("summary", {}),
        "user_space_sovereignty": user_space_sovereignty.get("summary", {}),
        "mediation_pilot": mediation_pilot.get("summary", {}),
        "install_validation_ok": bool(install_validation.get("ok", False)) if install_validation.get("available") else None,
        "audit_ok": bool(audit_summary.get("ok", False)) if audit_summary.get("available") else None,
        "recommended_handoff_artifact": "review_bundle",
        "operator_mode": operator_mode.get("current_mode", "user_mode"),
    }

    default_report_dir = str((Path(wm.workspace_dir) / "artifacts" / "operator-review").resolve())
    handoff = {
        "default_artifact": "review_bundle",
        "report_dir": default_report_dir,
        "recommended_command": (
            "scripts/agentos-kernelctl review-bundle "
            f"--workspace {wm.workspace_dir} "
            f"--report-dir {default_report_dir} --json"
        ),
        "history_command": (
            "scripts/agentos-kernelctl review-bundle-history "
            f"--report-dir {default_report_dir} --json"
        ),
    }

    ok = True

    return {
        "ok": ok,
        "exit_code": 0 if ok else 1,
        "workspace": str(wm.workspace_dir),
        "install_root": install_root,
        "runtime_status": runtime_status,
        "session_timeline": session_timeline,
        "broker_status": broker_status,
        "policy_correlation": policy_correlation,
        "approval_forensics": approval_forensics,
        "service_governance": service_governance,
        "automation_governance": automation_governance,
        "policy_maturity": policy_maturity,
        "provenance_graph": provenance_graph,
        "user_space_sovereignty": user_space_sovereignty,
        "mediation_pilot": mediation_pilot,
        "operator_mode": operator_mode,
        "install_validation": install_validation,
        "audit_summary": audit_summary,
        "summary": summary,
        "handoff": handoff,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build unified AgentOS operator evidence report")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--install-root", default="")
    parser.add_argument("--metadata", default="")
    parser.add_argument("--snapshot-label", default="agentos-demo-clean")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_evidence_report(
        workspace=args.workspace,
        install_root=args.install_root,
        metadata=args.metadata,
        snapshot_label=args.snapshot_label,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
        return int(payload["exit_code"])

    print("AgentOS Operator Evidence")
    print("=========================")
    print(f"Workspace: {payload['workspace']}")
    print(f"Runtime ok: {payload['summary']['runtime_ok']}")
    print(
        "Session: "
        f"phase={payload['summary']['session_phase'] or '(unknown)'} "
        f"origin={payload['summary']['session_origin'] or '(unknown)'}"
    )
    print(
        "Runtime session path: "
        f"origin={payload['summary']['runtime_session_origin'] or '(unknown)'} "
        f"family={payload['summary']['session_path_family'] or '(unknown)'} "
        f"label={payload['summary']['session_compatibility_label'] or '(unknown)'}"
    )
    print(
        "Broker recent actions: "
        + (", ".join(payload["summary"]["broker_recent_actions"]) if payload["summary"]["broker_recent_actions"] else "(none)")
    )
    print("Policy targets:")
    for item in payload["summary"]["policy_targets"]:
        print(f"- {item['policy_target']}: {item['status']}")
    print(
        "Approval forensics: "
        f"requested={payload['summary']['approval_forensics'].get('approval_requested', 0)} "
        f"denied={payload['summary']['approval_forensics'].get('approval_denied', 0)} "
        f"overrides={payload['summary']['approval_forensics'].get('broker_override_count', 0)} "
        f"status={payload['summary']['approval_forensics'].get('forensic_status', 'unknown')}"
    )
    print(
        "Service governance: "
        f"inventory={payload['summary']['service_governance'].get('inventory_units', 0)} "
        f"observed={payload['summary']['service_governance'].get('observed_units', 0)} "
        f"operator_actions={payload['summary']['service_governance'].get('operator_control_actions', 0)}"
    )
    print(
        "Automation governance: "
        f"scheduled={payload['summary']['automation_governance'].get('scheduled_task_count', 0)} "
        f"background={payload['summary']['automation_governance'].get('background_agent_count', 0)} "
        f"overrides={payload['summary']['automation_governance'].get('override_events', 0)}"
    )
    print(
        "Policy maturity: "
        f"avg_score={payload['summary']['policy_maturity'].get('average_readiness_score', 0)} "
        f"promote={len(payload['summary']['policy_maturity'].get('promotion_candidates', []))} "
        f"stabilize={len(payload['summary']['policy_maturity'].get('stabilization_candidates', []))}"
    )
    print(
        "Provenance graph: "
        f"nodes={payload['summary']['provenance_graph'].get('node_count', 0)} "
        f"edges={payload['summary']['provenance_graph'].get('edge_count', 0)} "
        f"chains={payload['summary']['provenance_graph'].get('chain_count', 0)}"
    )
    print(
        "User-space sovereignty: "
        f"model={payload['summary']['user_space_sovereignty'].get('default_interaction_model', '')} "
        f"managed={payload['summary']['user_space_sovereignty'].get('managed_action_count', 0)} "
        f"guided={payload['summary']['user_space_sovereignty'].get('guided_action_count', 0)} "
        f"passthrough={payload['summary']['user_space_sovereignty'].get('passthrough_action_count', 0)}"
    )
    print(
        "Mediation pilot: "
        f"targets={payload['summary']['mediation_pilot'].get('pilot_target_count', 0)} "
        f"mandatory={len(payload['summary']['mediation_pilot'].get('mandatory_targets', []))} "
        f"false_deny_attention={len(payload['summary']['mediation_pilot'].get('false_deny_attention_targets', []))}"
    )
    if payload["install_validation"]["available"]:
        print(f"Install validation: {payload['install_validation']['ok']}")
    if payload["audit_summary"]["available"]:
        print(f"Audit summary: {payload['audit_summary']['ok']}")
    return int(payload["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
