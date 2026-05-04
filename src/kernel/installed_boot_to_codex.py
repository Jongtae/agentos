from __future__ import annotations

import os
from pathlib import Path


INSTALLED_BOOT_TO_CODEX_SCHEMA_VERSION = "agentos-installed-boot-to-codex.v1"


def _read_env_file(path: Path) -> dict[str, str]:
    payload: dict[str, str] = {}
    if not path.exists():
        return payload
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        payload[key.strip()] = value.strip()
    return payload


def build_installed_boot_to_codex_summary(
    *,
    installed_boot: dict,
    primary_runtime: dict,
    runtime_contract: dict,
    next_boot_target: dict,
) -> dict:
    boot_file = Path(str(installed_boot.get("manifest_path", os.environ.get("AGENTOS_INSTALLED_BOOT_FILE", "/tmp/agentos-installed-boot.env"))))
    boot_env = _read_env_file(boot_file)
    evidence_file = Path(os.environ.get("AGENTOS_SLOT_SWITCH_EVIDENCE_FILE", "/tmp/agentos-slot-switch-evidence.env"))
    evidence_env = _read_env_file(evidence_file)
    target_slot = str(next_boot_target.get("target_slot", "") or evidence_env.get("planned_slot", ""))
    observed_slot = evidence_env.get("observed_slot", target_slot)
    managed_session_reachable = all(
        (
            str(installed_boot.get("runtime_target", "")) == "codex_cli_managed_session",
            str(primary_runtime.get("managed_runtime_target", "")) == "codex_cli_managed_session",
            ((runtime_contract.get("continuity_contract") or {}).get("rejoin_target") == "codex_cli_managed_session"),
        )
    )
    proof_ready = bool(installed_boot.get("manifest_exists")) and managed_session_reachable
    return {
        "schema_version": INSTALLED_BOOT_TO_CODEX_SCHEMA_VERSION,
        "installed_origin": str(installed_boot.get("origin", "installed_appliance_boot")),
        "installed_boot_file": str(boot_file),
        "installed_boot_exists": boot_file.exists(),
        "identity_path": list(installed_boot.get("identity_path", [])),
        "runtime_owner": boot_env.get("runtime_owner", str(installed_boot.get("runtime_owner", "codex_cli_managed_session"))),
        "runtime_target": boot_env.get("runtime_target", str(installed_boot.get("runtime_target", "codex_cli_managed_session"))),
        "target_slot": target_slot,
        "observed_slot": observed_slot,
        "slot_switch_evidence_file": str(evidence_file),
        "slot_switch_evidence_exists": evidence_file.exists(),
        "managed_session_reachable": managed_session_reachable,
        "continuity_ready": bool(installed_boot.get("runtime_continuity", False)),
        "next_boot_target": next_boot_target,
        "proof_status": "ready" if proof_ready else "attention",
    }
