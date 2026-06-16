#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DOC="$ROOT_DIR/docs/operations/public-preview-operations.md"
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
    "## Public Preview Contract",
    "## Automated Local Proof",
    "## Manual Proof Blockers",
    "## Non-Claims",
    "## Promotion Gate",
    "## Exit Condition",
]
for section in required_sections:
    assert section in doc, section

required_terms = [
    "Docker remains a developer/demo runtime preview",
    "not the product target",
    "live Gmail OAuth",
    "live Calendar OAuth",
    "live Telegram receiver proof",
    "live browser fallback proof",
    "VM/ISO boot",
    "live updater",
    "production operating system readiness",
    "boot ownership",
    "cleanup policy",
    "unobserved proof",
]
for term in required_terms:
    assert term in doc, term

assert "docs/operations/public-preview-operations.md" in index
assert "public-preview-operations-epic" in roadmap
assert "[P2-48] Add public preview smoke to golden runner" in tasks
assert "public preview operations epic is active" in tasks
assert "scripts/smoke_public_preview_operations.sh" in (
    Path("scripts/phase2_golden_demo_runner.py").read_text(encoding="utf-8")
)
PY

echo "public preview operations smoke: PASS"
