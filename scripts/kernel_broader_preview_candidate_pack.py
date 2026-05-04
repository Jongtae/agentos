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

from kernel_limited_preview_readiness_scoreboard import build_limited_preview_readiness_scoreboard
from kernel_preview_candidate import build_preview_candidate

SCHEMA_VERSION = "agentos-broader-preview-candidate-pack.v1"
LAYOUT_DIRNAME = "broader-preview-candidates"
REFERENCE_FILES = [
    ROOT_DIR / "docs" / "reference" / "limited-preview-readiness-scoreboard-v1.md",
    ROOT_DIR / "docs" / "reference" / "preview-candidate-decision-pack-v1.md",
    ROOT_DIR / "docs" / "reference" / "public-preview-candidate-v1.md",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def _promotion_state(*, limited_preview_decision: str, audience_decision: str) -> tuple[str, str]:
    if limited_preview_decision == "prepare_broader_preview_gate" and audience_decision in {"broader_preview_candidate", "limited_preview_extension_only"}:
        return "candidate_ready", "broader_preview_candidate"
    if limited_preview_decision == "extend_limited_preview" or audience_decision == "limited_preview_extension_only":
        return "candidate_watch", "limited_preview_extension_only"
    return "blocked", "revision_required_before_broader_preview"


def build_broader_preview_candidate_pack_markdown(*, label: str, payload: dict) -> str:
    summary = payload["summary"]
    lines = [
        "# AgentOS Broader Preview Candidate Pack",
        "",
        f"Candidate label: `{label}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Decision",
        "",
        f"- Promotion state: `{summary['promotion_state']}`",
        f"- Audience decision: `{summary['audience_decision']}`",
        f"- Limited preview decision: `{summary['limited_preview_decision']}`",
        f"- Legacy preview candidate state: `{summary['legacy_preview_candidate_state']}`",
        f"- Cohort coverage: `{summary['cohort_coverage']}`",
        f"- Blockers: `{summary['blocker_count']}`",
        f"- Watch findings: `{summary['watch_count']}`",
        f"- Polish findings: `{summary['polish_count']}`",
        f"- Direct-boot confidence: `{summary['direct_boot_confidence']}`",
        f"- Install-later confidence: `{summary['install_later_confidence']}`",
        f"- Recovery confidence: `{summary['recovery_confidence']}`",
        "",
        "## Must fix before broader preview",
        "",
    ]
    must_fix = summary.get("must_fix_before_broader_preview", [])
    if must_fix:
        lines.extend(f"- `{item}`" for item in must_fix)
    else:
        lines.append("- none")
    lines.extend([
        "",
        "## Can wait until after broader preview",
        "",
    ])
    can_wait = summary.get("can_wait_until_after_broader_preview", [])
    if can_wait:
        lines.extend(f"- `{item}`" for item in can_wait)
    else:
        lines.append("- none")
    lines.extend([
        "",
        "## Outstanding UX targets",
        "",
    ])
    targets = summary.get("outstanding_fix_targets", [])
    if targets:
        lines.extend(f"- `{item}`" for item in targets)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def build_broader_preview_candidate_pack(
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
    candidate_dir = root / f"broader-preview-candidate-{label}"
    candidate_dir.mkdir(parents=True, exist_ok=True)

    scoreboard = build_limited_preview_readiness_scoreboard(
        workspace=workspace,
        report_dir=str(candidate_dir / "limited-preview-readiness"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )
    preview_candidate = build_preview_candidate(
        workspace=workspace,
        report_dir=str(candidate_dir / "preview-candidate"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )

    references_dir = candidate_dir / "references"
    references_dir.mkdir(parents=True, exist_ok=True)
    copied_references: list[str] = []
    for ref in REFERENCE_FILES:
        if ref.exists():
            dest = references_dir / ref.name
            dest.write_text(ref.read_text(encoding="utf-8"), encoding="utf-8")
            copied_references.append(str(dest))

    scoreboard_summary = scoreboard["summary"]
    preview_summary = preview_candidate["summary"]
    promotion_state, audience_decision = _promotion_state(
        limited_preview_decision=scoreboard_summary["limited_preview_decision"],
        audience_decision=preview_summary["audience_decision"],
    )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "candidate_label": label,
        "workspace": str(Path(workspace).resolve()),
        "candidate_root": str(root),
        "candidate_dir": str(candidate_dir),
        "references": copied_references,
        "limited_preview_readiness": scoreboard,
        "preview_candidate": preview_candidate,
        "summary": {
            "ok": True,
            "promotion_state": promotion_state,
            "audience_decision": audience_decision,
            "limited_preview_decision": scoreboard_summary["limited_preview_decision"],
            "legacy_preview_candidate_state": preview_summary["candidate_state"],
            "cohort_coverage": scoreboard_summary["cohort_coverage"],
            "triage_state": scoreboard_summary["triage_state"],
            "direct_boot_confidence": scoreboard_summary["direct_boot_confidence"],
            "install_later_confidence": scoreboard_summary["install_later_confidence"],
            "recovery_confidence": scoreboard_summary["recovery_confidence"],
            "platform_baseline_ok": scoreboard_summary["platform_baseline_ok"],
            "blocker_count": scoreboard_summary["blocker_count"],
            "watch_count": scoreboard_summary["watch_count"],
            "polish_count": scoreboard_summary["polish_count"],
            "outstanding_fix_targets": scoreboard_summary["outstanding_fix_targets"],
            "must_fix_before_broader_preview": scoreboard_summary["must_fix_before_broader_preview"],
            "can_wait_until_after_broader_preview": scoreboard_summary["can_wait_until_after_broader_preview"],
        },
        "artifacts": {},
    }

    markdown_path = candidate_dir / "broader-preview-candidate-pack.md"
    manifest_path = candidate_dir / "broader-preview-candidate-pack.json"
    latest_manifest_path = root / "latest-broader-preview-candidate-pack.json"
    markdown_path.write_text(build_broader_preview_candidate_pack_markdown(label=label, payload=payload), encoding="utf-8")
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "broader_preview_candidate_pack_markdown": str(markdown_path),
        "broader_preview_candidate_pack_json": str(manifest_path),
        "latest_broader_preview_candidate_pack_json": str(latest_manifest_path),
        "limited_preview_readiness_json": scoreboard["artifacts"]["limited_preview_readiness_scoreboard_json"],
        "preview_candidate_manifest_json": preview_candidate["artifacts"]["preview_candidate_manifest_json"],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_broader_preview_candidate_pack(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "candidate_label",
        "workspace",
        "candidate_root",
        "candidate_dir",
        "references",
        "limited_preview_readiness",
        "preview_candidate",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("limited_preview_readiness", {}).get("schema_version") != "agentos-limited-preview-readiness-scoreboard.v1":
        errors.append("limited_preview_readiness must reference agentos-limited-preview-readiness-scoreboard.v1")
    if payload.get("preview_candidate", {}).get("schema_version") != "agentos-preview-candidate.v1":
        errors.append("preview_candidate must reference agentos-preview-candidate.v1")
    summary = payload.get("summary", {})
    if summary.get("promotion_state") not in {"candidate_ready", "candidate_watch", "blocked"}:
        errors.append("summary.promotion_state must be candidate_ready, candidate_watch, or blocked")
    if summary.get("audience_decision") not in {
        "broader_preview_candidate",
        "limited_preview_extension_only",
        "revision_required_before_broader_preview",
    }:
        errors.append("summary.audience_decision must be a known broader preview audience decision")
    for key in (
        "cohort_coverage",
        "triage_state",
        "direct_boot_confidence",
        "install_later_confidence",
        "recovery_confidence",
        "must_fix_before_broader_preview",
        "can_wait_until_after_broader_preview",
    ):
        if key not in summary:
            errors.append(f"summary.{key} must be present")
    if not payload.get("artifacts", {}).get("broader_preview_candidate_pack_json"):
        errors.append("artifacts.broader_preview_candidate_pack_json must be present")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an AgentOS broader preview candidate pack")
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
        errors = validate_broader_preview_candidate_pack(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_broader_preview_candidate_pack(
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
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        print(f"broader preview candidate pack ready: {payload['artifacts']['broader_preview_candidate_pack_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
