#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DOC="$ROOT_DIR/docs/architecture/capability-graduation-registry.md"
REGISTRY="$ROOT_DIR/docs/architecture/capability-graduation-registry.json"
INDEX="$ROOT_DIR/docs/index.md"
ROADMAP="$ROOT_DIR/docs/next-roadmap.md"
TASKS="$ROOT_DIR/TASKS.md"
README="$ROOT_DIR/README.md"
RUNNER="$ROOT_DIR/scripts/phase2_golden_demo_runner.py"

python3 - "$DOC" "$REGISTRY" "$INDEX" "$ROADMAP" "$TASKS" "$README" "$RUNNER" <<'PY'
import json
import sys
from pathlib import Path

doc_path, registry_path, index_path, roadmap_path, tasks_path, readme_path, runner_path = [
    Path(arg) for arg in sys.argv[1:]
]
doc = doc_path.read_text(encoding="utf-8")
registry = json.loads(registry_path.read_text(encoding="utf-8"))
index = index_path.read_text(encoding="utf-8")
roadmap = roadmap_path.read_text(encoding="utf-8")
tasks = tasks_path.read_text(encoding="utf-8")
readme = readme_path.read_text(encoding="utf-8")
runner = runner_path.read_text(encoding="utf-8")

for section in [
    "## Purpose",
    "## Graduation Criteria",
    "## Registry Contract",
    "## Seed Candidates",
    "## Non-Claims",
    "## Exit Condition",
]:
    assert section in doc, section

assert registry["schema_version"] == "agentos-capability-graduation-registry.v1"
assert registry["policy"]["browser_is_default"] is False
assert registry["policy"]["prefer_internal_capability"] is True
assert registry["policy"]["require_live_proof_before_claim"] is True

candidates = registry["candidates"]
assert len(candidates) >= 5
ids = {candidate["candidate_id"] for candidate in candidates}
for expected in {
    "calendar_readonly_live",
    "gmail_readonly_live",
    "web_research_brief",
    "browser_fallback_observed",
    "maildir_inbox_intake",
}:
    assert expected in ids, expected

for candidate in candidates:
    for field in [
        "candidate_id",
        "source_pattern",
        "target_capability",
        "current_route",
        "graduation_stage",
        "permission_level",
        "data_boundary",
        "safe_mock_available",
        "live_proof_required",
        "blockers",
        "exit_condition",
    ]:
        assert field in candidate, (candidate, field)
    assert candidate["permission_level"] in {
        "safe_read",
        "local_read",
        "external_read",
        "external_interactive",
    }
    assert isinstance(candidate["blockers"], list)

assert any(candidate["graduation_stage"] == "internal_capability" for candidate in candidates)
assert any(candidate["graduation_stage"] == "blocked" for candidate in candidates)
assert "production app ecosystem replacement" in doc
assert "docs/architecture/capability-graduation-registry.md" in index
assert "docs/architecture/capability-graduation-registry.json" in index
assert "capability-graduation-registry-epic" in roadmap
assert "The capability graduation registry epic is closed" in tasks
assert "Completed tasks: P2-66 and P2-67" in roadmap
assert "| Capability graduation registry | Completed |" in readme
assert "scripts/smoke_capability_graduation_registry.sh" in runner
PY

echo "capability graduation registry smoke: PASS"
