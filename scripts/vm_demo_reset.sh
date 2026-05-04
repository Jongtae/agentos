#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="${DEFAULT_WORKSPACE:-$ROOT_DIR/workspaces/default}"
USER_HOME="${HOME:-$ROOT_DIR}"
SNAPSHOT_LABEL="${AGENTOS_VM_SNAPSHOT_LABEL:-agentos-demo-clean}"
DRY_RUN=0

usage() {
  cat <<'USAGE'
Usage:
  scripts/vm_demo_reset.sh [--workspace <path>] [--user-home <path>] [--snapshot-label <label>] [--dry-run]

Purpose:
  Reset the AgentOS VM demo path back to a clean setup state by:
  - clearing first-run completion
  - removing boot integration assets
  - reinstalling boot integration assets
  - printing recommended VM snapshot labels
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --workspace)
      shift
      WORKSPACE="${1:-}"
      ;;
    --user-home)
      shift
      USER_HOME="${1:-}"
      ;;
    --snapshot-label)
      shift
      SNAPSHOT_LABEL="${1:-}"
      ;;
    --dry-run)
      DRY_RUN=1
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

run_shell_step() {
  local description="$1"
  local command_line="$2"
  echo "==> $description"
  echo "    $command_line"
  if [ "$DRY_RUN" -eq 1 ]; then
    return 0
  fi
  /bin/sh -lc "$command_line"
}

echo "AgentOS VM Demo Reset"
echo "====================="
echo "Workspace: $WORKSPACE"
echo "User home: $USER_HOME"
echo "Recommended snapshot label: $SNAPSHOT_LABEL"
echo "Appliance manifest: $ROOT_DIR/scripts/vm_appliance_manifest.py --workspace $WORKSPACE --snapshot-label $SNAPSHOT_LABEL --json"

run_shell_step "Reset AgentOS setup state" "cd '$ROOT_DIR' && scripts/agentos-kernelctl firstrun-reset --workspace '$WORKSPACE' --user-home '$USER_HOME'"

if [ "$DRY_RUN" -eq 0 ] && [ "$(id -u)" -eq 0 ]; then
  run_shell_step "Remove AgentOS boot integration assets" "cd '$ROOT_DIR' && scripts/uninstall_kernel_boot_integration.sh"
  run_shell_step "Reinstall AgentOS boot integration assets" "cd '$ROOT_DIR' && scripts/install_kernel_boot_integration.sh"
else
  run_shell_step "Remove AgentOS boot integration assets" "cd '$ROOT_DIR' && sudo scripts/uninstall_kernel_boot_integration.sh"
  run_shell_step "Reinstall AgentOS boot integration assets" "cd '$ROOT_DIR' && sudo scripts/install_kernel_boot_integration.sh"
fi

echo
echo "Recommended hypervisor actions:"
echo "  1. Save or rename the clean snapshot as: $SNAPSHOT_LABEL"
echo "  2. Reboot the VM and confirm AgentOS Setup appears again."
echo "  3. Run: scripts/vm_demo_flow.sh --workspace $WORKSPACE --skip-bootstrap"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "vm demo reset dry-run: PASS"
else
  echo "vm demo reset: PASS"
fi
