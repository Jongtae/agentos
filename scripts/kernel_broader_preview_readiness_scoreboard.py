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

from kernel_evaluator_cohort_pack import build_evaluator_cohort_pack
from kernel_recovery_clarity_fix_loop import build_recovery_clarity_fix_loop
from kernel_direct_boot_messaging_consistency import build_direct_boot_messaging_consistency
from kernel_limited_preview_iteration_ledger import build_limited_preview_iteration_ledger

SCHEMA_VERSION = "agentos-broader-preview-readiness-scoreboard.v1"
LAYOUT_DIRNAME = "broader-preview-readiness-scoreboard"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def build_broader_preview_readiness_scoreboard(
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
    run_dir = root / f"broader-preview-readiness-scoreboard-{snapshot_label or 'current'}"
    run_dir.mkdir(parents=True, exist_ok=True)

    cohort = build_evaluator_cohort_pack(
        workspace=workspace,
        report_dir=str(run_dir / "cohort"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=snapshot_label,
        session_id=session_id,
        limit=limit,
    )
    recovery = build_recovery_clarity_fix_loop(
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
    iteration = build_limited_preview_iteration_ledger(
        workspace=workspace,
        report_dir=str(run_dir / "iteration"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=snapshot_label,
        session_id=session_id,
        limit=limit,
    )

    cohort_posture = cohort.get("summary", {}).get("delivery_scope", "unknown")
    recovery_state = recovery.get("summary", {}).get("overall_state", "unknown")
    messaging_state = messaging.get("summary", {}).get("overall_state", "unknown")
    iteration_state = iteration.get("summary", {}).get("iteration_state", "unknown")

    blocked_reasons = []
    if recovery_state != "clear":
        blocked_reasons.append("recovery_clarity")
    if messaging_state != "ready":
        blocked_reasons.append("direct_boot_messaging")
    if iteration_state == "regressing":
        blocked_reasons.append("iteration_regression")
    if cohort_posture != "limited_preview_extension":
        blocked_reasons.append("cohort_posture")

    if blocked_reasons:
        candidate_state = "candidate_watch"
        audience_decision = "limited_preview_extension_only"
    else:
        candidate_state = "candidate_ready"
        audience_decision = "broader_preview_candidate"

    summary = {
        "ok": True,
        "candidate_state": candidate_state,
        "audience_decision": audience_decision,
        "recovery_clarity": recovery_state,
        "direct_boot_messaging": messaging_state,
        "iteration_stability": iteration_state,
        "cohort_posture": cohort_posture,
        "blocked_reasons": blocked_reasons,
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(Path(workspace).resolve()),
        "scoreboard_root": str(root),
        "scoreboard_dir": str(run_dir),
        "snapshot_label": snapshot_label or "current",
        "evaluator_cohort_pack_manifest": cohort,
        "recovery_clarity_fix_loop_manifest": recovery,
        "direct_boot_messaging_consistency_manifest": messaging,
        "limited_preview_iteration_ledger_manifest": iteration,
        "summary": summary,
        "artifacts": {},
    }

    markdown = [
        "# AgentOS Broader Preview Readiness Scoreboard",
        "",
        f"Run label: `{snapshot_label or 'current'}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Current decision",
        "",
        f"- Candidate state: `{candidate_state}`",
        f"- Audience decision: `{audience_decision}`",
        f"- Recovery clarity: `{recovery_state}`",
        f"- Direct-boot messaging: `{messaging_state}`",
        f"- Iteration stability: `{iteration_state}`",
        f"- Cohort posture: `{cohort_posture}`",
        "",
        "## Blocked reasons",
        "",
    ]
    if blocked_reasons:
        markdown.extend(f"- `{item}`" for item in blocked_reasons)
    else:
        markdown.append("- none")

    markdown_path = run_dir / "broader-preview-readiness-scoreboard.md"
    manifest_path = run_dir / "broader-preview-readiness-scoreboard.json"
    latest_manifest_path = root / "latest-broader-preview-readiness-scoreboard.json"
    markdown_path.write_text("\n".join(markdown) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "broader_preview_readiness_scoreboard_markdown": str(markdown_path),
        "broader_preview_readiness_scoreboard_manifest_json": str(manifest_path),
        "latest_broader_preview_readiness_scoreboard_manifest_json": str(latest_manifest_path),
        "evaluator_cohort_pack_manifest_json": cohort["artifacts"]["evaluator_cohort_pack_json"],
        "recovery_clarity_fix_loop_manifest_json": recovery["artifacts"]["recovery_clarity_fix_loop_json"],
        "direct_boot_messaging_consistency_manifest_json": messaging["artifacts"]["direct_boot_messaging_consistency_manifest_json"],
        "limited_preview_iteration_ledger_manifest_json": iteration["artifacts"]["limited_preview_iteration_ledger_manifest_json"],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_broader_preview_readiness_scoreboard(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "workspace",
        "scoreboard_root",
        "scoreboard_dir",
        "snapshot_label",
        "evaluator_cohort_pack_manifest",
        "recovery_clarity_fix_loop_manifest",
        "direct_boot_messaging_consistency_manifest",
        "limited_preview_iteration_ledger_manifest",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    summary = payload.get("summary", {})
    if summary.get("candidate_state") not in {"candidate_watch", "candidate_ready"}:
        errors.append("summary.candidate_state must be candidate_watch or candidate_ready")
    if summary.get("audience_decision") not in {"limited_preview_extension_only", "broader_preview_candidate"}:
        errors.append("summary.audience_decision must be limited_preview_extension_only or broader_preview_candidate")
    if payload.get("evaluator_cohort_pack_manifest", {}).get("schema_version") != "agentos-evaluator-cohort-pack.v1":
        errors.append("evaluator_cohort_pack_manifest must reference agentos-evaluator-cohort-pack.v1")
    if payload.get("recovery_clarity_fix_loop_manifest", {}).get("schema_version") != "agentos-recovery-clarity-fix-loop.v1":
        errors.append("recovery_clarity_fix_loop_manifest must reference agentos-recovery-clarity-fix-loop.v1")
    if payload.get("direct_boot_messaging_consistency_manifest", {}).get("schema_version") != "agentos-direct-boot-messaging-consistency.v1":
        errors.append("direct_boot_messaging_consistency_manifest must reference agentos-direct-boot-messaging-consistency.v1")
    if payload.get("limited_preview_iteration_ledger_manifest", {}).get("schema_version") != "agentos-limited-preview-iteration-ledger.v1":
        errors.append("limited_preview_iteration_ledger_manifest must reference agentos-limited-preview-iteration-ledger.v1")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an AgentOS broader preview readiness scoreboard")
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
        errors = validate_broader_preview_readiness_scoreboard(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_broader_preview_readiness_scoreboard(
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
    errors = validate_broader_preview_readiness_scoreboard(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
