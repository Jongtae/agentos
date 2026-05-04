#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kernel_control_history import build_control_history
from kernel_operator_case_export import build_case_export
from kernel_validation_window import build_validation_window

SCHEMA_VERSION = "agentos-operator-review-pack.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_review_pack(
    *,
    workspace: str,
    install_root: str = "",
    metadata: str = "",
    diagnostics_manifest: str = "",
    history_dir: str = "",
    snapshot_label: str = "current",
    session_id: str = "",
    limit: int = 50,
) -> dict:
    case_export = build_case_export(
        workspace=workspace,
        install_root=install_root,
        metadata=metadata,
        snapshot_label=snapshot_label,
        session_id=session_id,
        limit=limit,
    )
    validation_window = build_validation_window(
        workspace=workspace,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=snapshot_label,
    )
    control_history = build_control_history(workspace=workspace, limit=max(limit, 100))

    case_summary = case_export.get("summary", {})
    validation_summary = validation_window.get("summary", {})
    control_summary = control_history.get("summary", {})
    summary = {
        "session_phase": str(case_summary.get("session_phase", "")),
        "session_origin": str(case_summary.get("session_origin", "")),
        "approval_forensic_status": str(case_summary.get("approval_forensic_status", "")),
        "validation_stable": bool(validation_summary.get("stable", False)),
        "validation_changed_fields": list(validation_summary.get("changed_fields", [])),
        "control_categories": list(control_summary.get("categories", [])),
        "control_event_count": int(control_summary.get("event_count", 0) or 0),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(Path(workspace).resolve()),
        "summary": summary,
        "case_export": case_export,
        "validation_window": validation_window,
        "control_history": control_history,
        "references": {
            "primary_commands": [
                "scripts/agentos-kernelctl case-export --workspace ./workspaces/default --json",
                "scripts/agentos-kernelctl validation-window --workspace ./workspaces/default --report-dir ./artifacts/validation-history --json",
                "scripts/agentos-kernelctl control-history --workspace ./workspaces/default --json",
            ]
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build AgentOS operator review pack")
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
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
        return 0

    summary = payload["summary"]
    print("AgentOS Operator Review Pack")
    print("============================")
    print(
        "Summary: "
        f"phase={summary['session_phase'] or 'unknown'} "
        f"origin={summary['session_origin'] or 'unknown'} "
        f"forensics={summary['approval_forensic_status'] or 'unknown'} "
        f"validation_stable={summary['validation_stable']} "
        f"control_events={summary['control_event_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
