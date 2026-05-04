#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

ISO_ROOT="$TMP_DIR/iso-root"
LIVE_ROOT="$TMP_DIR/live-root"
REPORT="$TMP_DIR/boot-report.json"
OUT="$TMP_DIR/boot-flow-proof.json"

mkdir -p "$ISO_ROOT/agentos/boot-assets" "$LIVE_ROOT/etc/xdg/autostart" "$LIVE_ROOT/usr/local/bin"
for name in agentos-welcome-shell agentos-recovery-shell agentos-handoff agentos-install-appliance agentos-state-root-init agentos-installed-boot agentos-slot-metadata-init; do
  printf 'x' > "$LIVE_ROOT/usr/local/bin/$name"
done
printf 'desktop' > "$LIVE_ROOT/etc/xdg/autostart/agentos-welcome.desktop"
cat > "$REPORT" <<'JSON'
{"continue_present": true, "install_present": false, "install_path_available": true, "recovery_present": true, "installer_hidden_default_path": true, "default_boot_target_label": "Continue to AgentOS", "default_boot_target_entry_index": 0, "default_boot_target_configured": true}
JSON

python3 "$ROOT_DIR/scripts/verify_remastered_boot_flow.py" --iso-root "$ISO_ROOT" --live-root "$LIVE_ROOT" --boot-patch-report "$REPORT" --output "$OUT"
python3 "$ROOT_DIR/scripts/verify_remastered_boot_flow.py" --validate "$OUT" --json > "$TMP_DIR/validate.json"

python3 - "$OUT" "$TMP_DIR/validate.json" <<'PY'
import json, sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
validate = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
if payload.get('schema_version') != 'agentos-remastered-boot-flow-proof.v1':
    raise SystemExit('expected boot flow proof schema')
if payload.get('proof_status') != 'ready':
    raise SystemExit('expected ready proof status')
if payload.get('default_boot_target_label') != 'Continue to AgentOS':
    raise SystemExit('expected Continue to AgentOS default boot target label')
if payload.get('default_boot_target_configured') is not True:
    raise SystemExit('expected default boot target activation in proof')
if validate.get('ok') is not True:
    raise SystemExit('expected validation pass')
print('verify remastered boot flow smoke: PASS')
PY
