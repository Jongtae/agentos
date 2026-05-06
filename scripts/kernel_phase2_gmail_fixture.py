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

SCHEMA_VERSION = "agentos-phase2-gmail-fixture.v1"
MUTATING_ACTIONS = {"send", "delete", "archive"}


def build_gmail_fixture_report(
    fixture_path: str | Path,
    *,
    query: str = "",
    draft_to: str = "",
    draft_subject: str = "",
    action: str = "read",
) -> dict:
    fixture = Path(fixture_path).resolve()
    messages = _load_messages(fixture)
    normalized_query = query.strip().lower()
    selected = [
        message
        for message in messages
        if not normalized_query or normalized_query in _message_search_text(message)
    ]
    summary_lines = [
        f"{message.get('from', 'unknown')} -> {message.get('subject', 'no subject')}: {_preview(message.get('body', ''))}"
        for message in selected[:5]
    ]
    blocked = action in MUTATING_ACTIONS
    draft = {
        "to": draft_to or (selected[0].get("from", "") if selected else ""),
        "subject": draft_subject or (f"Re: {selected[0].get('subject', '')}".strip() if selected else "Re:"),
        "body": _draft_body(selected[0]) if selected else "Thanks. I will review this and follow up.",
        "send_allowed": False,
        "requires_confirmation": True,
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "adapter": "gmail_fixture",
        "oauth_required": False,
        "real_gmail_credentials_used": False,
        "allowed_actions": ["read", "search", "summarize", "draft"],
        "blocked_actions": sorted(MUTATING_ACTIONS),
        "requested_action": action,
        "query": query,
        "matched_count": len(selected),
        "messages": [_public_message(message) for message in selected[:10]],
        "summary": "\n".join(summary_lines),
        "draft": draft,
        "proof": {
            "ok": bool(not blocked and action in {"read", "search", "summarize", "draft"}),
            "blocker": "real_gmail_oauth_not_configured" if not blocked else f"gmail_{action}_requires_confirmation",
            "safe_fixture_mode": True,
        },
    }
    return scrub_payload(payload)


def _load_messages(fixture: Path) -> list[dict]:
    data = json.loads(fixture.read_text(encoding="utf-8"))
    messages = data.get("messages", data if isinstance(data, list) else [])
    if not isinstance(messages, list):
        raise ValueError("fixture must be a list or an object with messages")
    return [message for message in messages if isinstance(message, dict)]


def _message_search_text(message: dict) -> str:
    return " ".join(
        str(message.get(key, ""))
        for key in ("from", "to", "subject", "body", "labels")
    ).lower()


def _public_message(message: dict) -> dict:
    return {
        "id": str(message.get("id", "")),
        "from": str(message.get("from", "")),
        "subject": str(message.get("subject", "")),
        "preview": _preview(message.get("body", "")),
        "labels": message.get("labels", []),
    }


def _preview(text: object, limit: int = 120) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 3] + "..."


def _draft_body(message: dict) -> str:
    sender = str(message.get("from", "there")).split("<", 1)[0].strip() or "there"
    subject = str(message.get("subject", "your note")).strip()
    return "\n".join(
        [
            f"Hi {sender},",
            "",
            f"Thanks for the update on {subject}. I reviewed the context and will follow up with next steps.",
            "",
            "Best,",
            "AgentOS",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Phase 2 Gmail fixture read/search/summarize/draft boundary")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--query", default="")
    parser.add_argument("--draft-to", default="")
    parser.add_argument("--draft-subject", default="")
    parser.add_argument("--action", default="read")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_gmail_fixture_report(
        args.fixture,
        query=args.query,
        draft_to=args.draft_to,
        draft_subject=args.draft_subject,
        action=args.action,
    )
    print(json.dumps(payload, ensure_ascii=True) if args.json else f"gmail fixture: {payload['matched_count']} matched")
    return 0 if payload.get("proof", {}).get("safe_fixture_mode") else 1


if __name__ == "__main__":
    raise SystemExit(main())
