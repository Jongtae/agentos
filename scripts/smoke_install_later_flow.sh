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
name: "install-later-smoke"
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

STATUS_JSON="$TMP_DIR/status.json"
OPENAI_API_KEY=dummy \
AGENTOS_ENV_FILE="$ENV_FILE" \
AGENTOS_SESSION_MANAGED=1 \
AGENTOS_SESSION_ENTRY=live_appliance \
AGENTOS_LIVE_APPLIANCE=1 \
scripts/agentos-kernelctl status --workspace "$WORKSPACE" --json > "$STATUS_JSON"

python3 - "$STATUS_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
install_later = payload.get("runtime_status", {}).get("install_later", {})
if install_later.get("available") is not True:
    raise SystemExit("expected install-later availability on live appliance path")
if install_later.get("target_origin") != "installed_appliance_boot":
    raise SystemExit("expected installed_appliance_boot target origin")
identity = install_later.get("post_install_identity_path", [])
if identity != ["AgentOS Setup", "AgentOS Managed Session", "ai>"]:
    raise SystemExit("unexpected install-later identity path")
PY

SESSION_JSON="$TMP_DIR/session-contract.json"
OPENAI_API_KEY=dummy \
AGENTOS_ENV_FILE="$ENV_FILE" \
AGENTOS_SESSION_MANAGED=1 \
AGENTOS_SESSION_ENTRY=live_appliance \
AGENTOS_LIVE_APPLIANCE=1 \
scripts/agentos-kernelctl session-contract --workspace "$WORKSPACE" --json > "$SESSION_JSON"

python3 - "$SESSION_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
contract = payload.get("contract", {}).get("install_later_contract", {})
runtime = payload.get("runtime_status", {}).get("install_later", {})
if contract.get("source_origin") != "live_appliance_boot":
    raise SystemExit("expected live_appliance_boot install-later source")
if contract.get("target_origin") != "installed_appliance_boot":
    raise SystemExit("expected installed_appliance_boot contract target")
if runtime.get("available") is not True:
    raise SystemExit("expected install-later runtime availability")
if runtime.get("target_origin") != "installed_appliance_boot":
    raise SystemExit("expected installed_appliance_boot runtime target")
print("install-later flow smoke: PASS")
PY
