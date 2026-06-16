#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
PORT="${AGENTOS_DOCKER_PROOF_PROMOTION_SMOKE_PORT:-18796}"
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
curl -fsS "http://127.0.0.1:$PORT/api/proof-promotion" > "$TMP_DIR/proof-promotion.json"

python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
home = (root / "home.html").read_text(encoding="utf-8")
product = json.loads((root / "product.json").read_text(encoding="utf-8"))
promotion = json.loads((root / "proof-promotion.json").read_text(encoding="utf-8"))

assert promotion["schema_version"] == "agentos-product-layer-proof-promotion-center.v1"
assert promotion["surface"] == "Proof Promotion Center"
assert promotion["state"] == "ready"
assert product["proof_promotion_center"]["schema_version"] == promotion["schema_version"]
assert {feature["id"] for feature in product["features"]} >= {"proof_promotion_center"}

decisions = {item["id"]: item for item in promotion["promotion_decisions"]}
assert set(decisions) == {
    "docker-local-product-layer",
    "docker-daemon-observed-run",
    "vm-iso-runtime-ownership",
    "live-provider-readonly",
    "live-browser-release-attestation",
}
assert decisions["docker-local-product-layer"]["state"] == "ready_to_describe"
assert decisions["docker-daemon-observed-run"]["state"] == "blocked_until_observed_docker_daemon"
assert decisions["vm-iso-runtime-ownership"]["state"] == "blocked_until_observed_vm_iso"
assert decisions["live-provider-readonly"]["state"] == "blocked_until_live_credentials"
assert decisions["live-browser-release-attestation"]["state"] == "blocked_until_specialized_observed_evidence"

checklist = {item["id"]: item for item in promotion["sharing_checklist"]}
assert set(checklist) == {
    "describe_docker_local_product_layer",
    "include_validation_commands",
    "attach_source_surfaces",
    "withhold_stronger_claims",
}
assert checklist["describe_docker_local_product_layer"]["state"] == "share_ready"
assert checklist["include_validation_commands"]["state"] == "share_ready"
assert checklist["attach_source_surfaces"]["state"] == "share_ready"
assert checklist["withhold_stronger_claims"]["state"] == "blocked_until_observed_evidence"
assert "VM/ISO boot ownership" in checklist["describe_docker_local_product_layer"]["blocked_claim"]
assert "full Docker daemon proof" in checklist["include_validation_commands"]["blocked_claim"]
assert "private credentials" in checklist["attach_source_surfaces"]["blocked_claim"]
assert "auto-promote Docker-local proof" in checklist["withhold_stronger_claims"]["blocked_claim"]

assert promotion["source_surfaces"] == {
    "evidence_dashboard": "agentos-product-layer-evidence-dashboard.v1",
    "recovery_center": "agentos-product-layer-recovery-center.v1",
    "customer_proof_packet": "agentos-product-layer-customer-proof-packet.v1",
    "customer_handoff_bundle": "agentos-product-layer-customer-handoff-bundle.v1",
}
assert promotion["share_policy"] == {
    "secret_material_allowed": False,
    "automatic_claim_promotion": False,
    "requires_sanitized_observed_evidence_for_stronger_claims": True,
}
assert promotion["proof"]["docker_local_claims_ready"] is True
assert promotion["proof"]["docker_daemon_observed_claimed"] is False
assert promotion["proof"]["boot_or_iso_proof_claimed"] is False
assert promotion["proof"]["live_oauth_claimed"] is False
assert promotion["proof"]["live_browser_proof_claimed"] is False
assert promotion["proof"]["release_trust_claimed"] is False
assert promotion["proof"]["external_mutation_claimed"] is False
assert promotion["proof"]["hardware_attestation_claimed"] is False
assert promotion["proof"]["customer_facing_proof_promotion_ready"] is True

assert "Proof Promotion Center" in home
assert "Promotion Policy" in home
assert "proof promotion JSON" in home
assert "Automatic claim promotion" in home
assert "Stronger claims require observed evidence" in home
assert "Proof Sharing Checklist" in home
assert "Describe Docker-local Product Layer" in home
assert "Withhold stronger claims" in home
PY

echo "docker proof promotion center smoke: PASS"
