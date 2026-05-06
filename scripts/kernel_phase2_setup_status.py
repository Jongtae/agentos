#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "agentos-phase2-setup-status.v1"


def _state(configured: bool, *, invalid: bool = False) -> str:
    if invalid:
        return "invalid"
    return "configured" if configured else "missing"


def build_status(workspace: str, user_root: str) -> dict:
    workspace_path = Path(workspace).expanduser().resolve()
    user_root_path = Path(user_root).expanduser().resolve()
    openai_key = bool(os.environ.get("OPENAI_API_KEY", "").strip())
    telegram_token = bool(os.environ.get("AGENTOS_TELEGRAM_BOT_TOKEN", "").strip())
    telegram_chat = bool(os.environ.get("AGENTOS_TELEGRAM_ALLOWED_CHAT_IDS", "").strip())
    gmail_fixture = bool(os.environ.get("AGENTOS_GMAIL_FIXTURE", "").strip())
    adapters = {
        "llm": {"state": "configured" if openai_key else "degraded", "reason": "" if openai_key else "local_or_external_llm_not_confirmed"},
        "telegram": {"state": _state(telegram_token and telegram_chat), "reason": "" if telegram_token and telegram_chat else "telegram_runtime_config_missing"},
        "gmail": {"state": _state(gmail_fixture), "reason": "" if gmail_fixture else "gmail_fixture_or_oauth_missing"},
        "user_data": {"state": "configured", "reason": ""},
    }
    ready = adapters["user_data"]["state"] == "configured"
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace_path),
        "user_data_root": str(user_root_path),
        "overall_state": "degraded" if any(item["state"] in {"missing", "degraded", "invalid"} for item in adapters.values()) else "configured",
        "runtime_ready": ready,
        "adapters": adapters,
        "secrets_redacted": True,
        "next_actions": [
            "configure Telegram token and allowed chat IDs" if adapters["telegram"]["state"] == "missing" else "",
            "provide a Gmail fixture or OAuth adapter when Gmail proof is required" if adapters["gmail"]["state"] == "missing" else "",
        ],
        "proof": {"ok": ready, "secret_values_printed": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Phase 2 setup/status state")
    parser.add_argument("--workspace", default=os.environ.get("DEFAULT_WORKSPACE", "./workspaces/default"))
    parser.add_argument("--user-root", default=os.environ.get("AGENTOS_USER_DATA_ROOT", "./agentos-data/user"))
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = build_status(args.workspace, args.user_root)
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(json.dumps(payload, ensure_ascii=True))
    return 0 if payload["proof"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

