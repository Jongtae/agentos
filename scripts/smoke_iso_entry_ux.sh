#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
OUT_DIR="$TMP_DIR/release"

scripts/prepare_iso_assets.sh --version v0.35.0 >/dev/null
scripts/build_agentos_iso.sh --version v0.35.0 --output-dir "$OUT_DIR" --download-base-image >/dev/null

METADATA="$OUT_DIR/agentos-release-metadata.json"
python3 - "$METADATA" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
if payload.get('boot_experience_contract') != 'agentos_direct_ai_boot':
    raise SystemExit('expected direct-ai-boot contract in release metadata')
if payload.get('iso_default_boot_path') != 'continue_to_agentos_default_path':
    raise SystemExit('expected Continue to AgentOS default boot path in release metadata')
if payload.get('iso_fallback_boot_path') != 'installer_heavy_compatibility':
    raise SystemExit('expected installer-heavy fallback boot path in release metadata')
if payload.get('grub_theme_contract') != 'agentos_minimal_appliance_grub.v1':
    raise SystemExit('expected minimal grub contract in release metadata')
if payload.get('splash_theme_contract') != 'agentos_minimal_appliance_splash.v1':
    raise SystemExit('expected minimal splash contract in release metadata')
PY

python3 scripts/verify_release_identity_contract.py --metadata "$METADATA" --json >/dev/null
rg -q 'Continue to AgentOS' docs/reference/iso-entry-ux-wiring-v1.md
rg -q 'installer-heavy compatibility' docs/reference/iso-entry-ux-wiring-v1.md
rg -q 'agentos_minimal_appliance_grub.v1' docs/reference/iso-entry-ux-wiring-v1.md
rg -q 'agentos_minimal_appliance_splash.v1' docs/reference/iso-entry-ux-wiring-v1.md

echo "iso entry ux smoke: PASS"
