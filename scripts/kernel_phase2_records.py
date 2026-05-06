#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "agentos-phase2-records.v1"


def append_record(
    user_root: str | Path,
    *,
    title: str,
    body: str,
    source: str = "manual",
    tags: list[str] | None = None,
) -> dict:
    root = Path(user_root).expanduser().resolve()
    records_dir = root / "records"
    records_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": "agentos-phase2-record.v1",
        "id": datetime.now(timezone.utc).strftime("rec-%Y%m%d%H%M%S%f"),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "title": title.strip(),
        "body": body.strip(),
        "source": source.strip() or "manual",
        "tags": [tag.strip() for tag in tags or [] if tag.strip()],
        "secrets_allowed": False,
    }
    with (records_dir / "records.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")
    return _payload(root, "append", [record], query="", ok=True)


def find_records(user_root: str | Path, *, query: str = "", limit: int = 20) -> dict:
    root = Path(user_root).expanduser().resolve()
    records = _read_records(root)
    needle = query.strip().lower()
    if needle:
        records = [
            record
            for record in records
            if needle in " ".join(
                [
                    str(record.get("title", "")),
                    str(record.get("body", "")),
                    str(record.get("source", "")),
                    " ".join(str(tag) for tag in record.get("tags", [])),
                ]
            ).lower()
        ]
    return _payload(root, "find", records[: max(1, limit)], query=query, ok=True)


def _read_records(root: Path) -> list[dict]:
    path = root / "records" / "records.jsonl"
    if not path.exists():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return list(reversed(records))


def _payload(root: Path, action: str, records: list[dict], *, query: str, ok: bool) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "user_data_root": str(root),
        "records_path": str(root / "records" / "records.jsonl"),
        "action": action,
        "query": query,
        "matched_count": len(records),
        "records": records,
        "boundary": {
            "user_owned": True,
            "shared_folder_safe": True,
            "secrets_allowed": False,
            "second_brain_claimed": False,
        },
        "proof": {"ok": ok, "record_lookup_ready": True},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Append or find Phase 2 user-owned records")
    parser.add_argument("--user-root", default="./agentos-data/user")
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--find", action="store_true")
    parser.add_argument("--title", default="")
    parser.add_argument("--body", default="")
    parser.add_argument("--source", default="manual")
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--query", default="")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.append:
        payload = append_record(args.user_root, title=args.title, body=args.body, source=args.source, tags=args.tag)
    else:
        payload = find_records(args.user_root, query=args.query, limit=args.limit)
    print(json.dumps(payload, ensure_ascii=True) if args.json else f"records: {payload['matched_count']} matched")
    return 0 if payload.get("proof", {}).get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
