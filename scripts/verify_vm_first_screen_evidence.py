#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

SCHEMA_VERSION = "agentos-vm-first-screen-evidence.v1"
EVIDENCE_CONTRACT = "agentos_vm_first_screen_evidence.v1"
EXPECTED_FIRST_SCREEN = "AgentOS Welcome"
EXPECTED_FIRST_PATH = "Continue to AgentOS -> AgentOS Welcome -> AgentOS Setup -> ai>"


def build_report(*, iso_root: Path, boot_flow_proof: Path, boot_target_activation: Path) -> dict:
    flow = json.loads(boot_flow_proof.read_text(encoding="utf-8")) if boot_flow_proof.exists() else {}
    target = json.loads(boot_target_activation.read_text(encoding="utf-8")) if boot_target_activation.exists() else {}
    report_path = iso_root / "agentos" / "vm-first-screen-evidence.json"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "evidence_contract": EVIDENCE_CONTRACT,
        "iso_root": str(iso_root),
        "boot_flow_proof": str(boot_flow_proof),
        "boot_target_activation": str(boot_target_activation),
        "default_boot_target_label": target.get("default_boot_target_label", ""),
        "boot_target_activated": bool(target.get("boot_target_activated")),
        "welcome_autostart_included": bool(flow.get("welcome_autostart_included")),
        "welcome_shell_included": bool(flow.get("welcome_shell_included")),
        "expected_first_screen": EXPECTED_FIRST_SCREEN,
        "expected_first_path": EXPECTED_FIRST_PATH,
        "evidence_status": "incomplete",
        "report_path": str(report_path),
    }
    if (
        payload["default_boot_target_label"] == "Continue to AgentOS"
        and payload["boot_target_activated"]
        and payload["welcome_autostart_included"]
        and payload["welcome_shell_included"]
    ):
        payload["evidence_status"] = "ready"
    return payload


def validate_report(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("evidence_contract") != EVIDENCE_CONTRACT:
        errors.append(f"evidence_contract must be {EVIDENCE_CONTRACT}")
    if payload.get("default_boot_target_label") != "Continue to AgentOS":
        errors.append("default_boot_target_label must be Continue to AgentOS")
    if payload.get("boot_target_activated") is not True:
        errors.append("boot_target_activated must be true")
    if payload.get("welcome_autostart_included") is not True:
        errors.append("welcome_autostart_included must be true")
    if payload.get("welcome_shell_included") is not True:
        errors.append("welcome_shell_included must be true")
    if payload.get("expected_first_screen") != EXPECTED_FIRST_SCREEN:
        errors.append(f"expected_first_screen must be {EXPECTED_FIRST_SCREEN}")
    if payload.get("expected_first_path") != EXPECTED_FIRST_PATH:
        errors.append(f"expected_first_path must be {EXPECTED_FIRST_PATH}")
    if payload.get("evidence_status") != "ready":
        errors.append("evidence_status must be ready")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or validate VM first-screen evidence for remastered AgentOS ISO trees")
    parser.add_argument("--iso-root", default="")
    parser.add_argument("--boot-flow-proof", default="")
    parser.add_argument("--boot-target-activation", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_report(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        print(json.dumps(result, ensure_ascii=True) if args.json else ("PASS" if result["ok"] else "FAIL"))
        if not args.json and errors:
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_report(
        iso_root=Path(args.iso_root).resolve(),
        boot_flow_proof=Path(args.boot_flow_proof).resolve(),
        boot_target_activation=Path(args.boot_target_activation).resolve(),
    )
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
