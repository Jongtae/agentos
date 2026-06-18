#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
PORT="${AGENTOS_DOCKER_APPROVAL_CENTER_SNAPSHOT_SMOKE_PORT:-18803}"
PID=""
cleanup() {
  if [ -n "$PID" ]; then
    kill "$PID" >/dev/null 2>&1 || true
    wait "$PID" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

AGENTOS_DOCKER_TELEGRAM_POLLING=false \
PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR/scripts:$ROOT_DIR" \
python3 scripts/docker_runtime_preview.py \
  --host 127.0.0.1 \
  --port "$PORT" \
  --workspace "$TMP_DIR/workspace" \
  --user-root "$TMP_DIR/user" \
  > "$TMP_DIR/server.log" 2>&1 &
PID="$!"

for _ in $(seq 1 20); do
  if curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null
curl -fsS "http://127.0.0.1:$PORT/" > "$TMP_DIR/home.html"
curl -fsS "http://127.0.0.1:$PORT/api/product" > "$TMP_DIR/product.json"
curl -fsS "http://127.0.0.1:$PORT/api/approvals" > "$TMP_DIR/approvals.json"

python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
home = (root / "home.html").read_text(encoding="utf-8")
product = json.loads((root / "product.json").read_text(encoding="utf-8"))
approvals = json.loads((root / "approvals.json").read_text(encoding="utf-8"))
snapshot = approvals["completion_snapshot"]

assert product["approval_center"]["completion_snapshot"]["schema_version"] == snapshot["schema_version"]
assert approvals["schema_version"] == "agentos-product-layer-approval-center.v1"
assert approvals["proof"]["approval_center_completion_snapshot_ready"] is True
assert snapshot["schema_version"] == "agentos-product-layer-approval-center-completion-snapshot.v1"
assert snapshot["state"] == "ready"

assert {item["id"] for item in snapshot["completed_local_proof"]} == {
    "approval_requirements_visible",
    "capability_permissions_mapped",
    "blocked_actions_preserved",
}
assert {item["id"] for item in snapshot["approval_paths"]} == {
    "setup_needed",
    "confirmation_needed",
    "observed_proof_needed",
    "blocked_by_policy",
}
gates = {item["id"]: item for item in snapshot["validation_gates"]}
assert gates["approval_center_snapshot_gate"]["command"] == "scripts/smoke_docker_approval_center_snapshot.sh"
assert gates["product_layer_completion_gate"]["command"] == "scripts/smoke_docker_product_layer_completion.sh"
assert gates["runtime_preview_python_gate"]["command"] == "scripts/smoke_docker_runtime_preview_python.sh"
assert {item["id"] for item in snapshot["blocked_stronger_proof"]} == {
    "approval_execution",
    "external_write_execution",
    "destructive_action_execution",
    "live_provider_execution",
    "vm_iso_approval_ownership",
}
assert snapshot["proof"] == {
    "customer_facing_approval_center_snapshot_ready": True,
    "docker_preview_ready": True,
    "approval_records_ready": True,
    "approval_execution_claimed": False,
    "external_write_claimed": False,
    "destructive_action_executed_by_default": False,
    "live_provider_proof_claimed": False,
    "boot_or_iso_proof_claimed": False,
    "automatic_claim_promotion": False,
}

assert "Approval Center Completion Snapshot" in home
assert "Approval Paths" in home
assert "scripts/smoke_docker_approval_center_snapshot.sh" in home
assert "Approval execution" in home
PY

echo "docker approval center snapshot smoke: PASS"
