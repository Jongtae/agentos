#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
PORT="${AGENTOS_DOCKER_PROOF_PACKET_SMOKE_PORT:-18791}"
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
curl -fsS "http://127.0.0.1:$PORT/api/proof-packet" > "$TMP_DIR/proof-packet.json"

python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
home = (root / "home.html").read_text(encoding="utf-8")
product = json.loads((root / "product.json").read_text(encoding="utf-8"))
packet = json.loads((root / "proof-packet.json").read_text(encoding="utf-8"))

assert packet["schema_version"] == "agentos-product-layer-customer-proof-packet.v1"
assert packet["surface"] == "Customer Proof Packet"
assert packet["state"] == "ready"
assert product["customer_proof_packet"]["schema_version"] == packet["schema_version"]
assert {feature["id"] for feature in product["features"]} >= {"customer_proof_packet"}

claim_ids = {item["id"] for item in packet["completed_claims"]}
assert claim_ids >= {
    "docker-runtime-preview-ready",
    "product-layer-surfaces-ready",
    "guided-demo-path-ready",
    "golden-runtime-loop-ready",
}
assert set(packet["validation_commands"]) >= {
    "docker compose config",
    "scripts/smoke_docker_runtime_preview_python.sh",
    "scripts/smoke_docker_product_layer_completion.sh",
    "scripts/smoke_docker_guided_demo_journey.sh",
    "scripts/smoke_phase2_golden_demo.sh",
}
assert packet["proof_sources"] == {
    "onboarding_status": "agentos-product-layer-onboarding-status.v1",
    "guided_demo_journey": "agentos-product-layer-guided-demo-journey.v1",
    "evidence_dashboard": "agentos-product-layer-evidence-dashboard.v1",
    "recovery_center": "agentos-product-layer-recovery-center.v1",
}
assert {item["id"] for item in packet["non_claims"]} >= {
    "vm-iso-boot-proof",
    "live-oauth-proof",
    "live-browser-proof",
    "release-trust-proof",
    "hardware-attestation-proof",
}
assert {item["id"] for item in packet["next_blockers"]} >= {
    "vm-iso-observed-proof",
    "live-oauth-proof",
    "live-browser-proof",
    "release-trust-proof",
    "attestation-proof",
}
assert packet["proof"]["docker_preview_ready"] is True
assert packet["proof"]["customer_packet_ready"] is True
assert packet["proof"]["shareable_summary_ready"] is True
assert packet["proof"]["boot_or_iso_proof_claimed"] is False
assert packet["proof"]["live_oauth_claimed"] is False
assert packet["proof"]["live_browser_proof_claimed"] is False
assert packet["proof"]["release_trust_claimed"] is False
assert packet["proof"]["external_mutation_claimed"] is False
assert packet["proof"]["hardware_attestation_claimed"] is False
assert packet["proof"]["claim_promotion_automatic"] is False

assert "Customer Proof Packet" in home
assert "Packet Validation" in home
assert "proof packet JSON" in home
PY

echo "docker customer proof packet smoke: PASS"
