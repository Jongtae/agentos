#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
SECRETS="$TMP_DIR/secrets/gmail"
mkdir -p "$WORKSPACE" "$SECRETS"

status_file="$TMP_DIR/status.json"
read_file="$TMP_DIR/read.json"

if scripts/agentos-kernelctl gmail-status \
  --workspace "$WORKSPACE" \
  --credentials-path "$SECRETS/credentials.json" \
  --token-path "$SECRETS/token.json" \
  --json > "$status_file"; then
  echo "gmail-status unexpectedly passed without credentials" >&2
  exit 1
fi

if scripts/agentos-kernelctl gmail-read \
  --workspace "$WORKSPACE" \
  --credentials-path "$SECRETS/credentials.json" \
  --token-path "$SECRETS/token.json" \
  --query "roadmap" \
  --json > "$read_file"; then
  echo "gmail-read unexpectedly passed without credentials" >&2
  exit 1
fi

python3 - "$status_file" "$read_file" <<'PY'
import json
import sys
from pathlib import Path

status = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
read = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))

assert status["schema_version"] == "agentos-gmail-status.v1", status
assert status["proof"]["ok"] is False, status
assert status["proof"]["reason"] == "gmail_credentials_missing", status
assert "gmail-setup --serve-http" in status["operator_action_required"], status

assert read["schema_version"] == "agentos-gmail-read.v1", read
assert read["proof"]["ok"] is False, read
assert read["proof"]["reason"] == "gmail_credentials_missing", read
assert read["matched_count"] == 0, read
assert "refresh_token" not in json.dumps(read, ensure_ascii=True), read
PY

echo "gmail live missing credentials smoke: PASS"
