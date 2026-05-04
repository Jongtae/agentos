#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

INSTALL_ROOT="$TMP_DIR/install-root"
METADATA="$TMP_DIR/agentos-release-metadata.json"
INSTALL_MANIFEST="$TMP_DIR/install-verification.json"
VM_MANIFEST="$TMP_DIR/vm-appliance.json"

mkdir -p "$INSTALL_ROOT"

cat > "$METADATA" <<'JSON'
{
  "artifact_type": "iso",
  "distribution_contract": "agentos_managed_session",
  "primary_entry_contract": "agentos_setup_to_ai_shell"
}
JSON

AGENTOS_INSTALL_ROOT="$INSTALL_ROOT" \
AGENTOS_ENABLE_SYSTEMD=0 \
AGENTOS_BROKER_BYPASS=1 \
bash "$ROOT_DIR/scripts/install_kernel_boot_integration.sh" >/dev/null

python3 "$ROOT_DIR/scripts/export_install_verification_manifest.py" \
  --metadata "$METADATA" \
  --install-root "$INSTALL_ROOT" \
  --workspace "./workspaces/default" \
  --output "$INSTALL_MANIFEST" >/dev/null

python3 "$ROOT_DIR/scripts/vm_appliance_manifest.py" \
  --workspace "./workspaces/default" \
  --snapshot-label "agentos-demo-clean" \
  --output "$VM_MANIFEST" >/dev/null

python3 "$ROOT_DIR/scripts/export_install_verification_manifest.py" --validate "$INSTALL_MANIFEST" --json >/dev/null
python3 "$ROOT_DIR/scripts/vm_appliance_manifest.py" --validate "$VM_MANIFEST" --json >/dev/null

rg -q "scripts/vm_demo_flow.sh --workspace ./workspaces/default --skip-bootstrap" \
  "$ROOT_DIR/docs/runbooks/m5-substrate-runbook.md"
rg -q "scripts/vm_appliance_status.sh --workspace ./workspaces/default" \
  "$ROOT_DIR/docs/runbooks/m5-substrate-runbook.md"
rg -q "export_install_verification_manifest.py" \
  "$ROOT_DIR/docs/runbooks/distribution-packaging-runbook.md"
rg -q "install verification manifest smoke: PASS" \
  "$ROOT_DIR/docs/runbooks/m5-substrate-runbook.md"

echo "vm install operator walkthrough smoke: PASS"
