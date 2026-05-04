#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="${DEFAULT_WORKSPACE:-$ROOT_DIR/workspaces/default}"
AS_JSON=0

usage() {
  cat <<'USAGE'
Usage:
  scripts/vm_appliance_status.sh [--workspace <path>] [--json]

Purpose:
  Show the VM appliance quick path for health, runtime status, and broker state.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --workspace)
      shift
      WORKSPACE="${1:-}"
      ;;
    --json)
      AS_JSON=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift || true
done

HEALTH_JSON="$("$ROOT_DIR/scripts/agentos-kernelctl" health --workspace "$WORKSPACE" --json)"
STATUS_JSON="$("$ROOT_DIR/scripts/agentos-kernelctl" status --workspace "$WORKSPACE" --json)"
BROKER_JSON="$("$ROOT_DIR/scripts/agentos-kernelctl" broker-status --workspace "$WORKSPACE" --json)"

if [ "$AS_JSON" -eq 1 ]; then
  python3 - "$WORKSPACE" "$HEALTH_JSON" "$STATUS_JSON" "$BROKER_JSON" <<'PY'
import json
import sys

workspace = sys.argv[1]
health = json.loads(sys.argv[2])
status = json.loads(sys.argv[3])
broker = json.loads(sys.argv[4])
payload = {
    "workspace": workspace,
    "health": health,
    "status": status,
    "broker_status": broker,
}
print(json.dumps(payload, ensure_ascii=True))
PY
  exit 0
fi

echo "AgentOS VM Appliance Status"
echo "==========================="
echo "Workspace: $WORKSPACE"
echo "Health summary:"
python3 - "$HEALTH_JSON" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
checks = payload.get("checks", {})
print(f"  overall: {'PASS' if payload.get('ok') else 'FAIL'}")
print(f"  doctor: {'PASS' if checks.get('doctor_ok') else 'FAIL'}")
print(f"  status: {'PASS' if checks.get('status_ok') else 'FAIL'}")
print(f"  preflight: {'PASS' if checks.get('preflight_ready') else 'FAIL'}")
print(f"  service: {'PASS' if checks.get('service_healthy') else 'FAIL'}")
print(f"  policy_ready: {'PASS' if checks.get('policy_ready_ok') else 'FAIL'}")
PY
echo "Runtime status:"
python3 - "$STATUS_JSON" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
runtime = payload.get("runtime_status", {})
setup = runtime.get("setup_state", {})
origin = runtime.get("session_origin", {})
print(f"  setup_status: {setup.get('status', 'unknown')}")
print(f"  next_managed_entry: {setup.get('next_managed_entry', 'unknown')}")
print(f"  session_origin: {origin.get('category', 'unknown')}")
PY
echo "Broker status:"
python3 - "$BROKER_JSON" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
print(f"  service_contract: {payload.get('service_contract', 'unknown')}")
print(f"  recent_events: {payload.get('recent_event_count', 0)}")
print(f"  recent_decisions: {payload.get('decision_event_count', 0)}")
PY
