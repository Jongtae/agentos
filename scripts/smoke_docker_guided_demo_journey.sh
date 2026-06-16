#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
PORT="${AGENTOS_DOCKER_GUIDED_DEMO_SMOKE_PORT:-18790}"
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
curl -fsS "http://127.0.0.1:$PORT/api/demo-journey" > "$TMP_DIR/demo-journey.json"

python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
home = (root / "home.html").read_text(encoding="utf-8")
product = json.loads((root / "product.json").read_text(encoding="utf-8"))
journey = json.loads((root / "demo-journey.json").read_text(encoding="utf-8"))

assert journey["schema_version"] == "agentos-product-layer-guided-demo-journey.v1"
assert journey["surface"] == "Guided Demo Journey"
assert journey["state"] == "ready"
assert product["guided_demo_journey"]["schema_version"] == journey["schema_version"]
assert product["guided_demo_journey"]["stages"] == journey["stages"]
assert {feature["id"] for feature in product["features"]} >= {"guided_demo_journey"}

stage_ids = {item["id"] for item in journey["stages"]}
assert stage_ids == {
    "start_at_runtime_home",
    "inspect_work_inbox",
    "run_first_prompt",
    "review_activity_timeline",
    "check_evidence_and_recovery",
}
entrypoints = {item["entrypoint"] for item in journey["stages"]}
assert {"http://localhost:8787", "/api/work-inbox", "/api/prompt", "/api/timeline", "/api/evidence"} <= entrypoints

assert journey["validation"]["guided_demo_journey_smoke"] == "scripts/smoke_docker_guided_demo_journey.sh"
assert journey["proof"]["docker_preview_ready"] is True
assert journey["proof"]["customer_guided_journey_ready"] is True
assert journey["proof"]["boot_or_iso_proof_claimed"] is False
assert journey["proof"]["live_oauth_claimed"] is False
assert journey["proof"]["live_browser_proof_claimed"] is False
assert journey["proof"]["release_proof_claimed"] is False
assert journey["proof"]["external_mutation_claimed"] is False
assert journey["proof"]["hardware_attestation_claimed"] is False

assert "Guided Demo Journey" in home
assert "Journey Proof" in home
assert "demo journey JSON" in home
PY

echo "docker guided demo journey smoke: PASS"
