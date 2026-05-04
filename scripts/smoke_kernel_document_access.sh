#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE/docs"
printf '# hello\n\nworld\n' > "$WORKSPACE/docs/note.md"

OUT_JSON="$TMP_DIR/document.json"
python3 "$ROOT_DIR/scripts/kernel_document_access.py" \
  --workspace "$WORKSPACE" \
  --path docs/note.md \
  --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json, sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-document-access.v1"
assert payload["native_handled"] is True
assert payload["document_class"] == "markdown"
assert Path(payload["artifacts"]["latest_document_access_manifest_json"]).exists()
print("kernel document access smoke: PASS")
PY
