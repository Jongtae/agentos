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

from kernel_broader_preview_health_summary import build_broader_preview_health_summary
from kernel_broader_preview_drift_ledger import build_broader_preview_drift_ledger

SCHEMA_VERSION = "agentos-broader-preview-weekly-summary.v1"
LAYOUT_DIRNAME = "broader-preview-weekly-summaries"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def build_broader_preview_weekly_summary(
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
    summary_dir = root / f"broader-preview-weekly-summary-{label}"
    summary_dir.mkdir(parents=True, exist_ok=True)
    support_root = root.parent

    health = build_broader_preview_health_summary(
        workspace=workspace,
        report_dir=str(support_root / "w-h"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )
    drift = build_broader_preview_drift_ledger(
        workspace=workspace,
        report_dir=str(support_root / "w-d"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )

    health_summary = health["summary"]
    drift_summary = drift["summary"]
    summary = {
        "ok": True,
        "candidate_state": health_summary["candidate_state"],
        "audience_decision": health_summary["audience_decision"],
        "operating_health": health_summary["operating_health"],
        "operating_recommendation": health_summary["operating_recommendation"],
        "drift_state": drift_summary["drift_state"],
        "signal_state": drift["current_signal_snapshot"]["summary"]["signal_state"],
        "weekly_posture": "stable"
        if health_summary["operating_health"] in {"steady", "strong"} and drift_summary["drift_state"] != "regressing"
        else "watch",
        "pause_relevant_count": health_summary["issue_counts"]["pause"],
        "continue_relevant_count": health_summary["issue_counts"]["continue"],
        "expand_relevant_count": health_summary["issue_counts"]["expand"],
        "improved_fields": drift_summary["improved_fields"],
        "regressed_fields": drift_summary["regressed_fields"],
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "summary_label": label,
        "workspace": str(Path(workspace).resolve()),
        "summary_root": str(root),
        "summary_dir": str(summary_dir),
        "broader_preview_health_summary": health,
        "broader_preview_drift_ledger": drift,
        "summary": summary,
        "artifacts": {},
    }

    lines = [
        "# AgentOS Broader Preview Weekly Summary",
        "",
        f"Summary label: `{label}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Weekly posture",
        "",
        f"- Candidate state: `{summary['candidate_state']}`",
        f"- Audience decision: `{summary['audience_decision']}`",
        f"- Operating health: `{summary['operating_health']}`",
        f"- Operating recommendation: `{summary['operating_recommendation']}`",
        f"- Drift state: `{summary['drift_state']}`",
        f"- Signal state: `{summary['signal_state']}`",
        f"- Weekly posture: `{summary['weekly_posture']}`",
        f"- Pause issues: `{summary['pause_relevant_count']}`",
        f"- Continue issues: `{summary['continue_relevant_count']}`",
        f"- Expand issues: `{summary['expand_relevant_count']}`",
        "",
        "## Drift detail",
        "",
    ]
    for title, items in (
        ("improved_fields", summary["improved_fields"]),
        ("regressed_fields", summary["regressed_fields"]),
    ):
        lines.append(f"### {title}")
        if items:
            lines.extend(f"- `{item}`" for item in items)
        else:
            lines.append("- none")
        lines.append("")

    markdown_path = summary_dir / "broader-preview-weekly-summary.md"
    manifest_path = summary_dir / "broader-preview-weekly-summary.json"
    latest_manifest_path = root / "latest-broader-preview-weekly-summary.json"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "broader_preview_weekly_summary_markdown": str(markdown_path),
        "broader_preview_weekly_summary_json": str(manifest_path),
        "latest_broader_preview_weekly_summary_json": str(latest_manifest_path),
        "broader_preview_health_summary_json": health["artifacts"]["broader_preview_health_summary_manifest_json"],
        "broader_preview_drift_ledger_json": drift["artifacts"]["broader_preview_drift_ledger_json"],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_broader_preview_weekly_summary(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "summary_label",
        "workspace",
        "summary_root",
        "summary_dir",
        "broader_preview_health_summary",
        "broader_preview_drift_ledger",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("broader_preview_health_summary", {}).get("schema_version") != "agentos-broader-preview-health-summary.v1":
        errors.append("broader_preview_health_summary must reference agentos-broader-preview-health-summary.v1")
    if payload.get("broader_preview_drift_ledger", {}).get("schema_version") != "agentos-broader-preview-drift-ledger.v1":
        errors.append("broader_preview_drift_ledger must reference agentos-broader-preview-drift-ledger.v1")
    if payload.get("summary", {}).get("weekly_posture") not in {"watch", "stable"}:
        errors.append("summary.weekly_posture must be watch or stable")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export broader preview weekly summary")
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
        errors = validate_broader_preview_weekly_summary(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_broader_preview_weekly_summary(
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
    errors = validate_broader_preview_weekly_summary(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
