#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
PORT="${AGENTOS_DOCKER_CUSTOMER_HANDOFF_SMOKE_PORT:-18795}"
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
curl -fsS "http://127.0.0.1:$PORT/api/customer-handoff" > "$TMP_DIR/customer-handoff.json"

python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
home = (root / "home.html").read_text(encoding="utf-8")
product = json.loads((root / "product.json").read_text(encoding="utf-8"))
handoff = json.loads((root / "customer-handoff.json").read_text(encoding="utf-8"))

assert handoff["schema_version"] == "agentos-product-layer-customer-handoff-bundle.v1"
assert handoff["surface"] == "Customer Handoff Bundle"
assert handoff["state"] == "ready"
assert product["customer_handoff_bundle"]["schema_version"] == handoff["schema_version"]
assert {feature["id"] for feature in product["features"]} >= {"customer_handoff_bundle"}

assert handoff["try_path"] == {
    "command": "docker compose up --build",
    "url": "http://localhost:8787",
    "first_prompt": "status",
    "docker_is_default_public_try_path": True,
}
checklist = {item["id"]: item["state"] for item in handoff["handoff_checklist"]}
assert checklist == {
    "run_preview": "ready",
    "open_runtime_home": "ready",
    "inspect_guided_path": "ready",
    "run_validation_commands": "ready",
    "record_remaining_blockers": "blocked_until_observed_evidence",
}
report = handoff["handoff_report"]
assert report["schema_version"] == "agentos-product-layer-customer-handoff-report.v1"
assert report["title"] == "Docker customer handoff report"
assert {item["id"] for item in report["sections"]} == {
    "reproduced_try_path",
    "inspected_product_surfaces",
    "local_validation_evidence",
    "remaining_observed_proof_blockers",
    "share_safe_non_claims",
}
assert {item["id"]: item["state"] for item in report["sections"]}["remaining_observed_proof_blockers"] == "blocked_until_observed_evidence"
assert report["share_policy"] == {
    "safe_to_share_without_secrets": True,
    "secret_material_allowed": False,
    "automatic_claim_promotion": False,
    "requires_sanitized_observed_evidence_for_stronger_claims": True,
}
assert {item["id"] for item in handoff["inspect_surfaces"]} >= {
    "runtime_home",
    "onboarding_status",
    "guided_demo_journey",
    "customer_proof_packet",
    "recovery_center",
    "evidence_dashboard",
}
assert set(handoff["validation_commands"]) >= {
    "docker compose config",
    "scripts/smoke_docker_customer_handoff_bundle.sh",
    "scripts/smoke_docker_runtime_preview_python.sh",
    "scripts/smoke_docker_product_layer_completion.sh",
    "scripts/smoke_phase2_golden_demo.sh",
}
assert handoff["handoff_sources"] == {
    "onboarding_status": "agentos-product-layer-onboarding-status.v1",
    "guided_demo_journey": "agentos-product-layer-guided-demo-journey.v1",
    "customer_proof_packet": "agentos-product-layer-customer-proof-packet.v1",
    "recovery_center": "agentos-product-layer-recovery-center.v1",
}
assert {item["id"] for item in handoff["next_blockers"]} >= {
    "vm-iso-observed-proof",
    "live-oauth-proof",
    "live-browser-proof",
    "release-trust-proof",
    "attestation-proof",
}
assert handoff["proof"]["docker_main_try_path"] is True
assert handoff["proof"]["customer_handoff_ready"] is True
assert handoff["proof"]["boot_or_iso_proof_claimed"] is False
assert handoff["proof"]["live_oauth_claimed"] is False
assert handoff["proof"]["live_browser_proof_claimed"] is False
assert handoff["proof"]["release_trust_claimed"] is False
assert handoff["proof"]["external_mutation_claimed"] is False
assert handoff["proof"]["hardware_attestation_claimed"] is False

assert "Customer Handoff Bundle" in home
assert "Handoff Surfaces" in home
assert "Handoff Checklist" in home
assert "Handoff Report" in home
assert "Handoff Validation" in home
assert "Record remaining proof blockers" in home
assert "Stronger claims require observed evidence" in home
assert "customer handoff JSON" in home
PY

echo "docker customer handoff bundle smoke: PASS"
