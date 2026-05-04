#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kernel_preview_readiness_scorecard import build_preview_readiness_scorecard

SCHEMA_VERSION = "agentos-preview-rehearsal-loop.v1"
LAYOUT_DIRNAME = "preview-rehearsals"
REFERENCE_FILES = [
    ROOT_DIR / "docs" / "reference" / "preview-readiness-scorecard-v1.md",
    ROOT_DIR / "docs" / "reference" / "external-evaluation-runbook-contract-v1.md",
    ROOT_DIR / "docs" / "reference" / "preview-release-candidate-checklist-v1.md",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def _next_action(band: str, recommendation: str, scorecard_summary: dict) -> str:
    if recommendation == "revise":
        return "revise_before_preview"
    if "watch" in {scorecard_summary.get("direct_boot_quality"), scorecard_summary.get("setup_clarity"), scorecard_summary.get("recovery_clarity")} :
        return "repeat_rehearsal_after_review"
    if recommendation == "hold":
        return "collect_one_more_feedback_cycle"
    if band == "ready":
        return "proceed_to_preview_candidate"
    return "repeat_rehearsal_after_review"


def build_rehearsal_markdown(*, label: str, payload: dict, copied_references: list[str]) -> str:
    summary = payload["summary"]
    preflight = payload["preflight"]
    lines = [
        "# AgentOS Public Preview Rehearsal",
        "",
        f"Run label: `{label}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Preflight",
        "",
        f"- Passed: `{preflight['passed']}`",
        f"- Readiness band: `{summary['readiness_band']}`",
        f"- Recommendation: `{summary['recommendation']}`",
        f"- Next action: `{summary['next_action']}`",
        f"- Total score: `{summary['total_score']}`",
        f"- Direct-boot quality: `{summary['direct_boot_quality']}`",
        f"- Setup clarity: `{summary['setup_clarity']}`",
        f"- Recovery clarity: `{summary['recovery_clarity']}`",
        "",
        "## Loop",
        "",
        "1. Run the preview readiness scorecard and confirm the current band.",
        "2. Review the external evaluation checklist and artifact chain.",
        "3. Confirm install identity, recovery ladder, and platform baseline remain intact.",
        "4. Capture whether the run should proceed, hold, or revise.",
        "5. Store the rehearsal manifest as the current preview dry-run record.",
        "6. Treat direct-boot quality, setup clarity, and recovery clarity as first-class gates.",
        "",
        "## Gate details",
        "",
        f"- Platform baseline ok: `{preflight['checks']['platform_baseline_ok']}`",
        f"- Artifact chain complete: `{preflight['checks']['artifact_chain_complete']}`",
        f"- Recommendation acceptable: `{preflight['checks']['recommendation_acceptable']}`",
        f"- Readiness band acceptable: `{preflight['checks']['readiness_band_acceptable']}`",
        "",
        "## Included references",
        "",
    ]
    lines.extend(f"- `{Path(path).name}`" for path in copied_references)
    return "\n".join(lines) + "\n"


def build_preview_rehearsal_loop(
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
    run_label = snapshot_label or "current"
    run_dir = root / f"preview-rehearsal-{run_label}"
    run_dir.mkdir(parents=True, exist_ok=True)

    scorecard = build_preview_readiness_scorecard(
        workspace=workspace,
        report_dir=str(run_dir / "readiness"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=run_label,
        session_id=session_id,
        limit=limit,
    )

    references_dir = run_dir / "references"
    references_dir.mkdir(parents=True, exist_ok=True)
    copied_references: list[str] = []
    for ref in REFERENCE_FILES:
        if not ref.exists():
            continue
        dest = references_dir / ref.name
        shutil.copyfile(ref, dest)
        copied_references.append(str(dest))

    summary = scorecard["summary"]
    preflight = {
        "passed": summary["artifact_chain_complete"] and summary["recommendation"] != "revise" and summary["readiness_band"] in {"ready", "watch"},
        "checks": {
            "platform_baseline_ok": scorecard["components"]["platform_validation"]["summary"]["ok"],
            "artifact_chain_complete": summary["artifact_chain_complete"],
            "recommendation_acceptable": summary["recommendation"] in {"advance", "hold"},
            "readiness_band_acceptable": summary["readiness_band"] in {"ready", "watch"},
        },
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "run_label": run_label,
        "workspace": str(Path(workspace).resolve()),
        "rehearsal_root": str(root),
        "rehearsal_dir": str(run_dir),
        "references": copied_references,
        "preview_readiness_scorecard": scorecard,
        "preflight": preflight,
        "summary": {
            "ok": True,
            "total_score": summary["total_score"],
            "readiness_band": summary["readiness_band"],
            "recommendation": summary["recommendation"],
            "next_action": _next_action(summary["readiness_band"], summary["recommendation"], summary),
            "preflight_passed": preflight["passed"],
            "direct_boot_quality": summary["direct_boot_quality"],
            "setup_clarity": summary["setup_clarity"],
            "recovery_clarity": summary["recovery_clarity"],
            "ux_areas_flagged": summary.get("ux_areas_flagged", []),
        },
        "artifacts": {},
    }

    markdown_path = run_dir / "preview-rehearsal.md"
    manifest_path = run_dir / "preview-rehearsal-manifest.json"
    latest_manifest_path = root / "latest-preview-rehearsal-manifest.json"
    markdown_path.write_text(build_rehearsal_markdown(label=run_label, payload=payload, copied_references=copied_references), encoding="utf-8")
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "preview_rehearsal_markdown": str(markdown_path),
        "preview_rehearsal_manifest_json": str(manifest_path),
        "latest_preview_rehearsal_manifest_json": str(latest_manifest_path),
        "preview_readiness_scorecard_json": scorecard["artifacts"]["preview_readiness_scorecard_json"],
        "external_evaluation_manifest_json": scorecard["artifacts"]["external_evaluation_manifest"],
        "platform_validation_manifest_json": scorecard["artifacts"]["platform_validation_manifest"],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_preview_rehearsal_loop(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "run_label",
        "workspace",
        "rehearsal_root",
        "rehearsal_dir",
        "references",
        "preview_readiness_scorecard",
        "preflight",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    scorecard = payload.get("preview_readiness_scorecard")
    if not isinstance(scorecard, dict) or scorecard.get("schema_version") != "agentos-preview-readiness-scorecard.v1":
        errors.append("preview_readiness_scorecard must reference agentos-preview-readiness-scorecard.v1")
    preflight = payload.get("preflight", {})
    if not isinstance(preflight, dict) or "checks" not in preflight:
        errors.append("preflight.checks must be present")
    summary = payload.get("summary", {})
    if summary.get("next_action") not in {
        "proceed_to_preview_candidate",
        "collect_one_more_feedback_cycle",
        "repeat_rehearsal_after_review",
        "revise_before_preview",
    }:
        errors.append("summary.next_action must be a known preview rehearsal action")
    for key in ("direct_boot_quality", "setup_clarity", "recovery_clarity"):
        if summary.get(key) not in {"ready", "watch"}:
            errors.append(f"summary.{key} must be ready or watch")
    for key in (
        "preview_rehearsal_markdown",
        "preview_rehearsal_manifest_json",
        "preview_readiness_scorecard_json",
    ):
        if not payload.get("artifacts", {}).get(key):
            errors.append(f"artifacts.{key} must be present")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an AgentOS public preview rehearsal loop")
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
        errors = validate_preview_rehearsal_loop(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_preview_rehearsal_loop(
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
    errors = validate_preview_rehearsal_loop(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
        return 0 if not errors else 1

    print("AgentOS Public Preview Rehearsal")
    print("===============================")
    print(f"Readiness band: {payload['summary']['readiness_band']}")
    print(f"Recommendation: {payload['summary']['recommendation']}")
    print(f"Next action: {payload['summary']['next_action']}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
