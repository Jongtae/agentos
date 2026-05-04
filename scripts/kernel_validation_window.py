#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kernel_operator_evidence import build_evidence_report

SCHEMA_VERSION = "agentos-validation-window.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_diagnostics_summary(path: str) -> dict[str, Any]:
    if not path:
        return {
            "available": False,
            "ok": None,
            "overall_exit": None,
            "readiness_status": "",
            "approval_anomaly_detected": None,
        }
    payload = _read_json(path)
    trace_health = payload.get("trace_health", {}) if isinstance(payload.get("trace_health"), dict) else {}
    approval_anomaly = trace_health.get("approval_anomaly", {}) if isinstance(trace_health.get("approval_anomaly"), dict) else {}
    kernel_ready = payload.get("kernel_policy_ready", {}) if isinstance(payload.get("kernel_policy_ready"), dict) else {}
    return {
        "available": True,
        "ok": int(payload.get("overall_exit", 1) or 1) == 0,
        "overall_exit": int(payload.get("overall_exit", 1) or 1),
        "readiness_status": str(kernel_ready.get("overall_status", "")),
        "approval_anomaly_detected": bool(approval_anomaly.get("anomaly_detected", False)),
        "bundle_dir": str(payload.get("bundle_dir", "")),
    }


def _overall_state(evidence: dict[str, Any], diagnostics: dict[str, Any]) -> str:
    if not bool((evidence.get("summary") or {}).get("runtime_ok", False)):
        return "runtime_attention"
    if diagnostics.get("available") and diagnostics.get("ok") is False:
        return "diagnostics_attention"
    if any(
        str((item.get("comparison") or {}).get("status", "")) not in ("aligned", "observed")
        for item in (evidence.get("policy_correlation", {}) or {}).get("policy_targets", [])
    ):
        return "policy_drift"
    return "stable"


def build_window_snapshot(
    *,
    workspace: str,
    install_root: str = "",
    metadata: str = "",
    diagnostics_manifest: str = "",
    snapshot_label: str = "current",
) -> dict[str, Any]:
    evidence = build_evidence_report(
        workspace=workspace,
        install_root=install_root,
        metadata=metadata,
    )
    diagnostics = _load_diagnostics_summary(diagnostics_manifest)
    policy_targets = {
        str(item.get("policy_target", "")): str((item.get("comparison") or {}).get("status", ""))
        for item in (evidence.get("policy_correlation", {}) or {}).get("policy_targets", [])
        if str(item.get("policy_target", ""))
    }
    summary = {
        "runtime_ok": bool((evidence.get("summary") or {}).get("runtime_ok", False)),
        "session_phase": str((evidence.get("summary") or {}).get("session_phase", "")),
        "session_origin": str((evidence.get("summary") or {}).get("session_origin", "")),
        "install_validation_ok": (evidence.get("summary") or {}).get("install_validation_ok", None),
        "audit_ok": (evidence.get("summary") or {}).get("audit_ok", None),
        "diagnostics_ok": diagnostics.get("ok", None),
        "diagnostics_readiness_status": diagnostics.get("readiness_status", ""),
        "approval_forensic_status": str(((evidence.get("summary") or {}).get("approval_forensics") or {}).get("forensic_status", "")),
        "policy_targets": policy_targets,
        "overall_state": _overall_state(evidence, diagnostics),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "label": snapshot_label,
        "workspace": str(Path(workspace).resolve()),
        "summary": summary,
        "sources": {
            "install_root": install_root,
            "metadata": metadata,
            "diagnostics_manifest": diagnostics_manifest,
        },
    }


def _extract_snapshot(payload: dict[str, Any]) -> dict[str, Any] | None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        return None
    if isinstance(payload.get("current_snapshot"), dict):
        return payload["current_snapshot"]
    if isinstance(payload.get("summary"), dict):
        return payload
    return None


def _load_history(history_dir: str, current_label: str) -> list[dict[str, Any]]:
    if not history_dir:
        return []
    root = Path(history_dir)
    if not root.exists():
        return []
    snapshots: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        snapshot = _extract_snapshot(payload)
        if not snapshot:
            continue
        if str(snapshot.get("label", path.stem)) == current_label:
            continue
        snapshots.append(snapshot)
    snapshots.sort(key=lambda item: str(item.get("generated_at_utc", "")))
    return snapshots


def _norm(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _compare(history: list[dict[str, Any]], current: dict[str, Any]) -> dict[str, Any]:
    current_summary = current.get("summary", {}) if isinstance(current.get("summary"), dict) else {}
    changed_fields: set[str] = set()
    windows: list[dict[str, Any]] = []
    for item in history:
        summary = item.get("summary", {}) if isinstance(item.get("summary"), dict) else {}
        item_changes: list[str] = []
        for key in sorted(set(summary.keys()) | set(current_summary.keys())):
            if _norm(summary.get(key)) != _norm(current_summary.get(key)):
                item_changes.append(key)
                changed_fields.add(key)
        windows.append(
            {
                "label": str(item.get("label", "")),
                "generated_at_utc": str(item.get("generated_at_utc", "")),
                "changed_fields": item_changes,
            }
        )
    return {
        "history_count": len(history),
        "changed_fields": sorted(changed_fields),
        "changed_window_count": sum(1 for item in windows if item["changed_fields"]),
        "windows": windows,
        "stable": len(changed_fields) == 0,
    }


def build_validation_window(
    *,
    workspace: str,
    install_root: str = "",
    metadata: str = "",
    diagnostics_manifest: str = "",
    history_dir: str = "",
    snapshot_label: str = "current",
) -> dict[str, Any]:
    current = build_window_snapshot(
        workspace=workspace,
        install_root=install_root,
        metadata=metadata,
        diagnostics_manifest=diagnostics_manifest,
        snapshot_label=snapshot_label,
    )
    comparison = _compare(_load_history(history_dir, snapshot_label), current)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "history_dir": str(Path(history_dir).resolve()) if history_dir else "",
        "current_snapshot": current,
        "comparison": comparison,
        "summary": {
            "history_count": comparison["history_count"],
            "changed_window_count": comparison["changed_window_count"],
            "changed_fields": comparison["changed_fields"],
            "stable": comparison["stable"],
            "current_overall_state": str((current.get("summary") or {}).get("overall_state", "")),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build AgentOS validation window report")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--install-root", default="")
    parser.add_argument("--metadata", default="")
    parser.add_argument("--diagnostics-manifest", default="")
    parser.add_argument("--history-dir", default="")
    parser.add_argument("--snapshot-label", default="current")
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_validation_window(
        workspace=args.workspace,
        install_root=args.install_root,
        metadata=args.metadata,
        diagnostics_manifest=args.diagnostics_manifest,
        history_dir=args.history_dir,
        snapshot_label=args.snapshot_label,
    )
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
        return 0

    summary = payload["summary"]
    print("AgentOS Validation Window")
    print("=========================")
    print(f"History count: {summary['history_count']}")
    print(f"Changed windows: {summary['changed_window_count']}")
    print(f"Current overall state: {summary['current_overall_state'] or 'unknown'}")
    print("Changed fields: " + (", ".join(summary["changed_fields"]) if summary["changed_fields"] else "(none)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
