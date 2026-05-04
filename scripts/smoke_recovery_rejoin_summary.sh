#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

SUMMARY="AgentOS Recovery -> Return to AgentOS -> ai>"
DETAIL="AgentOS Recovery -> AgentOS Setup -> AgentOS Managed Session -> ai>"

rg -q "$SUMMARY" README.md
rg -q "$SUMMARY" docs/runbooks/vm-install-quickstart.md
rg -q "$SUMMARY" docs/runbooks/vm-install-guide.md
rg -q "$SUMMARY" docs/runbooks/agentos-operations-runbook.md
rg -q "$SUMMARY" scripts/agentos-firstrun
rg -q "$SUMMARY" scripts/install_kernel_boot_integration.sh
rg -q "$SUMMARY" scripts/agentos-kernelctl
rg -q "$SUMMARY" docs/reference/agentos-recovery-path-contract-v1.md
rg -q "$DETAIL" docs/runbooks/agentos-operations-runbook.md
rg -q "$DETAIL" docs/reference/agentos-recovery-path-contract-v1.md

echo "recovery rejoin summary smoke: PASS"
