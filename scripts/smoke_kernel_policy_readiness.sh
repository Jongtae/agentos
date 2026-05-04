#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"

cat > "$WORKSPACE/spec.yaml" <<'EOF'
name: "kernel-policy-readiness-smoke"
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

OUT_WARN="$TMP_DIR/warn.json"
scripts/agentos-kernelctl policy-ready --workspace "$WORKSPACE" --parser-cmd sh --json > "$OUT_WARN"
python3 - "$OUT_WARN" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("overall_status") not in {"warn", "degraded"}:
    raise SystemExit("expected warn/degraded before bridge output")
if payload.get("mechanism", {}).get("ready_for_enforced_pilot") is True:
    raise SystemExit("expected not-ready before bridge output")
if "profile_rendered" not in payload.get("failing_checks", []):
    raise SystemExit("expected profile_rendered in failing_checks before bridge output")
if payload.get("operator_state") != "blocked":
    raise SystemExit("expected operator_state=blocked before bridge output")
if payload.get("pilot_targets", {}).get("next_policy_target") != "network_allowlist":
    raise SystemExit("expected next_policy_target=network_allowlist before bridge output")
if payload.get("pilot_targets", {}).get("next_policy_target_ready") is not False:
    raise SystemExit("expected next_policy_target_ready=false before bridge output")
if "next_policy_target_contract" not in payload.get("warning_checks", []):
    raise SystemExit("expected next_policy_target_contract warning before bridge output")
PY

scripts/agentos-kernelctl policy-bridge --workspace "$WORKSPACE" >/dev/null

OUT_PASS="$TMP_DIR/pass.json"
scripts/agentos-kernelctl policy-ready --workspace "$WORKSPACE" --parser-cmd sh --json > "$OUT_PASS"
python3 - "$OUT_PASS" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("overall_status") != "pass":
    raise SystemExit("expected pass after bridge output with parser available")
if payload.get("bridge", {}).get("profile_exists") is not True:
    raise SystemExit("expected profile_exists=true")
if payload.get("bridge", {}).get("state_exists") is not True:
    raise SystemExit("expected state_exists=true")
if payload.get("mechanism", {}).get("ready_for_enforced_pilot") is not True:
    raise SystemExit("expected ready_for_enforced_pilot=true")
if payload.get("failing_checks") != []:
    raise SystemExit("expected no failing_checks after bridge output")
if payload.get("warning_checks") != []:
    raise SystemExit("expected no warning_checks after bridge output")
if payload.get("bridge", {}).get("lifecycle_summary", {}).get("bridge_state") != "rendered":
    raise SystemExit("expected lifecycle bridge_state=rendered")
if payload.get("pilot_targets", {}).get("next_policy_target") != "network_allowlist":
    raise SystemExit("expected next_policy_target=network_allowlist after bridge output")
if payload.get("pilot_targets", {}).get("next_policy_target_ready") is not True:
    raise SystemExit("expected next_policy_target_ready=true after bridge output")
if payload.get("bridge", {}).get("network_allowlist_count", 0) < 1:
    raise SystemExit("expected network_allowlist_count >= 1 after bridge output")
PY

OUT_ENABLED="$TMP_DIR/enabled.json"
scripts/agentos-kernelctl policy-enforce \
  --workspace "$WORKSPACE" \
  --enable \
  --confirm \
  --require-ready \
  --parser-cmd sh \
  --json > /dev/null

scripts/agentos-kernelctl policy-ready --workspace "$WORKSPACE" --parser-cmd sh --json > "$OUT_ENABLED"
python3 - "$OUT_ENABLED" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
enforced = payload.get("enforced_pilot", {})
if enforced.get("configured_enabled") is not True:
    raise SystemExit("expected configured_enabled=true")
if enforced.get("effective_enabled") is not True:
    raise SystemExit("expected effective_enabled=true")
PY

echo "kernel policy readiness smoke: PASS"
