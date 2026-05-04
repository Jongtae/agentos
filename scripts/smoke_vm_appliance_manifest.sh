#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

OUT="$TMP_DIR/vm-appliance.json"
scripts/vm_appliance_manifest.py \
  --workspace ./workspaces/default \
  --snapshot-label agentos-demo-clean \
  --output "$OUT"

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("schema_version") != "agentos-vm-appliance.v1":
    raise SystemExit("unexpected schema_version")
if payload.get("appliance_contract") != "agentos_vm_demo":
    raise SystemExit("unexpected appliance_contract")
if payload.get("primary_entry_contract") != "agentos_setup_to_ai_shell":
    raise SystemExit("unexpected primary entry contract")
if "qemu" not in payload.get("recommended_hypervisors", []):
    raise SystemExit("expected qemu hypervisor hint")
if not payload.get("health_commands"):
    raise SystemExit("expected health commands")
if not payload.get("recovery_commands"):
    raise SystemExit("expected recovery commands")
PY

scripts/vm_appliance_manifest.py --validate "$OUT" --json >/dev/null

echo "vm appliance manifest smoke: PASS"
