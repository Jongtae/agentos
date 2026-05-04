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
echo HEALTH_OK >/dev/null
exit 0
EOF
chmod +x "$FAKE_CODEX"

cat >"$WORKSPACE/spec.yaml" <<EOF
name: codex-runtime-contract-smoke
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

OUT="$TMP_DIR/codex-runtime-contract.json"
export OPENAI_API_KEY=dummy
export AGENTOS_SESSION_MANAGED=1
export AGENTOS_SESSION_ENTRY=live_appliance

python3 "$ROOT_DIR/scripts/kernel_codex_runtime_contract.py" --workspace "$WORKSPACE" --output "$OUT"
python3 "$ROOT_DIR/scripts/kernel_codex_runtime_contract.py" --validate "$OUT" --json >/dev/null

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
if payload.get('schema_version') != 'agentos-codex-runtime-contract.v1':
    raise SystemExit('expected codex runtime contract schema')
if payload.get('primary_runtime') != 'codex_cli':
    raise SystemExit('expected codex_cli primary runtime')
if payload.get('provider_contract', {}).get('expected_provider') != 'codex':
    raise SystemExit('expected codex provider contract')
if not payload.get('launch_contract', {}).get('command_available'):
    raise SystemExit('expected available codex command')
if payload.get('continuity_contract', {}).get('rejoin_target') != 'codex_cli_managed_session':
    raise SystemExit('expected codex runtime rejoin target')
if 'Codex CLI Managed Session' not in payload.get('launch_contract', {}).get('launch_path', []):
    raise SystemExit('expected codex launch path wording')
print('kernel codex runtime contract smoke: PASS')
PY
