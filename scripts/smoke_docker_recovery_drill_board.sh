#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
PORT="${AGENTOS_DOCKER_RECOVERY_DRILL_SMOKE_PORT:-18830}"
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
curl -fsS "http://127.0.0.1:$PORT/api/product-map" > "$TMP_DIR/product-map.json"
curl -fsS "http://127.0.0.1:$PORT/api/recovery-drills" > "$TMP_DIR/recovery-drills.json"

python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
home = (root / "home.html").read_text(encoding="utf-8")
product = json.loads((root / "product.json").read_text(encoding="utf-8"))
product_map = json.loads((root / "product-map.json").read_text(encoding="utf-8"))
drills = json.loads((root / "recovery-drills.json").read_text(encoding="utf-8"))

assert drills["schema_version"] == "agentos-product-layer-recovery-drill-board.v1"
assert drills["surface"] == "Recovery Drill Board"
assert drills["state"] == "ready"
assert product["recovery_drill_board"]["schema_version"] == drills["schema_version"]
assert {feature["id"] for feature in product["features"]} >= {"recovery_drill_board"}

drill_ids = {item["id"] for item in drills["drills"]}
assert drill_ids == {
    "preview_health_check",
    "runtime_preview_python_smoke",
    "product_layer_completion_recheck",
    "cleanup_policy_recheck",
    "vm_iso_rejoin_blocker_review",
    "live_adapter_recovery_review",
}
by_id = {item["id"]: item for item in drills["drills"]}
assert by_id["preview_health_check"]["command"] == "curl -fsS http://127.0.0.1:8787/healthz"
assert by_id["runtime_preview_python_smoke"]["command"] == "scripts/smoke_docker_runtime_preview_python.sh"
assert by_id["product_layer_completion_recheck"]["command"] == "scripts/smoke_docker_product_layer_completion.sh"
assert "cleanup_temp_artifacts.py" in by_id["cleanup_policy_recheck"]["command"]
assert by_id["vm_iso_rejoin_blocker_review"]["state"] == "blocked_until_observed_vm_run"
assert by_id["live_adapter_recovery_review"]["state"] == "blocked_until_tester_credentials"
assert "VM/ISO boot" in by_id["vm_iso_rejoin_blocker_review"]["claim_boundary"]
assert "live OAuth" in by_id["live_adapter_recovery_review"]["claim_boundary"]

assert "scripts/smoke_docker_recovery_drill_board.sh" in drills["validation_commands"]
assert drills["proof"] == {
    "customer_facing_recovery_drills_ready": True,
    "docker_main_try_path": True,
    "docker_daemon_observed_claimed": False,
    "boot_or_iso_proof_claimed": False,
    "live_oauth_claimed": False,
    "live_browser_proof_claimed": False,
    "release_trust_claimed": False,
    "external_mutation_claimed": False,
    "hardware_attestation_claimed": False,
}
assert "recovery_drill_board" in product_map["recommended_path"]
surface_ids = {
    surface["id"]
    for group in product_map["surface_groups"]
    for surface in group.get("surfaces", [])
}
assert "recovery_drill_board" in surface_ids
routes = {route["id"]: route["route"] for route in product_map["reviewer_routes"]}
assert "recovery_drill_board" in routes["runtime_evaluator"]
assert "recovery_drill_board" in routes["trust_reviewer"]

assert "Recovery Drill Board" in home
assert "Drill Validation" in home
assert "recovery drills JSON" in home
PY

echo "docker recovery drill board smoke: PASS"
