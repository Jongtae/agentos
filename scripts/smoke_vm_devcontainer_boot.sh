#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f "$ROOT_DIR/.devcontainer/devcontainer.json" ]; then
  echo "[vm-smoke] missing .devcontainer/devcontainer.json"
  exit 1
fi

if [ ! -f "$ROOT_DIR/.devcontainer/Dockerfile" ]; then
  echo "[vm-smoke] missing .devcontainer/Dockerfile"
  exit 1
fi

echo "[vm-smoke] substrate profile detected"

scripts/demo_boot_flow.sh
scripts/smoke_kernel_boot_integration.sh
scripts/smoke_kernel_boot_rollback.sh
scripts/smoke_kernelctl_health.sh
scripts/smoke_kernelctl_audit.sh
scripts/smoke_kernelctl_repair.sh
scripts/smoke_kernelctl_repair_dry_run.sh
scripts/smoke_kernelctl_repair_selective.sh
scripts/smoke_kernelctl_repair_report_file.sh
scripts/smoke_kernelctl_repair_report_dir.sh
scripts/smoke_kernelctl_repair_report_retention.sh
scripts/smoke_kernelctl_report_status.sh
scripts/smoke_kernel_policy_enforce_require_ready.sh
scripts/smoke_vm_enforced_control.sh

# In Ubuntu VM environments with AppArmor tooling, run strict readiness mode as well.
if command -v apparmor_parser >/dev/null 2>&1; then
  scripts/smoke_kernel_policy_enforce_require_ready.sh --strict-apparmor
fi

echo "vm/devcontainer boot smoke: PASS"
