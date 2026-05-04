#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$(mktemp -d)"
trap 'rm -rf "$WORKSPACE"' EXIT
mkdir -p "$WORKSPACE/artifacts/kernel-policy"
OUT="$WORKSPACE/policy-maturity.json"

python3 "$ROOT_DIR/scripts/kernel_policy_maturity.py" \
  --workspace "$WORKSPACE" \
  --parser-cmd python3 \
  --output "$OUT"

python3 "$ROOT_DIR/scripts/kernel_policy_maturity.py" \
  --validate "$OUT" \
  --json >/tmp/agentos-policy-maturity-validate.json

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-policy-maturity.v1"
assert len(payload["targets"]) == 3
assert payload["summary"]["average_readiness_score"] >= 0
PY

echo "smoke_kernel_policy_maturity.sh: PASS"
