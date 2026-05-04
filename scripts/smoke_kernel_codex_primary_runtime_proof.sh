#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE/sandbox"

FAKE_CODEX="$TMP_DIR/fake-codex.sh"
cat >"$FAKE_CODEX" <<'EOF'
#!/usr/bin/env bash
if [ "${1:-}" = "--output-last-message" ]; then
  shift
  printf 'HEALTH_OK'
  exit 0
fi
printf 'HEALTH_OK'
EOF
chmod +x "$FAKE_CODEX"

cat >"$WORKSPACE/spec.yaml" <<EOF
name: codex-runtime-proof-smoke
tools:
  bash: true
runtime:
  workspace_root: ./sandbox
kernel_engine:
  provider: codex
  mode: single
  codex:
    command: "$FAKE_CODEX"
    timeout_sec: 5
    model: gpt-test
EOF

OUT="$TMP_DIR/codex-runtime-proof.json"
export OPENAI_API_KEY=dummy
export AGENTOS_SESSION_MANAGED=1
export AGENTOS_SESSION_ENTRY=live_appliance

python3 "$ROOT_DIR/scripts/kernel_codex_primary_runtime_proof.py" --workspace "$WORKSPACE" --output "$OUT"
python3 "$ROOT_DIR/scripts/kernel_codex_primary_runtime_proof.py" --validate "$OUT" --json >/dev/null

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
if payload.get('schema_version') != 'agentos-codex-primary-runtime-proof.v1':
    raise SystemExit('expected codex primary runtime proof schema')
summary = payload.get('summary', {})
if not summary.get('ok'):
    raise SystemExit('expected overall runtime proof ok')
if not summary.get('primary_runtime_ok'):
    raise SystemExit('expected primary_runtime_ok')
if not summary.get('runtime_contract_ok'):
    raise SystemExit('expected runtime_contract_ok')
print('kernel codex primary runtime proof smoke: PASS')
PY
