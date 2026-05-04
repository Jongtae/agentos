#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$TMP_DIR/welcome.json" <<'EOF'
{
  "schema_version": "agentos-welcome-first-vm-proof-pack.v1",
  "summary": {
    "ok": true,
    "expected_path": "Continue to AgentOS -> AgentOS Welcome -> AgentOS Setup -> ai>"
  }
}
EOF
cat > "$TMP_DIR/reboot.json" <<'EOF'
{
  "schema_version": "agentos-installed-reboot-slot-proof.v1",
  "summary": {
    "ok": true,
    "expected_installed_path": "Installed AgentOS Boot -> AgentOS Setup -> AgentOS Managed Session -> ai>"
  }
}
EOF
cat > "$TMP_DIR/recovery.json" <<'EOF'
{
  "schema_version": "agentos-recovery-reentry-after-slot-switch.v1",
  "summary": {
    "ok": true,
    "expected_return_path": "AgentOS Recovery -> Return to AgentOS -> ai>"
  }
}
EOF
OUT="$TMP_DIR/signoff.json"
"$ROOT_DIR/scripts/kernel_appliance_boot_signoff_pack.py" \
  --report-dir "$TMP_DIR/reports" \
  --welcome-first-vm-proof-pack "$TMP_DIR/welcome.json" \
  --installed-reboot-slot-proof "$TMP_DIR/reboot.json" \
  --recovery-reentry-after-slot-switch "$TMP_DIR/recovery.json" \
  --output "$OUT"

python3 - <<'PY' "$OUT"
import json
import sys
payload = json.loads(open(sys.argv[1], 'r', encoding='utf-8').read())
assert payload['schema_version'] == 'agentos-appliance-boot-signoff-pack.v1'
assert payload['summary']['ok'] is True
print('PASS')
PY

echo "kernel appliance boot signoff pack smoke: PASS"
