#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
WORKSPACE="$TMP_DIR/workspace"
REPORT_DIR="$TMP_DIR/reports"
INSTALL_ROOT="$TMP_DIR/install-root"
mkdir -p "$WORKSPACE"

cat > "$WORKSPACE/spec.yaml" <<'YAML'
name: platform-validation-smoke
kernel_engine:
  provider: none
  mode: single
runtime:
  workspace_root: ./
YAML

AGENTOS_INSTALL_ROOT="$INSTALL_ROOT" \
AGENTOS_ENABLE_SYSTEMD=0 \
DEFAULT_WORKSPACE="$WORKSPACE" \
"$ROOT_DIR/scripts/install_kernel_boot_integration.sh" >/dev/null 2>&1

OUT="$TMP_DIR/platform-validation.json"
python3 "$ROOT_DIR/scripts/kernel_platform_validation.py" \
  --workspace "$WORKSPACE" \
  --report-dir "$REPORT_DIR" \
  --install-root "$INSTALL_ROOT" \
  --output "$OUT"
python3 "$ROOT_DIR/scripts/kernel_platform_validation.py" --validate "$OUT" --json >/dev/null
python3 - "$OUT" <<'PY'
import json, sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("schema_version") != "agentos-platform-validation-matrix.v1":
    raise SystemExit("expected platform validation schema version")
summary = payload.get("summary", {})
if summary.get("active_architecture") != "x86_64":
    raise SystemExit("expected x86_64 active architecture")
if summary.get("environment_count") != 3:
    raise SystemExit("expected three validation environments")
if summary.get("active_origin_count") != 3:
    raise SystemExit("expected three active origins")
matrix = payload.get("validation_matrix", {})
for key in ("x86_64_live_appliance_vm", "x86_64_installed_appliance_vm", "x86_64_workstation_legacy_compat"):
    if key not in matrix:
        raise SystemExit(f"expected validation entry: {key}")
if payload.get("origin_summary", {}).get("preferred") != ["live_appliance_boot", "installed_appliance_boot"]:
    raise SystemExit("expected preferred appliance origins")
print("kernel platform validation smoke: PASS")
PY
