#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]

SCHEMA_VERSION = "agentos-codex-execution-window-discipline.v1"


def build_payload() -> dict:
    agents = (ROOT_DIR / "AGENTS.md").read_text(encoding="utf-8")
    phase_closeout = (ROOT_DIR / ".codex" / "checklists" / "phase-closeout.md").read_text(encoding="utf-8")
    task_closeout = (ROOT_DIR / ".codex" / "checklists" / "task-closeout.md").read_text(encoding="utf-8")
    phase_start = (ROOT_DIR / ".codex" / "prompts" / "phase-start.md").read_text(encoding="utf-8")
    task_start = (ROOT_DIR / ".codex" / "prompts" / "task-start.md").read_text(encoding="utf-8")
    checks = {
        "agents_runtime_impact_statement": "runtime impact statement" in agents,
        "agents_runtime_proof_completed": "runtime proof completed" in agents,
        "phase_closeout_runtime_proof": "Runtime proof completed" in phase_closeout,
        "task_closeout_runtime_proof": "Runtime proof completed" in task_closeout,
        "phase_start_runtime_impact": "runtime impact statement" in phase_start,
        "task_start_runtime_impact": "runtime impact statement" in task_start,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "checks": checks,
        "ok": all(checks.values()),
    }


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    checks = payload.get("checks", {})
    for key in (
        "agents_runtime_impact_statement",
        "agents_runtime_proof_completed",
        "phase_closeout_runtime_proof",
        "task_closeout_runtime_proof",
        "phase_start_runtime_impact",
        "task_start_runtime_impact",
    ):
        if checks.get(key) is not True:
            errors.append(f"checks.{key} must be true")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or validate runtime-first execution window discipline")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_payload(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        print(json.dumps(result, ensure_ascii=True) if args.json else ("PASS" if result["ok"] else "FAIL"))
        if not args.json and errors:
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_payload()
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
