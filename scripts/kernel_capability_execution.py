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

from kernel.control_plane_capabilities import EXECUTION_OWNERSHIP_SCHEMA, build_execution_ownership_report


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != EXECUTION_OWNERSHIP_SCHEMA:
        errors.append(f"schema_version must be {EXECUTION_OWNERSHIP_SCHEMA}")
    if not isinstance(payload.get("sampled_execution_paths"), list):
        errors.append("sampled_execution_paths must be a list")
    summary = payload.get("summary") or {}
    if "native_capability_handler_count" not in summary:
        errors.append("summary.native_capability_handler_count must be present")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AgentOS capability execution ownership report")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--sample-file", action="append", default=[])
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
            print("capability execution: PASS" if result["ok"] else "capability execution: FAIL")
        return 0 if result["ok"] else 1

    samples = []
    for sample_file in args.sample_file:
        sample_path = Path(sample_file)
        if sample_path.exists():
            samples.append(json.loads(sample_path.read_text(encoding="utf-8")))
    payload = build_execution_ownership_report(args.workspace, samples=samples)
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
