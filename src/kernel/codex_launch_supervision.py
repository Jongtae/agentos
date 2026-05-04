from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from kernel.engine.base import EngineRunResult


CODEX_LAUNCH_SUPERVISION_SCHEMA_VERSION = "agentos-codex-launch-supervision.v1"


def supervision_state_file(*, state_root: str) -> Path:
    return Path(os.environ.get("AGENTOS_CODEX_SUPERVISION_STATE_FILE", Path(state_root) / "runtime" / "codex-launch-supervision.json"))


def load_supervision_state(*, state_root: str) -> dict:
    state_file = supervision_state_file(state_root=state_root)
    if not state_file.exists():
        return {}
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_supervision_state(*, state_root: str, payload: dict) -> Path:
    state_file = supervision_state_file(state_root=state_root)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return state_file


def update_supervision_state(
    *,
    state_root: str,
    session_origin: str,
    command: str,
    restart_policy: str,
    max_attempts: int,
    cooldown_sec: int,
    run_result: EngineRunResult,
) -> dict:
    previous = load_supervision_state(state_root=state_root)
    previous_attempts = int(previous.get("attempt_count", 0) or 0)
    previous_restarts = int(previous.get("restart_count", 0) or 0)
    failed = not bool(run_result.ok)
    attempt_count = previous_attempts + 1
    restart_count = previous_restarts + (1 if failed and restart_policy == "on_failure" and attempt_count < max_attempts else 0)
    next_action = "none"
    if failed and restart_policy == "on_failure":
        next_action = "restart_codex_cli" if attempt_count < max_attempts else "escalate_to_recovery"
    elif run_result.ok:
        next_action = "continue_managed_session"
    payload = {
        "schema_version": CODEX_LAUNCH_SUPERVISION_SCHEMA_VERSION,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "session_origin": session_origin,
        "command": command,
        "attempt_count": attempt_count,
        "restart_count": restart_count,
        "restart_policy": restart_policy,
        "max_attempts": max_attempts,
        "cooldown_sec": cooldown_sec,
        "last_launch_state": "succeeded" if run_result.ok else "failed",
        "last_error_type": run_result.error_type,
        "last_error_message": run_result.error_message,
        "last_exit_code": run_result.exit_code,
        "next_action": next_action,
    }
    save_supervision_state(state_root=state_root, payload=payload)
    return payload


def build_codex_launch_supervision_summary(
    *,
    state_root: str,
    provider: str,
    engine_status: str,
    restart_policy: str,
    max_attempts: int,
    cooldown_sec: int,
) -> dict:
    state = load_supervision_state(state_root=state_root)
    attempt_count = int(state.get("attempt_count", 0) or 0)
    restart_count = int(state.get("restart_count", 0) or 0)
    last_launch_state = str(state.get("last_launch_state", "not_started") or "not_started")
    last_error_type = str(state.get("last_error_type", "") or "")
    last_error_message = str(state.get("last_error_message", "") or "")
    last_exit_code = state.get("last_exit_code")
    next_action = str(state.get("next_action", "continue_managed_session" if engine_status == "PASS" else "launch_codex_cli") or "")
    failure_class = "none"
    if last_launch_state == "failed":
        failure_class = last_error_type or "launch_failed"
    health_state = "healthy" if provider == "codex" and engine_status == "PASS" else "attention"
    return {
        "schema_version": CODEX_LAUNCH_SUPERVISION_SCHEMA_VERSION,
        "runtime_owner": "codex_cli_managed_session",
        "provider": str(provider or ""),
        "supervision_enabled": True,
        "restart_policy": restart_policy,
        "max_attempts": max_attempts,
        "cooldown_sec": cooldown_sec,
        "state_file": str(supervision_state_file(state_root=state_root)),
        "state_file_exists": supervision_state_file(state_root=state_root).exists(),
        "attempt_count": attempt_count,
        "restart_count": restart_count,
        "last_launch_state": last_launch_state,
        "last_error_type": last_error_type,
        "last_error_message": last_error_message,
        "last_exit_code": last_exit_code,
        "failure_class": failure_class,
        "engine_status": engine_status,
        "health_state": health_state,
        "next_action": next_action,
        "restart_supported": restart_policy == "on_failure",
        "rejoin_target": "codex_cli_managed_session",
        "recovery_target": "codex_runtime_recovery",
    }
