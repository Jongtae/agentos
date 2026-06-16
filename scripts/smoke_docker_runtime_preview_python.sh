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
curl -fsS "http://127.0.0.1:$PORT/api/work-inbox" > "$TMP_DIR/work-inbox.json"
curl -fsS "http://127.0.0.1:$PORT/api/recovery" > "$TMP_DIR/recovery.json"
curl -fsS "http://127.0.0.1:$PORT/api/evidence" > "$TMP_DIR/evidence.json"
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
work_inbox = json.loads((root / "work-inbox.json").read_text())
recovery = json.loads((root / "recovery.json").read_text())
evidence = json.loads((root / "evidence.json").read_text())
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
assert product["work_inbox"]["schema_version"] == "agentos-product-layer-work-inbox.v1"
assert product["recovery_center"]["schema_version"] == "agentos-product-layer-recovery-center.v1"
assert product["evidence_dashboard"]["schema_version"] == "agentos-product-layer-evidence-dashboard.v1"
assert {feature["id"] for feature in product["features"]} >= {
    "runtime_home",
    "work_inbox",
    "activity_timeline",
    "recovery_center",
    "evidence_dashboard",
}
assert work_inbox["schema_version"] == "agentos-product-layer-work-inbox.v1"
assert work_inbox["proof"]["docker_preview_ready"] is True
assert work_inbox["proof"]["read_first_only"] is True
assert work_inbox["proof"]["external_mutation_claimed"] is False
assert work_inbox["proof"]["live_oauth_claimed"] is False
assert {source["id"] for source in work_inbox["sources"]} >= {"native_fixture", "maildir", "gmail", "calendar"}
assert {workflow["id"] for workflow in work_inbox["workflows"]} >= {"inbox_summary", "draft_preparation", "search_and_triage"}
assert recovery["schema_version"] == "agentos-product-layer-recovery-center.v1"
assert recovery["proof"]["docker_preview_ready"] is True
assert recovery["proof"]["customer_facing_recovery_ready"] is True
assert recovery["proof"]["boot_or_iso_proof_claimed"] is False
assert recovery["proof"]["live_oauth_claimed"] is False
assert recovery["proof"]["live_browser_proof_claimed"] is False
assert recovery["proof"]["release_trust_claimed"] is False
assert recovery["proof"]["hardware_attestation_claimed"] is False
assert {item["id"] for item in recovery["items"]} >= {
    "vm-iso-observed-proof",
    "live-oauth-proof",
    "live-browser-proof",
    "release-trust-proof",
    "attestation-proof",
}
assert evidence["schema_version"] == "agentos-product-layer-evidence-dashboard.v1"
assert evidence["proof"]["docker_preview_ready"] is True
assert evidence["proof"]["customer_facing_evidence_ready"] is True
assert evidence["proof"]["boot_or_iso_proof_claimed"] is False
assert evidence["proof"]["live_oauth_claimed"] is False
assert evidence["proof"]["live_browser_proof_claimed"] is False
assert evidence["proof"]["release_trust_claimed"] is False
assert evidence["proof"]["hardware_attestation_claimed"] is False
assert {item["id"] for item in evidence["evidence"]} >= {
    "docker-runtime-preview",
    "phase2-golden-runtime-loop",
    "work-inbox-read-first",
    "activity-timeline",
}
assert {item["id"] for item in evidence["non_claims"]} >= {
    "vm-iso-boot-proof",
    "live-oauth-proof",
    "live-browser-proof",
    "release-trust-proof",
    "hardware-attestation-proof",
}
assert "Runtime Home" in home
assert "Recovery Center" in home
assert "recovery JSON" in home
assert "Work Inbox" in home
assert "Inbox Workflows" in home
assert "Evidence Dashboard" in home
assert "evidence JSON" in home
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
