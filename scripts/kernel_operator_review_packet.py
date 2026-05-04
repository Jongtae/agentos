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

from kernel_operator_review_pack import build_review_pack


def build_review_packet_markdown(payload: dict) -> str:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    case_summary = (payload.get("case_export", {}) or {}).get("summary", {}) or {}
    validation_summary = (payload.get("validation_window", {}) or {}).get("summary", {}) or {}
    control_summary = (payload.get("control_history", {}) or {}).get("summary", {}) or {}

    lines = [
        "# AgentOS Operator Review Packet",
        "",
        "## Summary",
        f"- Workspace: `{payload.get('workspace', '')}`",
        f"- Session phase: `{summary.get('session_phase', 'unknown')}`",
        f"- Session origin: `{summary.get('session_origin', 'unknown')}`",
        f"- Approval forensics: `{summary.get('approval_forensic_status', 'unknown')}`",
        f"- Validation stable: `{summary.get('validation_stable', False)}`",
        f"- Control events: `{summary.get('control_event_count', 0)}`",
        "",
        "## Review Pack Snapshot",
        f"- Approval requested: `{case_summary.get('approval_requested', 0)}`",
        f"- Approval denied: `{case_summary.get('approval_denied', 0)}`",
        f"- Broker overrides: `{case_summary.get('broker_override_count', 0)}`",
        f"- Milestones: `{case_summary.get('milestone_count', 0)}`",
        "",
        "## Validation Drift",
        f"- Stable: `{validation_summary.get('stable', False)}`",
        f"- Changed fields: `{', '.join(validation_summary.get('changed_fields', [])) or '(none)'}`",
        f"- Current overall state: `{validation_summary.get('current_overall_state', 'unknown')}`",
        "",
        "## Control History",
        f"- Categories: `{', '.join(control_summary.get('categories', [])) or '(none)'}`",
        f"- Latest bridge state: `{control_summary.get('latest_bridge_state', 'unknown')}`",
        f"- Latest enforce target: `{control_summary.get('latest_enforce_policy_target', 'unknown')}`",
        "",
        "## Primary Commands",
    ]
    for command in ((payload.get("references", {}) or {}).get("primary_commands", []) or []):
        lines.append(f"- `{command}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a human-friendly AgentOS operator review packet")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--install-root", default="")
    parser.add_argument("--metadata", default="")
    parser.add_argument("--diagnostics-manifest", default="")
    parser.add_argument("--history-dir", default="")
    parser.add_argument("--snapshot-label", default="current")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_review_pack(
        workspace=args.workspace,
        install_root=args.install_root,
        metadata=args.metadata,
        diagnostics_manifest=args.diagnostics_manifest,
        history_dir=args.history_dir,
        snapshot_label=args.snapshot_label,
        session_id=args.session_id,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
        return 0

    text = build_review_packet_markdown(payload)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
