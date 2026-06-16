#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
PORT="${AGENTOS_DOCKER_PREVIEW_SMOKE_PORT:-18787}"
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
curl -fsS "http://127.0.0.1:$PORT/api/status" > "$TMP_DIR/status.json"
curl -fsS "http://127.0.0.1:$PORT/api/product" > "$TMP_DIR/product.json"
curl -fsS \
  -H 'Content-Type: application/json' \
  -d '{"message":"hi"}' \
  "http://127.0.0.1:$PORT/api/prompt" > "$TMP_DIR/prompt.json"
curl -fsS "http://127.0.0.1:$PORT/api/activity" > "$TMP_DIR/activity.json"

python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
status = json.loads((root / "status.json").read_text())
product = json.loads((root / "product.json").read_text())
prompt = json.loads((root / "prompt.json").read_text())
activity = json.loads((root / "activity.json").read_text())
home = (root / "home.html").read_text()

assert status["proof"]["docker_preview_surface_ready"] is True
assert status["proof"]["product_layer_runtime_home_ready"] is True
assert status["proof"]["boot_or_iso_proof"] is False
assert status["telegram"]["transport"] == "polling_preview"
assert product["schema_version"] == "agentos-product-layer-runtime-home.v1"
assert product["proof"]["docker_main_try_path"] is True
assert product["proof"]["boot_or_iso_proof_claimed"] is False
assert product["proof"]["customer_facing_summary_ready"] is True
assert {feature["id"] for feature in product["features"]} >= {
    "runtime_home",
    "work_inbox",
    "activity_timeline",
    "recovery_center",
    "evidence_dashboard",
}
assert "Runtime Home" in home
assert "Recovery Center" in home
assert "Work Inbox" in home
assert prompt["ok"] is True
assert prompt["intent"] == "greeting", prompt
assert "DuckDuckGo" not in json.dumps(prompt)
assert activity["activity_feed_ready"] is True
assert len(activity["events"]) >= 1

combined = "\n".join(p.read_text(errors="ignore") for p in root.glob("*.json"))
for forbidden in ("AGENTOS_TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY", "xoxb-", "sk-"):
    assert forbidden not in combined
PY

echo "docker runtime preview python smoke: PASS"
