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

from kernel_direct_boot_ux_burndown import build_direct_boot_ux_burndown
from kernel_feedback_triage import build_feedback_triage

SCHEMA_VERSION = "agentos-recovery-clarity-fix-loop.v1"
LAYOUT_DIRNAME = "recovery-clarity-fix-loop"
TRACKS = {
    "runtime_copy": {"recovery"},
    "operator_notes": {"artifact_packaging", "operator_handoff"},
    "rejoin_path": {"recovery", "session_entry", "install_later"},
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def _normalize_track(name: str, findings: list[dict]) -> dict:
    buckets = {str(item.get("promotion_bucket", "")) for item in findings}
    if "blocker" in buckets:
        status = "blocked"
    elif "watch" in buckets:
        status = "watch"
    elif name == "operator_notes" and findings:
        status = "watch"
    else:
        status = "ready"
    return {
        "track": name,
        "status": status,
        "finding_count": len(findings),
        "titles": [str(item.get("title", "")) for item in findings],
        "findings": findings,
    }


def _track_finding(name: str, finding: dict) -> bool:
    area = str(finding.get("area", "")).strip()
    artifact_ref = str(finding.get("artifact_ref", "")).strip()
    if name == "runtime_copy":
        return area == "recovery" and "runbook" not in artifact_ref
    if name == "operator_notes":
        return "runbook" in artifact_ref or area in TRACKS[name]
    if name == "rejoin_path":
        detail = str(finding.get("detail", "")).lower()
        title = str(finding.get("title", "")).lower()
        return area in TRACKS[name] or "rejoin" in detail or "rejoin" in title
    return False


def build_recovery_clarity_fix_loop(
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
    run_dir = root / f"recovery-clarity-fix-loop-{snapshot_label or 'current'}"
    run_dir.mkdir(parents=True, exist_ok=True)

    triage = build_feedback_triage(
        workspace=workspace,
        report_dir=str(run_dir / "triage"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=snapshot_label,
        session_id=session_id,
        limit=limit,
    )
    burndown = build_direct_boot_ux_burndown(
        workspace=workspace,
        report_dir=str(run_dir / "burndown"),
        feedback_file=feedback_file,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        history_dir=history_dir,
        snapshot_label=snapshot_label,
        session_id=session_id,
        limit=limit,
    )

    direct_boot_findings = triage.get("domain_buckets", {}).get("direct_boot_ux", [])
    general_preview_findings = triage.get("domain_buckets", {}).get("general_preview", [])
    track_findings = direct_boot_findings + general_preview_findings
    recovery_findings = [
        item
        for item in track_findings
        if _track_finding("runtime_copy", item) or _track_finding("rejoin_path", item)
    ]
    tracks = {
        name: _normalize_track(name, [item for item in track_findings if _track_finding(name, item)])
        for name in TRACKS
    }

    blocked = [name for name, payload in tracks.items() if payload["status"] == "blocked"]
    watch = [name for name, payload in tracks.items() if payload["status"] == "watch"]
    ready = [name for name, payload in tracks.items() if payload["status"] == "ready"]
    if blocked:
        overall_state = "blocked"
    elif watch:
        overall_state = "watch"
    else:
        overall_state = "clear"

    summary = {
        "ok": True,
        "overall_state": overall_state,
        "recovery_clarity": burndown["summary"]["recovery_clarity"],
        "recovery_findings": [str(item.get("title", "")) for item in recovery_findings],
        "runtime_copy_state": tracks["runtime_copy"]["status"],
        "operator_notes_state": tracks["operator_notes"]["status"],
        "rejoin_path_state": tracks["rejoin_path"]["status"],
        "blocked_tracks": blocked,
        "watch_tracks": watch,
        "ready_tracks": ready,
        "must_fix_before_broader_preview": [
            title
            for title in triage["summary"].get("must_fix_before_broader_preview", [])
            if title in [str(item.get("title", "")) for item in recovery_findings] or "Recovery" in title or "rejoin" in title.lower()
        ],
        "can_wait_until_after_broader_preview": [
            title
            for title in triage["summary"].get("can_wait_until_after_broader_preview", [])
            if title not in [str(item.get("title", "")) for item in recovery_findings]
        ],
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(Path(workspace).resolve()),
        "fix_loop_root": str(root),
        "fix_loop_dir": str(run_dir),
        "snapshot_label": snapshot_label or "current",
        "feedback_triage_manifest": triage,
        "direct_boot_ux_burndown_manifest": burndown,
        "tracks": tracks,
        "summary": summary,
        "artifacts": {},
    }

    lines = [
        "# AgentOS Recovery Clarity Fix Loop",
        "",
        f"Run label: `{snapshot_label or 'current'}`",
        f"Generated at: `{payload['generated_at_utc']}`",
        "",
        "## Overall state",
        "",
        f"- Overall state: `{summary['overall_state']}`",
        f"- Recovery clarity: `{summary['recovery_clarity']}`",
        f"- Runtime copy state: `{summary['runtime_copy_state']}`",
        f"- Operator notes state: `{summary['operator_notes_state']}`",
        f"- Rejoin path state: `{summary['rejoin_path_state']}`",
        "",
        "## Must fix before broader preview",
        "",
    ]
    must_fix = summary["must_fix_before_broader_preview"]
    if must_fix:
        lines.extend(f"- `{item}`" for item in must_fix)
    else:
        lines.append("- none")
    lines.extend(["", "## Tracks", ""])
    for track in ("runtime_copy", "operator_notes", "rejoin_path"):
        track_payload = tracks[track]
        lines.append(f"### {track}")
        lines.append(f"- status: `{track_payload['status']}`")
        lines.append(f"- finding_count: `{track_payload['finding_count']}`")
        if track_payload["titles"]:
            lines.extend(f"- outstanding: `{title}`" for title in track_payload["titles"])
        else:
            lines.append("- outstanding: none")
        lines.append("")

    markdown_path = run_dir / "recovery-clarity-fix-loop.md"
    manifest_path = run_dir / "recovery-clarity-fix-loop.json"
    latest_manifest_path = root / "latest-recovery-clarity-fix-loop.json"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "recovery_clarity_fix_loop_markdown": str(markdown_path),
        "recovery_clarity_fix_loop_json": str(manifest_path),
        "latest_recovery_clarity_fix_loop_json": str(latest_manifest_path),
        "feedback_triage_manifest_json": triage["artifacts"]["feedback_triage_manifest_json"],
        "direct_boot_ux_burndown_manifest_json": burndown["artifacts"]["direct_boot_ux_burndown_manifest_json"],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_recovery_clarity_fix_loop(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "workspace",
        "fix_loop_root",
        "fix_loop_dir",
        "snapshot_label",
        "feedback_triage_manifest",
        "direct_boot_ux_burndown_manifest",
        "tracks",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("feedback_triage_manifest", {}).get("schema_version") != "agentos-feedback-triage.v1":
        errors.append("feedback_triage_manifest must reference agentos-feedback-triage.v1")
    if payload.get("direct_boot_ux_burndown_manifest", {}).get("schema_version") != "agentos-direct-boot-ux-burndown.v1":
        errors.append("direct_boot_ux_burndown_manifest must reference agentos-direct-boot-ux-burndown.v1")
    tracks = payload.get("tracks", {})
    for key in ("runtime_copy", "operator_notes", "rejoin_path"):
        track = tracks.get(key)
        if not isinstance(track, dict):
            errors.append(f"tracks.{key} must be present")
            continue
        if track.get("status") not in {"blocked", "watch", "ready"}:
            errors.append(f"tracks.{key}.status must be blocked, watch, or ready")
    summary = payload.get("summary", {})
    if summary.get("overall_state") not in {"blocked", "watch", "clear"}:
        errors.append("summary.overall_state must be blocked, watch, or clear")
    for key in ("must_fix_before_broader_preview", "can_wait_until_after_broader_preview", "blocked_tracks", "watch_tracks", "ready_tracks"):
        if not isinstance(summary.get(key), list):
            errors.append(f"summary.{key} must be a list")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an AgentOS recovery clarity fix loop report")
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
        errors = validate_recovery_clarity_fix_loop(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_recovery_clarity_fix_loop(
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
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        print(f"recovery clarity fix loop ready: {payload['artifacts']['recovery_clarity_fix_loop_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
