from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.kernel_approval_forensics import build_approval_forensics
from scripts.kernel_control_history import build_control_history
from scripts.kernel_session_replay import build_session_replay

SCHEMA_VERSION = "agentos-provenance-graph.v1"


def _node_id(prefix: str, value: str) -> str:
    return f"{prefix}:{value}"


def build_provenance_graph(*, workspace: str, session_id: str = "", limit: int = 50) -> dict:
    workspace_path = Path(workspace).resolve()
    replay = build_session_replay(str(workspace_path), session_id=session_id, limit=limit)
    forensics = build_approval_forensics(str(workspace_path), session_id=session_id, limit=limit)
    control_history = build_control_history(workspace=str(workspace_path), limit=limit)

    nodes: list[dict] = []
    edges: list[dict] = []
    seen_nodes: set[str] = set()

    ownership = replay.get("ownership_summary", {}) or {}
    session_key = str(ownership.get("session_id", "") or session_id or "agentos-session")
    session_node = _node_id("session", session_key)
    nodes.append(
        {
            "id": session_node,
            "kind": "session",
            "label": str(ownership.get("session_phase", "unknown")) or "unknown",
            "summary": {
                "session_origin": ownership.get("session_origin", "unknown"),
                "next_managed_entry": ownership.get("next_managed_entry", "unknown"),
            },
        }
    )
    seen_nodes.add(session_node)

    milestone_nodes: list[str] = []
    for index, item in enumerate(replay.get("milestones", []) or []):
        node_id = _node_id("milestone", f"{index}")
        milestone_nodes.append(node_id)
        nodes.append(
            {
                "id": node_id,
                "kind": "milestone",
                "label": str(item.get("milestone", "event")),
                "timestamp_utc": str(item.get("timestamp_utc", "")),
                "summary": str(item.get("summary", "")),
                "source": str(item.get("source", "")),
            }
        )
        seen_nodes.add(node_id)
        edges.append({"from": session_node, "to": node_id, "relation": "contains"})
        if index > 0:
            edges.append({"from": milestone_nodes[index - 1], "to": node_id, "relation": "next"})

    approval_ids = list((forensics.get("correlation") or {}).get("approval_ids", []))
    request_ids = list((forensics.get("correlation") or {}).get("request_ids", []))

    approval_nodes: list[str] = []
    for approval_id in approval_ids:
        node_id = _node_id("approval", approval_id)
        approval_nodes.append(node_id)
        nodes.append(
            {
                "id": node_id,
                "kind": "approval",
                "label": approval_id,
                "summary": forensics.get("summary", {}),
            }
        )
        seen_nodes.add(node_id)
        edges.append({"from": session_node, "to": node_id, "relation": "approval_context"})

    request_nodes: list[str] = []
    for request_id in request_ids:
        node_id = _node_id("request", request_id)
        request_nodes.append(node_id)
        nodes.append(
            {
                "id": node_id,
                "kind": "request",
                "label": request_id,
                "summary": {"request_id": request_id},
            }
        )
        seen_nodes.add(node_id)
        edges.append({"from": session_node, "to": node_id, "relation": "request_context"})

    for approval_node in approval_nodes:
        for request_node in request_nodes:
            edges.append({"from": request_node, "to": approval_node, "relation": "approval_gate"})

    history_nodes: list[str] = []
    for index, item in enumerate(control_history.get("timeline", []) or []):
        node_id = _node_id("control", f"{index}")
        history_nodes.append(node_id)
        nodes.append(
            {
                "id": node_id,
                "kind": "control_event",
                "label": str(item.get("action", "event")),
                "timestamp_utc": str(item.get("timestamp_utc", "")),
                "summary": str(item.get("summary", "")),
                "category": str(item.get("category", "")),
            }
        )
        seen_nodes.add(node_id)
        if milestone_nodes:
            edges.append({"from": milestone_nodes[-1], "to": node_id, "relation": "results_in"})
        if index > 0:
            edges.append({"from": history_nodes[index - 1], "to": node_id, "relation": "next"})

    causal_chains = []
    if milestone_nodes:
        causal_chains.append(
            {
                "chain_id": "session-primary",
                "description": "Primary session causality from session ownership through runtime milestones and control transitions",
                "node_ids": [session_node] + milestone_nodes + history_nodes,
            }
        )
    if request_nodes or approval_nodes:
        causal_chains.append(
            {
                "chain_id": "approval-control",
                "description": "Approval and request correlation chain for mediated actions",
                "node_ids": [session_node] + request_nodes + approval_nodes,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "workspace": str(workspace_path),
        "session_id": session_id,
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "chain_count": len(causal_chains),
            "latest_session_phase": str(ownership.get("session_phase", "unknown")),
            "approval_requested": int((forensics.get("summary") or {}).get("approval_requested", 0)),
            "approval_denied": int((forensics.get("summary") or {}).get("approval_denied", 0)),
            "control_event_count": len(history_nodes),
        },
        "nodes": nodes,
        "edges": edges,
        "causal_chains": causal_chains,
    }
