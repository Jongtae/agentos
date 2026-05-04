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

from kernel_public_preview_announcement_readiness import build_public_preview_announcement_readiness
from kernel_public_preview_escalation_pack import build_public_preview_escalation_pack

SCHEMA_VERSION = "agentos-public-preview-decision-ledger.v1"
LAYOUT_DIRNAME = "public-preview-decision-ledgers"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def build_public_preview_decision_ledger(
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
    ledger_dir = root / f"public-preview-decision-ledger-{label}"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    support_root = root.parent

    readiness = build_public_preview_announcement_readiness(
        workspace=workspace,
        report_dir=str(support_root / "ppdl-r"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )
    escalation = build_public_preview_escalation_pack(
        workspace=workspace,
        report_dir=str(support_root / "ppdl-e"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )

    readiness_summary = readiness["summary"]
    escalation_summary = escalation["summary"]

    ready_signals: list[str] = []
    hold_reasons: list[str] = []
    if readiness_summary["announcement_readiness"] == "ready":
        ready_signals.append("announcement_readiness")
    else:
        hold_reasons.append("announcement_not_ready")
    if escalation_summary["position_alignment_ok"]:
        ready_signals.append("position_alignment")
    else:
        hold_reasons.append("position_alignment_missing")
    if escalation_summary["weekly_posture"] == "stable":
        ready_signals.append("stable_weekly_posture")
    else:
        hold_reasons.append("weekly_posture_watch")

    decision_state = "ready_for_public_preview_decision" if not hold_reasons else "hold_before_public_preview_decision"
    recommended_next_step = (
        "run_public_preview_go_no_go"
        if decision_state == "ready_for_public_preview_decision"
        else "continue_public_preview_preparation"
    )

    summary = {
        "ok": True,
        "candidate_state": escalation_summary["candidate_state"],
        "audience_decision": escalation_summary["audience_decision"],
        "announcement_readiness": readiness_summary["announcement_readiness"],
        "announcement_decision": readiness_summary["announcement_decision"],
        "escalation_decision": escalation_summary["escalation_decision"],
        "decision_state": decision_state,
        "recommended_next_step": recommended_next_step,
        "ready_signals": ready_signals,
        "hold_reasons": hold_reasons,
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "ledger_label": label,
        "workspace": str(Path(workspace).resolve()),
        "ledger_root": str(root),
        "ledger_dir": str(ledger_dir),
        "public_preview_announcement_readiness": readiness,
        "public_preview_escalation_pack": escalation,
        "summary": summary,
        "artifacts": {},
    }

    lines = [
        "# AgentOS Public Preview Decision Ledger",
        "",
        f"Ledger label: `{label}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Decision posture",
        "",
        f"- Candidate state: `{summary['candidate_state']}`",
        f"- Audience decision: `{summary['audience_decision']}`",
        f"- Announcement readiness: `{summary['announcement_readiness']}`",
        f"- Announcement decision: `{summary['announcement_decision']}`",
        f"- Escalation decision: `{summary['escalation_decision']}`",
        f"- Decision state: `{summary['decision_state']}`",
        f"- Recommended next step: `{summary['recommended_next_step']}`",
        "",
        "## Ready signals",
    ]
    if summary["ready_signals"]:
        lines.extend(f"- `{item}`" for item in summary["ready_signals"])
    else:
        lines.append("- none")
    lines.extend(["", "## Hold reasons"])
    if summary["hold_reasons"]:
        lines.extend(f"- `{item}`" for item in summary["hold_reasons"])
    else:
        lines.append("- none")

    markdown_path = ledger_dir / "public-preview-decision-ledger.md"
    manifest_path = ledger_dir / "public-preview-decision-ledger.json"
    latest_manifest_path = root / "latest-public-preview-decision-ledger.json"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "public_preview_decision_ledger_markdown": str(markdown_path),
        "public_preview_decision_ledger_json": str(manifest_path),
        "latest_public_preview_decision_ledger_json": str(latest_manifest_path),
        "public_preview_announcement_readiness_json": readiness["artifacts"]["public_preview_announcement_readiness_json"],
        "public_preview_escalation_pack_json": escalation["artifacts"]["public_preview_escalation_pack_json"],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_public_preview_decision_ledger(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "ledger_label",
        "workspace",
        "ledger_root",
        "ledger_dir",
        "public_preview_announcement_readiness",
        "public_preview_escalation_pack",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("public_preview_announcement_readiness", {}).get("schema_version") != "agentos-public-preview-announcement-readiness.v1":
        errors.append("public_preview_announcement_readiness must reference agentos-public-preview-announcement-readiness.v1")
    if payload.get("public_preview_escalation_pack", {}).get("schema_version") != "agentos-public-preview-escalation-pack.v1":
        errors.append("public_preview_escalation_pack must reference agentos-public-preview-escalation-pack.v1")
    summary = payload.get("summary", {})
    if summary.get("decision_state") not in {"ready_for_public_preview_decision", "hold_before_public_preview_decision"}:
        errors.append("summary.decision_state must be ready_for_public_preview_decision or hold_before_public_preview_decision")
    if summary.get("recommended_next_step") not in {"run_public_preview_go_no_go", "continue_public_preview_preparation"}:
        errors.append("summary.recommended_next_step must be run_public_preview_go_no_go or continue_public_preview_preparation")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export public preview decision ledger")
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
        errors = validate_public_preview_decision_ledger(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_public_preview_decision_ledger(
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
    errors = validate_public_preview_decision_ledger(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
