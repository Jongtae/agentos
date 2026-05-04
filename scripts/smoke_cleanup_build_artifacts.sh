#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

BUILD_ROOT="$TMP_DIR/build-output"
mkdir -p "$BUILD_ROOT/release" "$BUILD_ROOT/iso-assets"

for version in 0.36.60 0.36.61 0.36.62 0.36.63; do
  printf 'iso' >"$BUILD_ROOT/release/agentos-v${version}-amd64.iso"
  printf 'manifest' >"$BUILD_ROOT/manifest-v${version}.txt"
  mkdir -p "$BUILD_ROOT/iso-assets/v${version}"
  mkdir -p "$BUILD_ROOT/remaster-v${version}"
done
printf 'boot' >"$BUILD_ROOT/release/agentos-v0.36.63-boot-test.iso"
printf 'tmp' >"$BUILD_ROOT/manifest-vsmoke-iso-123.txt"
mkdir -p "$BUILD_ROOT/remaster-vsmoke-iso-123" "$BUILD_ROOT/iso-assets/vsmoke-iso-123"

set +e
OUTPUT="$(python3 "$ROOT_DIR/scripts/cleanup_build_artifacts.py" --build-root "$BUILD_ROOT" --keep-release-count 2 --json)"
STATUS=$?
set -e

if [ "$STATUS" -eq 0 ]; then
  echo "expected stale build artifact policy check to fail before cleanup" >&2
  exit 1
fi

python3 - <<'PY' "$OUTPUT"
import json
import sys
payload = json.loads(sys.argv[1])
assert payload["policy_status"] == "fail", payload
assert payload["stale_candidate_count"] >= 5, payload
PY

python3 "$ROOT_DIR/scripts/cleanup_build_artifacts.py" \
  --build-root "$BUILD_ROOT" \
  --keep-release-count 2 \
  --delete \
  --json >/dev/null

python3 "$ROOT_DIR/scripts/cleanup_build_artifacts.py" \
  --build-root "$BUILD_ROOT" \
  --keep-release-count 2 \
  --json >/dev/null
