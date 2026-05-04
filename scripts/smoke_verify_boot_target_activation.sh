#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

ISO_ROOT="$TMP_DIR/iso-root"
mkdir -p "$ISO_ROOT/agentos"
PATCH_REPORT="$TMP_DIR/boot-entry-patch-report.json"
cat > "$PATCH_REPORT" <<'EOF'
{"continue_present": true, "install_present": false, "install_path_available": true, "recovery_present": true, "installer_hidden_default_path": true, "default_boot_target_label": "Continue to AgentOS", "default_boot_target_entry_index": 0, "grub_default_target_configured": true, "default_boot_target_configured": true}
EOF

OUT="$TMP_DIR/boot-target-activation.json"
python3 "$ROOT_DIR/scripts/verify_boot_target_activation.py" \
  --iso-root "$ISO_ROOT" \
  --boot-patch-report "$PATCH_REPORT" \
  --output "$OUT" >/dev/null

python3 "$ROOT_DIR/scripts/verify_boot_target_activation.py" --validate "$OUT" --json >/dev/null

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["schema_version"] == "agentos-boot-target-activation.v1"
assert payload["boot_target_contract"] == "agentos_continue_boot_target.v1"
assert payload["default_boot_target_label"] == "Continue to AgentOS"
assert payload["default_boot_target_entry_index"] == 0
assert payload["install_path_available"] is True
assert payload["boot_target_activated"] is True
print("verify boot target activation smoke: PASS")
PY
