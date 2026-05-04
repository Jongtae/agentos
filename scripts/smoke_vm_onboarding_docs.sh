#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT_DIR"

check() {
  local file=$1
  local pattern=$2
  if ! rg -q --fixed-strings "$pattern" "$file"; then
    echo "missing pattern in $file: $pattern" >&2
    exit 1
  fi
}

check README.md "brew install --cask utm"
check README.md "AgentOS Setup -> AgentOS Managed Session -> ai>"
check README.md "vm-install-quickstart.md"
check docs/runbooks/vm-install-quickstart.md 'Do not use an `ARM64` guest with the current `amd64` AgentOS ISO.'
check docs/runbooks/vm-install-quickstart.md "Your first goal is not \"install Ubuntu Server\"."
check docs/runbooks/vm-install-quickstart.md "AgentOS Recovery"
check docs/runbooks/vm-install-guide.md "Install UTM with Homebrew:"
check docs/runbooks/vm-install-guide.md "Emulate -> x86_64"
check docs/runbooks/vm-install-guide.md "you are not preparing to manually install Ubuntu as the main experience"
check docs/runbooks/vm-install-guide.md "install later if you want persistence"
check docs/runbooks/distribution-packaging-runbook.md "This runbook is the advanced/fallback reference."
check docs/runbooks/distribution-packaging-runbook.md "If you simply want to try AgentOS in a VM, do not start here."

echo "vm onboarding docs smoke: PASS"
