#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

REL_DIR="$TMP_DIR/release"
mkdir -p "$REL_DIR"

VERSION="v0.35.1"
ARCH="arm64"
ISO_NAME="agentos-${VERSION}-${ARCH}.iso"
ISO_PATH="$REL_DIR/$ISO_NAME"
SHA_PATH="$REL_DIR/SHA256SUMS"
MANIFEST_PATH="$TMP_DIR/manifest-${VERSION}.txt"

python3 - "$ISO_PATH" <<'PY'
from pathlib import Path
import os
import sys
Path(sys.argv[1]).write_bytes(os.urandom(4096))
PY

(
  cd "$REL_DIR"
  sha256sum "$ISO_NAME" > "$SHA_PATH"
)

cat > "$MANIFEST_PATH" <<EOF
agentos_version=$VERSION
arch=$ARCH
toolchain=ubuntu-image+autoinstall
base_image=/tmp/base.iso
output_iso=$ISO_PATH
utc_built=2026-01-01T00:00:00Z
EOF

OUT_JSON="$TMP_DIR/verify.json"
scripts/verify_iso_release_metadata.py \
  --iso "$ISO_PATH" \
  --sha256sums "$SHA_PATH" \
  --manifest "$MANIFEST_PATH" \
  --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if not payload.get("ok", False):
    raise SystemExit("expected metadata verification ok=true")
if payload.get("version") != "v0.35.1":
    raise SystemExit("version mismatch")
if payload.get("arch") != "arm64":
    raise SystemExit("arch mismatch")
if not payload.get("sha256_actual"):
    raise SystemExit("missing sha256_actual")
PY

echo "iso release metadata smoke: PASS"
