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

from kernel_feedback_triage import build_feedback_triage

SCHEMA_VERSION = "agentos-direct-boot-ux-burndown.v1"
LAYOUT_DIRNAME = "direct-boot-ux-burndown"
TARGET_AREA_MAP = {
    "boot_clarity": {"boot"},
    "setup_clarity": {"setup", "install_identity", "managed_session", "session_entry", "install_later"},
    "recovery_clarity": {"recovery"},
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def _target_status(findings: list[dict]) -> str:
    buckets = {str(item.get("promotion_bucket", "")) for item in findings}
    if "blocker" in buckets:
        return "blocked"
    if "watch" in buckets:
        return "watch"
    return "ready"


def _target_payload(name: str, findings: list[dict]) -> dict:
    return {
        "target": name,
        "status": _target_status(findings),
        "outstanding_count": len(findings),
        "outstanding_titles": [item["title"] for item in findings],
        "findings": findings,
    }


def build_direct_boot_ux_burndown(
    *,
    workspace: str,
    report_dir: str,
    feedback_triage_manifest: str = "",
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
    run_dir = root / f"direct-boot-ux-burndown-{snapshot_label or 'current'}"
    run_dir.mkdir(parents=True, exist_ok=True)

    if feedback_triage_manifest:
        triage = json.loads(Path(feedback_triage_manifest).read_text(encoding="utf-8"))
    else:
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

    direct_boot_findings = triage.get("domain_buckets", {}).get("direct_boot_ux", [])
    targets = {}
    for target, areas in TARGET_AREA_MAP.items():
        matches = [item for item in direct_boot_findings if str(item.get("area", "")) in areas]
        targets[target] = _target_payload(target, matches)

    blocked = [name for name, payload in targets.items() if payload["status"] == "blocked"]
    watch = [name for name, payload in targets.items() if payload["status"] == "watch"]
    ready = [name for name, payload in targets.items() if payload["status"] == "ready"]
    if blocked:
        burn_down_state = "blocked"
    elif watch:
        burn_down_state = "watch"
    else:
        burn_down_state = "clear"

    markdown_lines = [
        "# AgentOS Direct-Boot UX Burn-Down",
        "",
        f"Run label: `{snapshot_label or 'current'}`",
        f"Generated at: `{_utc_now()}`",
        "",
        "## Overall state",
        "",
        f"- Burn-down state: `{burn_down_state}`",
        f"- Blocked targets: `{len(blocked)}`",
        f"- Watch targets: `{len(watch)}`",
        f"- Ready targets: `{len(ready)}`",
        "",
        "## Targets",
        "",
    ]
    for target in ("boot_clarity", "setup_clarity", "recovery_clarity"):
        payload = targets[target]
        markdown_lines.append(f"### {target}")
        markdown_lines.append(f"- status: `{payload['status']}`")
        markdown_lines.append(f"- outstanding_count: `{payload['outstanding_count']}`")
        if payload["outstanding_titles"]:
            markdown_lines.extend(f"- outstanding: `{title}`" for title in payload["outstanding_titles"])
        else:
            markdown_lines.append("- outstanding: none")
        markdown_lines.append("")

    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(Path(workspace).resolve()),
        "burndown_root": str(root),
        "burndown_dir": str(run_dir),
        "snapshot_label": snapshot_label or "current",
        "feedback_triage_manifest": triage,
        "targets": targets,
        "summary": {
            "ok": True,
            "burn_down_state": burn_down_state,
            "blocked_targets": blocked,
            "watch_targets": watch,
            "ready_targets": ready,
            "boot_clarity": targets["boot_clarity"]["status"],
            "setup_clarity": targets["setup_clarity"]["status"],
            "recovery_clarity": targets["recovery_clarity"]["status"],
            "outstanding_fix_targets": blocked + watch,
            "cleared_fix_targets": ready,
        },
        "artifacts": {},
    }
    markdown_path = run_dir / "direct-boot-ux-burndown.md"
    manifest_path = run_dir / "direct-boot-ux-burndown.json"
    latest_manifest_path = root / "latest-direct-boot-ux-burndown.json"
    markdown_path.write_text("\n".join(markdown_lines) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(result, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(result, ensure_ascii=True) + "\n", encoding="utf-8")
    result["artifacts"] = {
        "direct_boot_ux_burndown_markdown": str(markdown_path),
        "direct_boot_ux_burndown_manifest_json": str(manifest_path),
        "latest_direct_boot_ux_burndown_manifest_json": str(latest_manifest_path),
        "feedback_triage_manifest_json": triage["artifacts"]["feedback_triage_manifest_json"],
    }
    manifest_path.write_text(json.dumps(result, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(result, ensure_ascii=True) + "\n", encoding="utf-8")
    return result


def validate_direct_boot_ux_burndown(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "workspace",
        "burndown_root",
        "burndown_dir",
        "snapshot_label",
        "feedback_triage_manifest",
        "targets",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    triage = payload.get("feedback_triage_manifest")
    if not isinstance(triage, dict) or triage.get("schema_version") != "agentos-feedback-triage.v1":
        errors.append("feedback_triage_manifest must reference agentos-feedback-triage.v1")
    targets = payload.get("targets", {})
    for key in ("boot_clarity", "setup_clarity", "recovery_clarity"):
        target = targets.get(key)
        if not isinstance(target, dict):
            errors.append(f"targets.{key} must be present")
            continue
        if target.get("status") not in {"blocked", "watch", "ready"}:
            errors.append(f"targets.{key}.status must be blocked, watch, or ready")
    summary = payload.get("summary", {})
    if summary.get("burn_down_state") not in {"blocked", "watch", "clear"}:
        errors.append("summary.burn_down_state must be blocked, watch, or clear")
    for key in ("blocked_targets", "watch_targets", "ready_targets", "outstanding_fix_targets", "cleared_fix_targets"):
        if not isinstance(summary.get(key), list):
            errors.append(f"summary.{key} must be a list")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an AgentOS direct-boot UX burn-down report")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--report-dir", default="./workspaces/default/artifacts")
    parser.add_argument("--feedback-triage-manifest", default="")
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
        errors = validate_direct_boot_ux_burndown(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_direct_boot_ux_burndown(
        workspace=args.workspace,
        report_dir=args.report_dir,
        feedback_triage_manifest=args.feedback_triage_manifest,
        feedback_file=args.feedback_file,
        install_root=args.install_root,
        metadata=args.metadata,
        diagnostics_manifest=args.diagnostics_manifest,
        history_dir=args.history_dir,
        snapshot_label=args.snapshot_label,
        session_id=args.session_id,
        limit=args.limit,
    )
    errors = validate_direct_boot_ux_burndown(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
        return 0 if not errors else 1

    print("AgentOS Direct-Boot UX Burn-Down")
    print("=================================")
    print(f"Burn-down state: {payload['summary']['burn_down_state']}")
    print(f"Outstanding fix targets: {', '.join(payload['summary']['outstanding_fix_targets']) or 'none'}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
