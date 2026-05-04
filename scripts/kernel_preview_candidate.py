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

from kernel_preview_rehearsal_loop import build_preview_rehearsal_loop

SCHEMA_VERSION = "agentos-preview-candidate.v1"
LAYOUT_DIRNAME = "preview-candidates"
REFERENCE_FILES = [
    ROOT_DIR / "docs" / "reference" / "preview-rehearsal-loop-v1.md",
    ROOT_DIR / "docs" / "reference" / "preview-readiness-scorecard-v1.md",
    ROOT_DIR / "docs" / "reference" / "preview-release-candidate-checklist-v1.md",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def _candidate_decision(rehearsal: dict) -> tuple[str, str]:
    summary = rehearsal["summary"]
    if summary["recommendation"] == "revise":
        return "not_ready", "revision_required_before_broader_preview"
    if "watch" in {summary.get("direct_boot_quality"), summary.get("setup_clarity"), summary.get("recovery_clarity")} :
        return "candidate_watch", "limited_preview_extension_only"
    if summary["preflight_passed"] and summary["readiness_band"] == "ready":
        return "candidate_ready", "broader_preview_candidate"
    if summary["preflight_passed"] and summary["readiness_band"] == "watch":
        return "candidate_watch", "limited_preview_extension_only"
    return "not_ready", "repeat_rehearsal_first"


def build_candidate_markdown(*, label: str, payload: dict, copied_references: list[str]) -> str:
    summary = payload["summary"]
    lines = [
        "# AgentOS Preview Candidate",
        "",
        f"Candidate label: `{label}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Decision",
        "",
        f"- Candidate state: `{summary['candidate_state']}`",
        f"- Audience decision: `{summary['audience_decision']}`",
        f"- Readiness band: `{summary['readiness_band']}`",
        f"- Recommendation: `{summary['recommendation']}`",
        f"- Next action: `{summary['next_action']}`",
        f"- Direct-boot quality: `{summary['direct_boot_quality']}`",
        f"- Setup clarity: `{summary['setup_clarity']}`",
        f"- Recovery clarity: `{summary['recovery_clarity']}`",
        "",
        "## Why",
        "",
        "This candidate pack is the Stage 5 closeout artifact for deciding whether the current baseline is suitable for a broader preview audience.",
        "It preserves the rehearsal result and turns it into a single decision statement.",
        "",
        "## Included references",
        "",
    ]
    lines.extend(f"- `{Path(path).name}`" for path in copied_references)
    return "\n".join(lines) + "\n"


def build_preview_candidate(
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
    candidate_dir = root / f"preview-candidate-{label}"
    candidate_dir.mkdir(parents=True, exist_ok=True)

    rehearsal = build_preview_rehearsal_loop(
        workspace=workspace,
        report_dir=str(candidate_dir / "rehearsal"),
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
        if not ref.exists():
            continue
        dest = references_dir / ref.name
        shutil.copyfile(ref, dest)
        copied_references.append(str(dest))

    candidate_state, audience_decision = _candidate_decision(rehearsal)
    summary = rehearsal["summary"]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "candidate_label": label,
        "workspace": str(Path(workspace).resolve()),
        "candidate_root": str(root),
        "candidate_dir": str(candidate_dir),
        "references": copied_references,
        "preview_rehearsal": rehearsal,
        "summary": {
            "ok": True,
            "candidate_state": candidate_state,
            "audience_decision": audience_decision,
            "readiness_band": summary["readiness_band"],
            "recommendation": summary["recommendation"],
            "next_action": summary["next_action"],
            "preflight_passed": summary["preflight_passed"],
            "direct_boot_quality": summary["direct_boot_quality"],
            "setup_clarity": summary["setup_clarity"],
            "recovery_clarity": summary["recovery_clarity"],
        },
        "artifacts": {},
    }

    markdown_path = candidate_dir / "preview-candidate.md"
    manifest_path = candidate_dir / "preview-candidate-manifest.json"
    latest_manifest_path = root / "latest-preview-candidate-manifest.json"
    markdown_path.write_text(build_candidate_markdown(label=label, payload=payload, copied_references=copied_references), encoding="utf-8")
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "preview_candidate_markdown": str(markdown_path),
        "preview_candidate_manifest_json": str(manifest_path),
        "latest_preview_candidate_manifest_json": str(latest_manifest_path),
        "preview_rehearsal_manifest_json": rehearsal["artifacts"]["preview_rehearsal_manifest_json"],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_preview_candidate(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "candidate_label",
        "workspace",
        "candidate_root",
        "candidate_dir",
        "references",
        "preview_rehearsal",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    rehearsal = payload.get("preview_rehearsal")
    if not isinstance(rehearsal, dict) or rehearsal.get("schema_version") != "agentos-preview-rehearsal-loop.v1":
        errors.append("preview_rehearsal must reference agentos-preview-rehearsal-loop.v1")
    summary = payload.get("summary", {})
    if summary.get("candidate_state") not in {"candidate_ready", "candidate_watch", "not_ready"}:
        errors.append("summary.candidate_state must be a known candidate state")
    if summary.get("audience_decision") not in {
        "broader_preview_candidate",
        "limited_preview_extension_only",
        "repeat_rehearsal_first",
        "revision_required_before_broader_preview",
    }:
        errors.append("summary.audience_decision must be a known decision value")
    for key in ("direct_boot_quality", "setup_clarity", "recovery_clarity"):
        if summary.get(key) not in {"ready", "watch"}:
            errors.append(f"summary.{key} must be ready or watch")
    if not payload.get("artifacts", {}).get("preview_candidate_manifest_json"):
        errors.append("artifacts.preview_candidate_manifest_json must be present")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an AgentOS preview candidate decision pack")
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
        errors = validate_preview_candidate(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_preview_candidate(
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
    errors = validate_preview_candidate(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
        return 0 if not errors else 1

    print("AgentOS Preview Candidate")
    print("=========================")
    print(f"Candidate state: {payload['summary']['candidate_state']}")
    print(f"Audience decision: {payload['summary']['audience_decision']}")
    print(f"Recommendation: {payload['summary']['recommendation']}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
