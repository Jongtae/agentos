#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$(mktemp)"
trap 'rm -f "$OUT"' EXIT

"$ROOT_DIR/scripts/agentos-kernelctl" vm-e2e-proof --workspace "$ROOT_DIR/workspaces/default" --json >"$OUT"
python3 "$ROOT_DIR/scripts/kernel_vm_e2e_proof.py" --validate "$OUT" --json >/dev/null
python3 - "$OUT" <<'PY'
import json
import sys

payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
summary = payload["summary"]
required = (
    "vm_e2e_runtime_ok",
    "vm_e2e_capability_ok",
    "vm_e2e_intake_ok",
    "vm_e2e_service_permission_ok",
    "vm_e2e_escalation_integrity_ok",
)
for key in required:
    assert summary.get(key) is True, f"{key} must be true"
PY
echo "kernel vm e2e proof smoke: PASS"
