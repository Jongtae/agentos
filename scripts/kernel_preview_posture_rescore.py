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

from kernel_broader_preview_readiness_scoreboard import build_broader_preview_readiness_scoreboard
from kernel_recovery_watch_reevaluation import build_recovery_watch_reevaluation

SCHEMA_VERSION = "agentos-preview-posture-rescore.v1"
LAYOUT_DIRNAME = "preview-posture-rescore"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def build_preview_posture_rescore(
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
    run_dir = root / f"preview-posture-rescore-{snapshot_label or 'current'}"
    run_dir.mkdir(parents=True, exist_ok=True)

    broader = build_broader_preview_readiness_scoreboard(
        workspace=workspace,
        report_dir=str(run_dir / "broader"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=snapshot_label,
        session_id=session_id,
        limit=limit,
    )
    recovery = build_recovery_watch_reevaluation(
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

    broader_state = broader["summary"]["candidate_state"]
    broader_audience = broader["summary"]["audience_decision"]
    recovery_state = recovery["summary"]["recovery_state"]

    if broader_state == "candidate_ready" and recovery_state == "ready":
        candidate_state = "broader_preview_candidate"
        audience_decision = "broader_preview_candidate"
    else:
        candidate_state = "candidate_watch"
        audience_decision = "limited_preview_extension_only"

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(Path(workspace).resolve()),
        "rescore_root": str(root),
        "rescore_dir": str(run_dir),
        "snapshot_label": snapshot_label or "current",
        "broader_preview_readiness_manifest": broader,
        "recovery_watch_reevaluation_manifest": recovery,
        "summary": {
            "ok": True,
            "broader_readiness_state": broader_state,
            "broader_readiness_audience": broader_audience,
            "recovery_state": recovery_state,
            "candidate_state": candidate_state,
            "audience_decision": audience_decision,
        },
        "artifacts": {},
    }

    markdown = [
        "# AgentOS Preview Posture Re-score",
        "",
        f"Run label: `{snapshot_label or 'current'}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Updated posture",
        "",
        f"- Broader readiness state: `{broader_state}`",
        f"- Recovery state: `{recovery_state}`",
        f"- Candidate state: `{candidate_state}`",
        f"- Audience decision: `{audience_decision}`",
    ]

    markdown_path = run_dir / "preview-posture-rescore.md"
    manifest_path = run_dir / "preview-posture-rescore.json"
    latest_manifest_path = root / "latest-preview-posture-rescore.json"
    markdown_path.write_text("\n".join(markdown) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "preview_posture_rescore_markdown": str(markdown_path),
        "preview_posture_rescore_manifest_json": str(manifest_path),
        "latest_preview_posture_rescore_manifest_json": str(latest_manifest_path),
        "broader_preview_readiness_manifest_json": broader["artifacts"]["broader_preview_readiness_scoreboard_manifest_json"],
        "recovery_watch_reevaluation_manifest_json": recovery["artifacts"]["recovery_watch_reevaluation_manifest_json"],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_preview_posture_rescore(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "workspace",
        "rescore_root",
        "rescore_dir",
        "snapshot_label",
        "broader_preview_readiness_manifest",
        "recovery_watch_reevaluation_manifest",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("broader_preview_readiness_manifest", {}).get("schema_version") != "agentos-broader-preview-readiness-scoreboard.v1":
        errors.append("broader_preview_readiness_manifest must reference agentos-broader-preview-readiness-scoreboard.v1")
    if payload.get("recovery_watch_reevaluation_manifest", {}).get("schema_version") != "agentos-recovery-watch-reevaluation.v1":
        errors.append("recovery_watch_reevaluation_manifest must reference agentos-recovery-watch-reevaluation.v1")
    if payload.get("summary", {}).get("candidate_state") not in {"candidate_watch", "broader_preview_candidate"}:
        errors.append("summary.candidate_state must be candidate_watch or broader_preview_candidate")
    if payload.get("summary", {}).get("audience_decision") not in {"limited_preview_extension_only", "broader_preview_candidate"}:
        errors.append("summary.audience_decision must be limited_preview_extension_only or broader_preview_candidate")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an AgentOS preview posture rescore report")
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
        errors = validate_preview_posture_rescore(payload)
        if errors:
            for item in errors:
                print(item, file=sys.stderr)
            return 1
        print("PASS")
        return 0

    payload = build_preview_posture_rescore(
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
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print(json.dumps(payload["summary"], ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
