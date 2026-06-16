#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DOC="$ROOT_DIR/docs/architecture/inbox-capability-ownership-boundary.md"
INDEX="$ROOT_DIR/docs/index.md"
ROADMAP="$ROOT_DIR/docs/next-roadmap.md"
TASKS="$ROOT_DIR/TASKS.md"

python3 - "$DOC" "$INDEX" "$ROADMAP" "$TASKS" <<'PY'
import sys
from pathlib import Path

doc_path, index_path, roadmap_path, tasks_path = [Path(arg) for arg in sys.argv[1:]]
doc = doc_path.read_text(encoding="utf-8")
index = index_path.read_text(encoding="utf-8")
roadmap = roadmap_path.read_text(encoding="utf-8")
tasks = tasks_path.read_text(encoding="utf-8")

required_sections = [
    "## Owned Intake Paths",
    "## External Read-Only Adapters",
    "## Mutation Blockers",
    "## User-Owned Records",
    "## Activity And Recovery",
    "## Non-Claims",
    "## Exit Condition",
]
for section in required_sections:
    assert section in doc, section

required_terms = [
    "native fixture intake",
    "Maildir intake",
    "normalized inbox intake records",
    "Gmail",
    "Calendar",
    "explicit read-only adapters",
    "Fixture-backed Gmail and Calendar proof",
    "live OAuth",
    "proof",
    "send",
    "delete",
    "archive",
    "redacted proof",
    "user-owned records",
    "browser or app automation as the default inbox path",
    "complete app ecosystem replacement",
]
for term in required_terms:
    assert term in doc, term

assert "docs/architecture/inbox-capability-ownership-boundary.md" in index
assert "inbox-capability-ownership-boundary-epic" in roadmap
assert "[P2-54] Define inbox capability ownership boundary" in tasks
assert "inbox capability ownership boundary epic is active" in tasks
assert "native/local inbox intake" in roadmap
assert "live Gmail and Calendar OAuth" in roadmap
PY

echo "inbox capability ownership boundary smoke: PASS"
