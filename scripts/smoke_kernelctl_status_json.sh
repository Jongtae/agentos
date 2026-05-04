#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"

FAKE_CODEX="$TMP_DIR/fake-codex.sh"
cat > "$FAKE_CODEX" <<'EOS'
#!/bin/sh
set -eu
out_file=""
prompt=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output-last-message)
      shift
      out_file="$1"
      ;;
    *)
      prompt="$1"
      ;;
  esac
  shift
done
if echo "$prompt" | grep -q 'Reply with exactly: HEALTH_OK'; then
  msg='HEALTH_OK'
else
  msg='{"summary":"noop","steps":[]}'
fi
if [ -n "$out_file" ]; then
  printf "%s" "$msg" > "$out_file"
fi
printf "%s\n" "$msg"
EOS
chmod +x "$FAKE_CODEX"

cat > "$WORKSPACE/spec.yaml" <<EOS
name: "kernel-status-json-smoke"
ai_model:
  provider: "openai"
  model: "gpt-4o-mini"
kernel_engine:
  provider: "codex"
  mode: "single"
  codex:
    command: "$FAKE_CODEX"
    timeout_sec: 10
    model: ""
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
EOS

FAKE_SYSTEMCTL_ACTIVE="$TMP_DIR/fake-systemctl-active.sh"
cat > "$FAKE_SYSTEMCTL_ACTIVE" <<'EOS'
#!/bin/sh
set -eu
case "$1" in
  is-active)
    echo active
    ;;
  is-enabled)
    echo enabled
    ;;
  *)
    echo unknown
    ;;
esac
EOS
chmod +x "$FAKE_SYSTEMCTL_ACTIVE"

OUT_JSON="$TMP_DIR/status.json"
ENV_FILE="$TMP_DIR/agentos.env"
printf 'AGENTOS_PROVIDER="codex"\n' > "$ENV_FILE"
OPENAI_API_KEY=dummy AGENTOS_SYSTEMCTL_CMD="$FAKE_SYSTEMCTL_ACTIVE" \
  AGENTOS_SESSION_MANAGED=1 \
  AGENTOS_SESSION_ENTRY=live_appliance \
  AGENTOS_LIVE_APPLIANCE=1 \
  AGENTOS_SESSION_BANNER_VERSION=phase49-v1 \
  AGENTOS_ENV_FILE="$ENV_FILE" \
  scripts/agentos-kernelctl status --workspace "$WORKSPACE" --parser-cmd sh --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("ok") is not True:
    raise SystemExit("expected ok=true")
service = payload.get("service", {})
if service.get("active") != "active":
    raise SystemExit("expected active service")
runtime = payload.get("runtime_status", {})
if runtime.get("engine_status") != "PASS":
    raise SystemExit("expected runtime engine status PASS")
policy = payload.get("policy_ready", {})
if "overall_status" not in policy:
    raise SystemExit("expected policy_ready.overall_status")
recovery = payload.get("recovery_hints", {})
if recovery.get("path_label") != "AgentOS Recovery":
    raise SystemExit("expected recovery path label")
if recovery.get("recommended_rejoin_summary") != ["AgentOS Recovery", "Return to AgentOS", "ai>"]:
    raise SystemExit("expected recovery summary path")
if "AgentOS Recovery" not in (recovery.get("recommended_rejoin_path") or []):
    raise SystemExit("expected recovery rejoin path")
if recovery.get("tty_bypass_env") != "AGENTOS_BOOT_AUTOSTART=0":
    raise SystemExit("expected tty_bypass_env recovery hint")
if recovery.get("broker_bypass_env") != "AGENTOS_BROKER_BYPASS=1":
    raise SystemExit("expected broker_bypass_env recovery hint")
if recovery.get("broker_override_env") != "AGENTOS_BROKER_OVERRIDE=1":
    raise SystemExit("expected broker_override_env recovery hint")
ladder = recovery.get("recovery_ladder", [])
if len(ladder) != 4:
    raise SystemExit("expected four recovery ladder levels")
if ladder[0].get("trigger") != "AGENTOS_BOOT_AUTOSTART=0":
    raise SystemExit("expected recovery ladder level 1")
if ladder[-1].get("trigger") != "sudo scripts/uninstall_kernel_boot_integration.sh":
    raise SystemExit("expected recovery ladder final uninstall step")
setup = payload.get("runtime_status", {}).get("setup_state", {})
if setup.get("status") != "configured":
    raise SystemExit("expected setup_state.status=configured")
if setup.get("next_managed_entry") != "ai_shell":
    raise SystemExit("expected next_managed_entry=ai_shell")
origin = runtime.get("session_origin", {})
if origin.get("category") != "live_appliance_boot":
    raise SystemExit("expected session_origin.category=live_appliance_boot")
if origin.get("session_entry") != "live_appliance":
    raise SystemExit("expected session_origin.session_entry=live_appliance")
if origin.get("live_appliance") is not True:
    raise SystemExit("expected live_appliance flag")
compat = runtime.get("session_origin_compatibility", {})
if compat.get("path_family") != "appliance_first":
    raise SystemExit("expected appliance_first compatibility family")
if compat.get("label") != "live_appliance":
    raise SystemExit("expected live_appliance compatibility label")
install_later = runtime.get("install_later", {})
if install_later.get("available") is not True:
    raise SystemExit("expected install-later available on live appliance path")
if install_later.get("target_origin") != "installed_appliance_boot":
    raise SystemExit("expected install-later target origin")
recovery_path = runtime.get("recovery_path", {})
if recovery_path.get("label") != "AgentOS Recovery":
    raise SystemExit("expected runtime recovery label")
if origin.get("banner_version") != "phase49-v1":
    raise SystemExit("expected session_origin.banner_version=phase49-v1")
contract = runtime.get("session_start_contract", {})
if contract.get("schema_version") != "agentos-session-contract.v1":
    raise SystemExit("expected session_start_contract schema")
if contract.get("preferred_entry_origin") != "live_appliance_boot":
    raise SystemExit("expected preferred_entry_origin=live_appliance_boot")
validation = runtime.get("session_contract_validation", {})
if "engine" not in (validation.get("gates") or {}):
    raise SystemExit("expected session_contract_validation.gates.engine")
entry = runtime.get("runtime_entry", {})
if entry.get("preferred_origin") != "live_appliance_boot":
    raise SystemExit("expected runtime_entry.preferred_origin=live_appliance_boot")
appliance = runtime.get("appliance_platform", {})
if appliance.get("platform_model") != "agentos_managed_appliance_os":
    raise SystemExit("expected appliance platform model")
if appliance.get("active_slot") != "A":
    raise SystemExit("expected active slot A")
if appliance.get("system_images_read_only") is not True:
    raise SystemExit("expected read-only system images")
if appliance.get("next_boot_exists") is not False:
    raise SystemExit("expected no next boot metadata by default")
if "system_image_layout_contract" not in appliance:
    raise SystemExit("expected system image layout contract")
if (appliance.get("image_release_identity", {}) or {}).get("next_slot") != "B":
    raise SystemExit("expected image release identity next slot B")
PY

echo "kernelctl status json smoke: PASS"

OUT_INSTALLED="$TMP_DIR/status-installed.json"
OPENAI_API_KEY=dummy AGENTOS_SYSTEMCTL_CMD="$FAKE_SYSTEMCTL_ACTIVE" \
  AGENTOS_SESSION_MANAGED=1 \
  AGENTOS_SESSION_ENTRY=installed_appliance \
  AGENTOS_INSTALLED_APPLIANCE=1 \
  AGENTOS_SESSION_BANNER_VERSION=phase49-v1 \
  AGENTOS_ENV_FILE="$ENV_FILE" \
  scripts/agentos-kernelctl status --workspace "$WORKSPACE" --parser-cmd sh --json > "$OUT_INSTALLED"

python3 - "$OUT_INSTALLED" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
runtime = payload.get("runtime_status", {})
origin = runtime.get("session_origin", {})
if origin.get("category") != "installed_appliance_boot":
    raise SystemExit("expected installed_appliance_boot origin")
if origin.get("installed_appliance") is not True:
    raise SystemExit("expected installed_appliance flag")
compat = runtime.get("session_origin_compatibility", {})
if compat.get("label") != "installed_appliance":
    raise SystemExit("expected installed appliance label")
install_later = runtime.get("install_later", {})
if install_later.get("available") is not False:
    raise SystemExit("expected install-later unavailable on installed appliance")
if install_later.get("current_install_path") != "installed_appliance_boot":
    raise SystemExit("expected installed appliance current install path")
entry = runtime.get("runtime_entry", {})
if entry.get("preferred_installed_origin") != "installed_appliance_boot":
    raise SystemExit("expected preferred installed origin in runtime entry")
appliance = runtime.get("appliance_platform", {})
if appliance.get("inactive_slot") != "B":
    raise SystemExit("expected inactive slot B")
print("kernelctl status installed appliance smoke: PASS")
PY
