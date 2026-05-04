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

from kernel_broader_preview_continuation_pack import build_broader_preview_continuation_pack
from kernel_broader_preview_weekly_summary import build_broader_preview_weekly_summary
from kernel_public_preview_position_update import build_public_preview_position_update

SCHEMA_VERSION = "agentos-public-preview-escalation-pack.v1"
LAYOUT_DIRNAME = "public-preview-escalation-packs"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def build_public_preview_escalation_pack(
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
    pack_dir = root / f"public-preview-escalation-pack-{label}"
    pack_dir.mkdir(parents=True, exist_ok=True)
    support_root = root.parent

    weekly = build_broader_preview_weekly_summary(
        workspace=workspace,
        report_dir=str(support_root / "ppe-w"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )
    continuation = build_broader_preview_continuation_pack(
        workspace=workspace,
        report_dir=str(support_root / "ppe-c"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )
    position = build_public_preview_position_update(
        workspace=workspace,
        report_dir=str(support_root / "ppe-p"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )

    weekly_summary = weekly["summary"]
    continuation_summary = continuation["summary"]
    position_summary = position["summary"]
    alignment_ok = bool(
        position_summary["statement_mentions_broader_preview_candidate"]
        and position_summary["statement_mentions_operating_evidence"]
    )
    escalation_readiness = (
        "ready_for_announcement_check"
        if continuation_summary["audience_decision"] == "broader_preview_candidate"
        and weekly_summary["weekly_posture"] == "stable"
        and alignment_ok
        else "not_ready"
    )
    escalation_decision = (
        "check_public_preview_announcement_readiness"
        if escalation_readiness == "ready_for_announcement_check"
        else "hold_public_preview"
    )

    summary = {
        "ok": True,
        "candidate_state": continuation_summary["candidate_state"],
        "audience_decision": continuation_summary["audience_decision"],
        "operating_health": weekly_summary["operating_health"],
        "operating_recommendation": weekly_summary["operating_recommendation"],
        "weekly_posture": weekly_summary["weekly_posture"],
        "signal_state": weekly_summary["signal_state"],
        "public_statement_status": continuation_summary["public_statement_status"],
        "position_alignment_ok": alignment_ok,
        "escalation_readiness": escalation_readiness,
        "escalation_decision": escalation_decision,
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "pack_label": label,
        "workspace": str(Path(workspace).resolve()),
        "pack_root": str(root),
        "pack_dir": str(pack_dir),
        "broader_preview_weekly_summary": weekly,
        "broader_preview_continuation_pack": continuation,
        "public_preview_position_update": position,
        "summary": summary,
        "artifacts": {},
    }

    lines = [
        "# AgentOS Public Preview Escalation Pack",
        "",
        f"Pack label: `{label}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Escalation posture",
        "",
        f"- Candidate state: `{summary['candidate_state']}`",
        f"- Audience decision: `{summary['audience_decision']}`",
        f"- Operating health: `{summary['operating_health']}`",
        f"- Operating recommendation: `{summary['operating_recommendation']}`",
        f"- Weekly posture: `{summary['weekly_posture']}`",
        f"- Signal state: `{summary['signal_state']}`",
        f"- Public statement: `{summary['public_statement_status']}`",
        f"- Position alignment: `{summary['position_alignment_ok']}`",
        f"- Escalation readiness: `{summary['escalation_readiness']}`",
        f"- Escalation decision: `{summary['escalation_decision']}`",
    ]

    markdown_path = pack_dir / "public-preview-escalation-pack.md"
    manifest_path = pack_dir / "public-preview-escalation-pack.json"
    latest_manifest_path = root / "latest-public-preview-escalation-pack.json"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "public_preview_escalation_pack_markdown": str(markdown_path),
        "public_preview_escalation_pack_json": str(manifest_path),
        "latest_public_preview_escalation_pack_json": str(latest_manifest_path),
        "broader_preview_weekly_summary_json": weekly["artifacts"]["broader_preview_weekly_summary_json"],
        "broader_preview_continuation_pack_json": continuation["artifacts"]["broader_preview_continuation_pack_json"],
        "public_preview_position_update_json": position["artifacts"]["public_preview_position_update_json"],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_public_preview_escalation_pack(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "pack_label",
        "workspace",
        "pack_root",
        "pack_dir",
        "broader_preview_weekly_summary",
        "broader_preview_continuation_pack",
        "public_preview_position_update",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("broader_preview_weekly_summary", {}).get("schema_version") != "agentos-broader-preview-weekly-summary.v1":
        errors.append("broader_preview_weekly_summary must reference agentos-broader-preview-weekly-summary.v1")
    if payload.get("broader_preview_continuation_pack", {}).get("schema_version") != "agentos-broader-preview-continuation-pack.v1":
        errors.append("broader_preview_continuation_pack must reference agentos-broader-preview-continuation-pack.v1")
    if payload.get("public_preview_position_update", {}).get("schema_version") != "agentos-public-preview-position-update.v1":
        errors.append("public_preview_position_update must reference agentos-public-preview-position-update.v1")
    summary = payload.get("summary", {})
    if summary.get("escalation_readiness") not in {"not_ready", "ready_for_announcement_check"}:
        errors.append("summary.escalation_readiness must be not_ready or ready_for_announcement_check")
    if summary.get("escalation_decision") not in {"hold_public_preview", "check_public_preview_announcement_readiness"}:
        errors.append("summary.escalation_decision must be hold_public_preview or check_public_preview_announcement_readiness")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export public preview escalation pack")
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
        errors = validate_public_preview_escalation_pack(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_public_preview_escalation_pack(
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
    errors = validate_public_preview_escalation_pack(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
