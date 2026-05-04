#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

OUT_JSON="$(mktemp)"
trap 'rm -f "$OUT_JSON"' EXIT

scripts/kernel_mediation_coverage.py --workspace ./workspaces/default --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("schema_version") != "agentos-mediation-coverage.v1":
    raise SystemExit("expected mediation coverage schema")
summary = payload.get("summary", {})
if summary.get("mandatory_candidate_count", 0) < 1:
    raise SystemExit("expected mandatory candidates")
target_ids = {item.get("path_id") for item in payload.get("targets", [])}
if "destructive_shell_exec" not in target_ids:
    raise SystemExit("expected destructive_shell_exec target")
if "network_sensitive_exec" not in target_ids:
    raise SystemExit("expected network_sensitive_exec target")
print("kernel mediation coverage smoke: PASS")
PY
