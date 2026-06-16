#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

DOC="docs/architecture/inbox-workflow-promotion-boundary.md"
REGISTRY="docs/architecture/capability-graduation-registry.json"

python3 - "$DOC" "$REGISTRY" <<'PY'
import json
import sys
from pathlib import Path

doc = Path(sys.argv[1]).read_text(encoding="utf-8")
registry = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))

required_doc_terms = [
    "OS-native capabilities",
    "capability-graduation-registry.json",
    "candidate_id",
    "permission level",
    "user-owned records",
    "live proof blocker",
    "browser automation as the default runtime path",
    "send, delete, archive",
    "retention or compliance behavior",
]
for term in required_doc_terms:
    assert term in doc, term

assert registry["schema_version"] == "agentos-capability-graduation-registry.v1"
policy = registry["policy"]
assert policy["browser_is_default"] is False
assert policy["prefer_internal_capability"] is True
assert policy["require_user_owned_records"] is True
assert policy["require_live_proof_before_claim"] is True

candidates = {item["candidate_id"]: item for item in registry["candidates"]}
for candidate_id in [
    "maildir_inbox_intake",
    "gmail_readonly_live",
    "calendar_readonly_live",
    "browser_fallback_observed",
]:
    assert candidate_id in candidates, candidate_id
    candidate = candidates[candidate_id]
    assert candidate["permission_level"], candidate
    assert candidate["data_boundary"], candidate
    assert "exit_condition" in candidate and candidate["exit_condition"], candidate

maildir = candidates["maildir_inbox_intake"]
assert maildir["permission_level"] == "local_read", maildir
assert maildir["safe_mock_available"] is True, maildir
assert maildir["live_proof_required"] is True, maildir

browser = candidates["browser_fallback_observed"]
assert browser["graduation_stage"] == "blocked", browser
assert "observed-proof-record-required" in browser["blockers"], browser
PY

grep -q "inbox-workflow-promotion-boundary.md" docs/index.md
grep -q "broader app/inbox workflow promotion epic is active" TASKS.md
grep -q "broader-app-inbox-workflow-promotion-epic" docs/next-roadmap.md
grep -q "Inbox workflow promotion" README.md

echo "inbox workflow promotion boundary smoke: PASS"
