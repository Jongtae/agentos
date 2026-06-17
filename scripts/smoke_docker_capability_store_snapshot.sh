#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
PORT="${AGENTOS_DOCKER_CAPABILITY_STORE_SNAPSHOT_SMOKE_PORT:-18802}"
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
curl -fsS "http://127.0.0.1:$PORT/api/capabilities" > "$TMP_DIR/capabilities.json"

python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
home = (root / "home.html").read_text(encoding="utf-8")
product = json.loads((root / "product.json").read_text(encoding="utf-8"))
capabilities = json.loads((root / "capabilities.json").read_text(encoding="utf-8"))
snapshot = capabilities["completion_snapshot"]

assert product["capability_store"]["completion_snapshot"]["schema_version"] == snapshot["schema_version"]
assert capabilities["schema_version"] == "agentos-product-layer-capability-store.v1"
assert capabilities["proof"]["capability_store_completion_snapshot_ready"] is True
assert snapshot["schema_version"] == "agentos-product-layer-capability-store-completion-snapshot.v1"
assert snapshot["state"] == "ready"

assert {item["id"] for item in snapshot["completed_local_proof"]} == {
    "permission_registry_loaded",
    "safe_local_capabilities_visible",
    "blocked_actions_visible",
}
assert {item["id"] for item in snapshot["capability_paths"]} == {
    "safe_read",
    "safe_write_user_owned",
    "external_read",
    "lifecycle_confirmed",
    "destructive_blocked",
}
gates = {item["id"]: item for item in snapshot["validation_gates"]}
assert gates["capability_store_snapshot_gate"]["command"] == "scripts/smoke_docker_capability_store_snapshot.sh"
assert gates["product_layer_completion_gate"]["command"] == "scripts/smoke_docker_product_layer_completion.sh"
assert gates["runtime_preview_python_gate"]["command"] == "scripts/smoke_docker_runtime_preview_python.sh"
assert {item["id"] for item in snapshot["blocked_stronger_proof"]} == {
    "external_write_execution",
    "destructive_action_execution",
    "live_provider_execution",
    "vm_iso_capability_ownership",
}
assert snapshot["proof"] == {
    "customer_facing_capability_store_snapshot_ready": True,
    "docker_preview_ready": True,
    "permission_registry_loaded": True,
    "safe_local_capabilities_ready": True,
    "external_write_claimed": False,
    "destructive_action_executed_by_default": False,
    "live_provider_proof_claimed": False,
    "boot_or_iso_proof_claimed": False,
    "automatic_claim_promotion": False,
}

assert "Capability Store Completion Snapshot" in home
assert "Capability Paths" in home
assert "scripts/smoke_docker_capability_store_snapshot.sh" in home
assert "Destructive action execution" in home
PY

echo "docker capability store snapshot smoke: PASS"
