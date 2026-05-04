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

from kernel_broader_preview_signal_snapshot import build_broader_preview_signal_snapshot

SCHEMA_VERSION = "agentos-broader-preview-drift-ledger.v1"
LAYOUT_DIRNAME = "broader-preview-drift-ledgers"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def _discover_previous_snapshot(root: Path, current_label: str) -> dict | None:
    latest_path = root.parent / "broader-preview-signal-snapshots" / "latest-broader-preview-signal-snapshot.json"
    if not latest_path.exists():
        return None
    try:
        payload = json.loads(latest_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if str(payload.get("snapshot_label", "")) == current_label:
        return None
    return payload


def _field_lists(current: dict, previous: dict | None) -> tuple[list[str], list[str], list[str], list[str]]:
    tracked = (
        "candidate_state",
        "audience_decision",
        "operating_health",
        "operating_recommendation",
        "signal_state",
        "position_alignment_ok",
        "continue_relevant_count",
        "pause_relevant_count",
        "expand_relevant_count",
    )
    if not previous:
        return ([], [], [], list(tracked))

    improved: list[str] = []
    regressed: list[str] = []
    changed: list[str] = []
    unchanged: list[str] = []
    current_summary = current["summary"]
    previous_summary = previous["summary"]

    health_rank = {"watch": 0, "steady": 1, "strong": 2}
    signal_rank = {"watch": 0, "stable": 1}

    for field in tracked:
        cur = current_summary.get(field)
        prev = previous_summary.get(field)
        if cur == prev:
            unchanged.append(field)
            continue
        changed.append(field)
        if field == "operating_health":
            if health_rank.get(str(cur), -1) > health_rank.get(str(prev), -1):
                improved.append(field)
            else:
                regressed.append(field)
        elif field == "signal_state":
            if signal_rank.get(str(cur), -1) > signal_rank.get(str(prev), -1):
                improved.append(field)
            else:
                regressed.append(field)
        elif field == "pause_relevant_count":
            if int(cur or 0) < int(prev or 0):
                improved.append(field)
            else:
                regressed.append(field)
        elif field in {"continue_relevant_count", "expand_relevant_count"}:
            if int(cur or 0) <= int(prev or 0):
                improved.append(field)
            else:
                regressed.append(field)
        elif field == "position_alignment_ok":
            if bool(cur) and not bool(prev):
                improved.append(field)
            else:
                regressed.append(field)
        else:
            regressed.append(field)
    return improved, regressed, changed, unchanged


def build_broader_preview_drift_ledger(
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
    ledger_dir = root / f"broader-preview-drift-ledger-{label}"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    previous_snapshot = _discover_previous_snapshot(root, label)

    current_snapshot = build_broader_preview_signal_snapshot(
        workspace=workspace,
        report_dir=str(root.parent / "s"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=label,
        session_id=session_id,
        limit=limit,
    )

    improved, regressed, changed, unchanged = _field_lists(current_snapshot, previous_snapshot)
    if previous_snapshot is None:
        drift_state = "baseline"
        previous_label = "none"
    elif regressed:
        drift_state = "regressing"
        previous_label = str(previous_snapshot.get("snapshot_label", "unknown"))
    elif improved:
        drift_state = "improving"
        previous_label = str(previous_snapshot.get("snapshot_label", "unknown"))
    else:
        drift_state = "steady"
        previous_label = str(previous_snapshot.get("snapshot_label", "unknown"))

    summary = {
        "ok": True,
        "drift_state": drift_state,
        "current_snapshot_label": label,
        "previous_snapshot_label": previous_label,
        "improved_fields": improved,
        "regressed_fields": regressed,
        "changed_fields": changed,
        "unchanged_fields": unchanged,
        "candidate_state": current_snapshot["summary"]["candidate_state"],
        "audience_decision": current_snapshot["summary"]["audience_decision"],
        "operating_health": current_snapshot["summary"]["operating_health"],
        "signal_state": current_snapshot["summary"]["signal_state"],
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(Path(workspace).resolve()),
        "ledger_root": str(root),
        "ledger_dir": str(ledger_dir),
        "snapshot_label": label,
        "current_signal_snapshot": current_snapshot,
        "previous_signal_snapshot": previous_snapshot or {},
        "summary": summary,
        "artifacts": {},
    }

    lines = [
        "# AgentOS Broader Preview Drift Ledger",
        "",
        f"Snapshot label: `{label}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Drift summary",
        "",
        f"- Drift state: `{drift_state}`",
        f"- Previous snapshot: `{previous_label}`",
        f"- Candidate state: `{summary['candidate_state']}`",
        f"- Audience decision: `{summary['audience_decision']}`",
        f"- Operating health: `{summary['operating_health']}`",
        f"- Signal state: `{summary['signal_state']}`",
        "",
    ]
    for title, items in (
        ("improved_fields", improved),
        ("regressed_fields", regressed),
        ("changed_fields", changed),
        ("unchanged_fields", unchanged),
    ):
        lines.append(f"## {title}")
        lines.append("")
        if items:
            lines.extend(f"- `{item}`" for item in items)
        else:
            lines.append("- none")
        lines.append("")

    markdown_path = ledger_dir / "broader-preview-drift-ledger.md"
    manifest_path = ledger_dir / "broader-preview-drift-ledger.json"
    latest_manifest_path = root / "latest-broader-preview-drift-ledger.json"
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    payload["artifacts"] = {
        "broader_preview_drift_ledger_markdown": str(markdown_path),
        "broader_preview_drift_ledger_json": str(manifest_path),
        "latest_broader_preview_drift_ledger_json": str(latest_manifest_path),
        "current_signal_snapshot_json": current_snapshot["artifacts"]["broader_preview_signal_snapshot_json"],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_broader_preview_drift_ledger(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "workspace",
        "ledger_root",
        "ledger_dir",
        "snapshot_label",
        "current_signal_snapshot",
        "previous_signal_snapshot",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("current_signal_snapshot", {}).get("schema_version") != "agentos-broader-preview-signal-snapshot.v1":
        errors.append("current_signal_snapshot must reference agentos-broader-preview-signal-snapshot.v1")
    if payload.get("summary", {}).get("drift_state") not in {"baseline", "improving", "steady", "regressing"}:
        errors.append("summary.drift_state must be baseline, improving, steady, or regressing")
    for key in ("improved_fields", "regressed_fields", "changed_fields", "unchanged_fields"):
        if not isinstance(payload.get("summary", {}).get(key), list):
            errors.append(f"summary.{key} must be a list")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export broader preview drift ledger")
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
        errors = validate_broader_preview_drift_ledger(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_broader_preview_drift_ledger(
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
    errors = validate_broader_preview_drift_ledger(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
