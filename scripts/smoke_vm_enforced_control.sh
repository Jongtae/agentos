#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[vm-enforced] boot integration"
scripts/smoke_kernel_boot_integration.sh

echo "[vm-enforced] readiness + enforce"
scripts/smoke_kernel_policy_readiness.sh
scripts/smoke_kernel_policy_enforce_require_ready.sh

echo "[vm-enforced] recovery"
scripts/smoke_kernel_policy_recovery.sh

echo "vm enforced control smoke: PASS"
