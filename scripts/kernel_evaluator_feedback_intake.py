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

from kernel_preview_evaluation_kit import build_preview_evaluation_kit

SCHEMA_VERSION = "agentos-evaluator-feedback-intake.v1"
INTAKE_LAYOUT_DIRNAME = "feedback-intake"
ALLOWED_CHANNELS = {"internal_preview", "expert_review", "guided_eval"}
ALLOWED_RECOMMENDATIONS = {"advance", "hold", "revise"}
ALLOWED_SEVERITIES = {"critical", "high", "medium", "low", "note"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_intake_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == INTAKE_LAYOUT_DIRNAME:
        return report_root
    return report_root / INTAKE_LAYOUT_DIRNAME


def _normalize_feedback(raw: dict | None) -> dict:
    raw = raw or {}
    findings = raw.get("findings")
    if not isinstance(findings, list):
        findings = []
    normalized_findings = []
    for item in findings:
        if not isinstance(item, dict):
            continue
        normalized_findings.append(
            {
                "title": str(item.get("title", "untitled-finding")),
                "severity": str(item.get("severity", "note")),
                "area": str(item.get("area", "general")),
                "detail": str(item.get("detail", "")),
                "artifact_ref": str(item.get("artifact_ref", "")),
            }
        )
    return {
        "evaluator_id": str(raw.get("evaluator_id", "pending-evaluator")),
        "channel": str(raw.get("channel", "internal_preview")),
        "session_label": str(raw.get("session_label", "pending-session")),
        "recommendation": str(raw.get("recommendation", "hold")),
        "summary": str(raw.get("summary", "pending evaluator summary")),
        "findings": normalized_findings,
        "follow_up_requests": [str(item) for item in raw.get("follow_up_requests", [])] if isinstance(raw.get("follow_up_requests"), list) else [],
    }


def build_feedback_intake(
    *,
    workspace: str,
    report_dir: str,
    preview_kit_manifest: str = "",
    feedback_file: str = "",
    install_root: str = "",
    metadata: str = "",
    diagnostics_manifest: str = "",
    history_dir: str = "",
    snapshot_label: str = "current",
    session_id: str = "",
    limit: int = 50,
) -> dict:
    intake_root = resolve_intake_root(report_dir)
    intake_dir = intake_root / f"feedback-intake-{snapshot_label or 'current'}"
    intake_dir.mkdir(parents=True, exist_ok=True)

    if preview_kit_manifest:
        kit_manifest = json.loads(Path(preview_kit_manifest).read_text(encoding="utf-8"))
    else:
        kit_manifest = build_preview_evaluation_kit(
            workspace=workspace,
            report_dir=str(intake_dir / "preview-kit"),
            install_root=install_root,
            metadata=metadata,
            diagnostics_manifest=diagnostics_manifest,
            history_dir=history_dir,
            snapshot_label=snapshot_label,
            session_id=session_id,
            limit=limit,
        )

    raw_feedback = {}
    if feedback_file:
        raw_feedback = json.loads(Path(feedback_file).read_text(encoding="utf-8"))
    feedback = _normalize_feedback(raw_feedback)

    template = {
        "evaluator_id": "pending-evaluator",
        "channel": "internal_preview",
        "session_label": "pending-session",
        "recommendation": "hold",
        "summary": "pending evaluator summary",
        "findings": [
            {
                "title": "example finding",
                "severity": "medium",
                "area": "install_identity",
                "detail": "Describe the issue, risk, or observation in one paragraph.",
                "artifact_ref": "artifacts.evaluator_guide_markdown",
            }
        ],
        "follow_up_requests": [
            "List concrete follow-up requests here."
        ],
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(Path(workspace).resolve()),
        "intake_root": str(intake_root),
        "intake_dir": str(intake_dir),
        "preview_kit_manifest": kit_manifest,
        "feedback_contract": {
            "allowed_channels": sorted(ALLOWED_CHANNELS),
            "allowed_recommendations": sorted(ALLOWED_RECOMMENDATIONS),
            "allowed_severities": sorted(ALLOWED_SEVERITIES),
        },
        "feedback_packet": feedback,
        "feedback_template": template,
        "artifact_links": {
            "preview_kit_manifest_json": kit_manifest["artifacts"]["preview_kit_manifest_json"],
            "evaluator_guide_markdown": kit_manifest["artifacts"]["evaluator_guide_markdown"],
            "milestone_bundle_manifest_json": kit_manifest["artifacts"]["milestone_bundle_manifest_json"],
            "milestone_bundle_dir": kit_manifest["artifacts"]["milestone_bundle_dir"],
        },
        "summary": {
            "ok": True,
            "has_preview_kit": True,
            "has_feedback_findings": bool(feedback["findings"]),
            "recommendation": feedback["recommendation"],
            "channel": feedback["channel"],
        },
    }
    manifest_path = intake_dir / "feedback-intake-manifest.json"
    template_path = intake_dir / "feedback-template.json"
    latest_manifest_path = intake_root / "latest-feedback-intake-manifest.json"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    template_path.write_text(json.dumps(template, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "feedback_intake_manifest_json": str(manifest_path),
        "feedback_template_json": str(template_path),
        "latest_feedback_intake_manifest_json": str(latest_manifest_path),
    }
    return payload


def validate_feedback_intake(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "workspace",
        "intake_root",
        "intake_dir",
        "preview_kit_manifest",
        "feedback_contract",
        "feedback_packet",
        "feedback_template",
        "artifact_links",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")

    feedback = payload.get("feedback_packet", {})
    if not isinstance(feedback, dict):
        errors.append("feedback_packet must be an object")
    else:
        if feedback.get("channel") not in ALLOWED_CHANNELS:
            errors.append("feedback_packet.channel must be a supported channel")
        if feedback.get("recommendation") not in ALLOWED_RECOMMENDATIONS:
            errors.append("feedback_packet.recommendation must be a supported recommendation")
        findings = feedback.get("findings")
        if not isinstance(findings, list):
            errors.append("feedback_packet.findings must be a list")
        else:
            for idx, finding in enumerate(findings):
                if not isinstance(finding, dict):
                    errors.append(f"feedback_packet.findings[{idx}] must be an object")
                    continue
                if finding.get("severity") not in ALLOWED_SEVERITIES:
                    errors.append(f"feedback_packet.findings[{idx}].severity must be supported")

    preview = payload.get("preview_kit_manifest")
    if not isinstance(preview, dict):
        errors.append("preview_kit_manifest must be an object")
    else:
        if preview.get("schema_version") != "agentos-preview-evaluation-kit.v1":
            errors.append("preview_kit_manifest must reference agentos-preview-evaluation-kit.v1")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an AgentOS evaluator feedback intake packet")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--report-dir", default="./workspaces/default/artifacts")
    parser.add_argument("--preview-kit-manifest", default="")
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
        errors = validate_feedback_intake(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_feedback_intake(
        workspace=args.workspace,
        report_dir=args.report_dir,
        preview_kit_manifest=args.preview_kit_manifest,
        feedback_file=args.feedback_file,
        install_root=args.install_root,
        metadata=args.metadata,
        diagnostics_manifest=args.diagnostics_manifest,
        history_dir=args.history_dir,
        snapshot_label=args.snapshot_label,
        session_id=args.session_id,
        limit=args.limit,
    )
    errors = validate_feedback_intake(payload)
    payload["summary"]["ok"] = not errors
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(json.dumps(payload, ensure_ascii=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
