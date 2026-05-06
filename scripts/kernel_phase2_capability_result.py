#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "agentos-phase2-capability-result.v1"


def build_result(workspace: str, *, intent: str, capability: str, status: str, output: str = "") -> dict:
    workspace_path = Path(workspace).expanduser().resolve()
    artifacts = workspace_path / "artifacts" / "phase2-capability-results"
    artifacts.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace_path),
        "intent": intent,
        "capability": capability,
        "status": status,
        "needs_confirmation": status == "blocked",
        "user_message": output or f"{capability} {status}",
        "activity_state": "completed" if status == "ok" else status,
        "record": {
            "durable": status == "ok",
            "path": "",
        },
        "recovery": {
            "required": status not in {"ok"},
            "reason": "" if status == "ok" else status,
        },
        "proof": {"ok": status in {"ok", "blocked", "degraded", "failed"}},
    }
    if status == "ok":
        record_path = artifacts / "latest-capability-result.json"
        payload["record"]["path"] = str(record_path)
        record_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a Phase 2 capability result contract sample")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--intent", default="status")
    parser.add_argument("--capability", default="runtime_status")
    parser.add_argument("--status", choices=("ok", "blocked", "degraded", "failed"), default="ok")
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = build_result(args.workspace, intent=args.intent, capability=args.capability, status=args.status, output=args.output)
    print(json.dumps(payload, ensure_ascii=True) if args.json else f"capability result: {payload['status']}")
    return 0 if payload["proof"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

