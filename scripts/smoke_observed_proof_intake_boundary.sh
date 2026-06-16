#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DOC="$ROOT_DIR/docs/architecture/observed-proof-intake-boundary.md"
INDEX="$ROOT_DIR/docs/index.md"
ROADMAP="$ROOT_DIR/docs/next-roadmap.md"
TASKS="$ROOT_DIR/TASKS.md"
README="$ROOT_DIR/README.md"
RUNNER="$ROOT_DIR/scripts/phase2_golden_demo_runner.py"

python3 - "$DOC" "$INDEX" "$ROADMAP" "$TASKS" "$README" "$RUNNER" <<'PY'
import sys
from pathlib import Path

doc_path, index_path, roadmap_path, tasks_path, readme_path, runner_path = [
    Path(arg) for arg in sys.argv[1:]
]
doc = doc_path.read_text(encoding="utf-8")
index = index_path.read_text(encoding="utf-8")
roadmap = roadmap_path.read_text(encoding="utf-8")
tasks = tasks_path.read_text(encoding="utf-8")
readme = readme_path.read_text(encoding="utf-8")
runner = runner_path.read_text(encoding="utf-8")

required_sections = [
    "## Purpose",
    "## Intake Scope",
    "## Proof Classes",
    "## Required Record Shape",
    "## Storage Boundary",
    "## Runtime Impact",
    "## Epic Exit Condition",
]
for section in required_sections:
    assert section in doc, section

required_terms = [
    "Live credential proof",
    "VM/ISO proof",
    "Release proof",
    "Browser proof",
    "Boot-chain proof",
    "tokens and private content removed",
    "must not flip a proof flag",
    "observed proof record exists",
]
for term in required_terms:
    assert term in doc, term

assert "docs/architecture/observed-proof-intake-boundary.md" in index
assert "observed-proof-intake-and-blocker-handoff-epic" in roadmap
assert "[P2-64] Attach observed proof intake status to phase2 status" in tasks
assert "Completed tasks: P2-62 and P2-63" in roadmap
assert "Observed proof records now use" in tasks
assert "Observed proof intake" in readme
assert "scripts/smoke_observed_proof_intake_boundary.sh" in runner
assert "live credential, VM/ISO, release, browser, and boot-chain proof" in roadmap
assert "agentos-observed-proof-intake-status.v1" in tasks
PY

echo "observed proof intake boundary smoke: PASS"
