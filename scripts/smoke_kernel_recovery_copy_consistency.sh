#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE/artifacts"
OUT_JSON="$TMP_DIR/recovery-copy-consistency.json"

python3 scripts/kernel_recovery_copy_consistency.py \
  --workspace "$WORKSPACE" \
  --report-dir "$WORKSPACE/artifacts/public-preview" \
  --snapshot-label smoke \
  --output "$OUT_JSON" \
  --json >/dev/null

python3 scripts/kernel_recovery_copy_consistency.py --validate "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json, pathlib, sys
payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
assert payload["schema_version"] == "agentos-recovery-copy-consistency.v1"
assert payload["canonical_recovery_summary"] == "AgentOS Recovery -> Return to AgentOS -> ai>"
assert payload["canonical_recovery_detail"] == "AgentOS Recovery -> AgentOS Setup -> AgentOS Managed Session -> ai>"
assert payload["summary"]["overall_state"] in {"watch", "ready"}
assert pathlib.Path(payload["artifacts"]["recovery_copy_consistency_manifest_json"]).exists()
print("kernel recovery copy consistency smoke: PASS")
PY
