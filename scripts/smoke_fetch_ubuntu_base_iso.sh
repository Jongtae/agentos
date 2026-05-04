#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

SOURCE_ISO="$TMP_DIR/source.iso"
MANIFEST_PATH="$TMP_DIR/base-image.json"
OUTPUT_DIR="$TMP_DIR/cache"

printf 'agentos-base-iso-smoke' > "$SOURCE_ISO"
EXPECTED_SHA="$(python3 - "$SOURCE_ISO" <<'PY'
import hashlib
import sys
from pathlib import Path
path = Path(sys.argv[1])
h = hashlib.sha256()
h.update(path.read_bytes())
print(h.hexdigest())
PY
)"

cat > "$MANIFEST_PATH" <<JSON
{
  "schema_version": "agentos-ubuntu-base-image.v1",
  "ubuntu_version": "24.04.4",
  "release_codename": "noble",
  "artifact_type": "desktop-live-iso",
  "arch": "amd64",
  "filename": "ubuntu-24.04.4-desktop-amd64.iso",
  "download_url": "file://$SOURCE_ISO",
  "sha256": "$EXPECTED_SHA"
}
JSON

RESOLVED_PATH="$($ROOT_DIR/scripts/fetch_ubuntu_base_iso.sh --manifest "$MANIFEST_PATH" --output-dir "$OUTPUT_DIR" --print-path)"
if [ ! -f "$RESOLVED_PATH" ]; then
  echo "[fetch-base-iso-smoke] resolved path missing"
  exit 1
fi

if ! cmp -s "$SOURCE_ISO" "$RESOLVED_PATH"; then
  echo "[fetch-base-iso-smoke] downloaded file content mismatch"
  exit 1
fi

SECOND_PATH="$($ROOT_DIR/scripts/fetch_ubuntu_base_iso.sh --manifest "$MANIFEST_PATH" --output-dir "$OUTPUT_DIR" --print-path)"
if [ "$SECOND_PATH" != "$RESOLVED_PATH" ]; then
  echo "[fetch-base-iso-smoke] cache reuse returned different path"
  exit 1
fi

echo "fetch ubuntu base iso smoke: PASS"
