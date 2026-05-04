#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_report_status(report_dir: str) -> dict:
    root = Path(report_dir)
    files = sorted(root.glob("kernel-repair-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

    total_bytes = 0
    newest_meta: dict = {}
    valid_json_count = 0
    invalid_json_files: list[str] = []
    ok_count = 0
    fail_count = 0
    shadow_summary: dict = {}
    alignment_summary: dict = {}

    for idx, path in enumerate(files):
        stat = path.stat()
        total_bytes += stat.st_size
        payload = {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            valid_json_count += 1
        except Exception:
            invalid_json_files.append(str(path))

        if payload.get("ok") is True:
            ok_count += 1
        elif payload.get("ok") is False:
            fail_count += 1

        if idx == 0:
            after = payload.get("after", {}) if isinstance(payload, dict) else {}
            shadow_mode = after.get("shadow_mode", {}) if isinstance(after, dict) else {}
            event_fabric = after.get("event_fabric", {}) if isinstance(after, dict) else {}
            newest_meta = {
                "path": str(path),
                "size_bytes": stat.st_size,
                "ok": payload.get("ok"),
                "mode": payload.get("mode"),
                "needs_repair": payload.get("needs_repair"),
            }
            shadow_summary = {
                "available": bool(shadow_mode.get("available", False)),
                "aligned": bool(shadow_mode.get("aligned", False)),
                "delta": int(shadow_mode.get("delta", 0) or 0),
                "user_space_blocked_count": int(shadow_mode.get("user_space_blocked_count", 0) or 0),
                "shadow_detected_count": int(shadow_mode.get("shadow_detected_count", 0) or 0),
                "coverage_summary": shadow_mode.get("coverage_summary", {}),
                "policy_targets": shadow_mode.get("policy_targets", []),
            }
            alignment_summary = {
                "available": bool(event_fabric.get("available", False)),
                "overall_aligned": bool(event_fabric.get("overall_aligned", False)),
                "total_events": int(event_fabric.get("total_events", 0) or 0),
                "recent_kinds": event_fabric.get("recent_kinds", []),
                "enforced_pilot": event_fabric.get("enforced_pilot", {}),
                "supported_policy_targets": event_fabric.get("supported_policy_targets", []),
                "next_policy_target": str(event_fabric.get("next_policy_target", "")),
                "policy_targets": event_fabric.get("policy_targets", []),
            }

    status_ok = len(invalid_json_files) == 0
    return {
        "ok": status_ok,
        "exit_code": 0 if status_ok else 1,
        "report_dir": str(root),
        "report_count": len(files),
        "total_bytes": total_bytes,
        "valid_json_count": valid_json_count,
        "invalid_json_files": invalid_json_files,
        "ok_reports": ok_count,
        "fail_reports": fail_count,
        "newest_report": newest_meta,
        "shadow_summary": shadow_summary,
        "alignment_summary": alignment_summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentOS kernel repair report archive status")
    parser.add_argument("--report-dir", default="./artifacts/kernel-repair-reports")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_report_status(args.report_dir)
    if args.json:
        print(json.dumps(report, ensure_ascii=True))
        return int(report["exit_code"])

    print("AgentOS Kernel Repair Report Status")
    print("==================================")
    print(f"Report dir: {report['report_dir']}")
    print(f"Report count: {report['report_count']}")
    print(f"Total bytes: {report['total_bytes']}")
    print(f"Valid JSON: {report['valid_json_count']}")
    print(f"Invalid JSON files: {len(report['invalid_json_files'])}")
    print(f"ok/fail reports: {report['ok_reports']}/{report['fail_reports']}")
    if report["newest_report"]:
        nr = report["newest_report"]
        print(f"Newest report: {nr.get('path')}")
        print(f"Newest mode/ok: {nr.get('mode')}/{nr.get('ok')}")
    shadow = report.get("shadow_summary", {}) or {}
    if shadow:
        print(
            "Shadow summary: "
            f"available={shadow.get('available')} "
            f"aligned={shadow.get('aligned')} "
            f"delta={shadow.get('delta')}"
        )
        coverage = shadow.get("coverage_summary", {}) or {}
        if coverage:
            print(
                "  coverage: "
                f"targets={coverage.get('policy_target_count')} "
                f"aligned={coverage.get('aligned_count')} "
                f"divergent={coverage.get('divergent_count')}"
            )
    alignment = report.get("alignment_summary", {}) or {}
    if alignment:
        print(
            "Alignment summary: "
            f"available={alignment.get('available')} "
            f"overall_aligned={alignment.get('overall_aligned')} "
            f"events={alignment.get('total_events')}"
        )
        policy_targets = alignment.get("policy_targets", []) or []
        for item in policy_targets:
            print(
                f"  - {item.get('policy_target')}: "
                f"status={item.get('status')} "
                f"delta={item.get('delta')}"
            )
    print(f"Overall: {'PASS' if report['ok'] else 'FAIL'}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
