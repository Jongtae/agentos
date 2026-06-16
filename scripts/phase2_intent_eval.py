#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from kernel.intent_dispatch import classify_intent

DEFAULT_EVAL = ROOT_DIR / "docs" / "acceptance" / "phase2-intent-eval.json"

LEGACY_TO_PHASE2 = {
    "telegram_start": "greeting",
    "telegram_help": "setup_help",
    "greeting": "greeting",
    "runtime_status": "status",
    "local_workspace_search": "workspace_file_request",
    "web_search_summary": "web_search_request",
    "memory_note": "record_lookup",
    "setup_help": "setup_help",
    "gmail_read_or_draft": "gmail_read_or_draft",
    "calendar_readonly": "calendar_readonly",
    "record_lookup": "record_lookup",
    "lifecycle_recovery": "lifecycle_recovery",
    "unknown_needs_clarification": "unknown_or_unsupported",
}


def phase2_intent(prompt: str) -> str:
    result = classify_intent(prompt, source="operator")
    return LEGACY_TO_PHASE2.get(str(result.get("intent", "")), "unknown_or_unsupported")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Phase 2 seed intent classification cases")
    parser.add_argument("--eval-file", default=str(DEFAULT_EVAL))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = json.loads(Path(args.eval_file).read_text(encoding="utf-8"))
    rows = []
    for case in payload.get("cases", []):
        actual = phase2_intent(str(case.get("prompt", "")))
        expected = str(case.get("expected_intent", ""))
        rows.append(
            {
                "id": case.get("id", ""),
                "expected_intent": expected,
                "actual_intent": actual,
                "ok": actual == expected,
            }
        )
    failed = [row for row in rows if not row["ok"]]
    result = {
        "schema_version": "agentos-phase2-intent-eval-result.v1",
        "ok": not failed,
        "case_count": len(rows),
        "failed_count": len(failed),
        "failures": failed,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=True))
    else:
        print("phase2 intent eval: PASS" if result["ok"] else "phase2 intent eval: FAIL")
        if failed:
            for row in failed:
                print(f"- {row['id']}: expected {row['expected_intent']}, got {row['actual_intent']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
