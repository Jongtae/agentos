#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kernel_public_preview_decision_ledger import build_public_preview_decision_ledger
from kernel_broader_preview_weekly_summary import build_broader_preview_weekly_summary

SCHEMA_VERSION = "agentos-public-preview-operating-brief.v1"
LAYOUT_DIRNAME = "public-preview-operating-briefs"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def build_public_preview_operating_brief(
    *,
    workspace: str,
    report_dir: str,
    feedback_file: str = "",
    install_root: str = "",
    metadata: str = "",
    diagnostics_manifest: str = "",
    history_dir: str = "",
    snapshot_label: str = "current",
    session_id: str = "",
    limit: int = 50,
) -> dict:
    root = resolve_root(report_dir)
    label = snapshot_label or "current"
    brief_dir = root / f"public-preview-operating-brief-{label}"
    brief_dir.mkdir(parents=True, exist_ok=True)
    support_root = root.parent

    ledger = build_public_preview_decision_ledger(
        workspace=workspace,
        report_dir=str(support_root / "ppob-l"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )
    weekly = build_broader_preview_weekly_summary(
        workspace=workspace,
        report_dir=str(support_root / "ppob-w"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )

    ledger_summary = ledger["summary"]
    weekly_summary = weekly["summary"]
    operating_posture = (
        "decision_ready"
        if ledger_summary["decision_state"] == "ready_for_public_preview_decision" and weekly_summary["weekly_posture"] == "stable"
        else "decision_watch"
    )

    summary = {
        "ok": True,
        "candidate_state": ledger_summary["candidate_state"],
        "audience_decision": ledger_summary["audience_decision"],
        "decision_state": ledger_summary["decision_state"],
        "recommended_next_step": ledger_summary["recommended_next_step"],
        "weekly_posture": weekly_summary["weekly_posture"],
        "operating_health": weekly_summary["operating_health"],
        "operating_recommendation": weekly_summary["operating_recommendation"],
        "signal_state": weekly_summary["signal_state"],
        "operating_posture": operating_posture,
        "pause_relevant_count": weekly_summary["pause_relevant_count"],
        "continue_relevant_count": weekly_summary["continue_relevant_count"],
        "expand_relevant_count": weekly_summary["expand_relevant_count"],
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "brief_label": label,
        "workspace": str(Path(workspace).resolve()),
        "brief_root": str(root),
        "brief_dir": str(brief_dir),
        "public_preview_decision_ledger": ledger,
        "broader_preview_weekly_summary": weekly,
        "summary": summary,
        "artifacts": {},
    }

    lines = [
        "# AgentOS Public Preview Operating Brief",
        "",
        f"Brief label: `{label}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Operating brief",
        "",
        f"- Candidate state: `{summary['candidate_state']}`",
        f"- Audience decision: `{summary['audience_decision']}`",
        f"- Decision state: `{summary['decision_state']}`",
        f"- Recommended next step: `{summary['recommended_next_step']}`",
        f"- Weekly posture: `{summary['weekly_posture']}`",
        f"- Operating health: `{summary['operating_health']}`",
        f"- Operating recommendation: `{summary['operating_recommendation']}`",
        f"- Signal state: `{summary['signal_state']}`",
        f"- Operating posture: `{summary['operating_posture']}`",
        f"- Pause issues: `{summary['pause_relevant_count']}`",
        f"- Continue issues: `{summary['continue_relevant_count']}`",
        f"- Expand issues: `{summary['expand_relevant_count']}`",
    ]

    markdown_path = brief_dir / "public-preview-operating-brief.md"
    manifest_path = brief_dir / "public-preview-operating-brief.json"
    latest_manifest_path = root / "latest-public-preview-operating-brief.json"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "public_preview_operating_brief_markdown": str(markdown_path),
        "public_preview_operating_brief_json": str(manifest_path),
        "latest_public_preview_operating_brief_json": str(latest_manifest_path),
        "public_preview_decision_ledger_json": ledger["artifacts"]["public_preview_decision_ledger_json"],
        "broader_preview_weekly_summary_json": weekly["artifacts"]["broader_preview_weekly_summary_json"],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_public_preview_operating_brief(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "brief_label",
        "workspace",
        "brief_root",
        "brief_dir",
        "public_preview_decision_ledger",
        "broader_preview_weekly_summary",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("public_preview_decision_ledger", {}).get("schema_version") != "agentos-public-preview-decision-ledger.v1":
        errors.append("public_preview_decision_ledger must reference agentos-public-preview-decision-ledger.v1")
    if payload.get("broader_preview_weekly_summary", {}).get("schema_version") != "agentos-broader-preview-weekly-summary.v1":
        errors.append("broader_preview_weekly_summary must reference agentos-broader-preview-weekly-summary.v1")
    if payload.get("summary", {}).get("operating_posture") not in {"decision_ready", "decision_watch"}:
        errors.append("summary.operating_posture must be decision_ready or decision_watch")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export public preview operating brief")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--report-dir", default="./workspaces/default/artifacts")
    parser.add_argument("--feedback-file", default="")
    parser.add_argument("--install-root", default="")
    parser.add_argument("--metadata", default="")
    parser.add_argument("--diagnostics-manifest", default="")
    parser.add_argument("--history-dir", default="")
    parser.add_argument("--snapshot-label", default="current")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_public_preview_operating_brief(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_public_preview_operating_brief(
        workspace=args.workspace,
        report_dir=args.report_dir,
        feedback_file=args.feedback_file,
        install_root=args.install_root,
        metadata=args.metadata,
        diagnostics_manifest=args.diagnostics_manifest,
        history_dir=args.history_dir,
        snapshot_label=args.snapshot_label,
        session_id=args.session_id,
        limit=args.limit,
    )
    errors = validate_public_preview_operating_brief(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
