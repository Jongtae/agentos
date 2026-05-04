#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo "build agentos deb smoke: SKIP (dpkg-deb not found)"
  exit 0
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

VERSION="v0.0.0-smoke-$(date +%s)-$$"
OUTPUT_DIR="$TMP_DIR/out"
mkdir -p "$OUTPUT_DIR"
RELEASE_METADATA_PATH="$OUTPUT_DIR/agentos-release-metadata.json"

BUILD_OUT="$TMP_DIR/build.out"
scripts/build_agentos_deb.sh --version "$VERSION" --output-dir "$OUTPUT_DIR" > "$BUILD_OUT"

PKG_VER="${VERSION#v}"
DEB_PATH="$OUTPUT_DIR/agentos_${PKG_VER}_amd64.deb"
if [ ! -f "$DEB_PATH" ]; then
  echo "missing deb output: $DEB_PATH"
  exit 1
fi

if [ ! -f "$OUTPUT_DIR/SHA256SUMS" ]; then
  echo "missing SHA256SUMS"
  exit 1
fi

if [ ! -f "$RELEASE_METADATA_PATH" ]; then
  echo "missing release metadata"
  exit 1
fi

if ! rg -q "Artifact type: deb" "$BUILD_OUT"; then
  echo "build summary missing artifact type"
  exit 1
fi

if ! rg -q "Release metadata: ${RELEASE_METADATA_PATH}" "$BUILD_OUT"; then
  echo "build summary missing release metadata path"
  exit 1
fi

if ! rg -q "$(basename "$DEB_PATH")" "$OUTPUT_DIR/SHA256SUMS"; then
  echo "SHA256SUMS does not reference deb package"
  exit 1
fi

python3 - "$RELEASE_METADATA_PATH" "$VERSION" "$PKG_VER" "$DEB_PATH" "$OUTPUT_DIR/SHA256SUMS" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("artifact_type") != "deb":
    raise SystemExit("release metadata artifact_type mismatch")
if payload.get("agentos_version") != sys.argv[2]:
    raise SystemExit("release metadata version mismatch")
if payload.get("package_version") != sys.argv[3]:
    raise SystemExit("release metadata package_version mismatch")
if payload.get("distribution_contract") != "agentos_managed_session":
    raise SystemExit("release metadata distribution contract mismatch")
if payload.get("primary_entry_contract") != "agentos_setup_to_ai_shell":
    raise SystemExit("release metadata entry contract mismatch")
if payload.get("output_path") != sys.argv[4]:
    raise SystemExit("release metadata output path mismatch")
if payload.get("sha256sums_path") != sys.argv[5]:
    raise SystemExit("release metadata sha path mismatch")
if payload.get("install_root") != "/usr/lib/agentos":
    raise SystemExit("release metadata install_root mismatch")
if payload.get("default_workspace") != "/var/lib/agentos/workspaces/default":
    raise SystemExit("release metadata default_workspace mismatch")
PY

python3 "$ROOT_DIR/scripts/release_identity_manifest.py" validate --input "$RELEASE_METADATA_PATH" --json >/dev/null
python3 "$ROOT_DIR/scripts/verify_release_identity_contract.py" --metadata "$RELEASE_METADATA_PATH" --json >/dev/null
python3 "$ROOT_DIR/scripts/verify_install_validation_contract.py" --metadata "$RELEASE_METADATA_PATH" --json >/dev/null

LISTING="$TMP_DIR/listing.txt"
dpkg-deb -c "$DEB_PATH" > "$LISTING"
if ! rg -q "usr/lib/agentos/scripts/install_kernel_boot_integration.sh" "$LISTING"; then
  echo "deb payload missing install integration script"
  exit 1
fi
if ! rg -q "usr/lib/agentos/src/main.py" "$LISTING"; then
  echo "deb payload missing runtime entrypoint"
  exit 1
fi

CONTROL_DIR="$TMP_DIR/control"
mkdir -p "$CONTROL_DIR"
dpkg-deb -e "$DEB_PATH" "$CONTROL_DIR"
if ! rg -q "install_kernel_boot_integration.sh" "$CONTROL_DIR/postinst"; then
  echo "postinst missing integration install command"
  exit 1
fi

echo "build agentos deb smoke: PASS"
