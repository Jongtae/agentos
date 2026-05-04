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

from kernel_broader_preview_health_summary import build_broader_preview_health_summary
from kernel_broader_preview_continuation_pack import build_broader_preview_continuation_pack
from kernel_public_preview_position_update import build_public_preview_position_update

SCHEMA_VERSION = "agentos-broader-preview-signal-snapshot.v1"
LAYOUT_DIRNAME = "broader-preview-signal-snapshots"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def build_broader_preview_signal_snapshot(
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
    snapshot_dir = root / f"broader-preview-signal-snapshot-{label}"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    support_root = root.parent

    health = build_broader_preview_health_summary(
        workspace=workspace,
        report_dir=str(support_root / "s-h"),
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
        report_dir=str(support_root / "s-c"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )
    public_position = build_public_preview_position_update(
        workspace=workspace,
        report_dir=str(support_root / "s-p"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )

    health_summary = health["summary"]
    continuation_summary = continuation["summary"]
    public_summary = public_position["summary"]
    summary = {
        "ok": True,
        "candidate_state": continuation_summary["candidate_state"],
        "audience_decision": continuation_summary["audience_decision"],
        "operating_health": health_summary["operating_health"],
        "operating_recommendation": health_summary["operating_recommendation"],
        "signal_state": "stable"
        if public_summary["statement_mentions_broader_preview_candidate"]
        and public_summary["statement_mentions_operating_evidence"]
        else "watch",
        "continue_relevant_count": health_summary["issue_counts"]["continue"],
        "pause_relevant_count": health_summary["issue_counts"]["pause"],
        "expand_relevant_count": health_summary["issue_counts"]["expand"],
        "position_alignment_ok": bool(
            public_summary["statement_mentions_broader_preview_candidate"]
            and public_summary["statement_mentions_operating_evidence"]
        ),
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "snapshot_label": label,
        "workspace": str(Path(workspace).resolve()),
        "snapshot_root": str(root),
        "snapshot_dir": str(snapshot_dir),
        "broader_preview_health_summary": health,
        "broader_preview_continuation_pack": continuation,
        "public_preview_position_update": public_position,
        "summary": summary,
        "artifacts": {},
    }

    lines = [
        "# AgentOS Broader Preview Signal Snapshot",
        "",
        f"Snapshot label: `{label}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Signal summary",
        "",
        f"- Candidate state: `{summary['candidate_state']}`",
        f"- Audience decision: `{summary['audience_decision']}`",
        f"- Operating health: `{summary['operating_health']}`",
        f"- Operating recommendation: `{summary['operating_recommendation']}`",
        f"- Signal state: `{summary['signal_state']}`",
        f"- Position alignment ok: `{summary['position_alignment_ok']}`",
        f"- Continue issues: `{summary['continue_relevant_count']}`",
        f"- Pause issues: `{summary['pause_relevant_count']}`",
        f"- Expand issues: `{summary['expand_relevant_count']}`",
    ]

    markdown_path = snapshot_dir / "broader-preview-signal-snapshot.md"
    manifest_path = snapshot_dir / "broader-preview-signal-snapshot.json"
    latest_manifest_path = root / "latest-broader-preview-signal-snapshot.json"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "broader_preview_signal_snapshot_markdown": str(markdown_path),
        "broader_preview_signal_snapshot_json": str(manifest_path),
        "latest_broader_preview_signal_snapshot_json": str(latest_manifest_path),
        "broader_preview_health_summary_json": health["artifacts"]["broader_preview_health_summary_manifest_json"],
        "broader_preview_continuation_pack_json": continuation["artifacts"]["broader_preview_continuation_pack_json"],
        "public_preview_position_update_json": public_position["artifacts"]["public_preview_position_update_json"],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_broader_preview_signal_snapshot(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "snapshot_label",
        "workspace",
        "snapshot_root",
        "snapshot_dir",
        "broader_preview_health_summary",
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
    if payload.get("broader_preview_health_summary", {}).get("schema_version") != "agentos-broader-preview-health-summary.v1":
        errors.append("broader_preview_health_summary must reference agentos-broader-preview-health-summary.v1")
    if payload.get("broader_preview_continuation_pack", {}).get("schema_version") != "agentos-broader-preview-continuation-pack.v1":
        errors.append("broader_preview_continuation_pack must reference agentos-broader-preview-continuation-pack.v1")
    if payload.get("public_preview_position_update", {}).get("schema_version") != "agentos-public-preview-position-update.v1":
        errors.append("public_preview_position_update must reference agentos-public-preview-position-update.v1")
    if payload.get("summary", {}).get("signal_state") not in {"stable", "watch"}:
        errors.append("summary.signal_state must be stable or watch")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export broader preview signal snapshot")
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
        errors = validate_broader_preview_signal_snapshot(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_broader_preview_signal_snapshot(
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
    errors = validate_broader_preview_signal_snapshot(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
