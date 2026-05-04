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

from kernel_public_preview_decision_pack import build_public_preview_decision_pack

SCHEMA_VERSION = "agentos-public-preview-launch-readiness-review.v1"
LAYOUT_DIRNAME = "public-preview-launch-readiness-reviews"
PUBLIC_STATEMENT = ROOT_DIR / "docs" / "reference" / "public-preview-candidate-v1.md"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def build_public_preview_launch_readiness_review(*, workspace: str, report_dir: str, feedback_file: str = "", install_root: str = "", metadata: str = "", diagnostics_manifest: str = "", history_dir: str = "", snapshot_label: str = "current", session_id: str = "", limit: int = 50) -> dict:
    root = resolve_root(report_dir)
    label = snapshot_label or "current"
    review_dir = root / f"public-preview-launch-readiness-review-{label}"
    review_dir.mkdir(parents=True, exist_ok=True)
    support_root = root.parent

    decision_pack = build_public_preview_decision_pack(
        workspace=workspace,
        report_dir=str(support_root / "pplrr-d"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )

    statement_text = PUBLIC_STATEMENT.read_text(encoding="utf-8") if PUBLIC_STATEMENT.exists() else ""
    statement_lower = statement_text.lower()
    pack_summary = decision_pack["summary"]
    mentions_public_preview = "public preview" in statement_lower
    mentions_go_no_go = "go/no-go" in statement_lower or "go no-go" in statement_lower or "announcement_ready_for_decision" in statement_text
    messaging_ok = bool(mentions_public_preview and mentions_go_no_go)
    launch_readiness = (
        "ready"
        if pack_summary["go_signal"] == "public_preview_go_candidate" and messaging_ok
        else "not_ready"
    )
    launch_decision = "proceed_to_public_preview_go_no_go" if launch_readiness == "ready" else "hold_public_preview_launch"

    summary = {
        "ok": True,
        "candidate_state": pack_summary["candidate_state"],
        "audience_decision": pack_summary["audience_decision"],
        "go_signal": pack_summary["go_signal"],
        "recommended_next_step": pack_summary["recommended_next_step"],
        "mentions_public_preview": mentions_public_preview,
        "mentions_go_no_go": mentions_go_no_go,
        "launch_readiness": launch_readiness,
        "launch_decision": launch_decision,
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "review_label": label,
        "workspace": str(Path(workspace).resolve()),
        "review_root": str(root),
        "review_dir": str(review_dir),
        "public_preview_decision_pack": decision_pack,
        "public_statement_path": str(PUBLIC_STATEMENT),
        "summary": summary,
        "artifacts": {},
    }

    lines = [
        "# AgentOS Public Preview Launch Readiness Review",
        "",
        f"Review label: `{label}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Launch readiness",
        "",
        f"- Candidate state: `{summary['candidate_state']}`",
        f"- Audience decision: `{summary['audience_decision']}`",
        f"- Go signal: `{summary['go_signal']}`",
        f"- Recommended next step: `{summary['recommended_next_step']}`",
        f"- Mentions public preview: `{summary['mentions_public_preview']}`",
        f"- Mentions go/no-go: `{summary['mentions_go_no_go']}`",
        f"- Launch readiness: `{summary['launch_readiness']}`",
        f"- Launch decision: `{summary['launch_decision']}`",
    ]

    markdown_path = review_dir / "public-preview-launch-readiness-review.md"
    manifest_path = review_dir / "public-preview-launch-readiness-review.json"
    latest_manifest_path = root / "latest-public-preview-launch-readiness-review.json"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "public_preview_launch_readiness_review_markdown": str(markdown_path),
        "public_preview_launch_readiness_review_json": str(manifest_path),
        "latest_public_preview_launch_readiness_review_json": str(latest_manifest_path),
        "public_preview_decision_pack_json": decision_pack["artifacts"]["public_preview_decision_pack_json"],
        "public_statement_path": str(PUBLIC_STATEMENT),
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_public_preview_launch_readiness_review(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {"schema_version", "generated_at_utc", "review_label", "workspace", "review_root", "review_dir", "public_preview_decision_pack", "public_statement_path", "summary", "artifacts"}
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("public_preview_decision_pack", {}).get("schema_version") != "agentos-public-preview-decision-pack.v1":
        errors.append("public_preview_decision_pack must reference agentos-public-preview-decision-pack.v1")
    summary = payload.get("summary", {})
    if summary.get("launch_readiness") not in {"ready", "not_ready"}:
        errors.append("summary.launch_readiness must be ready or not_ready")
    if summary.get("launch_decision") not in {"proceed_to_public_preview_go_no_go", "hold_public_preview_launch"}:
        errors.append("summary.launch_decision must be proceed_to_public_preview_go_no_go or hold_public_preview_launch")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export public preview launch readiness review")
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
        errors = validate_public_preview_launch_readiness_review(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1
    payload = build_public_preview_launch_readiness_review(workspace=args.workspace, report_dir=args.report_dir, feedback_file=args.feedback_file, install_root=args.install_root, metadata=args.metadata, diagnostics_manifest=args.diagnostics_manifest, history_dir=args.history_dir, snapshot_label=args.snapshot_label, session_id=args.session_id, limit=args.limit)
    errors = validate_public_preview_launch_readiness_review(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
