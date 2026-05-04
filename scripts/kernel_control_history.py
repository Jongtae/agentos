#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kernel.event_fabric.report import query_events, query_session_timeline
from workspace.manager import WorkspaceManager

SCHEMA_VERSION = "agentos-control-history.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _control_event(item: dict[str, Any]) -> dict[str, Any]:
    correlation = item.get("correlation") or {}
    decision = item.get("decision") or {}
    obj = item.get("object") or {}
    action = str(item.get("action", ""))
    request_kind = str(decision.get("request_kind", ""))
    category = "session"
    if action.startswith("policy_bridge"):
        category = "bridge"
    elif action.startswith("policy_enforce"):
        category = "enforce"
    elif request_kind == "override":
        category = "override"
    elif request_kind in {"operator_control", "install_control"}:
        category = "operator_control"
    return {
        "timestamp_utc": str(item.get("timestamp_utc", "")),
        "category": category,
        "kind": str(item.get("kind", "")),
        "action": action,
        "state": str(decision.get("state", "")),
        "reason": str(decision.get("reason", "")),
        "request_kind": request_kind,
        "policy_target": str(obj.get("policy_target", "")),
        "session_id": str(correlation.get("session_id", "") or obj.get("session_id", "")),
        "summary": _event_summary(action, decision, obj),
    }


def _event_summary(action: str, decision: dict[str, Any], obj: dict[str, Any]) -> str:
    state = str(decision.get("state", ""))
    reason = str(decision.get("reason", ""))
    policy_target = str(obj.get("policy_target", ""))
    if policy_target:
        return f"{action} -> {state} ({policy_target})".strip()
    if reason:
        return f"{action} -> {state} ({reason})".strip()
    return f"{action} -> {state}".strip()


def build_control_history(*, workspace: str, limit: int = 100) -> dict[str, Any]:
    wm = WorkspaceManager(workspace)
    events = query_events(wm.workspace_dir, limit=max(limit, 50))
    sessions = query_session_timeline(wm.workspace_dir, limit=20)

    timeline: list[dict[str, Any]] = []
    for item in events.get("events", []):
        decision = item.get("decision") or {}
        action = str(item.get("action", ""))
        request_kind = str(decision.get("request_kind", ""))
        if item.get("kind") in {"session.login", "session.logout"}:
            timeline.append(_control_event(item))
            continue
        if action.startswith("policy_bridge") or action.startswith("policy_enforce") or request_kind in {
            "override",
            "operator_control",
            "install_control",
        }:
            timeline.append(_control_event(item))

    policy_dir = Path(wm.workspace_dir) / "artifacts" / "kernel-policy"
    bridge_lifecycle = _load_json(policy_dir / "profile-lifecycle.json")
    enforce_config = _load_json(policy_dir / "enforced-pilot.json")
    current_state = {
        "bridge_state": str(bridge_lifecycle.get("bridge_state", "")),
        "bridge_reload_state": str(bridge_lifecycle.get("reload_state", "")),
        "bridge_disable_state": str(bridge_lifecycle.get("disable_state", "")),
        "bridge_operator_state": str(bridge_lifecycle.get("operator_state", "")),
        "enforce_configured_enabled": bool(enforce_config.get("enabled", False)),
        "enforce_policy_target": str(enforce_config.get("policy_target", "")),
    }

    timeline.sort(key=lambda item: item.get("timestamp_utc", ""))
    selected = timeline[-limit:]
    categories = sorted({item.get("category", "") for item in selected if item.get("category")})
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(Path(wm.workspace_dir).resolve()),
        "session_context": {
            "ownership_summary": sessions.get("ownership_summary", {}),
            "correlation_evidence": sessions.get("correlation_evidence", {}),
        },
        "current_state": current_state,
        "summary": {
            "event_count": len(selected),
            "categories": categories,
            "latest_bridge_state": current_state["bridge_state"],
            "latest_enforce_policy_target": current_state["enforce_policy_target"],
        },
        "timeline": selected,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build AgentOS control history timeline")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_control_history(workspace=args.workspace, limit=args.limit)
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
        return 0

    print("AgentOS Control History")
    print("=======================")
    print(f"Events: {payload['summary']['event_count']}")
    print("Categories: " + (", ".join(payload["summary"]["categories"]) or "(none)"))
    print(f"Latest bridge state: {payload['summary']['latest_bridge_state'] or 'unknown'}")
    print(f"Latest enforce policy target: {payload['summary']['latest_enforce_policy_target'] or 'unknown'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
