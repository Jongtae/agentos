#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$(mktemp)"
trap 'rm -f "$OUT"' EXIT
python3 "$ROOT_DIR/scripts/kernel_user_space_sovereignty.py" --output "$OUT"
python3 "$ROOT_DIR/scripts/kernel_user_space_sovereignty.py" --validate "$OUT" --json >/tmp/agentos-user-space-sovereignty-validate.json
python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-user-space-sovereignty.v1"
assert payload["summary"]["managed_action_count"] >= 1
assert "execute_high_impact_command" in payload["summary"]["priority_actions"]
PY

echo "smoke_kernel_user_space_sovereignty.sh: PASS"
