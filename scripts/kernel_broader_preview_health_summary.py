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

from kernel_broader_preview_cohort_operations import build_broader_preview_cohort_operations
from kernel_broader_preview_issue_ledger import build_broader_preview_issue_ledger

SCHEMA_VERSION = "agentos-broader-preview-health-summary.v1"
LAYOUT_DIRNAME = "broader-preview-health-summary"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def build_broader_preview_health_summary(
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
    summary_dir = root / f"broader-preview-health-summary-{label}"
    summary_dir.mkdir(parents=True, exist_ok=True)

    cohort_ops = build_broader_preview_cohort_operations(
        workspace=workspace,
        report_dir=str(root / "c"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )
    issue_ledger = build_broader_preview_issue_ledger(
        workspace=workspace,
        report_dir=str(root / "i"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )

    issue_counts = issue_ledger["summary"]["issue_counts"]
    pause_count = issue_counts["pause"]
    continue_count = issue_counts["continue"]
    expand_count = issue_counts["expand"]

    if pause_count > 0:
        operating_health = "watch"
        operating_recommendation = "continue_with_caution"
    elif continue_count > 0:
        operating_health = "steady"
        operating_recommendation = "continue"
    else:
        operating_health = "strong"
        operating_recommendation = "continue_and_prepare_expand"

    summary = {
        "ok": True,
        "candidate_state": cohort_ops["summary"]["candidate_state"],
        "audience_decision": cohort_ops["summary"]["audience_decision"],
        "operating_state": cohort_ops["summary"]["operating_state"],
        "operating_health": operating_health,
        "operating_recommendation": operating_recommendation,
        "issue_counts": issue_counts,
        "pause_relevant": issue_ledger["summary"]["pause_relevant"],
        "continue_relevant": issue_ledger["summary"]["continue_relevant"],
        "expand_relevant": issue_ledger["summary"]["expand_relevant"],
        "newly_introduced": issue_ledger["summary"]["newly_introduced"],
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(Path(workspace).resolve()),
        "summary_root": str(root),
        "summary_dir": str(summary_dir),
        "snapshot_label": label,
        "broader_preview_cohort_operations_manifest": cohort_ops,
        "broader_preview_issue_ledger_manifest": issue_ledger,
        "summary": summary,
        "artifacts": {},
    }

    lines = [
        "# AgentOS Broader Preview Health Summary",
        "",
        f"Run label: `{label}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Current health",
        "",
        f"- Candidate state: `{summary['candidate_state']}`",
        f"- Audience decision: `{summary['audience_decision']}`",
        f"- Operating state: `{summary['operating_state']}`",
        f"- Operating health: `{summary['operating_health']}`",
        f"- Operating recommendation: `{summary['operating_recommendation']}`",
        "",
        "## Issue counts",
        "",
        f"- Pause: `{pause_count}`",
        f"- Continue: `{continue_count}`",
        f"- Expand: `{expand_count}`",
        "",
    ]
    for title, items in (
        ("pause_relevant", summary["pause_relevant"]),
        ("continue_relevant", summary["continue_relevant"]),
        ("expand_relevant", summary["expand_relevant"]),
        ("newly_introduced", summary["newly_introduced"]),
    ):
        lines.append(f"## {title}")
        lines.append("")
        if items:
            lines.extend(f"- `{item}`" for item in items)
        else:
            lines.append("- none")
        lines.append("")

    markdown_path = summary_dir / "broader-preview-health-summary.md"
    manifest_path = summary_dir / "broader-preview-health-summary.json"
    latest_manifest_path = root / "latest-broader-preview-health-summary.json"
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    payload["artifacts"] = {
        "broader_preview_health_summary_markdown": str(markdown_path),
        "broader_preview_health_summary_manifest_json": str(manifest_path),
        "latest_broader_preview_health_summary_manifest_json": str(latest_manifest_path),
        "broader_preview_cohort_operations_manifest_json": cohort_ops["artifacts"]["broader_preview_cohort_operations_json"],
        "broader_preview_issue_ledger_manifest_json": issue_ledger["artifacts"]["broader_preview_issue_ledger_manifest_json"],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_broader_preview_health_summary(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "workspace",
        "summary_root",
        "summary_dir",
        "snapshot_label",
        "broader_preview_cohort_operations_manifest",
        "broader_preview_issue_ledger_manifest",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("broader_preview_cohort_operations_manifest", {}).get("schema_version") != "agentos-broader-preview-cohort-operations.v1":
        errors.append("broader_preview_cohort_operations_manifest must reference agentos-broader-preview-cohort-operations.v1")
    if payload.get("broader_preview_issue_ledger_manifest", {}).get("schema_version") != "agentos-broader-preview-issue-ledger.v1":
        errors.append("broader_preview_issue_ledger_manifest must reference agentos-broader-preview-issue-ledger.v1")
    summary = payload.get("summary", {})
    if summary.get("operating_health") not in {"watch", "steady", "strong"}:
        errors.append("summary.operating_health must be watch, steady, or strong")
    if summary.get("operating_recommendation") not in {"continue_with_caution", "continue", "continue_and_prepare_expand"}:
        errors.append("summary.operating_recommendation must be continue_with_caution, continue, or continue_and_prepare_expand")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export broader preview health summary")
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
        errors = validate_broader_preview_health_summary(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_broader_preview_health_summary(
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
    errors = validate_broader_preview_health_summary(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
