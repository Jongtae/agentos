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

from kernel.mediation_taxonomy import SCHEMA_VERSION, build_mediation_taxonomy


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "workspace",
        "origin_models",
        "mediation_classes",
        "execution_classes",
        "summary",
    }
    missing = sorted(required - set(payload.keys()))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not isinstance(payload.get("mediation_classes"), list) or not payload.get("mediation_classes"):
        errors.append("mediation_classes must be a non-empty list")
    if not isinstance(payload.get("execution_classes"), list) or not payload.get("execution_classes"):
        errors.append("execution_classes must be a non-empty list")
    if not isinstance(payload.get("origin_models"), dict):
        errors.append("origin_models must be an object")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Build AgentOS mediation taxonomy report")
    parser.add_argument("--workspace", default="./workspaces/default")
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
            print("mediation taxonomy: PASS" if result["ok"] else "mediation taxonomy: FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_mediation_taxonomy(workspace=args.workspace)
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

    print("AgentOS Mediation Taxonomy")
    print("==========================")
    print(f"Workspace: {payload['workspace']}")
    print(f"Execution classes: {payload['summary']['execution_class_count']}")
    for item in payload["execution_classes"]:
        print(
            f"- {item['class_name']}: origin={item['origin_model']} "
            f"requirement={item['mediation_requirement']} target={item['target_state']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
