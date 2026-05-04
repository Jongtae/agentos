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

from kernel_feedback_triage import build_feedback_triage
from kernel_limited_preview_iteration_ledger import build_limited_preview_iteration_ledger
from kernel_broader_preview_cohort_operations import build_broader_preview_cohort_operations

SCHEMA_VERSION = "agentos-broader-preview-issue-ledger.v1"
LAYOUT_DIRNAME = "broader-preview-issue-ledger"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def build_broader_preview_issue_ledger(
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
    ledger_dir = root / f"broader-preview-issue-ledger-{label}"
    ledger_dir.mkdir(parents=True, exist_ok=True)

    triage = build_feedback_triage(
        workspace=workspace,
        report_dir=str(ledger_dir / "triage"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )
    iteration = build_limited_preview_iteration_ledger(
        workspace=workspace,
        report_dir=str(ledger_dir / "iteration"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )
    cohort_ops = build_broader_preview_cohort_operations(
        workspace=workspace,
        report_dir=str(ledger_dir / "cohort-ops"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )

    blockers = triage.get("summary", {}).get("must_fix_before_broader_preview", [])
    can_wait = triage.get("summary", {}).get("can_wait_until_after_broader_preview", [])
    current_watch = iteration.get("summary", {}).get("current_watch_items", [])
    newly_introduced = iteration.get("summary", {}).get("newly_introduced", [])

    pause_relevant = sorted(set(blockers))
    continue_relevant = sorted(set(current_watch) - set(pause_relevant))
    expand_relevant = sorted(set(can_wait) - set(pause_relevant) - set(continue_relevant))

    if pause_relevant:
        operating_decision = "pause_risk_present"
    elif continue_relevant:
        operating_decision = "continue_with_watch_items"
    else:
        operating_decision = "expand_ready"

    summary = {
        "ok": True,
        "candidate_state": cohort_ops["summary"]["candidate_state"],
        "audience_decision": cohort_ops["summary"]["audience_decision"],
        "operating_decision": operating_decision,
        "continue_relevant": continue_relevant,
        "expand_relevant": expand_relevant,
        "pause_relevant": pause_relevant,
        "newly_introduced": newly_introduced,
        "issue_counts": {
            "continue": len(continue_relevant),
            "expand": len(expand_relevant),
            "pause": len(pause_relevant),
        },
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(Path(workspace).resolve()),
        "ledger_root": str(root),
        "ledger_dir": str(ledger_dir),
        "snapshot_label": label,
        "feedback_triage_manifest": triage,
        "limited_preview_iteration_ledger_manifest": iteration,
        "broader_preview_cohort_operations_manifest": cohort_ops,
        "summary": summary,
        "artifacts": {},
    }

    lines = [
        "# AgentOS Broader Preview Issue Ledger",
        "",
        f"Run label: `{label}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Operating decision",
        "",
        f"- Candidate state: `{summary['candidate_state']}`",
        f"- Audience decision: `{summary['audience_decision']}`",
        f"- Operating decision: `{summary['operating_decision']}`",
        "",
    ]
    for title, items in (
        ("pause_relevant", pause_relevant),
        ("continue_relevant", continue_relevant),
        ("expand_relevant", expand_relevant),
        ("newly_introduced", newly_introduced),
    ):
        lines.append(f"## {title}")
        lines.append("")
        if items:
            lines.extend(f"- `{item}`" for item in items)
        else:
            lines.append("- none")
        lines.append("")

    markdown_path = ledger_dir / "broader-preview-issue-ledger.md"
    manifest_path = ledger_dir / "broader-preview-issue-ledger.json"
    latest_manifest_path = root / "latest-broader-preview-issue-ledger.json"
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    payload["artifacts"] = {
        "broader_preview_issue_ledger_markdown": str(markdown_path),
        "broader_preview_issue_ledger_manifest_json": str(manifest_path),
        "latest_broader_preview_issue_ledger_manifest_json": str(latest_manifest_path),
        "feedback_triage_manifest_json": triage["artifacts"]["feedback_triage_manifest_json"],
        "limited_preview_iteration_ledger_manifest_json": iteration["artifacts"]["limited_preview_iteration_ledger_manifest_json"],
        "broader_preview_cohort_operations_manifest_json": cohort_ops["artifacts"]["broader_preview_cohort_operations_json"],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_broader_preview_issue_ledger(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "workspace",
        "ledger_root",
        "ledger_dir",
        "snapshot_label",
        "feedback_triage_manifest",
        "limited_preview_iteration_ledger_manifest",
        "broader_preview_cohort_operations_manifest",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("feedback_triage_manifest", {}).get("schema_version") != "agentos-feedback-triage.v1":
        errors.append("feedback_triage_manifest must reference agentos-feedback-triage.v1")
    if payload.get("limited_preview_iteration_ledger_manifest", {}).get("schema_version") != "agentos-limited-preview-iteration-ledger.v1":
        errors.append("limited_preview_iteration_ledger_manifest must reference agentos-limited-preview-iteration-ledger.v1")
    if payload.get("broader_preview_cohort_operations_manifest", {}).get("schema_version") != "agentos-broader-preview-cohort-operations.v1":
        errors.append("broader_preview_cohort_operations_manifest must reference agentos-broader-preview-cohort-operations.v1")
    summary = payload.get("summary", {})
    if summary.get("operating_decision") not in {"pause_risk_present", "continue_with_watch_items", "expand_ready"}:
        errors.append("summary.operating_decision must be pause_risk_present, continue_with_watch_items, or expand_ready")
    for key in ("continue_relevant", "expand_relevant", "pause_relevant", "newly_introduced"):
        if not isinstance(summary.get(key), list):
            errors.append(f"summary.{key} must be a list")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export broader preview issue ledger")
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
        errors = validate_broader_preview_issue_ledger(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_broader_preview_issue_ledger(
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
    errors = validate_broader_preview_issue_ledger(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
