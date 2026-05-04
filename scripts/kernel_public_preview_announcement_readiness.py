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

from kernel_public_preview_escalation_pack import build_public_preview_escalation_pack

SCHEMA_VERSION = "agentos-public-preview-announcement-readiness.v1"
LAYOUT_DIRNAME = "public-preview-announcement-readiness"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def build_public_preview_announcement_readiness(
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
    ready_dir = root / f"public-preview-announcement-readiness-{label}"
    ready_dir.mkdir(parents=True, exist_ok=True)

    escalation = build_public_preview_escalation_pack(
        workspace=workspace,
        report_dir=str(root.parent / "ppar-e"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )
    escal_summary = escalation["summary"]
    announcement_readiness = (
        "ready"
        if escal_summary["escalation_readiness"] == "ready_for_announcement_check"
        and escal_summary["position_alignment_ok"]
        else "not_ready"
    )
    announcement_decision = (
        "announcement_ready_for_decision"
        if announcement_readiness == "ready"
        else "hold_announcement"
    )
    summary = {
        "ok": True,
        "candidate_state": escal_summary["candidate_state"],
        "audience_decision": escal_summary["audience_decision"],
        "weekly_posture": escal_summary["weekly_posture"],
        "position_alignment_ok": escal_summary["position_alignment_ok"],
        "escalation_readiness": escal_summary["escalation_readiness"],
        "announcement_readiness": announcement_readiness,
        "announcement_decision": announcement_decision,
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "readiness_label": label,
        "workspace": str(Path(workspace).resolve()),
        "readiness_root": str(root),
        "readiness_dir": str(ready_dir),
        "public_preview_escalation_pack": escalation,
        "summary": summary,
        "artifacts": {},
    }

    lines = [
        "# AgentOS Public Preview Announcement Readiness",
        "",
        f"Readiness label: `{label}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Announcement readiness",
        "",
        f"- Candidate state: `{summary['candidate_state']}`",
        f"- Audience decision: `{summary['audience_decision']}`",
        f"- Weekly posture: `{summary['weekly_posture']}`",
        f"- Position alignment: `{summary['position_alignment_ok']}`",
        f"- Escalation readiness: `{summary['escalation_readiness']}`",
        f"- Announcement readiness: `{summary['announcement_readiness']}`",
        f"- Announcement decision: `{summary['announcement_decision']}`",
    ]

    markdown_path = ready_dir / "public-preview-announcement-readiness.md"
    manifest_path = ready_dir / "public-preview-announcement-readiness.json"
    latest_manifest_path = root / "latest-public-preview-announcement-readiness.json"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "public_preview_announcement_readiness_markdown": str(markdown_path),
        "public_preview_announcement_readiness_json": str(manifest_path),
        "latest_public_preview_announcement_readiness_json": str(latest_manifest_path),
        "public_preview_escalation_pack_json": escalation["artifacts"]["public_preview_escalation_pack_json"],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_public_preview_announcement_readiness(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "readiness_label",
        "workspace",
        "readiness_root",
        "readiness_dir",
        "public_preview_escalation_pack",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("public_preview_escalation_pack", {}).get("schema_version") != "agentos-public-preview-escalation-pack.v1":
        errors.append("public_preview_escalation_pack must reference agentos-public-preview-escalation-pack.v1")
    summary = payload.get("summary", {})
    if summary.get("announcement_readiness") not in {"ready", "not_ready"}:
        errors.append("summary.announcement_readiness must be ready or not_ready")
    if summary.get("announcement_decision") not in {"announcement_ready_for_decision", "hold_announcement"}:
        errors.append("summary.announcement_decision must be announcement_ready_for_decision or hold_announcement")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export public preview announcement readiness")
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
        errors = validate_public_preview_announcement_readiness(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_public_preview_announcement_readiness(
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
    errors = validate_public_preview_announcement_readiness(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
