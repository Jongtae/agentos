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

from kernel_direct_boot_ux_burndown import build_direct_boot_ux_burndown
from kernel_evaluator_cohort_pack import build_evaluator_cohort_pack
from kernel_feedback_triage import build_feedback_triage
from kernel_platform_validation import build_platform_validation_matrix

SCHEMA_VERSION = "agentos-limited-preview-readiness-scoreboard.v1"
LAYOUT_DIRNAME = "limited-preview-readiness"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def _decision(*, blockers: int, burn_down_state: str, recommendation: str, watch_targets: int, watch_count: int) -> str:
    if blockers > 0 or burn_down_state == "blocked" or recommendation == "revise":
        return "hold"
    if recommendation == "hold" or watch_targets > 0 or watch_count > 0 or burn_down_state == "watch":
        return "extend_limited_preview"
    return "prepare_broader_preview_gate"


def build_limited_preview_readiness_scoreboard(
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
    run_dir = root / f"limited-preview-readiness-{snapshot_label or 'current'}"
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
    burndown = build_direct_boot_ux_burndown(
        workspace=workspace,
        report_dir=str(run_dir / "ux"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=snapshot_label,
        session_id=session_id,
        limit=limit,
    )
    platform = build_platform_validation_matrix(
        workspace=workspace,
        report_dir=str(run_dir / "platform"),
        install_root=install_root,
        metadata=metadata,
        snapshot_label=snapshot_label or "current",
    )

    blockers = triage["summary"]["blocker_count"]
    watch_count = triage["summary"]["watch_count"]
    watch_targets = len(burndown["summary"]["watch_targets"])
    recommendation = triage["summary"]["recommendation"]
    burn_down_state = burndown["summary"]["burn_down_state"]
    decision = _decision(
        blockers=blockers,
        burn_down_state=burn_down_state,
        recommendation=recommendation,
        watch_targets=watch_targets,
        watch_count=watch_count,
    )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(Path(workspace).resolve()),
        "scoreboard_root": str(root),
        "scoreboard_dir": str(run_dir),
        "snapshot_label": snapshot_label or "current",
        "components": {
            "evaluator_cohort_pack": cohort,
            "feedback_triage": triage,
            "direct_boot_ux_burndown": burndown,
            "platform_validation": platform,
        },
        "summary": {
            "ok": True,
            "limited_preview_decision": decision,
            "cohort_coverage": cohort["summary"]["delivery_scope"],
            "triage_state": triage["summary"]["promotion_state"],
            "direct_boot_confidence": "ready" if burndown["summary"]["burn_down_state"] == "clear" else ("watch" if burndown["summary"]["burn_down_state"] == "watch" else "blocked"),
            "install_later_confidence": "ready" if burndown["summary"]["setup_clarity"] == "ready" else "watch",
            "recovery_confidence": "ready" if burndown["summary"]["recovery_clarity"] == "ready" else "watch",
            "platform_baseline_ok": platform["summary"]["ok"],
            "blocker_count": blockers,
            "watch_count": watch_count,
            "polish_count": triage["summary"]["polish_count"],
            "outstanding_fix_targets": burndown["summary"]["outstanding_fix_targets"],
            "must_fix_before_broader_preview": triage["summary"]["must_fix_before_broader_preview"],
            "can_wait_until_after_broader_preview": triage["summary"]["can_wait_until_after_broader_preview"],
        },
        "artifacts": {},
    }
    markdown = [
        "# AgentOS Limited Preview Readiness Scoreboard",
        "",
        f"Run label: `{snapshot_label or 'current'}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Decision",
        "",
        f"- Limited preview decision: `{payload['summary']['limited_preview_decision']}`",
        f"- Cohort coverage: `{payload['summary']['cohort_coverage']}`",
        f"- Triage state: `{payload['summary']['triage_state']}`",
        f"- Direct-boot confidence: `{payload['summary']['direct_boot_confidence']}`",
        f"- Install-later confidence: `{payload['summary']['install_later_confidence']}`",
        f"- Recovery confidence: `{payload['summary']['recovery_confidence']}`",
        f"- Platform baseline ok: `{payload['summary']['platform_baseline_ok']}`",
        f"- Blockers: `{payload['summary']['blocker_count']}`",
        f"- Watch findings: `{payload['summary']['watch_count']}`",
        f"- Polish findings: `{payload['summary']['polish_count']}`",
        "",
        "## Outstanding before broader preview",
        "",
    ]
    if payload['summary']['must_fix_before_broader_preview']:
        markdown.extend(f"- `{item}`" for item in payload['summary']['must_fix_before_broader_preview'])
    else:
        markdown.append("- none")
    markdown.extend([
        "",
        "## Can wait after broader preview",
        "",
    ])
    if payload['summary']['can_wait_until_after_broader_preview']:
        markdown.extend(f"- `{item}`" for item in payload['summary']['can_wait_until_after_broader_preview'])
    else:
        markdown.append("- none")

    manifest_path = run_dir / "limited-preview-readiness-scoreboard.json"
    markdown_path = run_dir / "limited-preview-readiness-scoreboard.md"
    latest_manifest_path = root / "latest-limited-preview-readiness-scoreboard.json"
    markdown_path.write_text("\n".join(markdown) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "limited_preview_readiness_scoreboard_json": str(manifest_path),
        "limited_preview_readiness_scoreboard_markdown": str(markdown_path),
        "latest_limited_preview_readiness_scoreboard_json": str(latest_manifest_path),
        "evaluator_cohort_pack_json": cohort["artifacts"]["evaluator_cohort_pack_json"],
        "feedback_triage_manifest_json": triage["artifacts"]["feedback_triage_manifest_json"],
        "direct_boot_ux_burndown_manifest_json": burndown["artifacts"]["direct_boot_ux_burndown_manifest_json"],
        "platform_validation_manifest_json": str(Path(platform["report_dir"]) / "platform-validation-matrix.json") if "report_dir" in platform else "",
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_limited_preview_readiness_scoreboard(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {"schema_version", "generated_at_utc", "workspace", "scoreboard_root", "scoreboard_dir", "snapshot_label", "components", "summary", "artifacts"}
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    components = payload.get("components", {})
    if components.get("evaluator_cohort_pack", {}).get("schema_version") != "agentos-evaluator-cohort-pack.v1":
        errors.append("components.evaluator_cohort_pack must reference agentos-evaluator-cohort-pack.v1")
    if components.get("feedback_triage", {}).get("schema_version") != "agentos-feedback-triage.v1":
        errors.append("components.feedback_triage must reference agentos-feedback-triage.v1")
    if components.get("direct_boot_ux_burndown", {}).get("schema_version") != "agentos-direct-boot-ux-burndown.v1":
        errors.append("components.direct_boot_ux_burndown must reference agentos-direct-boot-ux-burndown.v1")
    if components.get("platform_validation", {}).get("schema_version") != "agentos-platform-validation-matrix.v1":
        errors.append("components.platform_validation must reference agentos-platform-validation-matrix.v1")
    summary = payload.get("summary", {})
    if summary.get("limited_preview_decision") not in {"hold", "extend_limited_preview", "prepare_broader_preview_gate"}:
        errors.append("summary.limited_preview_decision must be hold, extend_limited_preview, or prepare_broader_preview_gate")
    for key in ("cohort_coverage", "triage_state", "direct_boot_confidence", "install_later_confidence", "recovery_confidence"):
        if key not in summary:
            errors.append(f"summary.{key} must be present")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an AgentOS limited preview readiness scoreboard")
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
        errors = validate_limited_preview_readiness_scoreboard(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_limited_preview_readiness_scoreboard(
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
    errors = validate_limited_preview_readiness_scoreboard(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
        return 0 if not errors else 1

    print("AgentOS Limited Preview Readiness Scoreboard")
    print("============================================")
    print(f"Decision: {payload['summary']['limited_preview_decision']}")
    print(f"Triage state: {payload['summary']['triage_state']}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
