#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"

cat > "$WORKSPACE/spec.yaml" <<'EOF'
name: "kernel-policy-recovery-smoke"
ai_model:
  provider: "openai"
  model: "gpt-4o-mini"
kernel_engine:
  provider: "none"
  mode: "single"
tools:
  bash: true
  file: true
  web: true
permissions:
  require_approval: true
memory:
  checkpointer: "sqlite"
  db_path: "./data/session.sqlite"
  store_path: "./data/memory.sqlite"
runtime:
  max_steps: 4
  max_message_window: 20
  workspace_root: "./"
EOF

# render bridge artifacts first so recovery path is exercised with a prepared profile state
scripts/agentos-kernelctl policy-bridge --workspace "$WORKSPACE" >/dev/null

OUT_ENABLE="$TMP_DIR/enable.json"
scripts/agentos-kernelctl policy-enforce \
  --workspace "$WORKSPACE" \
  --enable \
  --confirm \
  --policy-target network_allowlist \
  --json > "$OUT_ENABLE"

python3 - "$OUT_ENABLE" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("configured_enabled") is not True:
    raise SystemExit("expected configured_enabled=true after enable")
if payload.get("effective_enabled") is not True:
    raise SystemExit("expected effective_enabled=true after enable")
if payload.get("policy_target") != "network_allowlist":
    raise SystemExit("expected policy_target=network_allowlist after enable")
PY

OUT_ENV="$TMP_DIR/env-disable.json"
AGENTOS_KERNEL_POLICY_DISABLE=1 scripts/agentos-kernelctl policy-enforce \
  --workspace "$WORKSPACE" \
  --status \
  --json > "$OUT_ENV"

python3 - "$OUT_ENV" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("configured_enabled") is not True:
    raise SystemExit("configured_enabled should remain true under env disable")
if payload.get("effective_enabled") is not False:
    raise SystemExit("effective_enabled should be false under env disable")
if payload.get("kernel_disable_env_active") is not True:
    raise SystemExit("kernel_disable_env_active should be true")
if "AGENTOS_KERNEL_POLICY_DISABLE" not in payload.get("disable_switches", []):
    raise SystemExit("expected AGENTOS_KERNEL_POLICY_DISABLE in disable_switches")
if payload.get("policy_target") != "network_allowlist":
    raise SystemExit("policy_target should remain network_allowlist under session disable")
PY

OUT_BOOT_ENV="$TMP_DIR/boot-env-disable.json"
AGENTOS_KERNEL_POLICY_BOOT_DISABLE=1 scripts/agentos-kernelctl policy-enforce \
  --workspace "$WORKSPACE" \
  --status \
  --json > "$OUT_BOOT_ENV"

python3 - "$OUT_BOOT_ENV" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("configured_enabled") is not True:
    raise SystemExit("configured_enabled should remain true under boot disable")
if payload.get("effective_enabled") is not False:
    raise SystemExit("effective_enabled should be false under boot disable")
if "AGENTOS_KERNEL_POLICY_BOOT_DISABLE" not in payload.get("disable_switches", []):
    raise SystemExit("expected AGENTOS_KERNEL_POLICY_BOOT_DISABLE in disable_switches")
if payload.get("policy_target") != "network_allowlist":
    raise SystemExit("policy_target should remain network_allowlist under boot disable")
PY

OUT_DISABLE="$TMP_DIR/operator-disable.json"
scripts/agentos-kernelctl policy-enforce \
  --workspace "$WORKSPACE" \
  --disable \
  --json > "$OUT_DISABLE"

python3 - "$OUT_DISABLE" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("configured_enabled") is not False:
    raise SystemExit("expected configured_enabled=false after operator disable")
if payload.get("effective_enabled") is not False:
    raise SystemExit("expected effective_enabled=false after operator disable")
if payload.get("policy_target") != "network_allowlist":
    raise SystemExit("policy_target should remain network_allowlist after operator disable")
PY

echo "kernel policy recovery smoke: PASS"
