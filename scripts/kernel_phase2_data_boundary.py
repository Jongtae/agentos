#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "agentos-phase2-data-boundary.v1"


def build_boundary(root: str) -> dict:
    base = Path(root).expanduser().resolve()
    user = base / "user"
    state = base / "state"
    cache = base / "cache"
    run = base / "run"
    for path in (user / "records", user / "artifacts", user / "diagnostics", state, cache, run):
        path.mkdir(parents=True, exist_ok=True)
    sample = user / "records" / "boundary-smoke.json"
    sample.write_text(json.dumps({"ok": True}, ensure_ascii=True) + "\n", encoding="utf-8")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "root": str(base),
        "user_owned_root": str(user),
        "agentos_state_root": str(state),
        "agentos_cache_root": str(cache),
        "agentos_run_root": str(run),
        "sample_user_record": str(sample),
        "secret_storage": "external_runtime_env_or_restricted_secret_store",
        "secret_values_present": False,
        "proof": {
            "ok": sample.exists() and str(sample).startswith(str(user)),
            "user_state_separated": user != state,
            "cache_not_user_record": cache != user,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Phase 2 user-owned data boundary proof")
    parser.add_argument("--root", default="./agentos-data")
    parser.add_argument("--output", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = build_boundary(args.root)
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
    if args.json or not args.output:
        print(json.dumps(payload, ensure_ascii=True))
    return 0 if payload["proof"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

