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

from kernel.vm_integrated_proof import (
    SCHEMA_VERSION,
    build_vm_integrated_proof_foundation,
    validate_vm_integrated_proof_foundation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AgentOS VM integrated proof foundation")
    parser.add_argument("--report-dir", default="./workspaces/default/artifacts")
    parser.add_argument("--snapshot-label", default="current")
    parser.add_argument("--runtime-proof", default="")
    parser.add_argument("--capability-proof", default="")
    parser.add_argument("--intake-proof", default="")
    parser.add_argument("--service-permission-proof", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_vm_integrated_proof_foundation(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        else:
            print("PASS" if result["ok"] else "FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_vm_integrated_proof_foundation(
        report_dir=args.report_dir,
        snapshot_label=args.snapshot_label,
        runtime_proof=args.runtime_proof,
        capability_proof=args.capability_proof,
        intake_proof=args.intake_proof,
        service_permission_proof=args.service_permission_proof,
    )
    errors = validate_vm_integrated_proof_foundation(payload)
    payload["summary"]["ok"] = not errors
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        print(f"Integrated proof: {payload['artifacts']['vm_integrated_proof_foundation_markdown']}")
        print(f"Manifest: {payload['artifacts']['vm_integrated_proof_foundation_json']}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
