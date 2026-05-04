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

from kernel.unified_event_schema import UNIFIED_EVENT_SCHEMA_VERSION, unified_event_schema_contract


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {"schema_version", "base_required_fields", "common_fields", "causal_chain", "provenance", "event_families", "operator_views"}
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != UNIFIED_EVENT_SCHEMA_VERSION:
        errors.append(f"schema_version must be {UNIFIED_EVENT_SCHEMA_VERSION}")
    if not isinstance(payload.get("common_fields"), list) or len(payload.get("common_fields") or []) < 5:
        errors.append("common_fields must be a non-empty list")
    if not isinstance(payload.get("event_families"), list) or len(payload.get("event_families") or []) < 6:
        errors.append("event_families must include the unified families")
    causal = payload.get("causal_chain") or {}
    if not isinstance(causal.get("stable_fields"), list) or "request_id" not in causal.get("stable_fields", []):
        errors.append("causal_chain.stable_fields must include request_id")
    provenance = payload.get("provenance") or {}
    allowed_sources = (((provenance.get("source_contract") or {}).get("allowed_sources")) or [])
    if "broker" not in allowed_sources or "journald" not in allowed_sources:
        errors.append("provenance.source_contract.allowed_sources must include broker and journald")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or validate the AgentOS unified event schema")
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
            print("unified event schema: PASS" if result["ok"] else "unified event schema: FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = unified_event_schema_contract()
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
