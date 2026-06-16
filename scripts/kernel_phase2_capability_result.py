#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "agentos-phase2-capability-result.v1"
ROOT_DIR = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT_DIR / "docs" / "architecture" / "capability-permission-registry.json"


def load_permission_registry(path: str | Path = REGISTRY_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


PERMISSION_REGISTRY = load_permission_registry()
PERMISSION_LEVELS = tuple(PERMISSION_REGISTRY["permission_levels"])
OUTCOMES = tuple(PERMISSION_REGISTRY["outcomes"])
DEFAULT_PERMISSION_BY_CAPABILITY = {
    capability: str(declaration.get("permission_level", "unsupported"))
    for capability, declaration in (PERMISSION_REGISTRY.get("capabilities") or {}).items()
    if isinstance(declaration, dict)
}


def _default_permission(capability: str) -> str:
    fallback = str((PERMISSION_REGISTRY.get("defaults") or {}).get("unknown_capability_permission_level", "unsupported"))
    return DEFAULT_PERMISSION_BY_CAPABILITY.get(capability, fallback)


def _default_outcome(status: str, permission_level: str, requires_setup: bool) -> str:
    if status == "ok":
        return "completed"
    if requires_setup:
        return "blocked_needs_setup"
    if permission_level in {"external_write_confirmed", "lifecycle_confirmed"}:
        return "blocked_needs_confirmation"
    if permission_level in {"destructive_blocked", "unsupported"}:
        return "blocked_unsupported"
    return "failed_recoverable"


def _default_recovery_reason(outcome: str, permission_level: str) -> str:
    if outcome == "completed":
        return ""
    if outcome == "blocked_needs_setup":
        return "required setup or credentials are missing"
    if outcome == "blocked_needs_confirmation":
        return f"{permission_level} requires explicit user confirmation"
    if outcome == "blocked_unsupported":
        return f"{permission_level} is not executable in this Phase 2 slice"
    return "capability failed but can be retried or repaired"


def build_result(
    workspace: str,
    *,
    intent: str,
    capability: str,
    status: str,
    output: str = "",
    permission_level: str = "",
    outcome: str = "",
    requires_setup: bool = False,
) -> dict:
    workspace_path = Path(workspace).expanduser().resolve()
    artifacts = workspace_path / "artifacts" / "phase2-capability-results"
    artifacts.mkdir(parents=True, exist_ok=True)
    permission_level = permission_level or _default_permission(capability)
    outcome = outcome or _default_outcome(status, permission_level, requires_setup)
    needs_confirmation = outcome == "blocked_needs_confirmation"
    blocked = outcome.startswith("blocked_")
    recovery_reason = _default_recovery_reason(outcome, permission_level)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace_path),
        "intent": intent,
        "capability": capability,
        "status": status,
        "permission": {
            "level": permission_level,
            "requires_setup": requires_setup,
            "needs_confirmation": needs_confirmation,
            "secret_material_redacted": True,
        },
        "outcome": outcome,
        "needs_confirmation": needs_confirmation,
        "user_message": output or f"{capability} {status}",
        "activity_state": "completed" if status == "ok" else status,
        "record": {
            "durable": outcome == "completed" or permission_level == "safe_write_user_owned",
            "path": "",
            "includes_permission": True,
            "secrets_included": False,
        },
        "recovery": {
            "required": outcome != "completed",
            "reason": recovery_reason,
        },
        "proof": {
            "ok": status in {"ok", "blocked", "degraded", "failed"},
            "permission_checked": permission_level in PERMISSION_LEVELS,
            "outcome_checked": outcome in OUTCOMES,
            "registry_checked": capability in DEFAULT_PERMISSION_BY_CAPABILITY or permission_level == "unsupported",
            "blocked": blocked,
            "secrets_redacted": True,
        },
    }
    if payload["record"]["durable"]:
        record_path = artifacts / "latest-capability-result.json"
        payload["record"]["path"] = str(record_path)
        record_path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a Phase 2 capability result contract sample")
    parser.add_argument("--workspace", default="./workspaces/default")
    parser.add_argument("--intent", default="status")
    parser.add_argument("--capability", default="runtime_status")
    parser.add_argument("--status", choices=("ok", "blocked", "degraded", "failed"), default="ok")
    parser.add_argument("--permission-level", choices=PERMISSION_LEVELS, default="")
    parser.add_argument("--outcome", choices=OUTCOMES, default="")
    parser.add_argument("--requires-setup", action="store_true")
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = build_result(
        args.workspace,
        intent=args.intent,
        capability=args.capability,
        status=args.status,
        output=args.output,
        permission_level=args.permission_level,
        outcome=args.outcome,
        requires_setup=args.requires_setup,
    )
    print(json.dumps(payload, ensure_ascii=True) if args.json else f"capability result: {payload['status']}")
    return 0 if payload["proof"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
