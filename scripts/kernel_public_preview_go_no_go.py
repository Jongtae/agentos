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
from kernel_public_preview_launch_readiness_review import build_public_preview_launch_readiness_review

SCHEMA_VERSION = "agentos-public-preview-go-no-go.v1"
LAYOUT_DIRNAME = "public-preview-go-no-go"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def build_public_preview_go_no_go(*, workspace: str, report_dir: str, feedback_file: str = "", install_root: str = "", metadata: str = "", diagnostics_manifest: str = "", history_dir: str = "", snapshot_label: str = "current", session_id: str = "", limit: int = 50) -> dict:
    root = resolve_root(report_dir)
    label = snapshot_label or "current"
    decision_dir = root / f"public-preview-go-no-go-{label}"
    decision_dir.mkdir(parents=True, exist_ok=True)
    support_root = root.parent

    decision_pack = build_public_preview_decision_pack(workspace=workspace, report_dir=str(support_root / "ppgng-d"), feedback_file=feedback_file, install_root=install_root, metadata=metadata, diagnostics_manifest=diagnostics_manifest, history_dir=history_dir, snapshot_label=label, session_id=session_id, limit=limit)
    launch_review = build_public_preview_launch_readiness_review(workspace=workspace, report_dir=str(support_root / "ppgng-r"), feedback_file=feedback_file, install_root=install_root, metadata=metadata, diagnostics_manifest=diagnostics_manifest, history_dir=history_dir, snapshot_label=label, session_id=session_id, limit=limit)

    pack_summary = decision_pack["summary"]
    review_summary = launch_review["summary"]
    go_no_go = "go" if review_summary["launch_readiness"] == "ready" and pack_summary["go_signal"] == "public_preview_go_candidate" else "no_go"
    operating_decision = "proceed_with_public_preview" if go_no_go == "go" else "hold_public_preview"

    summary = {
        "ok": True,
        "candidate_state": pack_summary["candidate_state"],
        "audience_decision": pack_summary["audience_decision"],
        "go_signal": pack_summary["go_signal"],
        "launch_readiness": review_summary["launch_readiness"],
        "go_no_go": go_no_go,
        "operating_decision": operating_decision,
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "decision_label": label,
        "workspace": str(Path(workspace).resolve()),
        "decision_root": str(root),
        "decision_dir": str(decision_dir),
        "public_preview_decision_pack": decision_pack,
        "public_preview_launch_readiness_review": launch_review,
        "summary": summary,
        "artifacts": {},
    }

    lines = [
        "# AgentOS Public Preview Go/No-Go",
        "",
        f"Decision label: `{label}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Go/No-Go",
        "",
        f"- Candidate state: `{summary['candidate_state']}`",
        f"- Audience decision: `{summary['audience_decision']}`",
        f"- Go signal: `{summary['go_signal']}`",
        f"- Launch readiness: `{summary['launch_readiness']}`",
        f"- Go/No-Go: `{summary['go_no_go']}`",
        f"- Operating decision: `{summary['operating_decision']}`",
    ]

    markdown_path = decision_dir / "public-preview-go-no-go.md"
    manifest_path = decision_dir / "public-preview-go-no-go.json"
    latest_manifest_path = root / "latest-public-preview-go-no-go.json"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "public_preview_go_no_go_markdown": str(markdown_path),
        "public_preview_go_no_go_json": str(manifest_path),
        "latest_public_preview_go_no_go_json": str(latest_manifest_path),
        "public_preview_decision_pack_json": decision_pack["artifacts"]["public_preview_decision_pack_json"],
        "public_preview_launch_readiness_review_json": launch_review["artifacts"]["public_preview_launch_readiness_review_json"],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_public_preview_go_no_go(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {"schema_version", "generated_at_utc", "decision_label", "workspace", "decision_root", "decision_dir", "public_preview_decision_pack", "public_preview_launch_readiness_review", "summary", "artifacts"}
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("public_preview_decision_pack", {}).get("schema_version") != "agentos-public-preview-decision-pack.v1":
        errors.append("public_preview_decision_pack must reference agentos-public-preview-decision-pack.v1")
    if payload.get("public_preview_launch_readiness_review", {}).get("schema_version") != "agentos-public-preview-launch-readiness-review.v1":
        errors.append("public_preview_launch_readiness_review must reference agentos-public-preview-launch-readiness-review.v1")
    summary = payload.get("summary", {})
    if summary.get("go_no_go") not in {"go", "no_go"}:
        errors.append("summary.go_no_go must be go or no_go")
    if summary.get("operating_decision") not in {"proceed_with_public_preview", "hold_public_preview"}:
        errors.append("summary.operating_decision must be proceed_with_public_preview or hold_public_preview")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export public preview go/no-go decision")
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
        errors = validate_public_preview_go_no_go(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1
    payload = build_public_preview_go_no_go(workspace=args.workspace, report_dir=args.report_dir, feedback_file=args.feedback_file, install_root=args.install_root, metadata=args.metadata, diagnostics_manifest=args.diagnostics_manifest, history_dir=args.history_dir, snapshot_label=args.snapshot_label, session_id=args.session_id, limit=args.limit)
    errors = validate_public_preview_go_no_go(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
