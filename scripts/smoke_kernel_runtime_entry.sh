#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

python3 "$ROOT_DIR/scripts/kernel_runtime_entry.py" \
  --session-origin local_managed_tty1 \
  --setup-status configured \
  --next-managed-entry ai_shell \
  --output "$TMP_DIR/local.json"
python3 "$ROOT_DIR/scripts/kernel_runtime_entry.py" \
  --session-origin ssh \
  --setup-status configured \
  --next-managed-entry ai_shell \
  --output "$TMP_DIR/ssh.json"
python3 "$ROOT_DIR/scripts/kernel_runtime_entry.py" \
  --session-origin live_appliance_boot \
  --setup-status pending \
  --next-managed-entry setup_session \
  --output "$TMP_DIR/live.json"
python3 "$ROOT_DIR/scripts/kernel_runtime_entry.py" \
  --session-origin installed_appliance_boot \
  --setup-status configured \
  --next-managed-entry ai_shell \
  --output "$TMP_DIR/installed.json"
python3 "$ROOT_DIR/scripts/kernel_runtime_entry.py" --validate "$TMP_DIR/local.json" --json > "$TMP_DIR/validate.json"

python3 - "$TMP_DIR/local.json" "$TMP_DIR/ssh.json" "$TMP_DIR/live.json" "$TMP_DIR/installed.json" "$TMP_DIR/validate.json" <<'PY'
import json
import sys
from pathlib import Path

local = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
ssh = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
live = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
installed = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
validate = json.loads(Path(sys.argv[5]).read_text(encoding="utf-8"))
if local.get("effective_target") != "ai_shell":
    raise SystemExit("expected local managed tty1 to target ai_shell")
if local.get("fallback_target") != "normal_tty_shell":
    raise SystemExit("expected local managed tty1 fallback to normal_tty_shell")
if ssh.get("effective_target") != "login_shell":
    raise SystemExit("expected ssh path to stay on login_shell")
if live.get("effective_target") != "setup_session":
    raise SystemExit("expected live appliance boot to target setup_session")
if live.get("preferred_origin") != "live_appliance_boot":
    raise SystemExit("expected preferred origin to be live_appliance_boot")
if installed.get("effective_target") != "ai_shell":
    raise SystemExit("expected installed appliance boot to target ai_shell")
if installed.get("preferred_installed_origin") != "installed_appliance_boot":
    raise SystemExit("expected preferred installed origin to be installed_appliance_boot")
if installed.get("installed_appliance_boot") is not True:
    raise SystemExit("expected installed appliance boot flag")
if live.get("platform_model") != "agentos_managed_appliance_os":
    raise SystemExit("expected appliance platform model")
if live.get("update_model") != "image_based_ab_updates":
    raise SystemExit("expected image-based update model")
if live.get("slot_aware_runtime") is not True:
    raise SystemExit("expected slot-aware runtime")
if "installed_slot_a" not in (live.get("target_platform_states") or []):
    raise SystemExit("expected target platform states")
if validate.get("ok") is not True:
    raise SystemExit("expected runtime entry validation to pass")
PY

echo "runtime entry smoke: PASS"
