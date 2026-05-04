from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path


@dataclass(frozen=True)
class RetentionAction:
    path: str
    reason: str
    age_days: float
    size_bytes: int


def is_path_within_dir(path: Path, root: Path) -> bool:
    p = Path(path).resolve()
    r = Path(root).resolve()
    return r == p or r in p.parents


def plan_trace_retention(
    trace_file: Path,
    retention_days: int,
    keep_archives: int,
    now: datetime | None = None,
) -> list[RetentionAction]:
    base = Path(trace_file)
    if keep_archives < 0:
        keep_archives = 0
    if retention_days < 0:
        retention_days = 0
    if now is None:
        now = datetime.now(timezone.utc)

    archives = [p for p in base.parent.glob(f"{base.name}.*") if p.is_file()]
    archives.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    keep_set = set(archives[:keep_archives])
    actions: list[RetentionAction] = []
    seen: set[Path] = set()

    for item in archives:
        age_days = _age_days(item, now)
        reason = ""
        if item not in keep_set and age_days >= retention_days:
            reason = "older_than_retention_days"
        elif item not in keep_set:
            reason = "exceeds_keep_archives"
        if not reason:
            continue
        if item in seen:
            continue
        seen.add(item)
        actions.append(
            RetentionAction(
                path=str(item),
                reason=reason,
                age_days=age_days,
                size_bytes=item.stat().st_size,
            )
        )

    actions.sort(key=lambda a: a.path)
    return actions


def apply_trace_retention(actions: list[RetentionAction], apply: bool) -> dict:
    deleted = 0
    delete_errors = 0
    for action in actions:
        if not apply:
            continue
        try:
            Path(action.path).unlink(missing_ok=True)
            deleted += 1
        except Exception:
            delete_errors += 1

    return {
        "candidates": len(actions),
        "deleted": deleted,
        "delete_errors": delete_errors,
        "applied": bool(apply),
    }


def _age_days(path: Path, now: datetime) -> float:
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return max(0.0, (now - mtime).total_seconds() / 86400.0)


def retention_policy_from_env(default_days: int = 7, default_keep_archives: int = 1) -> dict:
    return {
        "retention_days": _env_int("AGENTOS_TRACE_RETENTION_DAYS", default_days),
        "keep_archives": _env_int("AGENTOS_TRACE_KEEP_ARCHIVES", default_keep_archives),
    }


def retention_health_summary(
    trace_file: Path,
    retention_days: int,
    keep_archives: int,
    now: datetime | None = None,
) -> dict:
    base = Path(trace_file)
    archives = [p for p in base.parent.glob(f"{base.name}.*") if p.is_file()]
    actions = plan_trace_retention(
        trace_file=base,
        retention_days=retention_days,
        keep_archives=keep_archives,
        now=now,
    )
    oldest_age_days = 0.0
    if archives:
        oldest_age_days = max(_age_days(item, now or datetime.now(timezone.utc)) for item in archives)

    return {
        "policy": {
            "retention_days": int(retention_days),
            "keep_archives": int(keep_archives),
        },
        "archive_count": len(archives),
        "archive_bytes": sum(item.stat().st_size for item in archives),
        "oldest_archive_age_days": round(oldest_age_days, 4),
        "pending_delete_count": len(actions),
        "pending_delete_paths": [a.path for a in actions],
    }


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except Exception:
        return default
    return max(0, value)
