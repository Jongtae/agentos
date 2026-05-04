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

from kernel.runtime_entry import build_runtime_entry_contract, RUNTIME_ENTRY_SCHEMA_VERSION


def build_payload(
    *,
    session_origin: str,
    setup_status: str,
    next_managed_entry: str,
) -> dict:
    return build_runtime_entry_contract(
        session_origin={"category": session_origin},
        setup_state={"status": setup_status, "next_managed_entry": next_managed_entry},
    )


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "primary_runtime",
        "primary_runtime_provider",
        "managed_runtime_target",
        "launch_path_summary",
        "installed_launch_path_summary",
        "recovery_return_path_summary",
        "default_origin",
        "preferred_origin",
        "preferred_installed_origin",
        "recovery_label",
        "platform_model",
        "update_model",
        "transitional_origin_vocabulary",
        "target_platform_states",
        "slot_aware_runtime",
        "current_origin",
        "current_rule_id",
        "behavior",
        "effective_target",
        "fallback_target",
        "agentos_first",
        "appliance_boot",
        "installed_appliance_boot",
        "setup_status",
        "next_managed_entry",
        "safe_mode_supported",
        "recovery_mode_supported",
        "bypass_mode_supported",
        "recovery_entry_points",
        "entry_rules",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != RUNTIME_ENTRY_SCHEMA_VERSION:
        errors.append(f"schema_version must be {RUNTIME_ENTRY_SCHEMA_VERSION}")
    if payload.get("primary_runtime") != "codex_cli":
        errors.append("primary_runtime must be codex_cli")
    if payload.get("primary_runtime_provider") != "codex":
        errors.append("primary_runtime_provider must be codex")
    if payload.get("managed_runtime_target") != "codex_cli_managed_session":
        errors.append("managed_runtime_target must be codex_cli_managed_session")
    if payload.get("default_origin") != "local_managed_tty1":
        errors.append("default_origin must be local_managed_tty1")
    if payload.get("preferred_origin") != "live_appliance_boot":
        errors.append("preferred_origin must be live_appliance_boot")
    if payload.get("preferred_installed_origin") != "installed_appliance_boot":
        errors.append("preferred_installed_origin must be installed_appliance_boot")
    if payload.get("recovery_label") != "AgentOS Recovery":
        errors.append("recovery_label must be AgentOS Recovery")
    if payload.get("platform_model") != "agentos_managed_appliance_os":
        errors.append("platform_model must be agentos_managed_appliance_os")
    if payload.get("update_model") != "image_based_ab_updates":
        errors.append("update_model must be image_based_ab_updates")
    if payload.get("transitional_origin_vocabulary") is not True:
        errors.append("transitional_origin_vocabulary must be true")
    if not isinstance(payload.get("target_platform_states"), list) or not payload.get("target_platform_states"):
        errors.append("target_platform_states must be a non-empty list")
    if payload.get("slot_aware_runtime") is not True:
        errors.append("slot_aware_runtime must be true")
    if not isinstance(payload.get("recovery_entry_points"), list) or not payload.get("recovery_entry_points"):
        errors.append("recovery_entry_points must be a non-empty list")
    if not isinstance(payload.get("entry_rules"), list) or not payload.get("entry_rules"):
        errors.append("entry_rules must be a non-empty list")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or validate the AgentOS runtime entry contract")
    parser.add_argument("--session-origin", default="local_managed_tty1")
    parser.add_argument("--setup-status", default="pending")
    parser.add_argument("--next-managed-entry", default="setup_session")
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
            print("runtime entry contract: PASS" if result["ok"] else "runtime entry contract: FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_payload(
        session_origin=args.session_origin,
        setup_status=args.setup_status,
        next_managed_entry=args.next_managed_entry,
    )
    errors = validate_payload(payload)
    if errors:
        if args.json:
            print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=True))
        else:
            for error in errors:
                print(error)
        return 1

    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
