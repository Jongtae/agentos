#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ARCH="${AGENTOS_BASE_IMAGE_ARCH:-amd64}"
MANIFEST_PATH="${AGENTOS_BASE_IMAGE_MANIFEST:-}"
OUTPUT_DIR="${AGENTOS_BASE_IMAGE_CACHE_DIR:-$ROOT_DIR/build-output/base-images}"
FORCE=0
PRINT_PATH_ONLY=0

usage() {
  cat <<USAGE
Usage:
  scripts/fetch_ubuntu_base_iso.sh [--arch amd64|arm64] [--manifest <path>] [--output-dir <dir>] [--force] [--print-path]

Defaults:
  manifest:   image-assets/base-images/ubuntu-24.04.4-desktop-<arch>.json
  output-dir: build-output/base-images

Behavior:
  - downloads the supported Ubuntu base ISO from the manifest
  - reuses a cached ISO when the SHA256 matches
  - prints the resolved local ISO path
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --arch)
      shift
      ARCH="${1:-}"
      ;;
    --manifest)
      shift
      MANIFEST_PATH="${1:-}"
      ;;
    --output-dir)
      shift
      OUTPUT_DIR="${1:-}"
      ;;
    --force)
      FORCE=1
      ;;
    --print-path)
      PRINT_PATH_ONLY=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift || true
done

case "$ARCH" in
  amd64|arm64) ;;
  *)
    echo "Invalid --arch '$ARCH'. Supported: amd64, arm64." >&2
    exit 2
    ;;
esac

if [ -z "$MANIFEST_PATH" ]; then
  MANIFEST_PATH="$ROOT_DIR/image-assets/base-images/ubuntu-24.04.4-desktop-${ARCH}.json"
fi

if [ ! -f "$MANIFEST_PATH" ]; then
  echo "Base image manifest not found: $MANIFEST_PATH" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required." >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required." >&2
  exit 1
fi

manifest_line="$(python3 - "$MANIFEST_PATH" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
required = ['schema_version', 'ubuntu_version', 'arch', 'filename', 'download_url', 'sha256']
missing = [k for k in required if not str(payload.get(k, '')).strip()]
if missing:
    raise SystemExit(f"missing required manifest fields: {', '.join(missing)}")
if payload.get('schema_version') != 'agentos-ubuntu-base-image.v1':
    raise SystemExit('unsupported schema_version')
print('\t'.join(str(payload.get(key, '')).strip() for key in ('filename', 'download_url', 'sha256', 'ubuntu_version', 'arch', 'artifact_type')))
PY
)"
IFS=$'\t' read -r FILENAME DOWNLOAD_URL EXPECTED_SHA256 UBUNTU_VERSION ARCH ARTIFACT_TYPE <<EOF2
$manifest_line
EOF2

if [ -z "$FILENAME" ] || [ -z "$DOWNLOAD_URL" ] || [ -z "$EXPECTED_SHA256" ]; then
  echo "failed to parse base image manifest: $MANIFEST_PATH" >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"
TARGET_PATH="$OUTPUT_DIR/$FILENAME"
TMP_PATH="$OUTPUT_DIR/$FILENAME.partial"

compute_sha256() {
  python3 - "$1" <<'PY'
import hashlib
import sys
from pathlib import Path
path = Path(sys.argv[1])
h = hashlib.sha256()
with path.open('rb') as f:
    for chunk in iter(lambda: f.read(1024 * 1024), b''):
        h.update(chunk)
print(h.hexdigest())
PY
}

emit_success() {
  local resolved_path="$1"
  if [ "$PRINT_PATH_ONLY" -eq 1 ]; then
    printf '%s\n' "$resolved_path"
  else
    echo "Resolved Ubuntu base ISO"
    echo "ubuntu_version: $UBUNTU_VERSION"
    echo "artifact_type:  $ARTIFACT_TYPE"
    echo "arch:           $ARCH"
    echo "source_url:     $DOWNLOAD_URL"
    echo "resolved_path:  $resolved_path"
  fi
}

if [ -f "$TARGET_PATH" ] && [ "$FORCE" -eq 0 ]; then
  ACTUAL_SHA256="$(compute_sha256 "$TARGET_PATH")"
  if [ "$ACTUAL_SHA256" = "$EXPECTED_SHA256" ]; then
    emit_success "$TARGET_PATH"
    exit 0
  fi
  rm -f "$TARGET_PATH"
fi

rm -f "$TMP_PATH"
curl -L --fail --progress-bar -o "$TMP_PATH" "$DOWNLOAD_URL"
ACTUAL_SHA256="$(compute_sha256 "$TMP_PATH")"
if [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]; then
  rm -f "$TMP_PATH"
  echo "Downloaded ISO checksum mismatch for $FILENAME" >&2
  echo "expected: $EXPECTED_SHA256" >&2
  echo "actual:   $ACTUAL_SHA256" >&2
  exit 1
fi
mv "$TMP_PATH" "$TARGET_PATH"
emit_success "$TARGET_PATH"
