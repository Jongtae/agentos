#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
PORT="${AGENTOS_DOCKER_PREVIEW_READINESS_SMOKE_PORT:-18800}"
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
curl -fsS "http://127.0.0.1:$PORT/api/preview-readiness" > "$TMP_DIR/preview-readiness.json"

python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
home = (root / "home.html").read_text(encoding="utf-8")
product = json.loads((root / "product.json").read_text(encoding="utf-8"))
preview = json.loads((root / "preview-readiness.json").read_text(encoding="utf-8"))

assert preview["schema_version"] == "agentos-product-layer-preview-readiness-board.v1"
assert preview["surface"] == "Preview Readiness Board"
assert preview["state"] == "ready"
assert product["preview_readiness_board"]["schema_version"] == preview["schema_version"]
assert {feature["id"] for feature in product["features"]} >= {"preview_readiness_board"}

checks = {item["id"]: item for item in preview["readiness_checks"]}
assert checks["docker_try_path_documented"]["state"] == "ready"
assert checks["product_layer_surfaces_visible"]["state"] == "ready"
assert checks["docker_safe_validation_available"]["state"] == "ready"
assert checks["public_preview_operations_contract_linked"]["state"] == "ready"
assert checks["observed_proof_blockers_visible"]["state"] == "blocked_until_observed_evidence"
assert "docs/operations/public-preview-operations.md" in checks["public_preview_operations_contract_linked"]["evidence"]

decisions = {item["id"]: item for item in preview["promotion_decisions"]}
assert decisions["share_docker_local_preview"]["state"] == "share_ready"
assert "Docker-local Product Layer preview" in decisions["share_docker_local_preview"]["allowed_claim"]
assert decisions["rerun_local_gates_before_demo"]["state"] == "recommended"
assert decisions["withhold_stronger_preview_claims"]["state"] == "blocked_until_observed_evidence"
assert "Do not auto-promote Docker-local proof" in decisions["withhold_stronger_preview_claims"]["blocked_claim"]

assert "scripts/smoke_public_preview_operations.sh" in preview["validation_commands"]
assert "scripts/smoke_docker_preview_readiness_board.sh" in preview["validation_commands"]
assert preview["operations_contract"]["manual_blockers_required_for_stronger_claims"] is True

assert preview["proof"] == {
    "docker_main_try_path": True,
    "customer_facing_preview_readiness_ready": True,
    "docker_daemon_observed_claimed": False,
    "boot_or_iso_proof_claimed": False,
    "live_oauth_claimed": False,
    "live_browser_proof_claimed": False,
    "release_trust_claimed": False,
    "external_mutation_claimed": False,
    "hardware_attestation_claimed": False,
    "automatic_claim_promotion": False,
}

assert "Preview Readiness Board" in home
assert "Preview Promotion Decisions" in home
assert "Preview Validation" in home
assert "Withhold stronger preview claims" in home
assert "preview readiness JSON" in home
PY

echo "docker preview readiness board smoke: PASS"
