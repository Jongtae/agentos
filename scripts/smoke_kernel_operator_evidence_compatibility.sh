#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE/artifacts"

cat > "$WORKSPACE/spec.yaml" <<'EOF'
name: "kernel-operator-evidence-compatibility-smoke"
kernel_engine:
  provider: "none"
  mode: "single"
runtime:
  workspace_root: "./"
EOF

OUT_JSON="$TMP_DIR/evidence.json"
AGENTOS_SESSION_MANAGED=1 AGENTOS_SESSION_ENTRY=local_tty1 python3 scripts/kernel_operator_evidence.py --workspace "$WORKSPACE" --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY2'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
summary = payload.get('summary', {})
if summary.get('runtime_session_origin') != 'local_managed_tty1':
    raise SystemExit('expected runtime_session_origin=local_managed_tty1')
if summary.get('session_path_family') != 'legacy_compatibility':
    raise SystemExit('expected session_path_family=legacy_compatibility')
if summary.get('session_compatibility_label') != 'legacy_tty1_installed':
    raise SystemExit('expected legacy compatibility label')
PY2

echo "kernel operator evidence compatibility smoke: PASS"
