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

from kernel_evaluator_feedback_intake import build_feedback_intake

SCHEMA_VERSION = "agentos-feedback-triage.v1"
LAYOUT_DIRNAME = "feedback-triage"
DIRECT_BOOT_UX_AREAS = {
    "boot",
    "setup",
    "recovery",
    "install_identity",
    "managed_session",
    "session_entry",
    "install_later",
}
SEVERITY_TO_BUCKET = {
    "critical": "blocker",
    "high": "blocker",
    "medium": "watch",
    "low": "polish",
    "note": "polish",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_root(report_dir: str) -> Path:
    report_root = Path(report_dir).resolve()
    if report_root.name == LAYOUT_DIRNAME:
        return report_root
    return report_root / LAYOUT_DIRNAME


def _normalize_finding(item: dict, index: int) -> dict:
    severity = str(item.get("severity", "note"))
    bucket = SEVERITY_TO_BUCKET.get(severity, "polish")
    area = str(item.get("area", "general"))
    domain = "direct_boot_ux" if area in DIRECT_BOOT_UX_AREAS else "general_preview"
    return {
        "finding_id": f"finding-{index + 1}",
        "title": str(item.get("title", "untitled-finding")),
        "severity": severity,
        "promotion_bucket": bucket,
        "domain": domain,
        "area": area,
        "detail": str(item.get("detail", "")),
        "artifact_ref": str(item.get("artifact_ref", "")),
    }


def _promotion_state(*, blockers: int, watch: int, direct_boot_watch: int, recommendation: str) -> str:
    if blockers > 0 or recommendation == "revise":
        return "blocked"
    if direct_boot_watch > 0 or watch > 0 or recommendation == "hold":
        return "watch"
    return "clear"


def build_feedback_triage(
    *,
    workspace: str,
    report_dir: str,
    feedback_intake_manifest: str = "",
    feedback_file: str = "",
    install_root: str = "",
    metadata: str = "",
    diagnostics_manifest: str = "",
    history_dir: str = "",
    snapshot_label: str = "current",
    session_id: str = "",
    limit: int = 50,
) -> dict:
    triage_root = resolve_root(report_dir)
    triage_dir = triage_root / f"feedback-triage-{snapshot_label or 'current'}"
    triage_dir.mkdir(parents=True, exist_ok=True)

    if feedback_intake_manifest:
        intake_manifest = json.loads(Path(feedback_intake_manifest).read_text(encoding="utf-8"))
    else:
        intake_manifest = build_feedback_intake(
            workspace=workspace,
            report_dir=str(triage_dir / "feedback"),
            feedback_file=feedback_file,
            install_root=install_root,
            metadata=metadata,
            diagnostics_manifest=diagnostics_manifest,
            history_dir=history_dir,
            snapshot_label=snapshot_label,
            session_id=session_id,
            limit=limit,
        )

    findings = intake_manifest.get("feedback_packet", {}).get("findings", [])
    normalized = [_normalize_finding(item, idx) for idx, item in enumerate(findings) if isinstance(item, dict)]

    blocker = [item for item in normalized if item["promotion_bucket"] == "blocker"]
    watch = [item for item in normalized if item["promotion_bucket"] == "watch"]
    polish = [item for item in normalized if item["promotion_bucket"] == "polish"]
    direct_boot_ux = [item for item in normalized if item["domain"] == "direct_boot_ux"]
    general_preview = [item for item in normalized if item["domain"] == "general_preview"]
    direct_boot_watch = [item for item in watch if item["domain"] == "direct_boot_ux"]
    must_fix = blocker + direct_boot_watch
    can_wait = [
        item for item in normalized if item["finding_id"] not in {entry["finding_id"] for entry in must_fix}
    ]
    recommendation = intake_manifest.get("feedback_packet", {}).get("recommendation", "hold")

    markdown_lines = [
        "# AgentOS Feedback Triage",
        "",
        f"Run label: `{snapshot_label or 'current'}`",
        f"Generated at: `{_utc_now()}`",
        "",
        "## Promotion Summary",
        "",
        f"- Recommendation: `{recommendation}`",
        f"- Promotion state: `{_promotion_state(blockers=len(blocker), watch=len(watch), direct_boot_watch=len(direct_boot_watch), recommendation=recommendation)}`",
        f"- Blockers: `{len(blocker)}`",
        f"- Watch: `{len(watch)}`",
        f"- Polish: `{len(polish)}`",
        f"- Direct-boot UX findings: `{len(direct_boot_ux)}`",
        "",
        "## Must fix before broader preview",
        "",
    ]
    if must_fix:
        markdown_lines.extend(f"- `{item['title']}` ({item['promotion_bucket']}, {item['domain']}, {item['severity']})" for item in must_fix)
    else:
        markdown_lines.append("- none")
    markdown_lines.extend([
        "",
        "## Can wait until after broader preview",
        "",
    ])
    if can_wait:
        markdown_lines.extend(f"- `{item['title']}` ({item['promotion_bucket']}, {item['domain']}, {item['severity']})" for item in can_wait)
    else:
        markdown_lines.append("- none")
    markdown_lines.extend([
        "",
        "## Direct-boot UX findings",
        "",
    ])
    if direct_boot_ux:
        markdown_lines.extend(f"- `{item['title']}` in `{item['area']}`" for item in direct_boot_ux)
    else:
        markdown_lines.append("- none")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(Path(workspace).resolve()),
        "triage_root": str(triage_root),
        "triage_dir": str(triage_dir),
        "snapshot_label": snapshot_label or "current",
        "feedback_intake_manifest": intake_manifest,
        "promotion_buckets": {
            "blocker": blocker,
            "watch": watch,
            "polish": polish,
        },
        "domain_buckets": {
            "direct_boot_ux": direct_boot_ux,
            "general_preview": general_preview,
        },
        "summary": {
            "ok": True,
            "recommendation": recommendation,
            "promotion_state": _promotion_state(
                blockers=len(blocker),
                watch=len(watch),
                direct_boot_watch=len(direct_boot_watch),
                recommendation=recommendation,
            ),
            "blocker_count": len(blocker),
            "watch_count": len(watch),
            "polish_count": len(polish),
            "direct_boot_ux_count": len(direct_boot_ux),
            "must_fix_before_broader_preview": [item["title"] for item in must_fix],
            "can_wait_until_after_broader_preview": [item["title"] for item in can_wait],
        },
        "artifacts": {},
    }
    markdown_path = triage_dir / "feedback-triage.md"
    manifest_path = triage_dir / "feedback-triage.json"
    latest_manifest_path = triage_root / "latest-feedback-triage.json"
    markdown_path.write_text("\n".join(markdown_lines) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    payload["artifacts"] = {
        "feedback_triage_markdown": str(markdown_path),
        "feedback_triage_manifest_json": str(manifest_path),
        "latest_feedback_triage_manifest_json": str(latest_manifest_path),
        "feedback_intake_manifest_json": intake_manifest["artifacts"]["feedback_intake_manifest_json"],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    latest_manifest_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def validate_feedback_triage(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "generated_at_utc",
        "workspace",
        "triage_root",
        "triage_dir",
        "snapshot_label",
        "feedback_intake_manifest",
        "promotion_buckets",
        "domain_buckets",
        "summary",
        "artifacts",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    intake = payload.get("feedback_intake_manifest")
    if not isinstance(intake, dict) or intake.get("schema_version") != "agentos-evaluator-feedback-intake.v1":
        errors.append("feedback_intake_manifest must reference agentos-evaluator-feedback-intake.v1")
    buckets = payload.get("promotion_buckets", {})
    for key in ("blocker", "watch", "polish"):
        if not isinstance(buckets.get(key), list):
            errors.append(f"promotion_buckets.{key} must be a list")
    domain = payload.get("domain_buckets", {})
    for key in ("direct_boot_ux", "general_preview"):
        if not isinstance(domain.get(key), list):
            errors.append(f"domain_buckets.{key} must be a list")
    summary = payload.get("summary", {})
    if summary.get("promotion_state") not in {"blocked", "watch", "clear"}:
        errors.append("summary.promotion_state must be blocked, watch, or clear")
    for key in ("blocker_count", "watch_count", "polish_count", "direct_boot_ux_count"):
        if not isinstance(summary.get(key), int):
            errors.append(f"summary.{key} must be an integer")
    for key in ("must_fix_before_broader_preview", "can_wait_until_after_broader_preview"):
        if not isinstance(summary.get(key), list):
            errors.append(f"summary.{key} must be a list")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an AgentOS feedback triage packet")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--report-dir", default="./workspaces/default/artifacts")
    parser.add_argument("--feedback-intake-manifest", default="")
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
        errors = validate_feedback_triage(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_feedback_triage(
        workspace=args.workspace,
        report_dir=args.report_dir,
        feedback_intake_manifest=args.feedback_intake_manifest,
        feedback_file=args.feedback_file,
        install_root=args.install_root,
        metadata=args.metadata,
        diagnostics_manifest=args.diagnostics_manifest,
        history_dir=args.history_dir,
        snapshot_label=args.snapshot_label,
        session_id=args.session_id,
        limit=args.limit,
    )
    errors = validate_feedback_triage(payload)
    payload["summary"]["ok"] = not errors
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
        return 0 if not errors else 1

    print("AgentOS Feedback Triage")
    print("=======================")
    print(f"Promotion state: {payload['summary']['promotion_state']}")
    print(f"Blockers: {payload['summary']['blocker_count']}")
    print(f"Watch: {payload['summary']['watch_count']}")
    print(f"Polish: {payload['summary']['polish_count']}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
