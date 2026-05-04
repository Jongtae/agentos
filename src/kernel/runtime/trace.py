from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class RuntimeTraceEvent:
    timestamp_utc: str
    event: str
    payload: dict


class RuntimeTraceWriter:
    def __init__(self, path: Path, enabled: bool = True, max_bytes: int = 0):
        self._path = Path(path)
        self._enabled = enabled
        self._max_bytes = max(0, int(max_bytes))

    @property
    def path(self) -> Path:
        return self._path

    @property
    def enabled(self) -> bool:
        return self._enabled

    def emit(self, event: str, payload: dict | None = None) -> None:
        if not self._enabled:
            return
        self._rotate_if_needed()
        item = RuntimeTraceEvent(
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            event=event,
            payload=payload or {},
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "timestamp_utc": item.timestamp_utc,
                        "event": item.event,
                        "payload": item.payload,
                    },
                    ensure_ascii=True,
                )
            )
            f.write("\n")

    def _rotate_if_needed(self) -> None:
        if self._max_bytes <= 0:
            return
        if not self._path.exists():
            return
        try:
            if self._path.stat().st_size <= self._max_bytes:
                return
        except Exception:
            return
        archive = self._path.with_suffix(self._path.suffix + ".1")
        try:
            if archive.exists():
                archive.unlink()
            self._path.rename(archive)
        except Exception:
            return


class NoopRuntimeTraceWriter:
    enabled = False

    def emit(self, event: str, payload: dict | None = None) -> None:
        _ = (event, payload)


def approval_counters_from_trace(path: Path) -> dict:
    counters = {
        "requested": 0,
        "approved": 0,
        "denied": 0,
        "blocked": 0,
        "trace_events": 0,
    }
    p = Path(path)
    if not p.exists():
        return counters

    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except Exception:
                continue
            counters["trace_events"] += 1
            event_name = str(event.get("event", ""))
            payload = event.get("payload", {}) or {}
            if event_name == "approval_requested":
                counters["requested"] += 1
            elif event_name == "approval_decision":
                if bool(payload.get("approved", False)):
                    counters["approved"] += 1
                else:
                    counters["denied"] += 1
            elif event_name == "step_blocked":
                counters["blocked"] += 1
    except Exception:
        return counters

    return counters


def approval_anomaly_from_counters(counters: dict) -> dict:
    requested = int(counters.get("requested", 0))
    denied = int(counters.get("denied", 0))
    blocked = int(counters.get("blocked", 0))

    denied_rate_warn = _env_float("AGENTOS_APPROVAL_DENY_RATE_WARN", 0.6)
    denied_min_requested = _env_int("AGENTOS_APPROVAL_DENY_MIN_REQUESTED", 5)
    blocked_warn = _env_int("AGENTOS_APPROVAL_BLOCKED_WARN", 5)

    if requested >= denied_min_requested and requested > 0:
        denied_rate = denied / requested
        if denied_rate >= denied_rate_warn:
            return {
                "anomaly_detected": True,
                "reason": "high_denied_rate",
                "details": f"denied_rate={denied_rate:.2f} requested={requested} denied={denied}",
            }
    if blocked >= blocked_warn:
        return {
            "anomaly_detected": True,
            "reason": "blocked_spike",
            "details": f"blocked={blocked} threshold={blocked_warn}",
        }
    return {"anomaly_detected": False, "reason": "", "details": ""}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except Exception:
        return default



def is_runtime_trace_enabled() -> bool:
    raw = os.environ.get("AGENTOS_ENABLE_RUNTIME_TRACE", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def runtime_trace_max_bytes(default: int = 0) -> int:
    raw = os.environ.get("AGENTOS_RUNTIME_TRACE_MAX_BYTES", "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except Exception:
        return default


def resolve_runtime_trace_path(workspace_dir: Path) -> Path:
    raw = os.environ.get("AGENTOS_RUNTIME_TRACE_FILE", "").strip()
    if raw:
        return Path(raw)
    return Path(workspace_dir) / "artifacts" / "runtime_trace.jsonl"


def build_runtime_trace_writer(workspace_dir: Path):
    enabled = is_runtime_trace_enabled()
    path = resolve_runtime_trace_path(workspace_dir)
    if not enabled:
        return NoopRuntimeTraceWriter()
    return RuntimeTraceWriter(path=path, enabled=True, max_bytes=runtime_trace_max_bytes(0))
