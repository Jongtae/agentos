from __future__ import annotations

import os
from pathlib import Path


CODEX_PERSISTENT_STATE_SCHEMA_VERSION = "agentos-codex-persistent-state.v1"


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


def build_codex_persistent_state_summary(
    *,
    state_root_usage: dict,
    runtime_contract: dict,
    install_later: dict,
    installed_boot: dict,
) -> dict:
    state_root = Path(str(state_root_usage.get("state_root", "/var/lib/agentos")))
    manifest_path = Path(str(state_root_usage.get("manifest_path", state_root / "state-layout.env")))
    manifest_env = _read_env_file(manifest_path)
    install_request_path = Path(os.environ.get("AGENTOS_INSTALL_REQUEST_FILE", "/tmp/agentos-install-request.env"))
    install_request_env = _read_env_file(install_request_path)
    installed_boot_path = Path(str(installed_boot.get("manifest_path", os.environ.get("AGENTOS_INSTALLED_BOOT_FILE", "/tmp/agentos-installed-boot.env"))))
    installed_boot_env = _read_env_file(installed_boot_path)

    paths = dict(state_root_usage.get("paths", {}))
    codex_runtime = paths.get("codex_runtime", {})
    codex_session = paths.get("codex_session", {})
    codex_logs = paths.get("codex_logs", {})
    codex_evidence = paths.get("codex_evidence", {})
    continuity_contract = (runtime_contract or {}).get("continuity_contract", {})
    continuity_requested = install_request_env.get("runtime_continuity", "").lower() == "true"
    continuity_observed = installed_boot_env.get("runtime_continuity", "").lower() == "true"
    continuity_ready = all(
        (
            bool(state_root_usage.get("initialized", False)),
            bool(codex_runtime.get("exists", False)),
            bool(codex_session.get("exists", False)),
            bool(codex_logs.get("exists", False)),
            bool(codex_evidence.get("exists", False)),
            continuity_contract.get("rejoin_target") == "codex_cli_managed_session",
        )
    )
    return {
        "schema_version": CODEX_PERSISTENT_STATE_SCHEMA_VERSION,
        "state_root": str(state_root),
        "manifest_path": str(manifest_path),
        "manifest_exists": manifest_path.exists(),
        "manifest_written_by": manifest_env.get("written_by", ""),
        "runtime_owner": "codex_cli_managed_session",
        "runtime_state_paths": {
            "codex_runtime": codex_runtime.get("path", str(state_root / "runtime" / "codex")),
            "codex_session": codex_session.get("path", str(state_root / "runtime" / "codex" / "session")),
            "codex_logs": codex_logs.get("path", str(state_root / "runtime" / "codex" / "logs")),
            "codex_evidence": codex_evidence.get("path", str(state_root / "runtime" / "codex" / "evidence")),
        },
        "runtime_state_paths_ready": all(
            bool(paths.get(name, {}).get("exists", False))
            for name in ("codex_runtime", "codex_session", "codex_logs", "codex_evidence")
        ),
        "runtime_continuity_requested": continuity_requested or install_later.get("available", False),
        "runtime_continuity_observed": continuity_observed or bool(installed_boot.get("available", False)),
        "runtime_continuity_contract": continuity_contract,
        "continuity_ready": continuity_ready,
        "install_request_file": str(install_request_path),
        "install_request_exists": install_request_path.exists(),
        "installed_boot_file": str(installed_boot_path),
        "installed_boot_exists": installed_boot_path.exists(),
        "present_paths": list(state_root_usage.get("present_paths", [])),
        "missing_paths": list(state_root_usage.get("missing_paths", [])),
        "proof_status": "ready" if continuity_ready else "attention",
    }
