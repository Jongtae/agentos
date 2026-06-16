#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

OUT="$TMP_DIR/vm-iso-proof-preflight.json"
python3 scripts/kernel_vm_iso_proof_preflight.py \
  --workspace "$TMP_DIR/workspace" \
  --vm-name "AgentOS Preview" \
  --iso-path "$TMP_DIR/agentos.iso" \
  --output "$OUT"

python3 scripts/kernel_vm_iso_proof_preflight.py --validate "$OUT" --json >/dev/null

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-vm-iso-proof-preflight.v1", payload
assert payload["proof"]["preflight_completed"] is True, payload
assert payload["proof"]["vm_iso_proof_completed"] is False, payload
assert payload["proof"]["observed_vm_boot"] is False, payload
assert payload["proof"]["observed_managed_runtime_rejoin"] is False, payload
assert payload["blockers"][0]["id"] == "vm-iso-proof-not-observed", payload
assert any("vm-utm-observe" in command for command in payload["planned_commands"]), payload
assert all(check["exists"] for check in payload["script_checks"]), payload
PY

echo "vm iso proof preflight smoke: PASS"
