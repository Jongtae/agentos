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

from io_utils import scrub_payload, write_json_file
from kernel.operator_activity import ACTIVITY_SCHEMA_VERSION, build_activity_feed_payload


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != ACTIVITY_SCHEMA_VERSION:
        errors.append(f"schema_version must be {ACTIVITY_SCHEMA_VERSION}")
    if payload.get("capability") != "activity_feed":
        errors.append("capability must be activity_feed")
    if not isinstance(payload.get("activity_feed_ready"), bool):
        errors.append("activity_feed_ready must be a boolean")
    if not isinstance(payload.get("events"), list):
        errors.append("events must be a list")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export human-readable AgentOS operator activity feed")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--limit", default="30")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_payload(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        print(json.dumps(result, ensure_ascii=True) if args.json else ("activity feed: PASS" if result["ok"] else "activity feed: FAIL"))
        return 0 if result["ok"] else 1

    payload = scrub_payload(build_activity_feed_payload(args.workspace, limit=int(args.limit or 30)))
    errors = validate_payload(payload)
    if errors:
        print(json.dumps({"ok": False, "errors": errors, "schema_version": payload.get("schema_version", "")}, ensure_ascii=True))
        return 1
    if args.output:
        write_json_file(args.output, payload)
    if args.json or not args.output:
        print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
