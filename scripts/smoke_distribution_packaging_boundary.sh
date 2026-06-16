#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DOC="$ROOT_DIR/docs/operations/distribution-packaging-proof-boundary.md"
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
    "## Local Packaging Checks",
    "## Release Artifact Requirements",
    "## VM And Installer Blockers",
    "## Non-Claims",
    "## Promotion Gate",
    "## Exit Condition",
]
for section in required_sections:
    assert section in doc, section

required_terms = [
    "scripts/smoke_agentos_iso_layout.sh",
    "Docker/local preview proof remains separate",
    "generated release artifacts are not committed",
    "generated ISO path",
    "release manifest",
    "checksum publication",
    "signing",
    "unsigned-preview statement",
    "secret-free artifact review",
    "build-output cleanup",
    "observed VM",
    "Docker evidence must not be reused as VM/ISO proof",
    "production OS distribution readiness",
    "installer readiness",
    "verified boot",
    "ISO freshness",
]
for term in required_terms:
    assert term in doc, term

assert "docs/operations/distribution-packaging-proof-boundary.md" in index
assert "distribution-packaging-proof-boundary-epic" in roadmap
assert "[P2-53] Record distribution packaging epic completion" in tasks
assert "distribution packaging proof boundary epic is closed" in tasks
assert "Completed tasks: P2-50, P2-51, and P2-52" in roadmap
assert "release manifest/checksum preflight" in tasks
PY

echo "distribution packaging boundary smoke: PASS"
