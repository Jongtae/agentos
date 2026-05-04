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

from kernel.policy_maturity import POLICY_LADDER, POLICY_MATURITY_SCHEMA_VERSION, POLICY_TARGET_ORDER, build_policy_maturity_report

REQUIRED_TOP_LEVEL_KEYS = {
    "ok",
    "exit_code",
    "schema_version",
    "workspace",
    "ladder",
    "targets",
    "summary",
    "readiness_baseline",
}


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_TOP_LEVEL_KEYS - set(payload.keys()))
    if missing:
        errors.append(f"missing top-level keys: {', '.join(missing)}")
    if payload.get("schema_version") != POLICY_MATURITY_SCHEMA_VERSION:
        errors.append("schema_version mismatch")
    if payload.get("ladder") != POLICY_LADDER:
        errors.append("ladder mismatch")
    targets = payload.get("targets") or []
    if len(targets) != len(POLICY_TARGET_ORDER):
        errors.append("unexpected target count")
    for item in targets:
        if "policy_target" not in item:
            errors.append("target missing policy_target")
            continue
        for key in (
            "current_level",
            "next_level",
            "readiness_score",
            "recommendation",
            "comparison_status",
            "readiness_inputs",
            "false_positive_tracking",
            "false_deny_tracking",
        ):
            if key not in item:
                errors.append(f"target {item['policy_target']} missing {key}")
        if item.get("current_level") not in POLICY_LADDER:
            errors.append(f"target {item.get('policy_target')} has invalid current_level")
        if item.get("next_level") not in POLICY_LADDER:
            errors.append(f"target {item.get('policy_target')} has invalid next_level")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Build AgentOS policy maturity ladder report")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--policy-dir", default="artifacts/kernel-policy")
    parser.add_argument("--parser-cmd", default="apparmor_parser")
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
            for item in errors:
                print(f"- {item}")
        return 0 if not errors else 1

    payload = build_policy_maturity_report(
        args.workspace,
        policy_dir=args.policy_dir,
        parser_cmd=args.parser_cmd,
    )
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print("AgentOS Policy Maturity Ladder")
        print("==============================")
        print(f"Workspace: {payload['workspace']}")
        print(f"Average readiness score: {payload['summary']['average_readiness_score']}")
        for item in payload["targets"]:
            print(
                f"- {item['policy_target']}: current={item['current_level']} next={item['next_level']} "
                f"score={item['readiness_score']} recommendation={item['recommendation']}"
            )
    return int(payload["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
