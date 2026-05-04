#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

ISO_ROOT="$TMP_DIR/iso-root"
mkdir -p "$ISO_ROOT/agentos"
BOOT_FLOW="$TMP_DIR/boot-flow-proof.json"
BOOT_TARGET="$TMP_DIR/boot-target-activation.json"
OUT="$TMP_DIR/vm-first-screen-evidence.json"

cat > "$BOOT_FLOW" <<'EOF'
{"welcome_autostart_included": true, "welcome_shell_included": true}
EOF
cat > "$BOOT_TARGET" <<'EOF'
{"default_boot_target_label": "Continue to AgentOS", "boot_target_activated": true}
EOF

python3 "$ROOT_DIR/scripts/verify_vm_first_screen_evidence.py" \
  --iso-root "$ISO_ROOT" \
  --boot-flow-proof "$BOOT_FLOW" \
  --boot-target-activation "$BOOT_TARGET" \
  --output "$OUT" >/dev/null

python3 "$ROOT_DIR/scripts/verify_vm_first_screen_evidence.py" --validate "$OUT" --json >/dev/null

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["schema_version"] == "agentos-vm-first-screen-evidence.v1"
assert payload["expected_first_screen"] == "AgentOS Welcome"
assert payload["expected_first_path"] == "Continue to AgentOS -> AgentOS Welcome -> AgentOS Setup -> ai>"
assert payload["evidence_status"] == "ready"
print("verify vm first-screen evidence smoke: PASS")
PY
