#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
PORT="${AGENTOS_DOCKER_PROOF_REQUEST_SMOKE_PORT:-18820}"
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
curl -fsS "http://127.0.0.1:$PORT/api/proof-requests" > "$TMP_DIR/proof-requests.json"

python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
home = (root / "home.html").read_text(encoding="utf-8")
product = json.loads((root / "product.json").read_text(encoding="utf-8"))
product_map = json.loads((root / "product-map.json").read_text(encoding="utf-8"))
requests = json.loads((root / "proof-requests.json").read_text(encoding="utf-8"))

assert requests["schema_version"] == "agentos-product-layer-observed-proof-request-board.v1"
assert requests["surface"] == "Observed Proof Request Board"
assert requests["state"] == "ready"
assert product["observed_proof_request_board"]["schema_version"] == requests["schema_version"]
assert {feature["id"] for feature in product["features"]} >= {"observed_proof_request_board"}

request_ids = {item["id"] for item in requests["requests"]}
assert request_ids == {
    "docker_daemon_observed",
    "vm_iso_runtime_rejoin",
    "live_readonly_oauth",
    "live_browser_fallback",
    "release_trust",
    "hardware_attestation",
}
by_id = {item["id"]: item for item in requests["requests"]}
assert by_id["docker_daemon_observed"]["state"] == "requested_when_daemon_available"
assert by_id["docker_daemon_observed"]["validation_command"] == "scripts/smoke_docker_runtime_preview.sh"
assert by_id["vm_iso_runtime_rejoin"]["state"] == "blocked_until_observed_vm_run"
assert "managed runtime rejoin" in by_id["vm_iso_runtime_rejoin"]["accepted_evidence"]
assert by_id["live_readonly_oauth"]["state"] == "blocked_until_tester_credentials"
assert "Do not attach OAuth tokens" in by_id["live_readonly_oauth"]["redaction_rule"]
assert by_id["release_trust"]["state"] == "blocked_until_release_artifacts"
assert by_id["hardware_attestation"]["state"] == "blocked_until_device_evidence"

assert requests["request_policy"] == {
    "secret_material_allowed": False,
    "automatic_claim_promotion": False,
    "requires_sanitized_observed_evidence": True,
    "docker_local_proof_is_not_vm_iso_proof": True,
}
assert "scripts/smoke_docker_observed_proof_request_board.sh" in requests["validation_commands"]
assert requests["proof"] == {
    "customer_facing_observed_proof_requests_ready": True,
    "secret_material_allowed": False,
    "automatic_claim_promotion": False,
    "docker_daemon_observed_claimed": False,
    "boot_or_iso_proof_claimed": False,
    "live_oauth_claimed": False,
    "live_browser_proof_claimed": False,
    "release_trust_claimed": False,
    "external_mutation_claimed": False,
    "hardware_attestation_claimed": False,
}
assert "observed_proof_request_board" in product_map["recommended_path"]
surface_ids = {
    surface["id"]
    for group in product_map["surface_groups"]
    for surface in group.get("surfaces", [])
}
assert "observed_proof_request_board" in surface_ids

assert "Observed Proof Request Board" in home
assert "Request Policy" in home
assert "proof requests JSON" in home
PY

echo "docker observed proof request board smoke: PASS"
