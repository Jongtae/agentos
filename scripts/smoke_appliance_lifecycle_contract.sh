#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
INSTALL_ROOT="$TMP_DIR/root"
REPORT_DIR="$TMP_DIR/reports"
mkdir -p "$WORKSPACE" "$REPORT_DIR"

cat > "$WORKSPACE/spec.yaml" <<'YAML'
name: "appliance-lifecycle-contract-smoke"
ai_model:
  provider: "openai"
  model: "gpt-4o-mini"
kernel_engine:
  provider: "none"
  mode: "single"
runtime:
  workspace_root: "./"
YAML

AGENTOS_INSTALL_ROOT="$INSTALL_ROOT" \
AGENTOS_ENABLE_SYSTEMD=0 \
DEFAULT_WORKSPACE="$WORKSPACE" \
"$ROOT_DIR/scripts/install_kernel_boot_integration.sh" >/dev/null

OUT_JSON="$TMP_DIR/lifecycle.json"
python3 "$ROOT_DIR/scripts/kernel_appliance_lifecycle.py" \
  --workspace "$WORKSPACE" \
  --report-dir "$REPORT_DIR" \
  --install-root "$INSTALL_ROOT" \
  --output "$OUT_JSON"

python3 "$ROOT_DIR/scripts/kernel_appliance_lifecycle.py" --validate "$OUT_JSON" --json > "$TMP_DIR/validate.json"

python3 - "$OUT_JSON" "$TMP_DIR/validate.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
validate = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
if payload.get("schema_version") != "agentos-appliance-lifecycle.v1":
    raise SystemExit("expected appliance lifecycle schema")
summary = payload.get("summary", {})
if summary.get("ok") is not True:
    raise SystemExit("expected lifecycle summary.ok=true")
actions = payload.get("actions", {})
for key in ("install", "upgrade", "rollback", "reset", "export"):
    if key not in actions:
        raise SystemExit(f"missing lifecycle action: {key}")
if validate.get("ok") is not True:
    raise SystemExit("expected lifecycle validation to pass")
PY

echo "appliance lifecycle contract smoke: PASS"
