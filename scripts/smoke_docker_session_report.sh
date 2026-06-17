#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
PORT="${AGENTOS_DOCKER_SESSION_REPORT_SMOKE_PORT:-18840}"
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
curl -fsS "http://127.0.0.1:$PORT/api/session-report" > "$TMP_DIR/session-report.json"

python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
home = (root / "home.html").read_text(encoding="utf-8")
product = json.loads((root / "product.json").read_text(encoding="utf-8"))
product_map = json.loads((root / "product-map.json").read_text(encoding="utf-8"))
report = json.loads((root / "session-report.json").read_text(encoding="utf-8"))

assert report["schema_version"] == "agentos-product-layer-session-report.v1"
assert report["surface"] == "Session Report"
assert report["state"] == "ready"
assert product["session_report"]["schema_version"] == report["schema_version"]
assert {feature["id"] for feature in product["features"]} >= {"session_report"}

section_ids = {item["id"] for item in report["report_sections"]}
assert section_ids == {
    "runtime_state",
    "recent_activity",
    "proof_sources",
    "recovery_drills",
    "stronger_proof_blockers",
}
assert set(report["proof_sources"]) >= {
    "/api/status",
    "/api/product",
    "/api/activity",
    "/api/evidence",
    "/api/proof-packet",
    "/api/recovery-drills",
    "/api/proof-requests",
}
assert "scripts/smoke_docker_session_report.sh" in report["validation_commands"]
assert report["proof"]["customer_facing_session_report_ready"] is True
assert report["proof"]["evidence_dashboard_linked"] is True
assert report["proof"]["recovery_drills_linked"] is True
for key in [
    "docker_daemon_observed_claimed",
    "boot_or_iso_proof_claimed",
    "live_oauth_claimed",
    "live_browser_proof_claimed",
    "release_trust_claimed",
    "external_mutation_claimed",
    "hardware_attestation_claimed",
]:
    assert report["proof"][key] is False

assert "session_report" in product_map["recommended_path"]
surface_ids = {
    surface["id"]
    for group in product_map["surface_groups"]
    for surface in group.get("surfaces", [])
}
assert "session_report" in surface_ids
routes = {route["id"]: route["route"] for route in product_map["reviewer_routes"]}
assert "session_report" in routes["proof_reviewer"]

assert "Session Report" in home
assert "Report Validation" in home
assert "session report JSON" in home
PY

echo "docker session report smoke: PASS"
