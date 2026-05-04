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
name: "kernel-session-contract-smoke"
kernel_engine:
  provider: "codex"
  mode: "single"
  codex:
    command: "$FAKE_CODEX"
    timeout_sec: 10
    model: ""
runtime:
  workspace_root: "./"
EOS

ENV_FILE="$TMP_DIR/agentos.env"
printf 'AGENTOS_PROVIDER="codex"\n' > "$ENV_FILE"
OUT_JSON="$TMP_DIR/session-contract.json"
OPENAI_API_KEY=dummy \
AGENTOS_ENV_FILE="$ENV_FILE" \
AGENTOS_SESSION_MANAGED=1 \
AGENTOS_SESSION_ENTRY=live_appliance \
AGENTOS_LIVE_APPLIANCE=1 \
AGENTOS_SESSION_BANNER_VERSION=phase49-v1 \
scripts/agentos-kernelctl session-contract --workspace "$WORKSPACE" --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("schema_version") != "agentos-session-contract-report.v1":
    raise SystemExit("expected session contract report schema")
contract = payload.get("contract", {})
if contract.get("schema_version") != "agentos-session-contract.v1":
    raise SystemExit("expected session contract schema")
validation = payload.get("validation", {})
if validation.get("overall_status") not in {"pass", "warn", "fail"}:
    raise SystemExit("expected overall status")
if "engine" not in (validation.get("gates") or {}):
    raise SystemExit("expected engine gate")
if payload.get("runtime_status", {}).get("setup_state", {}).get("next_managed_entry") != "ai_shell":
    raise SystemExit("expected configured ai_shell next entry")
origin = payload.get("runtime_status", {}).get("session_origin", {})
if origin.get("category") != "live_appliance_boot":
    raise SystemExit("expected live_appliance_boot origin")
if payload.get("contract", {}).get("preferred_entry_origin") != "live_appliance_boot":
    raise SystemExit("expected preferred live appliance entry origin")
install_later_contract = payload.get("contract", {}).get("install_later_contract", {})
if install_later_contract.get("target_origin") != "installed_appliance_boot":
    raise SystemExit("expected installed_appliance_boot install-later target")
platform_reset = payload.get("contract", {}).get("platform_reset_contract", {})
if platform_reset.get("platform_model") != "agentos_managed_appliance_os":
    raise SystemExit("expected appliance platform model")
if platform_reset.get("update_model") != "image_based_ab_updates":
    raise SystemExit("expected image-based update model")
if platform_reset.get("state_partition_required") is not True:
    raise SystemExit("expected state partition requirement")
compat = payload.get("runtime_status", {}).get("session_origin_compatibility", {})
if compat.get("path_family") != "appliance_first":
    raise SystemExit("expected appliance_first origin family")
install_later = payload.get("runtime_status", {}).get("install_later", {})
if install_later.get("available") is not True:
    raise SystemExit("expected install-later availability for live appliance path")
if install_later.get("target_origin") != "installed_appliance_boot":
    raise SystemExit("expected installed_appliance_boot runtime target")
print("kernel session contract smoke: PASS")
PY

OUT_INSTALLED="$TMP_DIR/session-contract-installed.json"
OPENAI_API_KEY=dummy \
AGENTOS_ENV_FILE="$ENV_FILE" \
AGENTOS_SESSION_MANAGED=1 \
AGENTOS_SESSION_ENTRY=installed_appliance \
AGENTOS_INSTALLED_APPLIANCE=1 \
AGENTOS_SESSION_BANNER_VERSION=phase49-v1 \
scripts/agentos-kernelctl session-contract --workspace "$WORKSPACE" --json > "$OUT_INSTALLED"

python3 - "$OUT_INSTALLED" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
contract = payload.get("contract", {})
installed = contract.get("installed_appliance_contract", {})
if installed.get("origin") != "installed_appliance_boot":
    raise SystemExit("expected installed appliance contract origin")
runtime = payload.get("runtime_status", {})
origin = runtime.get("session_origin", {})
if origin.get("category") != "installed_appliance_boot":
    raise SystemExit("expected installed appliance runtime origin")
compat = runtime.get("session_origin_compatibility", {})
if compat.get("label") != "installed_appliance":
    raise SystemExit("expected installed appliance compatibility label")
platform_reset = contract.get("platform_reset_contract", {})
if "installed_slot_b" not in (platform_reset.get("target_platform_states") or []):
    raise SystemExit("expected platform reset target states")
install_later = runtime.get("install_later", {})
if install_later.get("current_install_path") != "installed_appliance_boot":
    raise SystemExit("expected installed appliance current path")
print("kernel session contract installed smoke: PASS")
PY
