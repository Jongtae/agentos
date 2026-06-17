#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
PORT="${AGENTOS_DOCKER_ACTIVITY_TIMELINE_SNAPSHOT_SMOKE_PORT:-18801}"
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
curl -fsS "http://127.0.0.1:$PORT/api/timeline" > "$TMP_DIR/timeline.json"

python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
home = (root / "home.html").read_text(encoding="utf-8")
product = json.loads((root / "product.json").read_text(encoding="utf-8"))
timeline = json.loads((root / "timeline.json").read_text(encoding="utf-8"))
snapshot = timeline["completion_snapshot"]

assert product["activity_timeline"]["completion_snapshot"]["schema_version"] == snapshot["schema_version"]
assert timeline["schema_version"] == "agentos-product-layer-activity-timeline.v1"
assert timeline["proof"]["activity_timeline_completion_snapshot_ready"] is True
assert snapshot["schema_version"] == "agentos-product-layer-activity-timeline-completion-snapshot.v1"
assert snapshot["state"] == "ready"

assert {item["id"] for item in snapshot["narrated_stages"]} == {
    "received",
    "classified",
    "running",
    "completed_or_recovered",
}
assert {item["id"] for item in snapshot["record_surfaces"]} == {
    "activity_feed",
    "user_visible_records",
}
gates = {item["id"]: item for item in snapshot["validation_gates"]}
assert gates["activity_timeline_snapshot_gate"]["command"] == "scripts/smoke_docker_activity_timeline_snapshot.sh"
assert gates["product_layer_completion_gate"]["command"] == "scripts/smoke_docker_product_layer_completion.sh"
assert gates["runtime_preview_python_gate"]["command"] == "scripts/smoke_docker_runtime_preview_python.sh"
assert {item["id"] for item in snapshot["blocked_stronger_proof"]} == {
    "external_app_execution",
    "live_provider_activity",
    "browser_activity",
    "vm_iso_activity",
}
assert snapshot["proof"] == {
    "customer_facing_activity_timeline_snapshot_ready": True,
    "docker_preview_ready": True,
    "user_visible_records_ready": True,
    "external_app_execution_claimed": False,
    "live_provider_proof_claimed": False,
    "browser_activity_claimed": False,
    "boot_or_iso_proof_claimed": False,
    "automatic_claim_promotion": False,
}

assert "Activity Timeline Completion Snapshot" in home
assert "Narrated Stages" in home
assert "scripts/smoke_docker_activity_timeline_snapshot.sh" in home
assert "External app execution" in home
PY

echo "docker activity timeline snapshot smoke: PASS"
