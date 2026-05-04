#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

"$ROOT_DIR/scripts/smoke_broker_managed_exec.sh"
"$ROOT_DIR/scripts/smoke_broker_approval_mediation.sh"
"$ROOT_DIR/scripts/smoke_broker_event_fabric.sh"
"$ROOT_DIR/scripts/smoke_broker_session_entry.sh"
"$ROOT_DIR/scripts/smoke_broker_recovery_contract.sh"
"$ROOT_DIR/scripts/smoke_broker_status.sh"
bash "$ROOT_DIR/scripts/smoke_broker_operator_actions.sh"
bash "$ROOT_DIR/scripts/smoke_broker_install_paths.sh"
bash "$ROOT_DIR/scripts/smoke_broker_expanded_scope_recovery.sh"

echo "broker control smoke suite ok"
