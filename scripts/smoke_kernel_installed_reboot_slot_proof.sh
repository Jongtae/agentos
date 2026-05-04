#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$TMP_DIR/next.json" <<'EOF'
{
  "schema_version": "agentos-next-boot-target-integration.v1",
  "target_slot": "B"
}
EOF
cat > "$TMP_DIR/switch.json" <<'EOF'
{
  "schema_version": "agentos-installed-slot-switch-evidence.v1",
  "observed_slot": "B",
  "switch_confirmed": true,
  "identity_path": "Installed AgentOS Boot -> AgentOS Setup -> AgentOS Managed Session -> ai>"
}
EOF

OUT="$TMP_DIR/proof.json"
"$ROOT_DIR/scripts/kernel_installed_reboot_slot_proof.py" \
  --report-dir "$TMP_DIR/reports" \
  --next-boot-target "$TMP_DIR/next.json" \
  --installed-slot-switch-evidence "$TMP_DIR/switch.json" \
  --output "$OUT"

python3 - <<'PY' "$OUT"
import json
import sys
path = sys.argv[1]
payload = json.loads(open(path, 'r', encoding='utf-8').read())
assert payload['schema_version'] == 'agentos-installed-reboot-slot-proof.v1'
assert payload['summary']['ok'] is True
print('PASS')
PY

echo "kernel installed reboot slot proof smoke: PASS"
