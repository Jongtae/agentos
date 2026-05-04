#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"

cat > "$WORKSPACE/spec.yaml" <<'EOF'
name: "kernel-policy-enforce-smoke"
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

# enable without confirm should fail
if scripts/agentos-kernelctl policy-enforce --workspace "$WORKSPACE" --enable --json >/dev/null 2>&1; then
  echo "policy-enforce should fail without --confirm"
  exit 1
fi

# enforce-ready should fail before bridge/profile generation
if scripts/agentos-kernelctl policy-enforce --workspace "$WORKSPACE" --enable --confirm --require-ready --json >/dev/null 2>&1; then
  echo "policy-enforce should fail with --require-ready before policy profile exists"
  exit 1
fi

# generate profile artifact via policy bridge
scripts/agentos-kernelctl policy-bridge --workspace "$WORKSPACE" >/dev/null

OUT_ENABLE="$TMP_DIR/enable.json"
scripts/agentos-kernelctl policy-enforce \
  --workspace "$WORKSPACE" \
  --enable \
  --confirm \
  --policy-target destructive_action_approval \
  --json > "$OUT_ENABLE"

python3 - "$OUT_ENABLE" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if not payload.get("configured_enabled", False):
    raise SystemExit("expected configured_enabled=true")
if not payload.get("effective_enabled", False):
    raise SystemExit("expected effective_enabled=true")
if payload.get("policy_target") != "destructive_action_approval":
    raise SystemExit("expected policy_target=destructive_action_approval")
if payload.get("next_policy_target") != "destructive_action_approval":
    raise SystemExit("expected next_policy_target=destructive_action_approval")
if "destructive_action_approval" not in payload.get("supported_policy_targets", []):
    raise SystemExit("expected supported_policy_targets to include destructive_action_approval")
kernel = payload.get("kernel_mechanism") or {}
if not kernel.get("profile_exists", False):
    raise SystemExit("expected kernel profile artifact to exist")
PY

OUT_ENV="$TMP_DIR/env-disabled.json"
AGENTOS_KERNEL_POLICY_DISABLE=1 scripts/agentos-kernelctl policy-enforce --workspace "$WORKSPACE" --status --json > "$OUT_ENV"
python3 - "$OUT_ENV" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("configured_enabled") is not True:
    raise SystemExit("configured should remain true before disable")
if payload.get("effective_enabled") is not False:
    raise SystemExit("effective should be false when AGENTOS_KERNEL_POLICY_DISABLE=1")
if payload.get("policy_target") != "destructive_action_approval":
    raise SystemExit("policy_target should remain destructive_action_approval during env fallback")
PY

OUT_DISABLE="$TMP_DIR/disable.json"
scripts/agentos-kernelctl policy-enforce --workspace "$WORKSPACE" --disable --json > "$OUT_DISABLE"
python3 - "$OUT_DISABLE" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("configured_enabled") is not False:
    raise SystemExit("expected configured_enabled=false after disable")
if payload.get("policy_target") != "destructive_action_approval":
    raise SystemExit("policy_target should remain destructive_action_approval after disable")
PY

echo "kernel policy enforce pilot smoke: PASS"
