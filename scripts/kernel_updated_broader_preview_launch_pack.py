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

from kernel_broader_preview_launch_pack import build_broader_preview_launch_pack
from kernel_preview_posture_rescore import build_preview_posture_rescore

SCHEMA_VERSION = "agentos-updated-broader-preview-launch-pack.v1"
LAYOUT_DIRNAME = "updated-broader-preview-launch-packs"
PUBLIC_STATEMENT = ROOT_DIR / "docs" / "reference" / "public-preview-candidate-v1.md"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def build_updated_broader_preview_launch_pack(
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
    pack_dir = root / f"updated-broader-preview-launch-pack-{label}"
    pack_dir.mkdir(parents=True, exist_ok=True)

    rescore = build_preview_posture_rescore(
        workspace=workspace,
        report_dir=str(pack_dir / "rescore"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )
    prior_launch = build_broader_preview_launch_pack(
        workspace=workspace,
        report_dir=str(pack_dir / "prior-launch"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )

    references_dir = pack_dir / "references"
    references_dir.mkdir(parents=True, exist_ok=True)
    copied_statement = ""
    if PUBLIC_STATEMENT.exists():
        dest = references_dir / PUBLIC_STATEMENT.name
        dest.write_text(PUBLIC_STATEMENT.read_text(encoding="utf-8"), encoding="utf-8")
        copied_statement = str(dest)

    rescore_summary = rescore["summary"]
    prior_summary = prior_launch["summary"]
    summary = {
        "ok": True,
        "candidate_state": rescore_summary["candidate_state"],
        "audience_decision": rescore_summary["audience_decision"],
        "broader_readiness_state": rescore_summary["broader_readiness_state"],
        "recovery_state": rescore_summary["recovery_state"],
        "prior_candidate_state": prior_summary["candidate_state"],
        "prior_audience_decision": prior_summary["audience_decision"],
        "public_statement_status": "included" if copied_statement else "missing",
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "launch_label": label,
        "workspace": str(Path(workspace).resolve()),
        "launch_pack_root": str(root),
        "launch_pack_dir": str(pack_dir),
        "preview_posture_rescore": rescore,
        "prior_broader_preview_launch_pack": prior_launch,
        "public_statement_reference": copied_statement,
        "summary": summary,
        "artifacts": {},
    }

    lines = [
        "# AgentOS Updated Broader Preview Launch Pack",
        "",
        f"Launch label: `{label}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Updated decision",
        "",
        f"- Candidate state: `{summary['candidate_state']}`",
        f"- Audience decision: `{summary['audience_decision']}`",
        f"- Broader readiness state: `{summary['broader_readiness_state']}`",
        f"- Recovery state: `{summary['recovery_state']}`",
        f"- Previous candidate state: `{summary['prior_candidate_state']}`",
        f"- Previous audience decision: `{summary['prior_audience_decision']}`",
        f"- Public statement: `{summary['public_statement_status']}`",
    ]

    markdown_path = pack_dir / "updated-broader-preview-launch-pack.md"
    manifest_path = pack_dir / "updated-broader-preview-launch-pack.json"
    latest_manifest_path = root / "latest-updated-broader-preview-launch-pack.json"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "updated_broader_preview_launch_pack_markdown": str(markdown_path),
        "updated_broader_preview_launch_pack_json": str(manifest_path),
        "latest_updated_broader_preview_launch_pack_json": str(latest_manifest_path),
        "preview_posture_rescore_manifest_json": rescore["artifacts"]["preview_posture_rescore_manifest_json"],
        "prior_broader_preview_launch_pack_json": prior_launch["artifacts"]["broader_preview_launch_pack_json"],
        "public_statement_reference": copied_statement,
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_updated_broader_preview_launch_pack(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "launch_label",
        "workspace",
        "launch_pack_root",
        "launch_pack_dir",
        "preview_posture_rescore",
        "prior_broader_preview_launch_pack",
        "public_statement_reference",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("preview_posture_rescore", {}).get("schema_version") != "agentos-preview-posture-rescore.v1":
        errors.append("preview_posture_rescore must reference agentos-preview-posture-rescore.v1")
    if payload.get("prior_broader_preview_launch_pack", {}).get("schema_version") != "agentos-broader-preview-launch-pack.v1":
        errors.append("prior_broader_preview_launch_pack must reference agentos-broader-preview-launch-pack.v1")
    summary = payload.get("summary", {})
    if summary.get("candidate_state") not in {"candidate_watch", "broader_preview_candidate"}:
        errors.append("summary.candidate_state must be candidate_watch or broader_preview_candidate")
    if summary.get("audience_decision") not in {"limited_preview_extension_only", "broader_preview_candidate"}:
        errors.append("summary.audience_decision must be limited_preview_extension_only or broader_preview_candidate")
    if summary.get("public_statement_status") not in {"included", "missing"}:
        errors.append("summary.public_statement_status must be included or missing")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an updated AgentOS broader preview launch pack")
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
        errors = validate_updated_broader_preview_launch_pack(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_updated_broader_preview_launch_pack(
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
    errors = validate_updated_broader_preview_launch_pack(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
