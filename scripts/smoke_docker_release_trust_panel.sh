#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
PORT="${AGENTOS_DOCKER_RELEASE_TRUST_SMOKE_PORT:-18798}"
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
curl -fsS "http://127.0.0.1:$PORT/api/release-trust" > "$TMP_DIR/release-trust.json"

python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
home = (root / "home.html").read_text(encoding="utf-8")
product = json.loads((root / "product.json").read_text(encoding="utf-8"))
release = json.loads((root / "release-trust.json").read_text(encoding="utf-8"))

assert release["schema_version"] == "agentos-product-layer-release-trust-panel.v1"
assert product["release_trust_panel"]["schema_version"] == release["schema_version"]
assert release["surface"] == "Release Trust Panel"
assert release["state"] == "blocked"
assert release["preflight"]["local_manifest_checksum_preflight_available"] is True
assert release["preflight"]["preflight_script"] == "scripts/release_manifest_checksum_preflight.py"
assert {item["id"] for item in release["checks"]} >= {
    "artifact-manifest",
    "checksum-publication",
    "signing-evidence",
    "secret-free-review",
    "vm-iso-release-proof",
}

readiness = {item["id"]: item for item in release["readiness_checklist"]}
assert readiness["local_preflight_available"]["state"] == "ready"
assert readiness["artifact_manifest_required"]["state"] == "blocked_until_release_artifact"
assert readiness["checksum_publication_required"]["state"] == "blocked_until_checksum"
assert readiness["signing_or_unsigned_statement_required"]["state"] == "blocked_until_signature_or_unsigned_statement"
assert readiness["vm_iso_release_proof_required"]["state"] == "blocked_until_observed_vm_run"
assert "scripts/release_manifest_checksum_preflight.py" in readiness["local_preflight_available"]["validation"]

decisions = {item["id"]: item for item in release["customer_decisions"]}
assert decisions["describe_local_preflight_only"]["state"] == "share_ready"
assert "Docker preview" in decisions["describe_local_preflight_only"]["allowed_claim"]
assert decisions["withhold_release_readiness"]["state"] == "blocked_until_release_evidence"
assert "Do not present Docker preview proof as release readiness" in decisions["withhold_release_readiness"]["blocked_claim"]
assert decisions["route_to_observed_proof"]["state"] == "blocked_until_observed_evidence"

assert release["proof"] == {
    "docker_preview_ready": True,
    "release_artifact_observed": False,
    "manifest_validated": False,
    "checksum_published": False,
    "signing_observed": False,
    "release_uploaded": False,
    "vm_iso_release_proof_completed": False,
    "customer_facing_release_trust_ready": True,
}

assert "Release Trust Panel" in home
assert "Release Readiness Checklist" in home
assert "Release Customer Decisions" in home
assert "Withhold release readiness" in home
assert "Release uploaded" in home
PY

echo "docker release trust panel smoke: PASS"
