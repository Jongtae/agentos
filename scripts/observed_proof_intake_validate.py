#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT_DIR / "docs" / "architecture" / "observed-proof-intake-schema.json"
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected top-level object")
    return value


def validate_record(record: dict, schema: dict) -> list[str]:
    errors: list[str] = []
    for field in schema.get("required_fields", []):
        if field not in record:
            errors.append(f"missing required field: {field}")

    if record.get("schema_version") != schema.get("schema_version"):
        errors.append("schema_version mismatch")

    if record.get("status") not in set(schema.get("allowed_statuses", [])):
        errors.append("status must be one of: " + ", ".join(schema.get("allowed_statuses", [])))

    observed_at = record.get("observed_at_utc")
    if not isinstance(observed_at, str) or not UTC_RE.match(observed_at):
        errors.append("observed_at_utc must use YYYY-MM-DDTHH:MM:SSZ")

    for field in ("proof_surface", "claim", "observed_by"):
        if not isinstance(record.get(field), str) or not record.get(field, "").strip():
            errors.append(f"{field} must be a non-empty string")

    evidence = record.get("evidence")
    if not isinstance(evidence, list):
        errors.append("evidence must be a list")
        evidence = []
    blockers = record.get("blockers")
    if not isinstance(blockers, list):
        errors.append("blockers must be a list")
        blockers = []
    non_claims = record.get("remaining_non_claims")
    if not isinstance(non_claims, list):
        errors.append("remaining_non_claims must be a list")

    allowed_kinds = set(schema.get("allowed_evidence_kinds", []))
    for idx, item in enumerate(evidence):
        if not isinstance(item, dict):
            errors.append(f"evidence[{idx}] must be an object")
            continue
        if item.get("kind") not in allowed_kinds:
            errors.append(f"evidence[{idx}].kind is not allowed")
        for field in ("path_or_url", "redaction"):
            if not isinstance(item.get(field), str) or not item.get(field, "").strip():
                errors.append(f"evidence[{idx}].{field} must be a non-empty string")

    for idx, item in enumerate(blockers):
        if not isinstance(item, dict):
            errors.append(f"blockers[{idx}] must be an object")
            continue
        for field in ("id", "reason", "recovery_action"):
            if not isinstance(item.get(field), str) or not item.get(field, "").strip():
                errors.append(f"blockers[{idx}].{field} must be a non-empty string")

    if record.get("status") == "observed" and not evidence:
        errors.append("observed records require at least one evidence item")
    if record.get("status") in {"blocked", "rejected"} and not blockers:
        errors.append("blocked or rejected records require at least one blocker")

    lower_text = json.dumps(record, ensure_ascii=True).lower()
    for term in schema.get("secret_terms", []):
        if term.lower() in lower_text:
            errors.append(f"record contains forbidden secret term: {term}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an AgentOS observed proof intake record")
    parser.add_argument("record", help="Path to observed proof record JSON")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="Path to observed proof schema JSON")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation output")
    args = parser.parse_args()

    schema_path = Path(args.schema)
    record_path = Path(args.record)
    try:
        schema = _load_json(schema_path)
        record = _load_json(record_path)
        errors = validate_record(record, schema)
    except ValueError as exc:
        errors = [str(exc)]

    payload = {
        "schema_version": "agentos-observed-proof-intake-validator.v1",
        "record": str(record_path),
        "schema": str(schema_path),
        "ok": not errors,
        "errors": errors,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=True))
    elif errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
    else:
        print("observed proof intake record: PASS")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
