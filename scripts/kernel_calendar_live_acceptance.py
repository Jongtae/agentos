#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from io_utils import scrub_payload

SCHEMA_VERSION = "agentos-calendar-live-acceptance.v1"
STATUS_SCHEMA = "agentos-calendar-readonly-status.v1"
READ_SCHEMA = "agentos-phase2-calendar-fixture.v1"


def build_acceptance_pack(
    *,
    workspace: str | Path,
    status_json: str | Path = "",
    read_json: str | Path = "",
    query: str = "roadmap",
) -> dict:
    workspace_path = Path(workspace).expanduser().resolve()
    status_payload = _load_json(status_json)
    read_payload = _load_json(read_json)

    status_errors = _validate_status(status_payload) if status_payload else ["calendar_status_missing"]
    read_errors = _validate_read(read_payload) if read_payload else ["calendar_read_missing"]
    live_ready = bool(status_payload.get("live_oauth_ready")) if status_payload else False
    read_ok = bool(read_payload.get("proof", {}).get("ok")) if read_payload else False
    read_adapter = str(read_payload.get("adapter", "")) if read_payload else ""
    live_read_observed = live_ready and read_ok and read_adapter == "calendar_oauth_readonly"

    blockers = []
    if not live_read_observed:
        blockers.append(
            {
                "id": "calendar-live-oauth-proof-not-observed",
                "reason": "Live read-only Calendar proof requires user-provided OAuth status and read output.",
                "recovery_action": "Run the future read-only Calendar live adapter in the VM, then rebuild this acceptance pack with sanitized status and read JSON.",
            }
        )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace_path),
        "query": query,
        "inputs": {
            "status_json": str(status_json or ""),
            "read_json": str(read_json or ""),
        },
        "manual_commands": [
            "scripts/agentos-kernelctl phase2-run --message 'status' --json > calendar-status.json",
            "scripts/agentos-kernelctl phase2-run --message 'summarize my calendar roadmap events' --json > calendar-read.json",
            f"python3 scripts/kernel_calendar_live_acceptance.py --status-json calendar-status.json --read-json calendar-read.json --query {query!r} --json",
        ],
        "status_summary": _status_summary(status_payload),
        "read_summary": _read_summary(read_payload),
        "validation": {
            "status_errors": status_errors,
            "read_errors": read_errors,
            "fixture_or_mock_used": read_adapter in {"calendar_fixture", "calendar_oauth_readonly_mock"},
        },
        "blockers": blockers,
        "proof": {
            "ok": live_read_observed,
            "manual_acceptance_pack_completed": True,
            "live_calendar_oauth_completed": live_read_observed,
            "calendar_read_only_scope_required": True,
            "calendar_mutation_executed": False,
            "secrets_redacted": _secrets_redacted(status_payload, read_payload),
        },
    }
    return scrub_payload(payload)


def validate_acceptance_pack(payload: dict, *, require_live: bool = False) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    proof = payload.get("proof") or {}
    if proof.get("manual_acceptance_pack_completed") is not True:
        errors.append("proof.manual_acceptance_pack_completed must be true")
    if proof.get("calendar_mutation_executed") is not False:
        errors.append("proof.calendar_mutation_executed must be false")
    if proof.get("secrets_redacted") is not True:
        errors.append("proof.secrets_redacted must be true")
    if require_live and proof.get("live_calendar_oauth_completed") is not True:
        errors.append("proof.live_calendar_oauth_completed must be true for live signoff")
    return errors


def _load_json(path: str | Path) -> dict:
    if not str(path or "").strip():
        return {}
    target = Path(path).expanduser()
    if not target.exists():
        return {}
    return json.loads(target.read_text(encoding="utf-8"))


def _validate_status(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != STATUS_SCHEMA:
        errors.append(f"status.schema_version must be {STATUS_SCHEMA}")
    if (payload.get("proof") or {}).get("mutation_executed") is not False:
        errors.append("status.proof.mutation_executed must be false")
    return errors


def _validate_read(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != READ_SCHEMA:
        errors.append(f"read.schema_version must be {READ_SCHEMA}")
    if (payload.get("proof") or {}).get("mutation_executed") is not False:
        errors.append("read.proof.mutation_executed must be false")
    return errors


def _status_summary(payload: dict) -> dict:
    if not payload:
        return {"present": False}
    return {
        "present": True,
        "schema_version": payload.get("schema_version", ""),
        "current_route": str(payload.get("current_route", "")),
        "fixture_ready": bool(payload.get("fixture_ready")),
        "live_oauth_ready": bool(payload.get("live_oauth_ready")),
    }


def _read_summary(payload: dict) -> dict:
    if not payload:
        return {"present": False}
    return {
        "present": True,
        "schema_version": payload.get("schema_version", ""),
        "adapter": str(payload.get("adapter", "")),
        "matched_count": int(payload.get("matched_count", 0) or 0),
        "reason": str((payload.get("proof") or {}).get("blocker", "")),
        "event_ids": [str(event.get("id", "")) for event in payload.get("events", []) if isinstance(event, dict)],
    }


def _secrets_redacted(*payloads: dict) -> bool:
    combined = json.dumps(payloads, ensure_ascii=True)
    secret_terms = ("refresh_token", "access_token", "client_secret", "private_key")
    return not any(term in combined for term in secret_terms)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or validate Calendar live read-only manual acceptance pack")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--status-json", default="")
    parser.add_argument("--read-json", default="")
    parser.add_argument("--query", default="roadmap")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--require-live", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_acceptance_pack(payload, require_live=args.require_live)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("calendar live acceptance: PASS" if result["ok"] else "calendar live acceptance: FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_acceptance_pack(
        workspace=args.workspace,
        status_json=args.status_json,
        read_json=args.read_json,
        query=args.query,
    )
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(json.dumps(payload, ensure_ascii=True))
    return 0 if payload.get("proof", {}).get("manual_acceptance_pack_completed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
