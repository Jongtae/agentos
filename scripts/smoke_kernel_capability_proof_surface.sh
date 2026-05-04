#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE/docs"
printf 'hello\n' > "$WORKSPACE/docs/note.txt"

python3 "$ROOT_DIR/scripts/kernel_document_access.py" --workspace "$WORKSPACE" --path docs/note.txt --json >/dev/null
python3 "$ROOT_DIR/scripts/kernel_intake_surface.py" --workspace "$WORKSPACE" --json >/dev/null

OUT_JSON="$TMP_DIR/proof.json"
python3 "$ROOT_DIR/scripts/kernel_capability_proof_surface.py" \
  --workspace "$WORKSPACE" \
  --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json, sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-capability-proof-surface.v1"
assert "native_handled" in payload["proof_vocabulary"]
assert Path(payload["artifacts"]["latest_capability_proof_surface_json"]).exists()
print("kernel capability proof surface smoke: PASS")
PY
