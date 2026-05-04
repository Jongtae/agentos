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

from kernel_recovery_clarity_fix_loop import build_recovery_clarity_fix_loop
from kernel_recovery_copy_consistency import build_recovery_copy_consistency

SCHEMA_VERSION = "agentos-recovery-watch-reevaluation.v1"
LAYOUT_DIRNAME = "recovery-watch-reevaluation"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def build_recovery_watch_reevaluation(
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
    run_dir = root / f"recovery-watch-reevaluation-{snapshot_label or 'current'}"
    run_dir.mkdir(parents=True, exist_ok=True)

    fix_loop = build_recovery_clarity_fix_loop(
        workspace=workspace,
        report_dir=str(run_dir / "fix-loop"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=snapshot_label,
        session_id=session_id,
        limit=limit,
    )
    consistency = build_recovery_copy_consistency(
        workspace=workspace,
        report_dir=str(run_dir / "consistency"),
        snapshot_label=snapshot_label,
    )

    fix_state = fix_loop["summary"]["overall_state"]
    consistency_state = consistency["summary"]["overall_state"]

    if fix_state == "blocked" or consistency_state == "blocked":
        recovery_state = "blocked"
    elif fix_state in {"watch", "clear"} and consistency_state == "ready":
        recovery_state = "ready" if fix_state == "clear" else "watch"
    else:
        recovery_state = "watch"

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(Path(workspace).resolve()),
        "reevaluation_root": str(root),
        "reevaluation_dir": str(run_dir),
        "snapshot_label": snapshot_label or "current",
        "recovery_clarity_fix_loop_manifest": fix_loop,
        "recovery_copy_consistency_manifest": consistency,
        "summary": {
            "ok": True,
            "recovery_state": recovery_state,
            "fix_loop_state": fix_state,
            "copy_consistency_state": consistency_state,
            "can_promote_recovery_to_ready": recovery_state == "ready",
        },
        "artifacts": {},
    }

    markdown = [
        "# AgentOS Recovery Watch Re-evaluation",
        "",
        f"Run label: `{snapshot_label or 'current'}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Recovery state",
        "",
        f"- Recovery state: `{recovery_state}`",
        f"- Fix loop state: `{fix_state}`",
        f"- Copy consistency state: `{consistency_state}`",
        f"- Can promote recovery to ready: `{payload['summary']['can_promote_recovery_to_ready']}`",
    ]

    markdown_path = run_dir / "recovery-watch-reevaluation.md"
    manifest_path = run_dir / "recovery-watch-reevaluation.json"
    latest_manifest_path = root / "latest-recovery-watch-reevaluation.json"
    markdown_path.write_text("\n".join(markdown) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "recovery_watch_reevaluation_markdown": str(markdown_path),
        "recovery_watch_reevaluation_manifest_json": str(manifest_path),
        "latest_recovery_watch_reevaluation_manifest_json": str(latest_manifest_path),
        "recovery_clarity_fix_loop_manifest_json": fix_loop["artifacts"]["recovery_clarity_fix_loop_json"],
        "recovery_copy_consistency_manifest_json": consistency["artifacts"]["recovery_copy_consistency_manifest_json"],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_recovery_watch_reevaluation(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "workspace",
        "reevaluation_root",
        "reevaluation_dir",
        "snapshot_label",
        "recovery_clarity_fix_loop_manifest",
        "recovery_copy_consistency_manifest",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("recovery_clarity_fix_loop_manifest", {}).get("schema_version") != "agentos-recovery-clarity-fix-loop.v1":
        errors.append("recovery_clarity_fix_loop_manifest must reference agentos-recovery-clarity-fix-loop.v1")
    if payload.get("recovery_copy_consistency_manifest", {}).get("schema_version") != "agentos-recovery-copy-consistency.v1":
        errors.append("recovery_copy_consistency_manifest must reference agentos-recovery-copy-consistency.v1")
    if payload.get("summary", {}).get("recovery_state") not in {"blocked", "watch", "ready"}:
        errors.append("summary.recovery_state must be blocked, watch, or ready")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an AgentOS recovery watch re-evaluation report")
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
        errors = validate_recovery_watch_reevaluation(payload)
        if errors:
            for item in errors:
                print(item, file=sys.stderr)
            return 1
        print("PASS")
        return 0

    payload = build_recovery_watch_reevaluation(
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
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print(json.dumps(payload["summary"], ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
