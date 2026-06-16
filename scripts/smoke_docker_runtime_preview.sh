#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker runtime preview smoke: FAIL"
  echo "reason: docker command is not installed or not on PATH"
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "docker runtime preview smoke: FAIL"
  echo "reason: docker compose is unavailable"
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "docker runtime preview smoke: FAIL"
  echo "reason: Docker daemon is not running or not reachable"
  echo "recovery: start Docker Desktop, then rerun scripts/smoke_docker_runtime_preview.sh"
  exit 1
fi

TMP_CID=""
cleanup() {
  if [ -n "$TMP_CID" ]; then
    docker rm -f "$TMP_CID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

dump_container_diagnostics() {
  if [ -z "$TMP_CID" ]; then
    return
  fi
  echo "docker runtime preview smoke: container status"
  docker ps -a --filter "id=$TMP_CID" --no-trunc || true
  echo "docker runtime preview smoke: container logs"
  docker logs "$TMP_CID" || true
}

docker compose config >/dev/null
docker compose build agent-os >/dev/null

TMP_CID="$(
  docker run -d \
    -p 18787:8787 \
    -e DEFAULT_WORKSPACE=/app/workspaces/default \
    -e AGENTOS_USER_DATA_ROOT=/var/lib/agentos/user \
    -e AGENTOS_DOCKER_TELEGRAM_POLLING=false \
    agent-os:latest
)"

READY=false
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:18787/healthz >/dev/null 2>&1; then
    READY=true
    break
  fi
  if [ "$(docker inspect -f '{{.State.Running}}' "$TMP_CID" 2>/dev/null || true)" != "true" ]; then
    echo "docker runtime preview smoke: FAIL"
    echo "reason: container exited before /healthz became ready"
    dump_container_diagnostics
    exit 1
  fi
  sleep 1
done

if [ "$READY" != "true" ]; then
  echo "docker runtime preview smoke: FAIL"
  echo "reason: /healthz did not become ready before timeout"
  dump_container_diagnostics
  exit 1
fi

curl -fsS http://127.0.0.1:18787/healthz >/dev/null
curl -fsS http://127.0.0.1:18787/ >/dev/null
curl -fsS http://127.0.0.1:18787/api/status > /tmp/agentos-docker-status.json

python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path("/tmp/agentos-docker-status.json").read_text())
assert payload["proof"]["docker_preview_surface_ready"] is True
assert payload["proof"]["boot_or_iso_proof"] is False
assert payload["proof"]["secrets_redacted"] is True
assert payload["telegram"]["transport"] == "polling_preview"
PY

curl -fsS \
  -H 'Content-Type: application/json' \
  -d '{"message":"hi"}' \
  http://127.0.0.1:18787/api/prompt > /tmp/agentos-docker-prompt.json

python3 - <<'PY'
import json
from pathlib import Path
text = Path("/tmp/agentos-docker-prompt.json").read_text()
payload = json.loads(text)
assert payload["ok"] is True, payload
assert payload["intent"] in {"greeting", "unknown_needs_clarification", "status", "runtime_status"}, payload
for forbidden in ("AGENTOS_TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY", "xoxb-", "sk-"):
    assert forbidden not in text
PY

curl -fsS http://127.0.0.1:18787/api/activity > /tmp/agentos-docker-activity.json
python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path("/tmp/agentos-docker-activity.json").read_text())
assert payload["activity_feed_ready"] is True
assert isinstance(payload["events"], list)
PY

echo "docker runtime preview smoke: PASS"
