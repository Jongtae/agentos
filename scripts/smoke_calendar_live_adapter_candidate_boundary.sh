#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOC="$ROOT_DIR/docs/architecture/calendar-live-adapter-candidate-boundary.md"
ROADMAP="$ROOT_DIR/docs/next-roadmap.md"
README="$ROOT_DIR/README.md"

python3 - "$DOC" "$ROADMAP" "$README" <<'PY'
from pathlib import Path
import sys

doc = Path(sys.argv[1]).read_text(encoding="utf-8")
roadmap = Path(sys.argv[2]).read_text(encoding="utf-8")
readme = Path(sys.argv[3]).read_text(encoding="utf-8")

required_doc_terms = [
    "Status: Candidate contract, not live proof",
    "`calendar_fixture`",
    "`calendar_oauth_readonly_mock`",
    "`calendar_oauth_readonly`",
    "read-only Calendar scopes",
    "Tokens are stored outside repo files",
    "sanitized observed proof record",
    "`permission.level: external_read`",
    "`proof.live_calendar_oauth_completed: true`",
    "`proof.mutation_executed: false`",
    "creating events",
    "deleting events",
    "inviting attendees",
    "Until then, AgentOS may claim fixture-backed Calendar readiness",
    "but not live Calendar account proof",
]

for term in required_doc_terms:
    assert term in doc, f"missing contract term: {term}"

assert "calendar-live-adapter-candidate-epic" in roadmap
assert ("Active task: P2-76" in roadmap) or ("Completed tasks: P2-76 and P2-77" in roadmap)
assert "live Calendar OAuth requires explicit tester credentials" in roadmap
assert ("Calendar live adapter | Active" in readme) or ("Calendar live adapter | Completed" in readme)
assert "without claiming live OAuth or mutations" in readme

for forbidden in [
    "Calendar mutations are supported",
    "live Calendar proof is complete",
    "production-ready Calendar OAuth",
]:
    combined = "\n".join([doc, roadmap, readme])
    assert forbidden not in combined, f"forbidden live claim found: {forbidden}"
PY

echo "calendar live adapter candidate boundary smoke: PASS"
