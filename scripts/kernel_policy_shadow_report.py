#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from kernel.runtime.trace import resolve_runtime_trace_path
from workspace.manager import WorkspaceManager


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    items: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        row = line.strip()
        if not row:
            continue
        try:
            items.append(json.loads(row))
        except Exception:
            continue
    return items


def _count_user_space_workspace_blocks(runtime_trace_events: list[dict]) -> int:
    count = 0
    for item in runtime_trace_events:
        if str(item.get("event", "")) != "step_blocked":
            continue
        payload = item.get("payload", {}) or {}
        reason = str(payload.get("reason", "")).lower()
        detail = str(payload.get("detail", "")).lower()
        if "workspace" in reason or "workspace" in detail:
            count += 1
            continue
        if "../" in reason or "../" in detail:
            count += 1
    return count


def _count_user_space_network_blocks(runtime_trace_events: list[dict]) -> int:
    count = 0
    for item in runtime_trace_events:
        if str(item.get("event", "")) != "step_blocked":
            continue
        payload = item.get("payload", {}) or {}
        reason = str(payload.get("reason", "")).lower()
        detail = str(payload.get("detail", "")).lower()
        if "network_allowlist" in reason or "network_allowlist" in detail:
            count += 1
            continue
        if "web_domain_blocked" in reason or "browser_domain_blocked" in reason:
            count += 1
    return count


def _count_shadow_workspace_events(shadow_events: list[dict]) -> int:
    count = 0
    for item in shadow_events:
        event = str(item.get("event", ""))
        payload = item.get("payload", {}) or {}
        policy_target = str(payload.get("policy_target", ""))
        if event == "kernel.shadow.fs_outside_workspace.v1" or policy_target == "fs_workspace_boundary":
            count += 1
    return count


def _count_shadow_network_events(shadow_events: list[dict]) -> int:
    count = 0
    for item in shadow_events:
        event = str(item.get("event", ""))
        payload = item.get("payload", {}) or {}
        policy_target = str(payload.get("policy_target", ""))
        if event == "kernel.shadow.net_allowlist_violation.v1" or policy_target == "network_allowlist":
            count += 1
    return count


def _count_user_space_approval_events(runtime_trace_events: list[dict]) -> int:
    return sum(1 for item in runtime_trace_events if str(item.get("event", "")) == "approval_requested")


def _count_shadow_approval_events(shadow_events: list[dict]) -> int:
    count = 0
    for item in shadow_events:
        event = str(item.get("event", ""))
        payload = item.get("payload", {}) or {}
        policy_target = str(payload.get("policy_target", ""))
        if event == "kernel.shadow.destructive_action.v1" or policy_target == "destructive_action_approval":
            count += 1
    return count


def build_shadow_report(workspace: str, shadow_file: str = "", trace_file: str = "", output: str = "") -> dict:
    wm = WorkspaceManager(workspace)
    ws_dir = wm.workspace_dir

    shadow_path = Path(shadow_file) if shadow_file else (ws_dir / "artifacts" / "kernel-shadow-events.jsonl")
    runtime_trace_path = Path(trace_file) if trace_file else resolve_runtime_trace_path(ws_dir)

    shadow_events = _read_jsonl(shadow_path)
    runtime_events = _read_jsonl(runtime_trace_path)

    user_count = _count_user_space_workspace_blocks(runtime_events)
    shadow_count = _count_shadow_workspace_events(shadow_events)
    network_user_count = _count_user_space_network_blocks(runtime_events)
    network_shadow_count = _count_shadow_network_events(shadow_events)
    approval_user_count = _count_user_space_approval_events(runtime_events)
    approval_shadow_count = _count_shadow_approval_events(shadow_events)

    aligned = user_count == shadow_count
    delta = shadow_count - user_count
    network_aligned = network_user_count == network_shadow_count
    network_delta = network_shadow_count - network_user_count
    approval_aligned = approval_user_count == approval_shadow_count
    approval_delta = approval_shadow_count - approval_user_count
    policy_targets = [
        {
            "policy_target": "fs_workspace_boundary",
            "user_space_blocked_count": user_count,
            "shadow_detected_count": shadow_count,
            "comparison": {"aligned": aligned, "delta": delta, "status": "aligned" if aligned else "divergent"},
            "event_format": {
                "shadow_event_name": "kernel.shadow.fs_outside_workspace.v1",
                "shadow_payload_required_keys": ["policy_target", "path", "action"],
            },
        },
        {
            "policy_target": "network_allowlist",
            "user_space_blocked_count": network_user_count,
            "shadow_detected_count": network_shadow_count,
            "comparison": {
                "aligned": network_aligned,
                "delta": network_delta,
                "status": "aligned" if network_aligned else "divergent",
            },
            "event_format": {
                "shadow_event_name": "kernel.shadow.net_allowlist_violation.v1",
                "shadow_payload_required_keys": ["policy_target", "host", "port", "action"],
            },
        },
        {
            "policy_target": "destructive_action_approval",
            "user_space_blocked_count": approval_user_count,
            "shadow_detected_count": approval_shadow_count,
            "comparison": {
                "aligned": approval_aligned,
                "delta": approval_delta,
                "status": "aligned" if approval_aligned else "divergent",
            },
            "event_format": {
                "shadow_event_name": "kernel.shadow.destructive_action.v1",
                "shadow_payload_required_keys": ["policy_target", "approval_id", "action"],
            },
        },
    ]

    aligned_targets = [item["policy_target"] for item in policy_targets if item["comparison"]["aligned"]]
    divergent_targets = [item["policy_target"] for item in policy_targets if not item["comparison"]["aligned"]]
    coverage_summary = {
        "policy_target_count": len(policy_targets),
        "aligned_targets": aligned_targets,
        "divergent_targets": divergent_targets,
        "aligned_count": len(aligned_targets),
        "divergent_count": len(divergent_targets),
    }

    report = {
        "ok": True,
        "exit_code": 0,
        "workspace": str(ws_dir),
        "policy_target": "fs_workspace_boundary",
        "primary_policy_target": "fs_workspace_boundary",
        "next_policy_target": "network_allowlist",
        "runtime_trace_file": str(runtime_trace_path),
        "shadow_event_file": str(shadow_path),
        "runtime_trace_events": len(runtime_events),
        "shadow_events": len(shadow_events),
        "user_space_blocked_count": user_count,
        "shadow_detected_count": shadow_count,
        "comparison": {
            "aligned": aligned,
            "delta": delta,
        },
        "event_format": {
            "shadow_event_name": "kernel.shadow.fs_outside_workspace.v1",
            "shadow_payload_required_keys": ["policy_target", "path", "action"],
        },
        "coverage_summary": coverage_summary,
        "policy_targets": policy_targets,
        "overall_aligned": all(item["comparison"]["aligned"] for item in policy_targets),
        "next_policy_target": "destructive_action_approval",
    }

    if output:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build kernel shadow mode comparison report")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--shadow-file", default="")
    parser.add_argument("--trace-file", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_shadow_report(
        workspace=args.workspace,
        shadow_file=args.shadow_file,
        trace_file=args.trace_file,
        output=args.output,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=True))
    else:
        print("AgentOS Kernel Shadow Report")
        print("===========================")
        print(f"Workspace: {report['workspace']}")
        print(f"Policy target: {report['policy_target']}")
        print(f"Runtime trace: {report['runtime_trace_file']}")
        print(f"Shadow events: {report['shadow_event_file']}")
        print(f"User-space blocked count: {report['user_space_blocked_count']}")
        print(f"Shadow detected count: {report['shadow_detected_count']}")
        print(
            "Comparison: "
            f"aligned={report['comparison']['aligned']} "
            f"delta={report['comparison']['delta']}"
        )
        print(
            "Coverage summary: "
            f"targets={report['coverage_summary']['policy_target_count']} "
            f"aligned={report['coverage_summary']['aligned_count']} "
            f"divergent={report['coverage_summary']['divergent_count']}"
        )
        for item in report["policy_targets"]:
            comparison = item.get("comparison", {}) or {}
            print(
                f"- {item.get('policy_target')}: "
                f"status={comparison.get('status')} "
                f"user={item.get('user_space_blocked_count')} "
                f"shadow={item.get('shadow_detected_count')} "
                f"delta={comparison.get('delta')}"
            )
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
