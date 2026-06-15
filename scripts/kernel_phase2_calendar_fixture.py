#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from io_utils import scrub_payload

SCHEMA_VERSION = "agentos-phase2-calendar-fixture.v1"
MUTATING_ACTIONS = {"create", "update", "delete", "invite", "cancel"}


def build_calendar_fixture_report(
    fixture_path: str | Path,
    *,
    query: str = "",
    action: str = "read",
    limit: int = 5,
) -> dict:
    fixture = Path(fixture_path).expanduser().resolve()
    events = _load_events(fixture)
    normalized_query = query.strip().lower()
    selected = [
        event
        for event in events
        if not normalized_query or normalized_query in _event_search_text(event)
    ]
    selected = sorted(selected, key=lambda event: str(event.get("start", "")))[: max(1, int(limit or 5))]
    blocked = action in MUTATING_ACTIONS
    summary_lines = [
        f"{event.get('start', 'unscheduled')} {event.get('title', 'Untitled event')}: {_preview(event.get('description', ''))}"
        for event in selected
    ]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "adapter": "calendar_fixture",
        "oauth_required": False,
        "real_calendar_credentials_used": False,
        "allowed_actions": ["read", "search", "summarize"],
        "blocked_actions": sorted(MUTATING_ACTIONS),
        "requested_action": action,
        "query": query,
        "matched_count": len(selected),
        "events": [_public_event(event) for event in selected],
        "summary": "\n".join(summary_lines),
        "proof": {
            "ok": bool(not blocked and action in {"read", "search", "summarize"}),
            "blocker": "real_calendar_oauth_not_configured" if not blocked else f"calendar_{action}_requires_confirmation",
            "safe_fixture_mode": True,
            "read_only": True,
            "mutation_executed": False,
        },
    }
    return scrub_payload(payload)


def _load_events(fixture: Path) -> list[dict]:
    data = json.loads(fixture.read_text(encoding="utf-8"))
    events = data.get("events", data if isinstance(data, list) else [])
    if not isinstance(events, list):
        raise ValueError("fixture must be a list or an object with events")
    return [event for event in events if isinstance(event, dict)]


def _event_search_text(event: dict) -> str:
    return " ".join(
        str(event.get(key, ""))
        for key in ("id", "title", "description", "location", "attendees")
    ).lower()


def _public_event(event: dict) -> dict:
    return {
        "id": str(event.get("id", "")),
        "title": str(event.get("title", "")),
        "start": str(event.get("start", "")),
        "end": str(event.get("end", "")),
        "location": str(event.get("location", "")),
        "preview": _preview(event.get("description", "")),
        "attendees": event.get("attendees", []),
    }


def _preview(text: object, limit: int = 120) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 3] + "..."


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Phase 2 Calendar fixture read/search/summarize boundary")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--query", default="")
    parser.add_argument("--action", default="read")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_calendar_fixture_report(
        args.fixture,
        query=args.query,
        action=args.action,
        limit=args.limit,
    )
    print(json.dumps(payload, ensure_ascii=True) if args.json else f"calendar fixture: {payload['matched_count']} matched")
    return 0 if payload.get("proof", {}).get("safe_fixture_mode") else 1


if __name__ == "__main__":
    raise SystemExit(main())
