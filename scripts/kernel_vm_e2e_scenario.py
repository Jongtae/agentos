#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from kernel.vm_e2e_scenario import VM_E2E_SCENARIO_SCHEMA, run_vm_e2e_scenario


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != VM_E2E_SCENARIO_SCHEMA:
        errors.append(f"schema_version must be {VM_E2E_SCENARIO_SCHEMA}")
    summary = payload.get("summary") or {}
    for key in (
        "document_native_handled",
        "web_handled",
        "intake_ok",
        "service_permission_ready",
        "execution_samples",
    ):
        if key not in summary:
            errors.append(f"summary.{key} must be present")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh VM E2E scenario manifests")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--session-id", default="agentos:tty1")
    parser.add_argument("--boot-id", default="vm-e2e-boot")
    parser.add_argument("--web-url", default="https://example.com")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_payload(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("vm e2e scenario: PASS" if result["ok"] else "vm e2e scenario: FAIL")
        return 0 if result["ok"] else 1

    payload = run_vm_e2e_scenario(
        args.workspace,
        session_id=args.session_id,
        boot_id=args.boot_id,
        web_url=args.web_url,
    )
    errors = validate_payload(payload)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=True))
        return 1
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
