#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from io_utils import scrub_payload
from kernel.intent_dispatch import build_intent_dispatch_report
from kernel.operator_activity import build_activity_feed_payload

SCHEMA_VERSION = "agentos-phase2-runtime-preview.v1"


def _default_user_root() -> Path:
    return Path(os.environ.get("AGENTOS_USER_DATA_ROOT", "./agentos-data/user")).expanduser()


def build_preview(workspace: str, user_root: str, prompt: str) -> dict:
    workspace_path = Path(workspace).resolve()
    user_root_path = Path(user_root).expanduser().resolve()
    records_dir = user_root_path / "records" / "phase2-preview"
    records_dir.mkdir(parents=True, exist_ok=True)

    dispatch = build_intent_dispatch_report(
        workspace_path,
        source="operator",
        message_text=prompt,
        request_id="phase2-preview",
        write_manifest=True,
    )
    activity = build_activity_feed_payload(workspace_path, limit=12)
    record = {
        "schema_version": "agentos-phase2-preview-record.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "prompt": prompt,
        "intent": dispatch.get("intent", ""),
        "capability": dispatch.get("capability_executed", ""),
        "response": dispatch.get("response", ""),
    }
    record_path = records_dir / "latest-preview-record.json"
    record_path.write_text(json.dumps(scrub_payload(record), ensure_ascii=True) + "\n", encoding="utf-8")
    return scrub_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "workspace": str(workspace_path),
            "user_data_root": str(user_root_path),
            "docker_preview_boundary": "developer_demo_runtime_preview",
            "product_target": False,
            "prompt": prompt,
            "intent_dispatch": dispatch,
            "activity_feed": activity,
            "record_path": str(record_path),
            "proof": {
                "ok": bool(dispatch.get("proof", {}).get("ok", False)) and record_path.exists(),
                "docker_claims_boot_proof": False,
                "docker_claims_iso_freshness": False,
            },
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Phase 2 local/Docker runtime preview harness")
    parser.add_argument("--workspace", default=os.environ.get("DEFAULT_WORKSPACE", "./workspaces/default"))
    parser.add_argument("--user-root", default=str(_default_user_root()))
    parser.add_argument("--prompt", default="status")
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_preview(args.workspace, args.user_root, args.prompt)
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(json.dumps(payload, ensure_ascii=True))
    return 0 if payload.get("proof", {}).get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

