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

from kernel.capability_substrate import build_web_access_report

SCHEMA_VERSION = "agentos-phase2-browser-fallback-contract.v1"
CONTRACT_ARTIFACT = "latest-browser-fallback-contract.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _route_for_request(web_report: dict, *, repeated_pattern: bool) -> tuple[str, str, str]:
    proof = web_report.get("proof") if isinstance(web_report.get("proof"), dict) else {}
    reason = str(proof.get("reason", "") or web_report.get("escalation_reason", ""))
    selected_path = str(proof.get("selected_path", ""))
    if web_report.get("native_handled"):
        return ("internal_capability", "native_web_access_available", "web_access")
    if reason in {"domain_not_allowed", "invalid_url"}:
        return ("blocked_external_state", reason, "")
    if selected_path == "browser_escalated" or web_report.get("escalated_handled"):
        if repeated_pattern:
            return ("graduate_to_capability", str(web_report.get("escalation_reason", "browser_fallback_required")), "future_internal_capability")
        return ("allowed_browser_fallback", str(web_report.get("escalation_reason", "browser_fallback_required")), "browser_fallback")
    return ("blocked_external_state", reason or "unsupported_or_deferred", "")


def build_contract(
    workspace: str | Path,
    *,
    url: str,
    allow_domains: list[str] | None = None,
    requires_authentication: bool = False,
    interactive: bool = False,
    compatibility_required: bool = False,
    repeated_pattern: bool = False,
    write_manifest: bool = True,
) -> dict:
    workspace_path = Path(workspace).resolve()
    workspace_path.mkdir(parents=True, exist_ok=True)
    web_report = build_web_access_report(
        workspace_path,
        url,
        domain_allowlist=allow_domains or None,
        requires_authentication=requires_authentication,
        interactive=interactive,
        compatibility_required=compatibility_required,
        write_manifest=True,
    )
    route, reason, target = _route_for_request(web_report, repeated_pattern=repeated_pattern)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "workspace": str(workspace_path),
        "request": {
            "url": url,
            "allow_domains": list(allow_domains or []),
            "requires_authentication": bool(requires_authentication),
            "interactive": bool(interactive),
            "compatibility_required": bool(compatibility_required),
            "repeated_pattern": bool(repeated_pattern),
        },
        "routing": {
            "decision": route,
            "reason": reason,
            "target": target,
            "internal_capability_preferred": True,
            "browser_is_default": False,
        },
        "web_access": web_report,
        "graduation": {
            "candidate": route == "graduate_to_capability",
            "reason": "repeated browser fallback should become an internal AgentOS capability" if route == "graduate_to_capability" else "",
        },
        "proof": {
            "ok": route in {"internal_capability", "allowed_browser_fallback", "graduate_to_capability", "blocked_external_state"},
            "contract_only": True,
            "live_browser_executed": False,
            "third_party_auth_used": False,
            "internal_capability_preferred": True,
            "browser_default_blocked": True,
        },
        "blockers": _blockers(route, reason),
        "artifacts": {},
    }
    if write_manifest:
        artifact_dir = workspace_path / "artifacts" / "phase2-browser-fallback"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        manifest = artifact_dir / CONTRACT_ARTIFACT
        manifest.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
        payload["artifacts"]["latest_browser_fallback_contract_json"] = str(manifest)
    return payload


def _blockers(route: str, reason: str) -> list[dict]:
    if route != "blocked_external_state":
        return []
    return [
        {
            "id": "browser-fallback-blocked",
            "reason": reason or "external_state_required",
            "recovery_action": "Use an internal capability, add an explicit allow-domain, or create a credential-backed proof task.",
        }
    ]


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    routing = payload.get("routing") if isinstance(payload.get("routing"), dict) else {}
    if routing.get("decision") not in {"internal_capability", "allowed_browser_fallback", "blocked_external_state", "graduate_to_capability"}:
        errors.append("routing.decision is invalid")
    if routing.get("internal_capability_preferred") is not True:
        errors.append("routing.internal_capability_preferred must be true")
    if routing.get("browser_is_default") is not False:
        errors.append("routing.browser_is_default must be false")
    proof = payload.get("proof") if isinstance(payload.get("proof"), dict) else {}
    if proof.get("live_browser_executed") is not False:
        errors.append("proof.live_browser_executed must be false")
    if proof.get("third_party_auth_used") is not False:
        errors.append("proof.third_party_auth_used must be false")
    if proof.get("browser_default_blocked") is not True:
        errors.append("proof.browser_default_blocked must be true")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the Phase 2 browser fallback routing contract")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--url", default="https://example.com")
    parser.add_argument("--allow-domain", action="append", default=[])
    parser.add_argument("--requires-authentication", action="store_true")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--compatibility-required", action="store_true")
    parser.add_argument("--repeated-pattern", action="store_true")
    parser.add_argument("--validate", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.validate:
        payload = json.loads(Path(args.validate).read_text(encoding="utf-8"))
        errors = validate_payload(payload)
        result = {"ok": not errors, "errors": errors, "schema_version": payload.get("schema_version", "")}
        print(json.dumps(result, ensure_ascii=True) if args.json else ("PASS" if result["ok"] else "FAIL"))
        return 0 if result["ok"] else 1

    payload = build_contract(
        args.workspace,
        url=args.url,
        allow_domains=args.allow_domain,
        requires_authentication=args.requires_authentication,
        interactive=args.interactive,
        compatibility_required=args.compatibility_required,
        repeated_pattern=args.repeated_pattern,
    )
    print(json.dumps(payload, ensure_ascii=True) if args.json else f"browser fallback route: {payload['routing']['decision']}")
    return 0 if payload.get("proof", {}).get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
