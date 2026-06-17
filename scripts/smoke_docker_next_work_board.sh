#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
PORT="${AGENTOS_DOCKER_NEXT_WORK_SMOKE_PORT:-18810}"
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
curl -fsS "http://127.0.0.1:$PORT/api/next-work" > "$TMP_DIR/next-work.json"

python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
home = (root / "home.html").read_text(encoding="utf-8")
product = json.loads((root / "product.json").read_text(encoding="utf-8"))
product_map = json.loads((root / "product-map.json").read_text(encoding="utf-8"))
next_work = json.loads((root / "next-work.json").read_text(encoding="utf-8"))

assert next_work["schema_version"] == "agentos-product-layer-next-work-board.v1"
assert next_work["surface"] == "Next Work Board"
assert next_work["state"] == "ready"
assert product["next_work_board"]["schema_version"] == next_work["schema_version"]
assert {feature["id"] for feature in product["features"]} >= {"next_work_board"}

completed = {item["id"]: item for item in next_work["completed_product_proof"]}
assert set(completed) >= {
    "docker_product_layer_surfaces",
    "docker_customer_handoff",
    "runtime_truthfulness_gates",
}
assert completed["docker_product_layer_surfaces"]["state"] == "completed_local_proof"
assert "/api/product-map" in completed["docker_product_layer_surfaces"]["evidence"]

candidates = {item["id"]: item for item in next_work["safe_next_candidates"]}
assert set(candidates) == {
    "docker_daemon_observed_run",
    "live_readonly_provider_proof",
    "vm_iso_runtime_rejoin_proof",
    "release_and_attestation_evidence",
}
assert candidates["docker_daemon_observed_run"]["state"] == "ready_when_daemon_available"
assert "scripts/smoke_docker_runtime_preview.sh" in candidates["docker_daemon_observed_run"]["validation"]
assert candidates["live_readonly_provider_proof"]["state"] == "blocked_until_tester_credentials"
assert "live_oauth_credentials_missing" in candidates["live_readonly_provider_proof"]["blocked_by"]
assert candidates["vm_iso_runtime_rejoin_proof"]["state"] == "blocked_until_observed_vm_run"
assert "vm_iso_observed_run_missing" in candidates["vm_iso_runtime_rejoin_proof"]["blocked_by"]

blocked = {item["id"]: item for item in next_work["blocked_tracks"]}
assert set(blocked) == {"vm_iso", "live_oauth", "live_browser", "release", "hardware_attestation"}
assert blocked["vm_iso"]["state"] == "blocked_until_observed_vm_run"
assert blocked["release"]["state"] == "blocked_until_release_artifacts"

assert "scripts/smoke_docker_next_work_board.sh" in next_work["validation_commands"]
assert "scripts/smoke_docker_product_layer_completion.sh" in next_work["validation_commands"]
assert next_work["proof"] == {
    "customer_facing_next_work_ready": True,
    "docker_main_try_path": True,
    "docker_daemon_observed_claimed": False,
    "boot_or_iso_proof_claimed": False,
    "live_oauth_claimed": False,
    "live_browser_proof_claimed": False,
    "release_trust_claimed": False,
    "external_mutation_claimed": False,
    "hardware_attestation_claimed": False,
    "automatic_claim_promotion": False,
}

assert "next_work_board" in product_map["recommended_path"]
surface_ids = {
    surface["id"]
    for group in product_map["surface_groups"]
    for surface in group.get("surfaces", [])
}
assert "next_work_board" in surface_ids

assert "Next Work Board" in home
assert "Safe Next Candidates" in home
assert "Blocked Tracks" in home
assert "next work JSON" in home
PY

echo "docker next work board smoke: PASS"
