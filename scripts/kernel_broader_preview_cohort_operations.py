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

from kernel_updated_broader_preview_launch_pack import build_updated_broader_preview_launch_pack

SCHEMA_VERSION = "agentos-broader-preview-cohort-operations.v1"
LAYOUT_DIRNAME = "broader-preview-cohort-operations"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def build_broader_preview_cohort_operations(
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
    ops_dir = root / f"broader-preview-cohort-{label}"
    ops_dir.mkdir(parents=True, exist_ok=True)

    launch_pack = build_updated_broader_preview_launch_pack(
        workspace=workspace,
        report_dir=str(ops_dir / "launch-pack"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )

    launch_summary = launch_pack["summary"]
    summary = {
        "ok": True,
        "candidate_state": launch_summary["candidate_state"],
        "audience_decision": launch_summary["audience_decision"],
        "delivery_scope": "broader_preview_candidate",
        "cohort_mode": "broader_preview_operator_guided",
        "operating_state": "active" if launch_summary["candidate_state"] == "broader_preview_candidate" else "watch",
        "operating_rhythm": "weekly_operator_review",
        "issue_intake_path": "broader_preview_issue_ledger",
        "expansion_gate": "stage16_operating_decision",
        "public_statement_status": launch_summary["public_statement_status"],
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "cohort_label": label,
        "workspace": str(Path(workspace).resolve()),
        "cohort_root": str(root),
        "cohort_dir": str(ops_dir),
        "updated_broader_preview_launch_pack": launch_pack,
        "summary": summary,
        "artifacts": {},
    }

    guide_lines = [
        "# AgentOS Broader Preview Cohort Operations",
        "",
        f"Cohort label: `{label}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Current posture",
        "",
        f"- Candidate state: `{summary['candidate_state']}`",
        f"- Audience decision: `{summary['audience_decision']}`",
        f"- Delivery scope: `{summary['delivery_scope']}`",
        f"- Cohort mode: `{summary['cohort_mode']}`",
        f"- Operating state: `{summary['operating_state']}`",
        "",
        "## Operating rhythm",
        "",
        "- Run a bounded broader preview cohort on the appliance-first path.",
        "- Use the updated broader preview launch pack as the outward-facing source of truth.",
        "- Review cohort findings on a weekly operator rhythm.",
        "- Route new findings into the broader preview issue ledger before any expansion decision.",
        "",
        "## Product path to preserve",
        "",
        "- `boot -> tiny setup -> ai>` remains the primary broader preview path.",
        "- `Install AgentOS` remains a persistence action, not the first product story.",
        "- `AgentOS Recovery -> Return to AgentOS -> ai>` remains the beginner recovery summary.",
        "",
        "## Next gate",
        "",
        "- Expansion decisions belong to `Stage 16 / broader preview operating decision`.",
    ]

    markdown_path = ops_dir / "broader-preview-cohort-operations.md"
    manifest_path = ops_dir / "broader-preview-cohort-operations.json"
    latest_manifest_path = root / "latest-broader-preview-cohort-operations.json"
    markdown_path.write_text("\n".join(guide_lines) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "broader_preview_cohort_operations_markdown": str(markdown_path),
        "broader_preview_cohort_operations_json": str(manifest_path),
        "latest_broader_preview_cohort_operations_json": str(latest_manifest_path),
        "updated_broader_preview_launch_pack_json": launch_pack["artifacts"]["updated_broader_preview_launch_pack_json"],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_broader_preview_cohort_operations(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "cohort_label",
        "workspace",
        "cohort_root",
        "cohort_dir",
        "updated_broader_preview_launch_pack",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("updated_broader_preview_launch_pack", {}).get("schema_version") != "agentos-updated-broader-preview-launch-pack.v1":
        errors.append("updated_broader_preview_launch_pack must reference agentos-updated-broader-preview-launch-pack.v1")
    summary = payload.get("summary", {})
    if summary.get("delivery_scope") != "broader_preview_candidate":
        errors.append("summary.delivery_scope must be broader_preview_candidate")
    if summary.get("cohort_mode") != "broader_preview_operator_guided":
        errors.append("summary.cohort_mode must be broader_preview_operator_guided")
    if summary.get("operating_rhythm") != "weekly_operator_review":
        errors.append("summary.operating_rhythm must be weekly_operator_review")
    if summary.get("operating_state") not in {"active", "watch"}:
        errors.append("summary.operating_state must be active or watch")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export broader preview cohort operations")
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
        errors = validate_broader_preview_cohort_operations(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_broader_preview_cohort_operations(
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
    errors = validate_broader_preview_cohort_operations(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
