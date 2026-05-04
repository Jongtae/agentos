from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PolicyExecutionItem:
    action_id: str
    status: str
    reason: str
    command: str
    exit_code: int


def execute_policy_actions(
    actions: list[dict],
    workspace_dir: Path,
    apply: bool,
    max_actions: int = 10,
) -> dict:
    _ = Path(workspace_dir).resolve()
    root = Path(__file__).resolve().parents[3]
    items: list[PolicyExecutionItem] = []
    executed = 0
    would_execute = 0
    skipped = 0
    errors = 0

    for action in actions[: max(0, max_actions)]:
        action_id = str(action.get("id", ""))
        command = str(action.get("recommended_command", "")).strip()
        auto_safe = bool(action.get("auto_safe", False))
        if not command:
            skipped += 1
            items.append(PolicyExecutionItem(action_id, "skipped", "missing_command", command, -1))
            continue
        if not auto_safe:
            skipped += 1
            items.append(PolicyExecutionItem(action_id, "skipped", "not_auto_safe", command, -1))
            continue
        if not _allowed_command(command):
            skipped += 1
            items.append(PolicyExecutionItem(action_id, "skipped", "not_allowlisted", command, -1))
            continue

        if not apply:
            would_execute += 1
            items.append(PolicyExecutionItem(action_id, "would_execute", "dry_run", command, 0))
            continue

        rc = _run_command(command, root)
        if rc == 0:
            executed += 1
            items.append(PolicyExecutionItem(action_id, "executed", "ok", command, rc))
        else:
            errors += 1
            items.append(PolicyExecutionItem(action_id, "error", "non_zero_exit", command, rc))

    return {
        "apply": bool(apply),
        "max_actions": int(max_actions),
        "action_total": len(actions),
        "executed": executed,
        "would_execute": would_execute,
        "skipped": skipped,
        "errors": errors,
        "results": [
            {
                "action_id": item.action_id,
                "status": item.status,
                "reason": item.reason,
                "command": item.command,
                "exit_code": item.exit_code,
            }
            for item in items
        ],
    }


def _allowed_command(command: str) -> bool:
    allowed_prefixes = (
        "python3 scripts/runtime_trace_retention.py",
        "python3 scripts/runtime_governance_report.py",
        "python3 scripts/runtime_policy_actions_report.py",
    )
    return command.startswith(allowed_prefixes)


def _run_command(command: str, cwd: Path) -> int:
    try:
        proc = subprocess.run(
            shlex.split(command),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        return int(proc.returncode)
    except Exception:
        return 1
