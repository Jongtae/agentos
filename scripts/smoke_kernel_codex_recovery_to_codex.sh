#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"

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
name: codex-recovery-to-codex-smoke
tools:
  bash: true
kernel_engine:
  provider: codex
  mode: single
  codex:
    command: "$FAKE_CODEX"
    timeout_sec: 5
    model: gpt-test
EOF

OUT="$TMP_DIR/codex-recovery-to-codex.json"
export OPENAI_API_KEY=dummy
export AGENTOS_SESSION_MANAGED=1
export AGENTOS_SESSION_ENTRY=live_appliance

python3 "$ROOT_DIR/scripts/kernel_codex_recovery_to_codex.py" --workspace "$WORKSPACE" --output "$OUT"
python3 "$ROOT_DIR/scripts/kernel_codex_recovery_to_codex.py" --validate "$OUT" --json >/dev/null

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
if payload.get('schema_version') != 'agentos-codex-recovery-to-codex.v1':
    raise SystemExit('expected codex recovery to codex schema')
if payload.get('runtime_rejoin_target') != 'codex_cli_managed_session':
    raise SystemExit('expected codex recovery target')
if 'Codex CLI Managed Session' not in payload.get('detailed_rejoin_path', []):
    raise SystemExit('expected detailed codex rejoin path')
print('kernel codex recovery to codex smoke: PASS')
PY
