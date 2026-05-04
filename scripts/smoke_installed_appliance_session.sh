#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"

cat > "$WORKSPACE/spec.yaml" <<'EOS'
name: "installed-appliance-session-smoke"
kernel_engine:
  provider: "none"
  mode: "single"
runtime:
  workspace_root: "./"
EOS

OUT_RUNTIME="$TMP_DIR/runtime-entry.json"
OUT_SESSION="$TMP_DIR/session-contract.json"
OUT_STATUS="$TMP_DIR/status.json"

AGENTOS_SESSION_MANAGED=1 \
AGENTOS_SESSION_ENTRY=installed_appliance \
AGENTOS_INSTALLED_APPLIANCE=1 \
python3 "$ROOT_DIR/scripts/kernel_runtime_entry.py" \
  --session-origin installed_appliance_boot \
  --setup-status configured \
  --next-managed-entry ai_shell \
  --output "$OUT_RUNTIME"

AGENTOS_SESSION_MANAGED=1 \
AGENTOS_SESSION_ENTRY=installed_appliance \
AGENTOS_INSTALLED_APPLIANCE=1 \
python3 "$ROOT_DIR/scripts/kernel_session_contract.py" \
  --workspace "$WORKSPACE" \
  --json > "$OUT_SESSION"

AGENTOS_SESSION_MANAGED=1 \
AGENTOS_SESSION_ENTRY=installed_appliance \
AGENTOS_INSTALLED_APPLIANCE=1 \
python3 - <<'PY' "$WORKSPACE" "$OUT_STATUS"
import json
import sys
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / 'src'))
from status import status_report
from workspace.manager import WorkspaceManager

workspace = sys.argv[1]
out = Path(sys.argv[2])
payload = status_report(WorkspaceManager(workspace))
out.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
PY

python3 - <<'PY' "$OUT_RUNTIME" "$OUT_SESSION" "$OUT_STATUS"
import json
import sys
from pathlib import Path

runtime = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
session = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
status = json.loads(Path(sys.argv[3]).read_text(encoding='utf-8'))

if runtime.get('preferred_installed_origin') != 'installed_appliance_boot':
    raise SystemExit('expected preferred_installed_origin in runtime entry')
if runtime.get('effective_target') != 'ai_shell':
    raise SystemExit('expected installed appliance runtime target ai_shell')
contract = session.get('contract', {}).get('installed_appliance_contract', {})
if contract.get('origin') != 'installed_appliance_boot':
    raise SystemExit('expected installed appliance contract origin')
origin = status.get('session_origin', {})
if origin.get('category') != 'installed_appliance_boot':
    raise SystemExit('expected status session origin installed_appliance_boot')
compat = status.get('session_origin_compatibility', {})
if compat.get('label') != 'installed_appliance':
    raise SystemExit('expected installed appliance compatibility label')
install_later = status.get('install_later', {})
if install_later.get('current_install_path') != 'installed_appliance_boot':
    raise SystemExit('expected installed appliance current path')
print('installed appliance session smoke: PASS')
PY
