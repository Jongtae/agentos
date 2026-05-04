#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

INSTALL_ROOT="$TMP_DIR/install-root"
METADATA="$TMP_DIR/agentos-release-metadata.json"
MANIFEST="$TMP_DIR/install-verification.json"

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
  --output "$MANIFEST" >/dev/null

python3 "$ROOT_DIR/scripts/export_install_verification_manifest.py" \
  --validate "$MANIFEST" \
  --json >/dev/null

python3 - "$MANIFEST" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
summary = payload["summary"]
if not summary["ok"]:
    raise SystemExit("install verification summary should pass")
if summary["artifact_type"] != "iso":
    raise SystemExit("artifact_type mismatch")
if not summary["install_root_checked"]:
    raise SystemExit("install_root_checked should be true")
if not summary["health_commands"]:
    raise SystemExit("health_commands should be populated")
PY

echo "install verification manifest smoke: PASS"
