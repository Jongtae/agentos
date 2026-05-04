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

from kernel_external_evaluation_checklist import build_external_evaluation_checklist
from kernel_platform_validation import build_platform_validation_matrix

SCHEMA_VERSION = "agentos-preview-readiness-scorecard.v1"
LAYOUT_DIRNAME = "preview-readiness"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def _ux_quality(external_evaluation: dict) -> dict:
    findings = (((external_evaluation or {}).get("feedback_intake_manifest") or {}).get("feedback_packet") or {}).get("findings") or []
    areas = {str(item.get("area", "")).strip() for item in findings if isinstance(item, dict)}
    boot_score = 25 if "boot" not in areas else 10
    setup_score = 25 if "setup" not in areas else 10
    recovery_score = 25 if "recovery" not in areas else 10
    return {
        "direct_boot_quality": boot_score,
        "setup_clarity": setup_score,
        "recovery_clarity": recovery_score,
        "areas_flagged": sorted(a for a in areas if a),
    }

def _band(score: int, recommendation: str) -> str:
    if recommendation == "revise":
        return "hold"
    if recommendation == "hold":
        return "watch" if score >= 70 else "hold"
    if score >= 85:
        return "ready"
    if score >= 70:
        return "watch"
    return "hold"


def build_preview_readiness_scorecard(
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
    scorecard_dir = root / f"preview-readiness-{snapshot_label or 'current'}"
    scorecard_dir.mkdir(parents=True, exist_ok=True)

    platform = build_platform_validation_matrix(
        workspace=workspace,
        report_dir=str(scorecard_dir / "platform"),
        install_root=install_root,
        metadata=metadata,
        snapshot_label=snapshot_label or "current",
    )
    evaluation = build_external_evaluation_checklist(
        workspace=workspace,
        report_dir=str(scorecard_dir / "evaluation"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=snapshot_label or "current",
        session_id=session_id,
        limit=limit,
    )

    ux = _ux_quality(evaluation)
    scores = {
        "platform_baseline": 20 if platform["summary"]["ok"] else 8,
        "preview_artifact_chain": 15 if evaluation["summary"]["includes_preview_kit"] and evaluation["summary"]["includes_milestone_bundle"] else 5,
        "feedback_loop": 15 if evaluation["summary"]["includes_feedback_template"] else 5,
        "direct_boot_quality": ux["direct_boot_quality"],
        "setup_clarity": ux["setup_clarity"],
        "recovery_clarity": ux["recovery_clarity"],
        "recommendation_signal": 10 if evaluation["summary"]["recommendation"] == "advance" else (5 if evaluation["summary"]["recommendation"] == "hold" else 0),
    }
    total_score = sum(scores.values())
    recommendation = evaluation["summary"]["recommendation"]

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(Path(workspace).resolve()),
        "scorecard_root": str(root),
        "scorecard_dir": str(scorecard_dir),
        "snapshot_label": snapshot_label or "current",
        "components": {
            "platform_validation": platform,
            "external_evaluation": evaluation,
        },
        "score_breakdown": scores,
        "summary": {
            "ok": True,
            "total_score": total_score,
            "readiness_band": _band(total_score, recommendation),
            "recommendation": recommendation,
            "active_architecture": platform["summary"]["active_architecture"],
            "artifact_chain_complete": evaluation["summary"]["includes_preview_kit"] and evaluation["summary"]["includes_milestone_bundle"],
            "direct_boot_quality": "watch" if ux["direct_boot_quality"] < 20 else "ready",
            "setup_clarity": "watch" if ux["setup_clarity"] < 20 else "ready",
            "recovery_clarity": "watch" if ux["recovery_clarity"] < 20 else "ready",
            "ux_areas_flagged": ux["areas_flagged"],
        },
        "artifacts": {
            "platform_validation_manifest": str(scorecard_dir / "platform" / "platform-validation-matrix.json"),
            "external_evaluation_manifest": evaluation["artifacts"]["external_evaluation_manifest_json"],
        },
    }
    manifest_path = scorecard_dir / "preview-readiness-scorecard.json"
    latest_manifest_path = root / "latest-preview-readiness-scorecard.json"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    payload["artifacts"]["preview_readiness_scorecard_json"] = str(manifest_path)
    payload["artifacts"]["latest_preview_readiness_scorecard_json"] = str(latest_manifest_path)
    return payload


def validate_preview_readiness_scorecard(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "workspace",
        "scorecard_root",
        "scorecard_dir",
        "snapshot_label",
        "components",
        "score_breakdown",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    components = payload.get("components", {})
    platform = components.get("platform_validation")
    external = components.get("external_evaluation")
    if not isinstance(platform, dict) or platform.get("schema_version") != "agentos-platform-validation-matrix.v1":
        errors.append("components.platform_validation must reference agentos-platform-validation-matrix.v1")
    if not isinstance(external, dict) or external.get("schema_version") != "agentos-external-evaluation-checklist.v1":
        errors.append("components.external_evaluation must reference agentos-external-evaluation-checklist.v1")
    breakdown = payload.get("score_breakdown", {})
    for key in ("platform_baseline", "preview_artifact_chain", "feedback_loop", "direct_boot_quality", "setup_clarity", "recovery_clarity", "recommendation_signal"):
        if key not in breakdown:
            errors.append(f"score_breakdown.{key} must be present")
    summary = payload.get("summary", {})
    if summary.get("readiness_band") not in {"ready", "watch", "hold"}:
        errors.append("summary.readiness_band must be ready, watch, or hold")
    for key in ("direct_boot_quality", "setup_clarity", "recovery_clarity"):
        if summary.get(key) not in {"ready", "watch"}:
            errors.append(f"summary.{key} must be ready or watch")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an AgentOS preview readiness scorecard")
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
        errors = validate_preview_readiness_scorecard(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_preview_readiness_scorecard(
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
    errors = validate_preview_readiness_scorecard(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
        return 0 if not errors else 1

    print("AgentOS Preview Readiness Scorecard")
    print("===================================")
    print(f"Score: {payload['summary']['total_score']}")
    print(f"Band: {payload['summary']['readiness_band']}")
    print(f"Recommendation: {payload['summary']['recommendation']}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
