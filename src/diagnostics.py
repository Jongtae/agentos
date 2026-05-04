from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from doctor import doctor_report
from io_utils import scrub_payload, write_json_file
from status import status_report
from version import APP_VERSION


def _git_metadata(workspace_dir: Path) -> dict:
    def _run(*args: str) -> tuple[bool, str]:
        try:
            proc = subprocess.run(
                ["git", *args],
                cwd=str(workspace_dir),
                capture_output=True,
                text=True,
                timeout=3,
            )
        except Exception:
            return False, ""
        if proc.returncode != 0:
            return False, ""
        return True, (proc.stdout or "").strip()

    ok, root = _run("rev-parse", "--show-toplevel")
    if not ok or not root:
        return {"is_repo": False, "root": "", "branch": "", "commit": "", "dirty": False}

    _, branch = _run("rev-parse", "--abbrev-ref", "HEAD")
    _, commit = _run("rev-parse", "HEAD")
    _, status = _run("status", "--porcelain")

    return {
        "is_repo": True,
        "root": root,
        "branch": branch,
        "commit": commit,
        "dirty": bool(status),
    }


def snapshot_report(wm) -> dict:
    doctor = doctor_report(wm)
    status = status_report(wm)

    ok = bool(doctor.get("ok", False)) and bool(status.get("ok", False))
    exit_code = 0 if ok else 1

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "app_version": APP_VERSION,
        "workspace": str(wm.workspace_dir),
        "ok": ok,
        "exit_code": exit_code,
        "git": _git_metadata(wm.workspace_dir),
        "browser_runtime": status.get("browser_runtime", {}),
        "approval_counters": status.get("approval_counters", {}),
        "kernel_policy_ready": status.get("kernel_policy_ready", {}),
        "doctor": doctor,
        "status": status,
    }


def run_snapshot(wm) -> int:
    payload = snapshot_report(wm)
    print(json.dumps(scrub_payload(payload), ensure_ascii=True))
    return int(payload["exit_code"])


def write_snapshot_file(output_path: str, payload: dict) -> None:
    write_json_file(output_path, payload)
