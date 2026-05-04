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

from kernel_external_evaluation_checklist import build_external_evaluation_checklist

SCHEMA_VERSION = "agentos-evaluator-cohort-pack.v1"
LAYOUT_DIRNAME = "evaluator-cohort-packs"
REFERENCE_FILES = [
    ROOT_DIR / "docs" / "reference" / "preview-evaluation-kit-contract-v1.md",
    ROOT_DIR / "docs" / "reference" / "external-evaluation-runbook-contract-v1.md",
    ROOT_DIR / "docs" / "reference" / "public-preview-candidate-v1.md",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def build_cohort_markdown(*, label: str, payload: dict, copied_references: list[str]) -> str:
    summary = payload["summary"]
    lines = [
        "# AgentOS Evaluator Cohort Pack",
        "",
        f"Cohort label: `{label}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Intended audience",
        "",
        "This pack is for a bounded, operator-guided limited preview cohort.",
        "It assumes the appliance-first AgentOS path is the product truth and keeps the audience intentionally narrow.",
        "",
        "## Product path to evaluate",
        "",
        "- Boot the default AgentOS appliance path.",
        "- Reach `AgentOS Setup -> AgentOS Managed Session -> ai>`.",
        "- Use `Install AgentOS` only when evaluating persistence.",
        "- Use `AgentOS Recovery` when validating safe-shell fallback and rejoin.",
        "",
        "## Cohort package",
        "",
        f"- Audience mode: `{summary['audience_mode']}`",
        f"- Delivery scope: `{summary['delivery_scope']}`",
        f"- Preview decision: `{summary['preview_decision']}`",
        f"- Includes preview evaluation kit: `{summary['includes_preview_kit']}`",
        f"- Includes external evaluation checklist: `{summary['includes_external_evaluation']}`",
        f"- Includes feedback template: `{summary['includes_feedback_template']}`",
        "",
        "## Cohort evaluator procedure",
        "",
        "1. Read the evaluator guide in the nested preview kit.",
        "2. Follow the external evaluation checklist to validate boot, setup, install-later, and recovery.",
        "3. Keep feedback bounded to direct-boot product truth, not broad platform expansion.",
        "4. Return a normalized feedback packet through the included feedback template path.",
        "",
        "## Included references",
        "",
    ]
    lines.extend(f"- `{Path(path).name}`" for path in copied_references)
    return "\n".join(lines) + "\n"


def build_evaluator_cohort_pack(
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
    cohort_dir = root / f"evaluator-cohort-{label}"
    cohort_dir.mkdir(parents=True, exist_ok=True)

    external_manifest = build_external_evaluation_checklist(
        workspace=workspace,
        report_dir=str(cohort_dir / "external-evaluation"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )

    references_dir = cohort_dir / "references"
    references_dir.mkdir(parents=True, exist_ok=True)
    copied_references: list[str] = []
    for ref in REFERENCE_FILES:
        if not ref.exists():
            continue
        dest = references_dir / ref.name
        shutil.copyfile(ref, dest)
        copied_references.append(str(dest))

    preview_kit_manifest_json = external_manifest["artifacts"]["preview_kit_manifest_json"]
    feedback_template_json = external_manifest["artifacts"]["feedback_template_json"]
    manifest_path = cohort_dir / "evaluator-cohort-pack.json"
    latest_manifest_path = root / "latest-evaluator-cohort-pack.json"
    markdown_path = cohort_dir / "cohort-guide.md"

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "cohort_label": label,
        "workspace": str(Path(workspace).resolve()),
        "cohort_root": str(root),
        "cohort_dir": str(cohort_dir),
        "references": copied_references,
        "external_evaluation_manifest": external_manifest,
        "summary": {
            "ok": True,
            "audience_mode": "bounded_operator_guided",
            "delivery_scope": "limited_preview_extension",
            "preview_decision": "limited_preview_extension_only",
            "includes_preview_kit": True,
            "includes_external_evaluation": True,
            "includes_feedback_template": True,
            "reference_count": len(copied_references),
        },
        "artifacts": {},
    }

    markdown_path.write_text(build_cohort_markdown(label=label, payload=payload, copied_references=copied_references), encoding="utf-8")
    payload["artifacts"] = {
        "cohort_guide_markdown": str(markdown_path),
        "evaluator_cohort_pack_json": str(manifest_path),
        "latest_evaluator_cohort_pack_json": str(latest_manifest_path),
        "external_evaluation_manifest_json": external_manifest["artifacts"]["external_evaluation_manifest_json"],
        "preview_kit_manifest_json": preview_kit_manifest_json,
        "feedback_template_json": feedback_template_json,
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_evaluator_cohort_pack(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "cohort_label",
        "workspace",
        "cohort_root",
        "cohort_dir",
        "references",
        "external_evaluation_manifest",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    external = payload.get("external_evaluation_manifest")
    if not isinstance(external, dict) or external.get("schema_version") != "agentos-external-evaluation-checklist.v1":
        errors.append("external_evaluation_manifest must reference agentos-external-evaluation-checklist.v1")
    summary = payload.get("summary", {})
    if summary.get("audience_mode") != "bounded_operator_guided":
        errors.append("summary.audience_mode must be bounded_operator_guided")
    if summary.get("delivery_scope") != "limited_preview_extension":
        errors.append("summary.delivery_scope must be limited_preview_extension")
    if summary.get("preview_decision") != "limited_preview_extension_only":
        errors.append("summary.preview_decision must be limited_preview_extension_only")
    for key in (
        "cohort_guide_markdown",
        "evaluator_cohort_pack_json",
        "external_evaluation_manifest_json",
        "preview_kit_manifest_json",
        "feedback_template_json",
    ):
        if not payload.get("artifacts", {}).get(key):
            errors.append(f"artifacts.{key} must be present")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an AgentOS evaluator cohort pack")
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
        errors = validate_evaluator_cohort_pack(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_evaluator_cohort_pack(
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
    errors = validate_evaluator_cohort_pack(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
        return 0 if not errors else 1

    print("AgentOS Evaluator Cohort Pack")
    print("============================")
    print(f"Cohort dir: {payload['cohort_dir']}")
    print(f"Guide: {payload['artifacts']['cohort_guide_markdown']}")
    print(f"External evaluation manifest: {payload['artifacts']['external_evaluation_manifest_json']}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
