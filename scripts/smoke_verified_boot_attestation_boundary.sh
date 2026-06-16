#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DOC="$ROOT_DIR/docs/architecture/verified-boot-attestation-proof-boundary.md"
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
    "## Research Basis",
    "## Local Runtime Proof",
    "## Secure Boot Proof Requirements",
    "## TPM Measured Boot And Attestation Requirements",
    "## Linux IMA Requirements",
    "## Non-Claims",
    "## Promotion Gate",
    "## Exit Condition",
]
for section in required_sections:
    assert section in doc, section

required_terms = [
    "UEFI Secure Boot",
    "TCG TPM 2.0",
    "TCG EFI Platform Specification",
    "Linux Integrity Measurement Architecture",
    "firmware or VM Secure Boot state",
    "bootloader or shim signature path",
    "TPM or vTPM availability",
    "boot event log capture",
    "PCR values",
    "event-log replay against PCRs",
    "kernel support and boot parameters for IMA",
    "active IMA policy",
    "IMA measurement is not the same as IMA appraisal",
    "Docker runtime proof as boot-chain proof",
    "observed VM or hardware evidence",
]
for term in required_terms:
    assert term in doc, term

assert "docs/architecture/verified-boot-attestation-proof-boundary.md" in index
assert "verified-boot-attestation-proof-boundary-epic" in roadmap
assert "[P2-58] Define verified boot attestation proof boundary" in tasks
assert "verified boot and attestation proof boundary epic is active" in tasks
assert "Secure Boot, TPM measured boot, PCR/event-log, IMA" in roadmap
assert "hardware attestation claims blocked" in tasks
assert "scripts/smoke_verified_boot_attestation_boundary.sh" in tasks
PY

echo "verified boot attestation boundary smoke: PASS"
