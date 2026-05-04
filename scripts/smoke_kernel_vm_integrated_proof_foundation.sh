#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d /tmp/agentos-vm-integrated-proof-XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

cat >"$TMP_DIR/runtime.json" <<'JSON'
{"schema_version":"agentos-appliance-boot-signoff-pack.v1","summary":{"ok":true,"expected_primary_path":"Continue to AgentOS -> AgentOS Welcome -> AgentOS Setup -> ai>","expected_installed_path":"Installed AgentOS Boot -> AgentOS Setup -> AgentOS Managed Session -> ai>","expected_recovery_path":"AgentOS Recovery -> Return to AgentOS -> ai>"}}
JSON

cat >"$TMP_DIR/capability.json" <<'JSON'
{"schema_version":"agentos-capability-proof-surface.v1","web_access":{"escalation_reason":"interactive_or_js_heavy"},"summary":{"document_native_handled":true,"web_native_handled":false,"web_escalated_handled":true,"intake_native_items":1,"intake_escalated_items":0}}
JSON

cat >"$TMP_DIR/intake.json" <<'JSON'
{"schema_version":"agentos-intake-surface.v1","summary":{"ok":true,"total_items":1,"native_intake_items":1,"escalated_intake_items":0},"intake_items":[{"correlation":{"session_id":"agentos:tty1","request_id":"req-1"}}]}
JSON

cat >"$TMP_DIR/service-permission.json" <<'JSON'
{"schema_version":"agentos-service-governance.v1","inventory":[{"unit":"agentos-kernel.service"}],"summary":{"mandatory_broker_units":["agentos-kernel.service"],"approval_gated_units":["agentos-eventd.service"]},"permission_evidence":{"approval_id":"approval-1","escalation_reasons":["operator_control_change"]}}
JSON

python3 "$ROOT_DIR/scripts/kernel_vm_integrated_proof_foundation.py" \
  --report-dir "$TMP_DIR/reports" \
  --runtime-proof "$TMP_DIR/runtime.json" \
  --capability-proof "$TMP_DIR/capability.json" \
  --intake-proof "$TMP_DIR/intake.json" \
  --service-permission-proof "$TMP_DIR/service-permission.json" \
  --output "$TMP_DIR/foundation.json"

python3 "$ROOT_DIR/scripts/kernel_vm_integrated_proof_foundation.py" \
  --validate "$TMP_DIR/foundation.json" \
  --json > "$TMP_DIR/validate.json"

python3 - "$TMP_DIR/foundation.json" "$TMP_DIR/validate.json" <<'PY'
import json
import sys
foundation = json.load(open(sys.argv[1], encoding="utf-8"))
validate = json.load(open(sys.argv[2], encoding="utf-8"))
assert foundation["schema_version"] == "agentos-vm-integrated-proof-foundation.v1"
assert foundation["summary"]["ok"] is True
assert "interactive_or_js_heavy" in foundation["summary"]["escalation_reasons"]
assert validate["ok"] is True
print("kernel vm integrated proof foundation smoke: PASS")
PY
