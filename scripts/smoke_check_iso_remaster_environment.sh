#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

python3 "$ROOT_DIR/scripts/check_iso_remaster_environment.py" --json > "$TMP_DIR/report.json" || true

python3 - "$TMP_DIR/report.json" <<'PY'
import json
import sys
from pathlib import Path
path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding='utf-8'))
assert payload['schema_version'] == 'agentos-iso-remaster-environment.v1'
assert payload['supported_environment'] == 'linux-remaster-toolchain'
assert payload['required_tools'] == ['xorriso', 'unsquashfs', 'mksquashfs', 'bsdtar']
assert 'tools' in payload
PY

echo "iso remaster environment smoke: PASS"
