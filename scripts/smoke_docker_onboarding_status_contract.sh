#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
PORT="${AGENTOS_DOCKER_ONBOARDING_SMOKE_PORT:-18789}"
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
curl -fsS "http://127.0.0.1:$PORT/api/onboarding" > "$TMP_DIR/onboarding.json"
curl -fsS "http://127.0.0.1:$PORT/api/product" > "$TMP_DIR/product.json"

python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
home = (root / "home.html").read_text(encoding="utf-8")
onboarding = json.loads((root / "onboarding.json").read_text(encoding="utf-8"))
product = json.loads((root / "product.json").read_text(encoding="utf-8"))

assert onboarding["schema_version"] == "agentos-product-layer-onboarding-status.v1"
assert onboarding["surface"] == "Docker Onboarding Status"
assert onboarding["state"] == "ready"
assert product["onboarding_status"]["schema_version"] == onboarding["schema_version"]
assert product["onboarding_status"]["readiness_checklist"] == onboarding["readiness_checklist"]

step_ids = {item["id"] for item in onboarding["steps"]}
assert step_ids >= {
    "clone_repository",
    "copy_env",
    "start_docker_preview",
    "open_runtime_home",
    "try_prompt",
}

check_ids = {item["id"] for item in onboarding["readiness_checklist"]}
assert check_ids >= {
    "quickstart_documented",
    "preview_entrypoints_available",
    "basic_preview_no_api_key",
    "docker_validation_available",
    "observed_proof_boundaries_visible",
}
checks_by_id = {item["id"]: item for item in onboarding["readiness_checklist"]}
assert checks_by_id["quickstart_documented"]["state"] == "ready"
assert checks_by_id["preview_entrypoints_available"]["state"] == "ready"
assert checks_by_id["basic_preview_no_api_key"]["state"] == "ready"
assert checks_by_id["docker_validation_available"]["state"] == "ready"
assert checks_by_id["observed_proof_boundaries_visible"]["state"] == "blocked_on_external_evidence"

assert onboarding["entrypoints"]["browser_url"] == "http://localhost:8787"
assert onboarding["entrypoints"]["status_api"] == "/api/status"
assert onboarding["entrypoints"]["product_api"] == "/api/product"
assert onboarding["entrypoints"]["onboarding_api"] == "/api/onboarding"
assert onboarding["validation"]["onboarding_status_contract_smoke"] == "scripts/smoke_docker_onboarding_status_contract.sh"
assert onboarding["proof"]["docker_preview_ready"] is True
assert onboarding["proof"]["customer_onboarding_ready"] is True
assert onboarding["proof"]["requires_api_key_for_basic_preview"] is False
assert onboarding["proof"]["boot_or_iso_proof_claimed"] is False
assert onboarding["proof"]["live_oauth_claimed"] is False
assert onboarding["proof"]["live_browser_proof_claimed"] is False
assert onboarding["proof"]["release_proof_claimed"] is False
assert onboarding["proof"]["external_mutation_claimed"] is False
assert onboarding["proof"]["hardware_attestation_claimed"] is False

assert "Docker Onboarding Status" in home
assert "Readiness Checklist" in home
assert "Observed proof boundaries are visible" in home
assert "onboarding JSON" in home
PY

echo "docker onboarding status contract smoke: PASS"
