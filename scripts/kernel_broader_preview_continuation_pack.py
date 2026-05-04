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
from kernel_updated_broader_preview_launch_pack import build_updated_broader_preview_launch_pack

SCHEMA_VERSION = "agentos-broader-preview-continuation-pack.v1"
LAYOUT_DIRNAME = "broader-preview-continuation-packs"
PUBLIC_STATEMENT = ROOT_DIR / "docs" / "reference" / "public-preview-candidate-v1.md"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def build_broader_preview_continuation_pack(
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
    pack_dir = root / f"broader-preview-continuation-pack-{label}"
    pack_dir.mkdir(parents=True, exist_ok=True)
    support_root = root.parent

    health = build_broader_preview_health_summary(
        workspace=workspace,
        report_dir=str(support_root / "h"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )
    launch = build_updated_broader_preview_launch_pack(
        workspace=workspace,
        report_dir=str(support_root / "u"),
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

    health_summary = health["summary"]
    launch_summary = launch["summary"]
    summary = {
        "ok": True,
        "candidate_state": launch_summary["candidate_state"],
        "audience_decision": launch_summary["audience_decision"],
        "operating_health": health_summary["operating_health"],
        "operating_recommendation": health_summary["operating_recommendation"],
        "continue_relevant_count": len(health_summary["continue_relevant"]),
        "pause_relevant_count": len(health_summary["pause_relevant"]),
        "expand_relevant_count": len(health_summary["expand_relevant"]),
        "public_statement_status": "included" if copied_statement else "missing",
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "pack_label": label,
        "workspace": str(Path(workspace).resolve()),
        "pack_root": str(root),
        "pack_dir": str(pack_dir),
        "broader_preview_health_summary": health,
        "updated_broader_preview_launch_pack": launch,
        "public_statement_reference": copied_statement,
        "summary": summary,
        "artifacts": {},
    }

    lines = [
        "# AgentOS Broader Preview Continuation Pack",
        "",
        f"Pack label: `{label}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Continuation view",
        "",
        f"- Candidate state: `{summary['candidate_state']}`",
        f"- Audience decision: `{summary['audience_decision']}`",
        f"- Operating health: `{summary['operating_health']}`",
        f"- Operating recommendation: `{summary['operating_recommendation']}`",
        f"- Continue issues: `{summary['continue_relevant_count']}`",
        f"- Pause issues: `{summary['pause_relevant_count']}`",
        f"- Expand issues: `{summary['expand_relevant_count']}`",
        f"- Public statement: `{summary['public_statement_status']}`",
    ]

    markdown_path = pack_dir / "broader-preview-continuation-pack.md"
    manifest_path = pack_dir / "broader-preview-continuation-pack.json"
    latest_manifest_path = root / "latest-broader-preview-continuation-pack.json"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "broader_preview_continuation_pack_markdown": str(markdown_path),
        "broader_preview_continuation_pack_json": str(manifest_path),
        "latest_broader_preview_continuation_pack_json": str(latest_manifest_path),
        "broader_preview_health_summary_manifest_json": health["artifacts"]["broader_preview_health_summary_manifest_json"],
        "updated_broader_preview_launch_pack_json": launch["artifacts"]["updated_broader_preview_launch_pack_json"],
        "public_statement_reference": copied_statement,
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_broader_preview_continuation_pack(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "pack_label",
        "workspace",
        "pack_root",
        "pack_dir",
        "broader_preview_health_summary",
        "updated_broader_preview_launch_pack",
        "public_statement_reference",
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
    if payload.get("updated_broader_preview_launch_pack", {}).get("schema_version") != "agentos-updated-broader-preview-launch-pack.v1":
        errors.append("updated_broader_preview_launch_pack must reference agentos-updated-broader-preview-launch-pack.v1")
    summary = payload.get("summary", {})
    if summary.get("operating_health") not in {"watch", "steady", "strong"}:
        errors.append("summary.operating_health must be watch, steady, or strong")
    if summary.get("operating_recommendation") not in {"continue_with_caution", "continue", "continue_and_prepare_expand"}:
        errors.append("summary.operating_recommendation must be continue_with_caution, continue, or continue_and_prepare_expand")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export broader preview continuation pack")
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
        errors = validate_broader_preview_continuation_pack(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_broader_preview_continuation_pack(
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
    errors = validate_broader_preview_continuation_pack(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
