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

from kernel_public_preview_decision_ledger import build_public_preview_decision_ledger
from kernel_public_preview_messaging_review import build_public_preview_messaging_review
from kernel_public_preview_operating_brief import build_public_preview_operating_brief

SCHEMA_VERSION = "agentos-public-preview-decision-pack.v1"
LAYOUT_DIRNAME = "public-preview-decision-packs"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def build_public_preview_decision_pack(*, workspace: str, report_dir: str, feedback_file: str = "", install_root: str = "", metadata: str = "", diagnostics_manifest: str = "", history_dir: str = "", snapshot_label: str = "current", session_id: str = "", limit: int = 50) -> dict:
    root = resolve_root(report_dir)
    label = snapshot_label or "current"
    pack_dir = root / f"public-preview-decision-pack-{label}"
    pack_dir.mkdir(parents=True, exist_ok=True)
    support_root = root.parent

    ledger = build_public_preview_decision_ledger(workspace=workspace, report_dir=str(support_root / "ppdp-l"), feedback_file=feedback_file, install_root=install_root, metadata=metadata, diagnostics_manifest=diagnostics_manifest, history_dir=history_dir, snapshot_label=label, session_id=session_id, limit=limit)
    messaging = build_public_preview_messaging_review(workspace=workspace, report_dir=str(support_root / "ppdp-m"), feedback_file=feedback_file, install_root=install_root, metadata=metadata, diagnostics_manifest=diagnostics_manifest, history_dir=history_dir, snapshot_label=label, session_id=session_id, limit=limit)
    brief = build_public_preview_operating_brief(workspace=workspace, report_dir=str(support_root / "ppdp-b"), feedback_file=feedback_file, install_root=install_root, metadata=metadata, diagnostics_manifest=diagnostics_manifest, history_dir=history_dir, snapshot_label=label, session_id=session_id, limit=limit)

    ledger_summary = ledger["summary"]
    messaging_summary = messaging["summary"]
    brief_summary = brief["summary"]
    go_signal = (
        "public_preview_go_candidate"
        if ledger_summary["decision_state"] == "ready_for_public_preview_decision"
        and messaging_summary["review_state"] == "aligned"
        and brief_summary["operating_posture"] == "decision_ready"
        else "public_preview_hold_candidate"
    )
    recommended_next_step = (
        "run_public_preview_launch_readiness_review"
        if go_signal == "public_preview_go_candidate"
        else "continue_public_preview_preparation"
    )

    summary = {
        "ok": True,
        "candidate_state": ledger_summary["candidate_state"],
        "audience_decision": ledger_summary["audience_decision"],
        "decision_state": ledger_summary["decision_state"],
        "messaging_review_state": messaging_summary["review_state"],
        "operating_posture": brief_summary["operating_posture"],
        "go_signal": go_signal,
        "recommended_next_step": recommended_next_step,
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "pack_label": label,
        "workspace": str(Path(workspace).resolve()),
        "pack_root": str(root),
        "pack_dir": str(pack_dir),
        "public_preview_decision_ledger": ledger,
        "public_preview_messaging_review": messaging,
        "public_preview_operating_brief": brief,
        "summary": summary,
        "artifacts": {},
    }

    lines = [
        "# AgentOS Public Preview Decision Pack",
        "",
        f"Pack label: `{label}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Decision pack",
        "",
        f"- Candidate state: `{summary['candidate_state']}`",
        f"- Audience decision: `{summary['audience_decision']}`",
        f"- Decision state: `{summary['decision_state']}`",
        f"- Messaging review state: `{summary['messaging_review_state']}`",
        f"- Operating posture: `{summary['operating_posture']}`",
        f"- Go signal: `{summary['go_signal']}`",
        f"- Recommended next step: `{summary['recommended_next_step']}`",
    ]

    markdown_path = pack_dir / "public-preview-decision-pack.md"
    manifest_path = pack_dir / "public-preview-decision-pack.json"
    latest_manifest_path = root / "latest-public-preview-decision-pack.json"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "public_preview_decision_pack_markdown": str(markdown_path),
        "public_preview_decision_pack_json": str(manifest_path),
        "latest_public_preview_decision_pack_json": str(latest_manifest_path),
        "public_preview_decision_ledger_json": ledger["artifacts"]["public_preview_decision_ledger_json"],
        "public_preview_messaging_review_json": messaging["artifacts"]["public_preview_messaging_review_json"],
        "public_preview_operating_brief_json": brief["artifacts"]["public_preview_operating_brief_json"],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_public_preview_decision_pack(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {"schema_version", "generated_at_utc", "pack_label", "workspace", "pack_root", "pack_dir", "public_preview_decision_ledger", "public_preview_messaging_review", "public_preview_operating_brief", "summary", "artifacts"}
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("public_preview_decision_ledger", {}).get("schema_version") != "agentos-public-preview-decision-ledger.v1":
        errors.append("public_preview_decision_ledger must reference agentos-public-preview-decision-ledger.v1")
    if payload.get("public_preview_messaging_review", {}).get("schema_version") != "agentos-public-preview-messaging-review.v1":
        errors.append("public_preview_messaging_review must reference agentos-public-preview-messaging-review.v1")
    if payload.get("public_preview_operating_brief", {}).get("schema_version") != "agentos-public-preview-operating-brief.v1":
        errors.append("public_preview_operating_brief must reference agentos-public-preview-operating-brief.v1")
    if payload.get("summary", {}).get("go_signal") not in {"public_preview_go_candidate", "public_preview_hold_candidate"}:
        errors.append("summary.go_signal must be public_preview_go_candidate or public_preview_hold_candidate")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export public preview decision pack")
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
        errors = validate_public_preview_decision_pack(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1
    payload = build_public_preview_decision_pack(workspace=args.workspace, report_dir=args.report_dir, feedback_file=args.feedback_file, install_root=args.install_root, metadata=args.metadata, diagnostics_manifest=args.diagnostics_manifest, history_dir=args.history_dir, snapshot_label=args.snapshot_label, session_id=args.session_id, limit=args.limit)
    errors = validate_public_preview_decision_pack(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
