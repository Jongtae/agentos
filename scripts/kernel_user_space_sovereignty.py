#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from kernel.operator_mode import operator_mode_contract
from kernel.runtime_entry import build_runtime_entry_contract
from kernel.user_space_sovereignty import USER_SPACE_SOVEREIGNTY_SCHEMA_VERSION, build_user_space_sovereignty_report

REQUIRED_KEYS = {"schema_version", "session_origin", "setup_status", "launcher_semantics", "default_user_actions", "status", "summary"}


def _setup_state() -> dict:
    env_file = Path(os.environ.get("AGENTOS_ENV_FILE", Path.home() / ".config" / "agentos" / "env"))
    exists = env_file.exists()
    return {
        "status": "configured" if exists else "pending",
        "next_managed_entry": "ai_shell" if exists else "setup_session",
    }


def _session_origin() -> dict:
    managed = os.environ.get("AGENTOS_SESSION_MANAGED", "") == "1"
    session_entry = str(os.environ.get("AGENTOS_SESSION_ENTRY", "")).strip()
    ssh_active = bool(os.environ.get("SSH_TTY") or os.environ.get("SSH_CONNECTION"))
    if managed and session_entry == "local_tty1":
        category = "local_managed_tty1"
    elif ssh_active:
        category = "ssh"
    else:
        category = "noninteractive"
    return {"category": category}


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_KEYS - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != USER_SPACE_SOVEREIGNTY_SCHEMA_VERSION:
        errors.append(f"schema_version must be {USER_SPACE_SOVEREIGNTY_SCHEMA_VERSION}")
    if not isinstance(payload.get("default_user_actions"), list) or not payload.get("default_user_actions"):
        errors.append("default_user_actions must be a non-empty list")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Build AgentOS user-space sovereignty report")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_payload(payload)
        result = {"ok": not errors, "errors": errors}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("ok" if not errors else "invalid")
            for error in errors:
                print(f"- {error}")
        return 0 if not errors else 1

    session_origin = _session_origin()
    setup_state = _setup_state()
    runtime_entry = build_runtime_entry_contract(session_origin=session_origin, setup_state=setup_state)
    operator_mode = operator_mode_contract(session_origin=session_origin, setup_state=setup_state)
    payload = build_user_space_sovereignty_report(
        session_origin=session_origin,
        setup_state=setup_state,
        runtime_entry=runtime_entry,
        operator_mode=operator_mode,
    )
    errors = validate_payload(payload)
    if errors:
        if args.json:
            print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=True))
        else:
            for error in errors:
                print(error)
        return 1
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print("AgentOS User Space Sovereignty")
        print("===============================")
        print(f"Session origin: {payload['session_origin']}")
        print(f"Interaction model: {payload['summary']['default_interaction_model']}")
        print(f"Managed actions: {payload['summary']['managed_action_count']}")
        print(f"Guided actions: {payload['summary']['guided_action_count']}")
        print(f"Passthrough actions: {payload['summary']['passthrough_action_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
