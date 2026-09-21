#!/usr/bin/env python3
"""Validate the structural shape of an AgentOS execution-cursor comment."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

MARKER = "<!-- agentos-execution-cursor:v1 -->"
SCHEMA = "agentos-execution-cursor/v1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def parse_cursor_comment(text: str) -> dict[str, Any]:
    _require(text.count(MARKER) == 1, "cursor marker must appear exactly once")
    matches = JSON_BLOCK_RE.findall(text)
    _require(len(matches) == 1, "cursor must contain exactly one fenced json object")
    try:
        cursor = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise ValueError(f"cursor json is invalid: {exc}") from exc
    validate_cursor(cursor)
    return cursor


def validate_cursor(cursor: dict[str, Any]) -> None:
    _require(isinstance(cursor, dict), "cursor must be an object")
    required = {
        "schema", "generation", "epic_issue", "main_sha", "contracts",
        "completed_children", "current", "waiting",
        "owner_validation_pending", "protocol",
    }
    missing = required - set(cursor)
    _require(not missing, f"missing required fields: {sorted(missing)}")
    _require(cursor["schema"] == SCHEMA, "unsupported cursor schema")
    _require(isinstance(cursor["generation"], int) and cursor["generation"] >= 1, "generation must be >= 1")
    _require(isinstance(cursor["epic_issue"], int) and cursor["epic_issue"] > 0, "epic_issue must be positive")
    _require(isinstance(cursor["main_sha"], str) and SHA_RE.fullmatch(cursor["main_sha"]) is not None, "main_sha must be a full lowercase SHA")

    contracts = cursor["contracts"]
    _require(isinstance(contracts, dict) and contracts, "contracts must be a non-empty object")
    for path, sha in contracts.items():
        _require(isinstance(path, str) and path, "contract path must be non-empty")
        _require(isinstance(sha, str) and SHA_RE.fullmatch(sha) is not None, f"invalid contract SHA for {path}")

    completed = cursor["completed_children"]
    _require(isinstance(completed, list) and all(isinstance(x, int) and x > 0 for x in completed), "completed_children must contain positive issue numbers")
    _require(len(completed) == len(set(completed)), "completed_children must be unique")

    current = cursor["current"]
    _require(isinstance(current, list), "current must be a list")
    current_issues = []
    current_prs = []
    for entry in current:
        _require(isinstance(entry, dict), "current entry must be an object")
        for key in ("issue", "pr", "head_sha", "state", "next_action"):
            _require(key in entry, f"current entry missing {key}")
        _require(isinstance(entry["issue"], int) and entry["issue"] > 0, "current issue must be positive")
        _require(isinstance(entry["pr"], int) and entry["pr"] > 0, "current pr must be positive")
        _require(isinstance(entry["head_sha"], str) and SHA_RE.fullmatch(entry["head_sha"]) is not None, "current head_sha must be a full lowercase SHA")
        _require(isinstance(entry["state"], str) and entry["state"].strip(), "current state must be non-empty")
        _require(isinstance(entry["next_action"], str) and entry["next_action"].strip(), "current next_action must be non-empty")
        current_issues.append(entry["issue"])
        current_prs.append(entry["pr"])
    _require(len(current_issues) == len(set(current_issues)), "current issue numbers must be unique")
    _require(len(current_prs) == len(set(current_prs)), "current PR numbers must be unique")
    _require(not (set(completed) & set(current_issues)), "completed and current issues must not overlap")

    waiting = cursor["waiting"]
    _require(isinstance(waiting, list), "waiting must be a list")
    waiting_issues = []
    for entry in waiting:
        _require(isinstance(entry, dict) and {"issue", "waiting_for"}.issubset(entry), "waiting entry requires issue and waiting_for")
        _require(isinstance(entry["issue"], int) and entry["issue"] > 0, "waiting issue must be positive")
        deps = entry["waiting_for"]
        _require(isinstance(deps, list) and all(isinstance(x, int) and x > 0 for x in deps), "waiting_for must contain positive issue numbers")
        _require(len(deps) == len(set(deps)), "waiting_for entries must be unique")
        waiting_issues.append(entry["issue"])
    _require(len(waiting_issues) == len(set(waiting_issues)), "waiting issue numbers must be unique")
    _require(not (set(completed) & set(waiting_issues)), "completed and waiting issues must not overlap")

    pending = cursor["owner_validation_pending"]
    _require(isinstance(pending, list) and all(isinstance(x, str) and x.strip() for x in pending), "owner_validation_pending must be a list of non-empty strings")
    _require(isinstance(cursor["protocol"], dict), "protocol must be an object")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    parse_cursor_comment(args.file.read_text(encoding="utf-8"))
    print("execution cursor valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
