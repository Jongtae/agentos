#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

REQUIRED_TOP = ("timestamp_utc", "event", "payload")


def _parse_ts(raw: str) -> datetime:
    # accepts e.g. 2026-01-01T00:00:00Z or +00:00
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return datetime.fromisoformat(raw)


def validate_trace(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"trace file not found: {path}"

    prev_ts: datetime | None = None
    for idx, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception as e:
            return False, f"line {idx}: invalid json ({e})"

        for key in REQUIRED_TOP:
            if key not in obj:
                return False, f"line {idx}: missing field '{key}'"

        if not isinstance(obj.get("payload"), dict):
            return False, f"line {idx}: payload must be object"

        ts_raw = str(obj.get("timestamp_utc", ""))
        try:
            ts = _parse_ts(ts_raw)
        except Exception:
            return False, f"line {idx}: invalid timestamp_utc '{ts_raw}'"

        if prev_ts and ts < prev_ts:
            return False, f"line {idx}: timestamp out of order"
        prev_ts = ts

    return True, "runtime trace validation: PASS"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_runtime_trace.py <trace.jsonl>")
        return 2
    path = Path(sys.argv[1])
    ok, msg = validate_trace(path)
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
