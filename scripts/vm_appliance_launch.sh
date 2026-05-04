#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="${DEFAULT_WORKSPACE:-$ROOT_DIR/workspaces/default}"
SNAPSHOT_LABEL="${AGENTOS_VM_SNAPSHOT_LABEL:-agentos-demo-clean}"
UTM_VM_NAME="${AGENTOS_UTM_VM_NAME:-}"
DRY_RUN=0
SKIP_BOOTSTRAP=0

usage() {
  cat <<'USAGE'
Usage:
  scripts/vm_appliance_launch.sh [--workspace <path>] [--snapshot-label <label>] [--dry-run] [--skip-bootstrap] [--utm-vm-name <name>]

Purpose:
  Print the AgentOS VM appliance contract and hand off to the standard VM demo flow.

Notes:
  - `--dry-run` previews the contract and launch sequence.
  - `--skip-bootstrap` is forwarded to `scripts/vm_demo_flow.sh`.
  - `--utm-vm-name` forwards to the macOS UTM/utmctl observation path.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --workspace)
      shift
      WORKSPACE="${1:-}"
      ;;
    --snapshot-label)
      shift
      SNAPSHOT_LABEL="${1:-}"
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    --skip-bootstrap)
      SKIP_BOOTSTRAP=1
      ;;
    --utm-vm-name)
      shift
      UTM_VM_NAME="${1:-}"
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

echo "AgentOS VM Appliance Launch"
echo "==========================="
echo "Workspace: $WORKSPACE"
echo "Snapshot label: $SNAPSHOT_LABEL"
if [ -n "$UTM_VM_NAME" ]; then
  echo "UTM VM name: $UTM_VM_NAME"
fi
echo "Manifest:"
python3 "$ROOT_DIR/scripts/vm_appliance_manifest.py" \
  --workspace "$WORKSPACE" \
  --snapshot-label "$SNAPSHOT_LABEL" \
  --json

flow_args=(--workspace "$WORKSPACE")
if [ -n "$UTM_VM_NAME" ]; then
  flow_args+=(--utm-vm-name "$UTM_VM_NAME")
fi
if [ "$DRY_RUN" -eq 1 ]; then
  flow_args+=(--dry-run)
fi
if [ "$SKIP_BOOTSTRAP" -eq 1 ]; then
  flow_args+=(--skip-bootstrap)
fi

echo
echo "Hand-off:"
echo "  scripts/vm_demo_flow.sh ${flow_args[*]}"

"$ROOT_DIR/scripts/vm_demo_flow.sh" "${flow_args[@]}"
