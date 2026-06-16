#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
PORT="${AGENTOS_DOCKER_PRODUCT_MAP_SMOKE_PORT:-18797}"
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

python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
home = (root / "home.html").read_text(encoding="utf-8")
product = json.loads((root / "product.json").read_text(encoding="utf-8"))
product_map = json.loads((root / "product-map.json").read_text(encoding="utf-8"))

assert product_map["schema_version"] == "agentos-product-layer-map.v1"
assert product_map["surface"] == "Product Layer Map"
assert product_map["state"] == "ready"
assert product["product_map"]["schema_version"] == product_map["schema_version"]
assert {feature["id"] for feature in product["features"]} >= {"product_map"}

groups = {group["id"]: group for group in product_map["surface_groups"]}
assert set(groups) == {
    "start_here",
    "do_work",
    "prove_and_handoff",
    "blocked_until_observed",
}
assert [surface["id"] for surface in groups["start_here"]["surfaces"]] == [
    "runtime_home",
    "onboarding_status",
    "guided_demo_journey",
]
assert {surface["id"] for surface in groups["do_work"]["surfaces"]} >= {
    "work_inbox",
    "activity_timeline",
    "capability_store",
    "approval_center",
}
assert {surface["id"] for surface in groups["prove_and_handoff"]["surfaces"]} >= {
    "evidence_dashboard",
    "customer_proof_packet",
    "customer_handoff_bundle",
    "proof_promotion_center",
}
assert {surface["id"] for surface in groups["blocked_until_observed"]["surfaces"]} >= {
    "recovery_center",
    "observed_proof_uploader",
    "release_trust_panel",
    "attestation_status",
}
assert product_map["recommended_path"][:3] == [
    "runtime_home",
    "onboarding_status",
    "guided_demo_journey",
]
assert "proof_promotion_center" in product_map["recommended_path"]
routes = {route["id"]: route for route in product_map["reviewer_routes"]}
assert set(routes) == {
    "runtime_evaluator",
    "proof_reviewer",
    "capability_reviewer",
    "trust_reviewer",
}
assert routes["runtime_evaluator"]["route"] == [
    "runtime_home",
    "onboarding_status",
    "guided_demo_journey",
    "activity_timeline",
    "recovery_center",
]
assert "VM/ISO" in routes["runtime_evaluator"]["claim_boundary"]
assert routes["proof_reviewer"]["route"] == [
    "evidence_dashboard",
    "customer_proof_packet",
    "customer_handoff_bundle",
    "proof_promotion_center",
]
assert "sanitized observed evidence" in routes["proof_reviewer"]["claim_boundary"]
assert routes["capability_reviewer"]["route"] == [
    "work_inbox",
    "capability_store",
    "approval_center",
    "activity_timeline",
]
assert "external writes" in routes["capability_reviewer"]["claim_boundary"]
assert routes["trust_reviewer"]["route"] == [
    "observed_proof_uploader",
    "release_trust_panel",
    "attestation_status",
    "recovery_center",
]
assert "hardware trust proof" in routes["trust_reviewer"]["claim_boundary"]
assert product_map["proof"] == {
    "customer_facing_product_map_ready": True,
    "docker_main_try_path": True,
    "boot_or_iso_proof_claimed": False,
    "live_oauth_claimed": False,
    "live_browser_proof_claimed": False,
    "release_trust_claimed": False,
    "external_mutation_claimed": False,
    "hardware_attestation_claimed": False,
}

assert "Product Layer Map" in home
assert "Recommended Path" in home
assert "Reviewer Routes" in home
assert "Runtime evaluator" in home
assert "Trust reviewer" in home
assert "product map JSON" in home
assert "Prove and hand off" in home
assert "Blocked until observed" in home
PY

echo "docker product layer map smoke: PASS"
