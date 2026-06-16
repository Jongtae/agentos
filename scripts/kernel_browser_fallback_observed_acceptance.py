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

from kernel_phase2_browser_fallback_contract import SCHEMA_VERSION as CONTRACT_SCHEMA
from kernel_phase2_browser_fallback_contract import validate_payload as validate_contract
from observed_proof_intake_validate import DEFAULT_SCHEMA, _load_json, validate_record

SCHEMA_VERSION = "agentos-browser-fallback-observed-acceptance.v1"
SECRET_TERMS = ("access_token", "refresh_token", "client_secret", "bot_token", "api_key", "password")


def build_acceptance_pack(
    *,
    workspace: str | Path,
    contract_json: str | Path = "",
    observed_proof_json: str | Path = "",
    target_url: str = "https://example.com/app",
) -> dict:
    workspace_path = Path(workspace).expanduser().resolve()
    contract_payload = _load_optional_json(contract_json)
    observed_payload = _load_optional_json(observed_proof_json)

    contract_errors = validate_contract(contract_payload) if contract_payload else ["browser_fallback_contract_missing"]
    observed_errors = _validate_observed_record(observed_payload) if observed_payload else ["observed_proof_record_missing"]
    contract_decision = str((contract_payload.get("routing") or {}).get("decision", "")) if contract_payload else ""
    observed_browser_fallback = _observed_browser_fallback(observed_payload)
    observed_completed = (
        contract_decision in {"allowed_browser_fallback", "graduate_to_capability"}
        and not contract_errors
        and not observed_errors
        and observed_browser_fallback
    )

    blockers = []
    if not observed_completed:
        blockers.append(
            {
                "id": "browser-fallback-observed-proof-not-attached",
                "reason": "Observed browser fallback proof requires a user-approved browser session and a sanitized observed proof record.",
                "recovery_action": "Run the browser fallback manually with explicit user approval, save a sanitized observed proof record, then rebuild this acceptance pack with --observed-proof-json.",
            }
        )
    if contract_decision == "blocked_external_state":
        blockers.append(
            {
                "id": "browser-fallback-contract-blocked",
                "reason": str(((contract_payload.get("blockers") or [{}])[0]).get("reason", "external_state_required")),
                "recovery_action": "Use an allowed domain, an internal capability, or a separate credential-backed task before claiming browser fallback proof.",
            }
        )

    combined_inputs = {"contract": contract_payload, "observed": observed_payload}
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace_path),
        "target_url": target_url,
        "inputs": {
            "contract_json": str(contract_json or ""),
            "observed_proof_json": str(observed_proof_json or ""),
        },
        "manual_commands": [
            "python3 scripts/kernel_phase2_browser_fallback_contract.py --workspace <workspace> --url <url> --allow-domain <domain> --interactive --json > browser-contract.json",
            "Record a sanitized agentos-observed-proof-intake.v1 record after a user-approved browser fallback run.",
            "python3 scripts/observed_proof_intake_validate.py observed-browser-proof.json --json",
            "python3 scripts/kernel_browser_fallback_observed_acceptance.py --contract-json browser-contract.json --observed-proof-json observed-browser-proof.json --json",
        ],
        "contract_summary": _contract_summary(contract_payload),
        "observed_summary": _observed_summary(observed_payload),
        "validation": {
            "contract_errors": contract_errors,
            "observed_errors": observed_errors,
            "observed_browser_fallback": observed_browser_fallback,
        },
        "blockers": blockers,
        "proof": {
            "ok": observed_completed,
            "manual_acceptance_pack_completed": True,
            "live_browser_fallback_completed": observed_completed,
            "user_approved_browser_session_required": True,
            "browser_mutation_executed": False,
            "browser_is_default": False,
            "internal_capability_preferred": True,
            "contract_only_without_observed": not observed_completed,
            "secrets_redacted": _secrets_redacted(combined_inputs),
        },
    }
    return payload


def validate_acceptance_pack(payload: dict, *, require_observed: bool = False) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    proof = payload.get("proof") or {}
    if proof.get("manual_acceptance_pack_completed") is not True:
        errors.append("proof.manual_acceptance_pack_completed must be true")
    if proof.get("browser_mutation_executed") is not False:
        errors.append("proof.browser_mutation_executed must be false")
    if proof.get("browser_is_default") is not False:
        errors.append("proof.browser_is_default must be false")
    if proof.get("internal_capability_preferred") is not True:
        errors.append("proof.internal_capability_preferred must be true")
    if proof.get("secrets_redacted") is not True:
        errors.append("proof.secrets_redacted must be true")
    if require_observed and proof.get("live_browser_fallback_completed") is not True:
        errors.append("proof.live_browser_fallback_completed must be true for observed signoff")
    return errors


def _load_optional_json(path: str | Path) -> dict:
    if not str(path or "").strip():
        return {}
    target = Path(path).expanduser()
    if not target.exists():
        return {}
    return json.loads(target.read_text(encoding="utf-8"))


def _validate_observed_record(payload: dict) -> list[str]:
    if not payload:
        return ["observed_proof_record_missing"]
    schema = _load_json(DEFAULT_SCHEMA)
    return validate_record(payload, schema)


def _observed_browser_fallback(payload: dict) -> bool:
    if not payload:
        return False
    surface = str(payload.get("proof_surface", "")).lower()
    claim = str(payload.get("claim", "")).lower()
    status = str(payload.get("status", "")).lower()
    return status == "observed" and "browser" in surface and "fallback" in claim


def _contract_summary(payload: dict) -> dict:
    if not payload:
        return {"present": False}
    routing = payload.get("routing") if isinstance(payload.get("routing"), dict) else {}
    proof = payload.get("proof") if isinstance(payload.get("proof"), dict) else {}
    return {
        "present": True,
        "schema_version": payload.get("schema_version", ""),
        "decision": str(routing.get("decision", "")),
        "reason": str(routing.get("reason", "")),
        "browser_is_default": bool(routing.get("browser_is_default")),
        "live_browser_executed": bool(proof.get("live_browser_executed")),
    }


def _observed_summary(payload: dict) -> dict:
    if not payload:
        return {"present": False}
    return {
        "present": True,
        "schema_version": payload.get("schema_version", ""),
        "proof_surface": str(payload.get("proof_surface", "")),
        "claim": str(payload.get("claim", "")),
        "status": str(payload.get("status", "")),
        "evidence_count": len(payload.get("evidence", []) if isinstance(payload.get("evidence"), list) else []),
    }


def _secrets_redacted(payload: dict) -> bool:
    combined = json.dumps(payload, ensure_ascii=True).lower()
    return not any(term in combined for term in SECRET_TERMS)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or validate browser fallback observed proof acceptance pack")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--contract-json", default="")
    parser.add_argument("--observed-proof-json", default="")
    parser.add_argument("--target-url", default="https://example.com/app")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--require-observed", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_acceptance_pack(payload, require_observed=args.require_observed)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print("browser fallback observed acceptance: PASS" if result["ok"] else "browser fallback observed acceptance: FAIL")
            for error in errors:
                print(f"- {error}")
        return 0 if result["ok"] else 1

    payload = build_acceptance_pack(
        workspace=args.workspace,
        contract_json=args.contract_json,
        observed_proof_json=args.observed_proof_json,
        target_url=args.target_url,
    )
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(json.dumps(payload, ensure_ascii=True))
    return 0 if payload.get("proof", {}).get("manual_acceptance_pack_completed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
