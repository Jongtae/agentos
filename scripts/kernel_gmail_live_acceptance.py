#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kernel_gmail_setup import READ_SCHEMA, STATUS_SCHEMA, validate_payload

SCHEMA_VERSION = "agentos-gmail-live-acceptance.v1"


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

    status_errors = validate_payload(status_payload, STATUS_SCHEMA) if status_payload else ["gmail_status_missing"]
    read_errors = validate_payload(read_payload, READ_SCHEMA) if read_payload else ["gmail_read_missing"]
    live_ready = bool(status_payload.get("live_read_ready")) if status_payload else False
    read_ok = bool(read_payload.get("proof", {}).get("ok")) if read_payload else False
    read_adapter = str(read_payload.get("adapter", "")) if read_payload else ""
    mock_used = read_adapter.endswith("_mock")
    live_read_observed = live_ready and read_ok and read_adapter == "gmail_oauth_readonly"

    blockers = []
    if not live_read_observed:
        blockers.append(
            {
                "id": "gmail-live-oauth-proof-not-observed",
                "reason": "Live read-only Gmail proof requires user-provided OAuth status and read output.",
                "recovery_action": "Run gmail-setup, gmail-status, and gmail-read with read-only OAuth in the VM, then rebuild this acceptance pack with those JSON files.",
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
            "scripts/agentos-kernelctl gmail-setup --serve-http --host 0.0.0.0 --display-host <vm-ip>",
            "scripts/agentos-kernelctl gmail-status --json > gmail-status.json",
            f"scripts/agentos-kernelctl gmail-read --query {query!r} --json > gmail-read.json",
            f"python3 scripts/kernel_gmail_live_acceptance.py --status-json gmail-status.json --read-json gmail-read.json --query {query!r} --json",
        ],
        "status_summary": _status_summary(status_payload),
        "read_summary": _read_summary(read_payload),
        "validation": {
            "status_errors": status_errors,
            "read_errors": read_errors,
            "mock_used": mock_used,
        },
        "blockers": blockers,
        "proof": {
            "ok": live_read_observed,
            "manual_acceptance_pack_completed": True,
            "live_gmail_oauth_completed": live_read_observed,
            "gmail_read_only_scope_required": True,
            "gmail_mutation_executed": False,
            "secrets_redacted": "refresh_token" not in json.dumps({"status": status_payload, "read": read_payload}, ensure_ascii=True),
        },
    }
    return payload


def validate_acceptance_pack(payload: dict, *, require_live: bool = False) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    proof = payload.get("proof") or {}
    if proof.get("manual_acceptance_pack_completed") is not True:
        errors.append("proof.manual_acceptance_pack_completed must be true")
    if proof.get("gmail_mutation_executed") is not False:
        errors.append("proof.gmail_mutation_executed must be false")
    if proof.get("secrets_redacted") is not True:
        errors.append("proof.secrets_redacted must be true")
    if require_live and proof.get("live_gmail_oauth_completed") is not True:
        errors.append("proof.live_gmail_oauth_completed must be true for live signoff")
    return errors


def _load_json(path: str | Path) -> dict:
    if not str(path or "").strip():
        return {}
    target = Path(path).expanduser()
    if not target.exists():
        return {}
    return json.loads(target.read_text(encoding="utf-8"))


def _status_summary(payload: dict) -> dict:
    if not payload:
        return {"present": False}
    return {
        "present": True,
        "schema_version": payload.get("schema_version", ""),
        "live_read_ready": bool(payload.get("live_read_ready")),
        "reason": str((payload.get("proof") or {}).get("reason", "")),
        "credentials_path": str(payload.get("credentials_path", "")),
        "token_path": str(payload.get("token_path", "")),
    }


def _read_summary(payload: dict) -> dict:
    if not payload:
        return {"present": False}
    return {
        "present": True,
        "schema_version": payload.get("schema_version", ""),
        "adapter": str(payload.get("adapter", "")),
        "matched_count": int(payload.get("matched_count", 0) or 0),
        "reason": str((payload.get("proof") or {}).get("reason", "")),
        "message_ids": [str(message.get("id", "")) for message in payload.get("messages", []) if isinstance(message, dict)],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or validate Gmail live read-only manual acceptance pack")
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
            print("gmail live acceptance: PASS" if result["ok"] else "gmail live acceptance: FAIL")
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
