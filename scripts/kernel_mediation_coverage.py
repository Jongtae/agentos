#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_mediation_coverage_report(*, workspace: str) -> dict:
    workspace_path = str(Path(workspace).resolve())
    targets = [
        {
            "path_id": "destructive_shell_exec",
            "title": "Destructive shell execution",
            "class": "mandatory_candidate",
            "priority": "p0",
            "current_mediation_surface": "broker.exec + approval gate",
            "policy_targets": ["destructive_action_approval"],
            "approval_mode": "required",
            "shadow_mode": "required",
            "enforce_mode": "candidate",
            "evidence_mode": "required",
        },
        {
            "path_id": "file_overwrite",
            "title": "File overwrite and workspace escape",
            "class": "mandatory_candidate",
            "priority": "p0",
            "current_mediation_surface": "policy engine + fs workspace evidence",
            "policy_targets": ["fs_workspace_boundary", "destructive_action_approval"],
            "approval_mode": "conditional",
            "shadow_mode": "required",
            "enforce_mode": "candidate",
            "evidence_mode": "required",
        },
        {
            "path_id": "network_sensitive_exec",
            "title": "Network-sensitive execution",
            "class": "mandatory_candidate",
            "priority": "p0",
            "current_mediation_surface": "allowlist + network evidence",
            "policy_targets": ["network_allowlist"],
            "approval_mode": "conditional",
            "shadow_mode": "required",
            "enforce_mode": "candidate",
            "evidence_mode": "required",
        },
        {
            "path_id": "browser_cross_domain_navigation",
            "title": "Cross-domain browser navigation",
            "class": "approval_priority",
            "priority": "p1",
            "current_mediation_surface": "browser policy + approval adapter",
            "policy_targets": ["destructive_action_approval"],
            "approval_mode": "required",
            "shadow_mode": "recommended",
            "enforce_mode": "future_candidate",
            "evidence_mode": "required",
        },
        {
            "path_id": "operator_control_change",
            "title": "Operator control plane changes",
            "class": "approval_priority",
            "priority": "p1",
            "current_mediation_surface": "broker.operator_control",
            "policy_targets": ["destructive_action_approval"],
            "approval_mode": "conditional",
            "shadow_mode": "recommended",
            "enforce_mode": "future_candidate",
            "evidence_mode": "required",
        },
        {
            "path_id": "install_and_boot_integration",
            "title": "Install and boot integration control",
            "class": "approval_priority",
            "priority": "p1",
            "current_mediation_surface": "broker.install_control",
            "policy_targets": ["destructive_action_approval"],
            "approval_mode": "conditional",
            "shadow_mode": "recommended",
            "enforce_mode": "future_candidate",
            "evidence_mode": "required",
        },
        {
            "path_id": "service_and_background_governance",
            "title": "Service lifecycle and background automation",
            "class": "observe_priority",
            "priority": "p2",
            "current_mediation_surface": "event fabric coverage",
            "policy_targets": ["destructive_action_approval", "network_allowlist"],
            "approval_mode": "conditional",
            "shadow_mode": "recommended",
            "enforce_mode": "future_candidate",
            "evidence_mode": "required",
        },
    ]

    return {
        "schema_version": "agentos-mediation-coverage.v1",
        "workspace": workspace_path,
        "summary": {
            "target_count": len(targets),
            "mandatory_candidate_count": sum(1 for item in targets if item["class"] == "mandatory_candidate"),
            "approval_priority_count": sum(1 for item in targets if item["class"] == "approval_priority"),
            "observe_priority_count": sum(1 for item in targets if item["class"] == "observe_priority"),
            "policy_targets": sorted({target for item in targets for target in item["policy_targets"]}),
        },
        "mapping_rules": {
            "approval_mode": ["required", "conditional", "not_required"],
            "shadow_mode": ["required", "recommended", "not_applicable"],
            "enforce_mode": ["candidate", "future_candidate", "not_applicable"],
            "evidence_mode": ["required"],
        },
        "targets": targets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build AgentOS mediation coverage map report")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    payload = build_mediation_coverage_report(workspace=args.workspace)
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
        return 0

    print("AgentOS Mediation Coverage")
    print("==========================")
    print(f"Workspace: {payload['workspace']}")
    print(f"Targets: {payload['summary']['target_count']}")
    for item in payload["targets"]:
        print(
            f"- {item['path_id']}: class={item['class']} priority={item['priority']} "
            f"approval={item['approval_mode']} shadow={item['shadow_mode']} enforce={item['enforce_mode']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
