#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="${DEFAULT_WORKSPACE:-$ROOT_DIR/workspaces/default}"
DRY_RUN=0
SKIP_BOOTSTRAP=0
UTM_VM_NAME="${AGENTOS_UTM_VM_NAME:-}"
SESSION_ID="${AGENTOS_SESSION_ID:-}"

usage() {
  cat <<'USAGE'
Usage:
  scripts/vm_demo_flow.sh [--workspace <path>] [--dry-run] [--skip-bootstrap] [--utm-vm-name <name>]

Purpose:
  Reproduce the clean AgentOS VM demo path:
  boot AgentOS -> tiny setup -> ai>

Current implementation note:
  substrate bootstrap and boot-integration checks still exist underneath as compatibility helpers,
  but the user-facing demo story is appliance-first.

Notes:
  - Use `--dry-run` on non-Ubuntu hosts to preview the contract without executing VM-only steps.
  - Use `--skip-bootstrap` when the Ubuntu substrate prerequisites are already installed.
  - Use `--utm-vm-name` to switch to the macOS UTM/utmctl observation path.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --workspace)
      shift
      WORKSPACE="${1:-}"
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

if [ -n "$UTM_VM_NAME" ]; then
  echo "AgentOS VM Demo Flow"
  echo "===================="
  echo "Workspace: $WORKSPACE"
  echo "Goal: boot AgentOS -> tiny setup -> ai>"
  echo "UTM VM name: $UTM_VM_NAME"
  echo "Observation helper: $ROOT_DIR/scripts/vm_utmctl_observation.py --vm-name $UTM_VM_NAME --workspace $WORKSPACE${SESSION_ID:+ --session-id $SESSION_ID}"
  utm_args=(--vm-name "$UTM_VM_NAME" --workspace "$WORKSPACE")
  if [ -n "$SESSION_ID" ]; then
    utm_args+=(--session-id "$SESSION_ID")
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    "$ROOT_DIR/scripts/vm_utmctl_observation.py" "${utm_args[@]}" --dry-run
    echo "vm demo flow dry-run: PASS"
  else
    "$ROOT_DIR/scripts/vm_utmctl_observation.py" "${utm_args[@]}"
    echo "vm demo flow: PASS"
  fi
  exit 0
fi

run_step() {
  local description="$1"
  shift
  echo "==> $description"
  echo "    $*"
  if [ "$DRY_RUN" -eq 1 ]; then
    return 0
  fi
  "$@"
}

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

if [ "$DRY_RUN" -eq 0 ] && ! command -v apt-get >/dev/null 2>&1; then
  echo "vm_demo_flow.sh targets an Ubuntu/Debian substrate. Re-run with --dry-run on non-Ubuntu hosts." >&2
  exit 1
fi

echo "AgentOS VM Demo Flow"
echo "===================="
echo "Workspace: $WORKSPACE"
echo "Goal: boot AgentOS -> tiny setup -> ai>"
echo "Appliance manifest: $ROOT_DIR/scripts/vm_appliance_manifest.py --workspace $WORKSPACE --snapshot-label agentos-demo-clean --json"

if [ "$SKIP_BOOTSTRAP" -eq 0 ]; then
  run_step "Bootstrap Ubuntu substrate prerequisites" "$ROOT_DIR/scripts/bootstrap_ubuntu.sh"
  run_step "Validate Codex CLI bootstrap" "$ROOT_DIR/scripts/bootstrap_codex_cli.sh"
fi

run_step "Run substrate doctor (compatibility preflight)" "$ROOT_DIR/scripts/vm_substrate_doctor.sh" "$WORKSPACE"

if [ "$DRY_RUN" -eq 0 ] && [ "$(id -u)" -eq 0 ]; then
  run_step "Install AgentOS boot integration assets" "$ROOT_DIR/scripts/install_kernel_boot_integration.sh"
else
  run_shell_step "Install AgentOS boot integration assets" "cd '$ROOT_DIR' && sudo scripts/install_kernel_boot_integration.sh"
fi

run_step "Verify kernel boot integration" "$ROOT_DIR/scripts/smoke_kernel_boot_integration.sh"
run_step "Verify managed session health" "$ROOT_DIR/scripts/smoke_kernelctl_health.sh"
run_step "Verify managed session status surface" "$ROOT_DIR/scripts/smoke_kernelctl_status_json.sh"

echo
echo "Next VM demo steps:"
echo "  1. Boot the default AgentOS appliance path."
echo "  2. Let AgentOS Setup appear."
echo "  3. Complete tiny setup and confirm the next managed entry goes to ai>."
echo "  4. Only choose install when you want persistence."
echo "  5. Run: scripts/agentos-kernelctl health --workspace $WORKSPACE"
echo "  6. Run: scripts/agentos-kernelctl status --workspace $WORKSPACE --json"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "vm demo flow dry-run: PASS"
else
  echo "vm demo flow: PASS"
fi
