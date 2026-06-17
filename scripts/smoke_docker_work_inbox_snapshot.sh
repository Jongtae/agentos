#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
PORT="${AGENTOS_DOCKER_WORK_INBOX_SNAPSHOT_SMOKE_PORT:-18800}"
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
curl -fsS "http://127.0.0.1:$PORT/api/work-inbox" > "$TMP_DIR/work-inbox.json"

python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
home = (root / "home.html").read_text(encoding="utf-8")
product = json.loads((root / "product.json").read_text(encoding="utf-8"))
work_inbox = json.loads((root / "work-inbox.json").read_text(encoding="utf-8"))
snapshot = work_inbox["completion_snapshot"]

assert product["work_inbox"]["completion_snapshot"]["schema_version"] == snapshot["schema_version"]
assert work_inbox["schema_version"] == "agentos-product-layer-work-inbox.v1"
assert work_inbox["proof"]["work_inbox_completion_snapshot_ready"] is True
assert snapshot["schema_version"] == "agentos-product-layer-work-inbox-completion-snapshot.v1"
assert snapshot["surface"] == "Work Inbox Completion Snapshot"
assert snapshot["state"] == "ready"

assert {source["id"] for source in work_inbox["sources"]} == {
    "native_fixture",
    "maildir",
    "gmail",
    "calendar",
}
assert {workflow["id"] for workflow in work_inbox["workflows"]} == {
    "inbox_summary",
    "draft_preparation",
    "search_and_triage",
}
assert all(workflow["mutation_allowed"] is False for workflow in work_inbox["workflows"])

completed = {item["id"]: item for item in snapshot["completed_local_proof"]}
assert set(completed) == {
    "fixture_inbox_ready",
    "read_first_workflows_ready",
    "live_boundaries_visible",
}
assert "scripts/smoke_docker_work_inbox_snapshot.sh" in completed["fixture_inbox_ready"]["evidence"]

gates = {item["id"]: item for item in snapshot["validation_gates"]}
assert gates["work_inbox_snapshot_gate"]["command"] == "scripts/smoke_docker_work_inbox_snapshot.sh"
assert gates["product_layer_completion_gate"]["command"] == "scripts/smoke_docker_product_layer_completion.sh"
assert gates["runtime_preview_python_gate"]["command"] == "scripts/smoke_docker_runtime_preview_python.sh"

boundaries = {item["id"]: item for item in snapshot["mutation_boundaries"]}
assert boundaries["external_send_blocked"]["state"] == "blocked"
assert boundaries["production_sync_blocked"]["state"] == "blocked_until_observed_evidence"

blocked = {item["id"] for item in snapshot["blocked_stronger_proof"]}
assert blocked == {
    "live-gmail-oauth",
    "live-calendar-oauth",
    "observed-maildir-user-data-proof",
}
assert snapshot["proof"] == {
    "customer_facing_work_inbox_snapshot_ready": True,
    "docker_preview_ready": True,
    "read_first_only": True,
    "live_oauth_claimed": False,
    "browser_default_claimed": False,
    "external_mutation_claimed": False,
    "production_sync_claimed": False,
    "user_maildir_observed_claimed": False,
    "automatic_claim_promotion": False,
}

assert "Work Inbox Completion Snapshot" in home
assert "Mutation Boundaries" in home
assert "scripts/smoke_docker_work_inbox_snapshot.sh" in home
assert "External sends are blocked" in home
PY

echo "docker work inbox snapshot smoke: PASS"
