from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

AUDIT_FILE = "autoremediation_override_audit.jsonl"


def append_override_audit_event(
    workspace_dir: Path,
    *,
    event: str,
    decision_status: str,
    reason: str,
    forced: bool,
) -> Path:
    workspace = Path(workspace_dir).resolve()
    path = _audit_file_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "event": str(event),
        "decision_status": str(decision_status),
        "reason": str(reason),
        "forced": bool(forced),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    return path


def override_audit_report(
    *,
    workspace_dir: Path,
    max_recent: int = 5,
) -> dict:
    workspace = Path(workspace_dir).resolve()
    path = _audit_file_path(workspace)
    if not path.exists():
        return {
            "ok": True,
            "audit_file": str(path),
            "event_count": 0,
            "parse_errors": 0,
            "recent_events": [],
        }

    events: list[dict] = []
    parse_errors = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
        except Exception:
            parse_errors += 1
            continue
        if not isinstance(obj, dict):
            parse_errors += 1
            continue
        events.append(obj)

    keep = max(1, int(max_recent))
    return {
        "ok": True,
        "audit_file": str(path),
        "event_count": len(events),
        "parse_errors": parse_errors,
        "recent_events": events[-keep:],
    }


def _audit_file_path(workspace: Path) -> Path:
    return workspace / "artifacts" / AUDIT_FILE
