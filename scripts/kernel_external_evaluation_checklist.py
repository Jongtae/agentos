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

from kernel_evaluator_feedback_intake import build_feedback_intake

SCHEMA_VERSION = "agentos-external-evaluation-checklist.v1"
LAYOUT_DIRNAME = "external-evaluation-runs"
REFERENCE_FILES = [
    ROOT_DIR / "docs" / "reference" / "preview-evaluation-kit-contract-v1.md",
    ROOT_DIR / "docs" / "reference" / "evaluator-feedback-intake-contract-v1.md",
    ROOT_DIR / "docs" / "reference" / "public-milestone-bundle-contract.md",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def build_checklist_markdown(*, label: str, manifest: dict, copied_references: list[str]) -> str:
    lines = [
        "# AgentOS External Evaluation Checklist",
        "",
        f"Run label: `{label}`",
        f"Generated at: `{_utc_now()}`",
        "",
        "## Artifact chain",
        "",
        f"1. Public milestone bundle: `{manifest['artifact_links']['milestone_bundle_manifest_json']}`",
        f"2. Preview evaluation kit: `{manifest['artifact_links']['preview_kit_manifest_json']}`",
        f"3. Evaluator guide: `{manifest['artifact_links']['evaluator_guide_markdown']}`",
        f"4. Feedback intake manifest: `{manifest['artifacts']['feedback_intake_manifest_json']}`",
        f"5. Feedback template: `{manifest['artifacts']['feedback_template_json']}`",
        "",
        "## Evaluator procedure",
        "",
        "1. Read the evaluator guide and preview references.",
        "2. Review the milestone bundle and operator review artifacts.",
        "3. Validate install identity, managed session entry, and the recovery ladder.",
        "4. Record findings in the feedback template.",
        "5. Normalize the packet with `agentos-kernelctl feedback-intake` and attach the manifest.",
        "",
        "## Required checks",
        "",
        "- Install path matches `AgentOS Setup -> AgentOS Managed Session -> ai>`.",
        "- Recovery ladder remains explicit and usable.",
        "- Platform validation still matches the current x86_64 baseline.",
        "- Recommendation is one of `advance`, `hold`, or `revise`.",
        "",
        "## Included references",
        "",
    ]
    lines.extend(f"- `{Path(path).name}`" for path in copied_references)
    return "\n".join(lines) + "\n"


def build_external_evaluation_checklist(
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
    run_dir = root / f"external-evaluation-{snapshot_label or 'current'}"
    run_dir.mkdir(parents=True, exist_ok=True)

    intake_manifest = build_feedback_intake(
        workspace=workspace,
        report_dir=str(run_dir / "feedback"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=snapshot_label,
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

    checklist_path = run_dir / "external-evaluation-checklist.md"
    manifest_path = run_dir / "external-evaluation-manifest.json"
    latest_manifest_path = root / "latest-external-evaluation-manifest.json"
    checklist_path.write_text(
        build_checklist_markdown(
            label=snapshot_label or "current",
            manifest=intake_manifest,
            copied_references=copied_references,
        ),
        encoding="utf-8",
    )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "run_label": snapshot_label or "current",
        "workspace": str(Path(workspace).resolve()),
        "run_root": str(root),
        "run_dir": str(run_dir),
        "references": copied_references,
        "artifacts": {
            "external_evaluation_checklist_markdown": str(checklist_path),
            "external_evaluation_manifest_json": str(manifest_path),
            "latest_external_evaluation_manifest_json": str(latest_manifest_path),
            "preview_kit_manifest_json": intake_manifest["artifact_links"]["preview_kit_manifest_json"],
            "evaluator_guide_markdown": intake_manifest["artifact_links"]["evaluator_guide_markdown"],
            "feedback_intake_manifest_json": str(run_dir / "feedback" / "feedback-intake" / f"feedback-intake-{snapshot_label or 'current'}" / "feedback-intake-manifest.json"),
            "feedback_template_json": str(run_dir / "feedback" / "feedback-intake" / f"feedback-intake-{snapshot_label or 'current'}" / "feedback-template.json"),
        },
        "artifact_links": intake_manifest["artifact_links"],
        "feedback_intake_manifest": intake_manifest,
        "summary": {
            "ok": True,
            "includes_feedback_template": True,
            "includes_preview_kit": True,
            "includes_milestone_bundle": True,
            "reference_count": len(copied_references),
            "recommendation": intake_manifest["feedback_packet"]["recommendation"],
        },
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_external_evaluation_checklist(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "run_label",
        "workspace",
        "run_root",
        "run_dir",
        "references",
        "artifacts",
        "artifact_links",
        "feedback_intake_manifest",
        "summary",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    intake = payload.get("feedback_intake_manifest")
    if not isinstance(intake, dict):
        errors.append("feedback_intake_manifest must be an object")
    elif intake.get("schema_version") != "agentos-evaluator-feedback-intake.v1":
        errors.append("feedback_intake_manifest must reference agentos-evaluator-feedback-intake.v1")
    artifacts = payload.get("artifacts", {})
    for key in (
        "external_evaluation_checklist_markdown",
        "external_evaluation_manifest_json",
        "preview_kit_manifest_json",
        "feedback_intake_manifest_json",
        "feedback_template_json",
    ):
        if not artifacts.get(key):
            errors.append(f"artifacts.{key} must be present")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an AgentOS external evaluation checklist")
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
        errors = validate_external_evaluation_checklist(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_external_evaluation_checklist(
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
    errors = validate_external_evaluation_checklist(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
        return 0 if not errors else 1

    print("AgentOS External Evaluation Checklist")
    print("====================================")
    print(f"Run dir: {payload['run_dir']}")
    print(f"Checklist: {payload['artifacts']['external_evaluation_checklist_markdown']}")
    print(f"Feedback manifest: {payload['artifacts']['feedback_intake_manifest_json']}")
    print(f"Preview kit: {payload['artifacts']['preview_kit_manifest_json']}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
