#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
PORT="${AGENTOS_DOCKER_RUNTIME_HOME_SNAPSHOT_SMOKE_PORT:-18799}"
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

python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
home = (root / "home.html").read_text(encoding="utf-8")
product = json.loads((root / "product.json").read_text(encoding="utf-8"))
snapshot = product["completion_snapshot"]

assert product["schema_version"] == "agentos-product-layer-runtime-home.v1"
assert product["proof"]["runtime_home_completion_snapshot_ready"] is True
assert snapshot["schema_version"] == "agentos-product-layer-runtime-home-completion-snapshot.v1"
assert snapshot["surface"] == "Runtime Home Completion Snapshot"
assert snapshot["state"] == "ready"

completed = {item["id"]: item for item in snapshot["completed_local_proof"]}
assert set(completed) == {
    "docker_runtime_home_visible",
    "customer_path_available",
    "proof_boundaries_visible",
}
assert "/api/product" in completed["docker_runtime_home_visible"]["evidence"]
assert "/api/product-map" in completed["customer_path_available"]["evidence"]
assert "/api/proof-promotion" in completed["proof_boundaries_visible"]["evidence"]

gates = {item["id"]: item for item in snapshot["validation_gates"]}
assert gates["runtime_home_snapshot_gate"]["command"] == "scripts/smoke_docker_runtime_home_snapshot.sh"
assert gates["product_layer_completion_gate"]["command"] == "scripts/smoke_docker_product_layer_completion.sh"
assert gates["runtime_preview_python_gate"]["command"] == "scripts/smoke_docker_runtime_preview_python.sh"
assert gates["compose_config_gate"]["command"] == "docker compose config"

surfaces = {item["id"]: item for item in snapshot["review_surfaces"]}
assert set(surfaces) >= {
    "start_here",
    "guided_path",
    "preview_readiness",
    "product_map",
    "next_work",
    "recovery_drills",
    "session_report",
}
assert surfaces["start_here"]["source"] == "/api/product"
assert surfaces["session_report"]["source"] == "/api/session-report"

blocked = {item["id"]: item for item in snapshot["blocked_stronger_proof"]}
assert set(blocked) == {
    "docker_daemon_observed",
    "vm_iso_runtime_rejoin",
    "live_readonly_oauth",
    "release_browser_attestation",
}
assert blocked["docker_daemon_observed"]["state"] == "blocked_until_daemon_available"
assert blocked["vm_iso_runtime_rejoin"]["state"] == "blocked_until_observed_vm_run"

assert snapshot["proof"] == {
    "customer_facing_runtime_home_snapshot_ready": True,
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

assert "Runtime Home Completion Snapshot" in home
assert "Completed Local Proof" in home
assert "Validation Gates" in home
assert "Blocked Stronger Proof" in home
assert "scripts/smoke_docker_runtime_home_snapshot.sh" in home
assert "Docker Runtime Home is visible" in home
PY

echo "docker runtime home snapshot smoke: PASS"
