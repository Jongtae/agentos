#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

PRIVATE_TMP_ROOT="$TMP_DIR/private-tmp"
VAR_FOLDERS_ROOT="$TMP_DIR/var-folders"
mkdir -p "$PRIVATE_TMP_ROOT" "$VAR_FOLDERS_ROOT/fd/token/T"

printf 'stub\n' > "$PRIVATE_TMP_ROOT/agentos-remaster-9.sparseimage"
touch -t 202604200000 "$PRIVATE_TMP_ROOT/agentos-remaster-9.sparseimage"

mkdir -p "$VAR_FOLDERS_ROOT/fd/token/T/tmp.remaster/casper"
dd if=/dev/zero of="$VAR_FOLDERS_ROOT/fd/token/T/tmp.remaster/casper/filesystem.squashfs" bs=1024 count=4 >/dev/null 2>&1
touch -t 202604200000 "$VAR_FOLDERS_ROOT/fd/token/T/tmp.remaster"
touch -t 202604200000 "$VAR_FOLDERS_ROOT/fd/token/T/tmp.remaster/casper"
touch -t 202604200000 "$VAR_FOLDERS_ROOT/fd/token/T/tmp.remaster/casper/filesystem.squashfs"

set +e
OUTPUT="$(python3 "$ROOT_DIR/scripts/cleanup_temp_artifacts.py" --json --min-tmp-dir-size-mb 0 --private-tmp-root "$PRIVATE_TMP_ROOT" --var-folders-root "$VAR_FOLDERS_ROOT")"
STATUS=$?
set -e

if [ "$STATUS" -eq 0 ]; then
  echo "expected stale temp artifact policy check to fail before cleanup" >&2
  exit 1
fi

python3 - <<'PY' "$OUTPUT"
import json
import sys
payload = json.loads(sys.argv[1])
assert payload["stale_candidate_count"] == 2, payload
assert payload["policy_status"] == "fail", payload
PY

python3 "$ROOT_DIR/scripts/cleanup_temp_artifacts.py" \
  --delete \
  --json \
  --min-tmp-dir-size-mb 0 \
  --private-tmp-root "$PRIVATE_TMP_ROOT" \
  --var-folders-root "$VAR_FOLDERS_ROOT" >/dev/null

python3 "$ROOT_DIR/scripts/cleanup_temp_artifacts.py" \
  --json \
  --min-tmp-dir-size-mb 0 \
  --private-tmp-root "$PRIVATE_TMP_ROOT" \
  --var-folders-root "$VAR_FOLDERS_ROOT" >/dev/null
