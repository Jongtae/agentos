#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$TMP_DIR/reboot.json" <<'EOF'
{
  "schema_version": "agentos-installed-reboot-slot-proof.v1",
  "summary": {
    "ok": true
  }
}
EOF
cat > "$TMP_DIR/recovery.json" <<'EOF'
{
  "schema_version": "agentos-slot-recovery-logic.v1",
  "recovery_required": true,
  "return_action": "return_to_agentos",
  "return_path": "AgentOS Recovery -> Return to AgentOS -> ai>"
}
EOF

OUT="$TMP_DIR/proof.json"
"$ROOT_DIR/scripts/kernel_recovery_reentry_after_slot_switch.py" \
  --report-dir "$TMP_DIR/reports" \
  --installed-reboot-slot-proof "$TMP_DIR/reboot.json" \
  --slot-recovery-logic "$TMP_DIR/recovery.json" \
  --output "$OUT"

python3 - <<'PY' "$OUT"
import json
import sys
payload = json.loads(open(sys.argv[1], 'r', encoding='utf-8').read())
assert payload['schema_version'] == 'agentos-recovery-reentry-after-slot-switch.v1'
assert payload['summary']['ok'] is True
print('PASS')
PY

echo "kernel recovery re-entry after slot switch smoke: PASS"
