#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$(mktemp -d)"
trap 'rm -rf "$WORKSPACE"' EXIT
mkdir -p "$WORKSPACE/artifacts/kernel-policy"
OUT="$WORKSPACE/mediation-pilot.json"
python3 "$ROOT_DIR/scripts/kernel_mediation_pilot.py" --workspace "$WORKSPACE" --output "$OUT"
python3 "$ROOT_DIR/scripts/kernel_mediation_pilot.py" --validate "$OUT" --json >/tmp/agentos-mediation-pilot-validate.json
python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-mediation-pilot.v1"
assert len(payload["selected_targets"]) >= 2
assert "interactive_user_destructive" in payload["summary"]["mandatory_targets"]
PY

echo "smoke_kernel_mediation_pilot.sh: PASS"
