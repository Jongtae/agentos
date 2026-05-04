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
from kernel_recovery_clarity_fix_loop import build_recovery_clarity_fix_loop
from kernel_direct_boot_messaging_consistency import build_direct_boot_messaging_consistency

SCHEMA_VERSION = "agentos-limited-preview-iteration-ledger.v1"
LAYOUT_DIRNAME = "limited-preview-iteration-ledger"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def _extract_current_watch_set(triage: dict, recovery_loop: dict, messaging: dict) -> set[str]:
    triage_titles = set(triage.get("summary", {}).get("must_fix_before_broader_preview", []))
    recovery_titles = set(recovery_loop.get("summary", {}).get("must_fix_before_broader_preview", []))
    messaging_targets = {
        name
        for name in ("boot_messaging", "setup_messaging", "install_later_messaging", "recovery_messaging")
        if messaging.get("summary", {}).get(name) in {"blocked", "watch"}
    }
    return triage_titles | recovery_titles | messaging_targets


def _discover_previous_ledger(root: Path, current_label: str) -> Path | None:
    latest_path = root / "latest-limited-preview-iteration-ledger.json"
    if not latest_path.exists():
        return None
    try:
        payload = json.loads(latest_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if str(payload.get("snapshot_label", "")) == current_label:
        return None
    return latest_path


def build_limited_preview_iteration_ledger(
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
    run_dir = root / f"limited-preview-iteration-ledger-{snapshot_label or 'current'}"
    run_dir.mkdir(parents=True, exist_ok=True)

    triage = build_feedback_triage(
        workspace=workspace,
        report_dir=str(run_dir / "triage"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=snapshot_label,
        session_id=session_id,
        limit=limit,
    )
    recovery_loop = build_recovery_clarity_fix_loop(
        workspace=workspace,
        report_dir=str(run_dir / "recovery"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=snapshot_label,
        session_id=session_id,
        limit=limit,
    )
    messaging = build_direct_boot_messaging_consistency(
        workspace=workspace,
        report_dir=str(run_dir / "messaging"),
        snapshot_label=snapshot_label,
    )

    current_watch_set = _extract_current_watch_set(triage, recovery_loop, messaging)
    previous_path = _discover_previous_ledger(root, snapshot_label or "current")
    previous_watch_set: set[str] = set()
    previous_label = ""
    if previous_path:
        previous_payload = json.loads(previous_path.read_text(encoding="utf-8"))
        previous_label = str(previous_payload.get("snapshot_label", ""))
        previous_watch_set = set(previous_payload.get("summary", {}).get("current_watch_items", []))

    fixed_since_last = sorted(previous_watch_set - current_watch_set)
    still_watching = sorted(current_watch_set & previous_watch_set) if previous_watch_set else sorted(current_watch_set)
    newly_introduced = sorted(current_watch_set - previous_watch_set) if previous_watch_set else []

    if not previous_watch_set:
        iteration_state = "baseline"
    elif newly_introduced:
        iteration_state = "regressing"
    elif fixed_since_last:
        iteration_state = "improving"
    else:
        iteration_state = "steady"

    summary = {
        "ok": True,
        "iteration_state": iteration_state,
        "current_watch_items": sorted(current_watch_set),
        "fixed_since_last_iteration": fixed_since_last,
        "still_watching": still_watching,
        "newly_introduced": newly_introduced,
        "previous_iteration_label": previous_label or "none",
        "current_iteration_label": snapshot_label or "current",
        "recovery_clarity": recovery_loop.get("summary", {}).get("overall_state", "unknown"),
        "direct_boot_consistency": messaging.get("summary", {}).get("overall_state", "unknown"),
        "triage_promotion_state": triage.get("summary", {}).get("promotion_state", "unknown"),
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(Path(workspace).resolve()),
        "ledger_root": str(root),
        "ledger_dir": str(run_dir),
        "snapshot_label": snapshot_label or "current",
        "feedback_triage_manifest": triage,
        "recovery_clarity_fix_loop_manifest": recovery_loop,
        "direct_boot_messaging_consistency_manifest": messaging,
        "summary": summary,
        "artifacts": {},
    }

    markdown = [
        "# AgentOS Limited Preview Iteration Ledger",
        "",
        f"Run label: `{snapshot_label or 'current'}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Iteration state",
        "",
        f"- Iteration state: `{iteration_state}`",
        f"- Previous iteration: `{summary['previous_iteration_label']}`",
        f"- Current watch count: `{len(summary['current_watch_items'])}`",
        "",
        "## Changes since last iteration",
        "",
    ]
    for label, items in (
        ("fixed_since_last_iteration", fixed_since_last),
        ("still_watching", still_watching),
        ("newly_introduced", newly_introduced),
    ):
        markdown.append(f"### {label}")
        if items:
            markdown.extend(f"- `{item}`" for item in items)
        else:
            markdown.append("- none")
        markdown.append("")

    markdown_path = run_dir / "limited-preview-iteration-ledger.md"
    manifest_path = run_dir / "limited-preview-iteration-ledger.json"
    latest_manifest_path = root / "latest-limited-preview-iteration-ledger.json"
    markdown_path.write_text("\n".join(markdown) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "limited_preview_iteration_ledger_markdown": str(markdown_path),
        "limited_preview_iteration_ledger_manifest_json": str(manifest_path),
        "latest_limited_preview_iteration_ledger_manifest_json": str(latest_manifest_path),
        "feedback_triage_manifest_json": triage["artifacts"]["feedback_triage_manifest_json"],
        "recovery_clarity_fix_loop_manifest_json": recovery_loop["artifacts"]["recovery_clarity_fix_loop_json"],
        "direct_boot_messaging_consistency_manifest_json": messaging["artifacts"]["direct_boot_messaging_consistency_manifest_json"],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_limited_preview_iteration_ledger(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "workspace",
        "ledger_root",
        "ledger_dir",
        "snapshot_label",
        "feedback_triage_manifest",
        "recovery_clarity_fix_loop_manifest",
        "direct_boot_messaging_consistency_manifest",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    summary = payload.get("summary", {})
    if summary.get("iteration_state") not in {"baseline", "improving", "steady", "regressing"}:
        errors.append("summary.iteration_state must be baseline, improving, steady, or regressing")
    for key in ("current_watch_items", "fixed_since_last_iteration", "still_watching", "newly_introduced"):
        if not isinstance(summary.get(key), list):
            errors.append(f"summary.{key} must be a list")
    if payload.get("feedback_triage_manifest", {}).get("schema_version") != "agentos-feedback-triage.v1":
        errors.append("feedback_triage_manifest must reference agentos-feedback-triage.v1")
    if payload.get("recovery_clarity_fix_loop_manifest", {}).get("schema_version") != "agentos-recovery-clarity-fix-loop.v1":
        errors.append("recovery_clarity_fix_loop_manifest must reference agentos-recovery-clarity-fix-loop.v1")
    if payload.get("direct_boot_messaging_consistency_manifest", {}).get("schema_version") != "agentos-direct-boot-messaging-consistency.v1":
        errors.append("direct_boot_messaging_consistency_manifest must reference agentos-direct-boot-messaging-consistency.v1")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an AgentOS limited preview iteration ledger")
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
        errors = validate_limited_preview_iteration_ledger(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_limited_preview_iteration_ledger(
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
    errors = validate_limited_preview_iteration_ledger(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
