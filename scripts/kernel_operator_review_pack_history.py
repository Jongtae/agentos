#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "agentos-operator-review-pack-history.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if payload.get("schema_version") != "agentos-operator-review-pack.v1":
        return None
    return payload


def _normalize(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def build_review_pack_history(*, history_dir: str, limit: int = 20) -> dict[str, Any]:
    root = Path(history_dir).resolve()
    entries: list[dict[str, Any]] = []
    if root.exists():
        for path in sorted(root.glob("*.json")):
            payload = _load_json(path)
            if not payload:
                continue
            summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
            entries.append(
                {
                    "path": str(path),
                    "generated_at_utc": str(payload.get("generated_at_utc", "")),
                    "workspace": str(payload.get("workspace", "")),
                    "summary": summary,
                }
            )

    entries.sort(key=lambda item: item.get("generated_at_utc", ""))
    selected = entries[-max(1, int(limit)) :]
    changed_fields: set[str] = set()
    windows: list[dict[str, Any]] = []
    prev_summary: dict[str, Any] | None = None
    for item in selected:
        summary = item["summary"]
        drift: list[str] = []
        if prev_summary is not None:
            for key in sorted(set(prev_summary.keys()) | set(summary.keys())):
                if _normalize(prev_summary.get(key)) != _normalize(summary.get(key)):
                    drift.append(key)
                    changed_fields.add(key)
        windows.append(
            {
                "generated_at_utc": item["generated_at_utc"],
                "path": item["path"],
                "summary": summary,
                "drift_fields": drift,
            }
        )
        prev_summary = summary

    latest_summary = selected[-1]["summary"] if selected else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "history_dir": str(root),
        "summary": {
            "review_pack_count": len(selected),
            "stable": len(changed_fields) == 0,
            "changed_fields": sorted(changed_fields),
            "latest_session_phase": str(latest_summary.get("session_phase", "")),
            "latest_approval_forensic_status": str(latest_summary.get("approval_forensic_status", "")),
            "latest_validation_stable": bool(latest_summary.get("validation_stable", False)) if latest_summary else False,
        },
        "windows": windows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build AgentOS operator review-pack history report")
    parser.add_argument("--history-dir", default="./artifacts/review-pack-history")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_review_pack_history(history_dir=args.history_dir, limit=args.limit)
    text = json.dumps(payload, ensure_ascii=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(text)
        return 0

    summary = payload["summary"]
    print("AgentOS Review Pack History")
    print("===========================")
    print(f"Review packs: {summary['review_pack_count']}")
    print(f"Stable: {summary['stable']}")
    print("Changed fields: " + (", ".join(summary["changed_fields"]) if summary["changed_fields"] else "(none)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
