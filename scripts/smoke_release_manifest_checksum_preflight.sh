#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

ARTIFACT="$TMP_DIR/agentos-0.0.0-test-amd64.iso"
MANIFEST="$TMP_DIR/release-identity.json"
CHECKSUM="$TMP_DIR/SHA256SUMS"
BUILD_MANIFEST="$TMP_DIR/build-manifest.txt"
BASE_IMAGE="$TMP_DIR/base.iso"
ASSET_BUNDLE="$TMP_DIR/assets.tar"
ASSET_MANIFEST="$TMP_DIR/asset-manifest.txt"
BLOCKED="$TMP_DIR/blocked.json"
READY="$TMP_DIR/ready.json"

set +e
PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 "$ROOT_DIR/scripts/release_manifest_checksum_preflight.py" --json >"$BLOCKED"
blocked_code=$?
set -e
[ "$blocked_code" -eq 3 ]

printf "fixture iso bytes\n" >"$ARTIFACT"
printf "build manifest\n" >"$BUILD_MANIFEST"
printf "base image\n" >"$BASE_IMAGE"
printf "asset bundle\n" >"$ASSET_BUNDLE"
printf "asset manifest\n" >"$ASSET_MANIFEST"
python3 - "$ARTIFACT" "$CHECKSUM" <<'PY'
import hashlib
import sys
from pathlib import Path

artifact = Path(sys.argv[1])
checksum = Path(sys.argv[2])
checksum.write_text(
    f"{hashlib.sha256(artifact.read_bytes()).hexdigest()}  {artifact.name}\n",
    encoding="utf-8",
)
PY

PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 "$ROOT_DIR/scripts/release_identity_manifest.py" write \
  --output "$MANIFEST" \
  --artifact-type iso \
  --agentos-version 0.0.0-test \
  --arch amd64 \
  --output-path "$ARTIFACT" \
  --sha256sums-path "$CHECKSUM" \
  --build-manifest-path "$BUILD_MANIFEST" \
  --base-image-path "$BASE_IMAGE" \
  --asset-bundle-path "$ASSET_BUNDLE" \
  --asset-manifest-path "$ASSET_MANIFEST" \
  --boot-target-activated \
  --boot-flow-proof-included \
  --vm-first-screen-evidence-included \
  --agentos-welcome-assets-staged \
  --agentos-welcome-owns-first-screen >/dev/null

PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 "$ROOT_DIR/scripts/release_manifest_checksum_preflight.py" \
  --artifact "$ARTIFACT" \
  --manifest "$MANIFEST" \
  --checksum "$CHECKSUM" \
  --json >"$READY"

python3 - "$BLOCKED" "$READY" <<'PY'
import json
import sys

blocked = json.loads(open(sys.argv[1], encoding="utf-8").read())
ready = json.loads(open(sys.argv[2], encoding="utf-8").read())

assert blocked["schema_version"] == "agentos-release-manifest-checksum-preflight.v1"
assert blocked["status"] == "blocked"
assert {"release-artifact-required", "release-manifest-required", "checksum-file-required"} <= {
    blocker["id"] for blocker in blocked["blockers"]
}
assert blocked["proof"]["release_uploaded"] is False
assert blocked["proof"]["signing_observed"] is False
assert blocked["proof"]["vm_iso_proof_completed"] is False

assert ready["schema_version"] == "agentos-release-manifest-checksum-preflight.v1"
assert ready["status"] == "ready"
assert ready["blockers"] == []
assert ready["proof"]["artifact_observed"] is True
assert ready["proof"]["manifest_validated"] is True
assert ready["proof"]["checksum_matched"] is True
assert ready["proof"]["release_uploaded"] is False
assert ready["proof"]["signing_observed"] is False
assert ready["proof"]["vm_iso_proof_completed"] is False
assert ready["non_claims"]["release_uploaded"] is True
assert ready["non_claims"]["vm_iso_proof_completed"] is True
PY

echo "release manifest checksum preflight smoke: PASS"
