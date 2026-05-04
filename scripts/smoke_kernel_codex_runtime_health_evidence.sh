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
if [ "${1:-}" = "exec" ]; then
  printf 'HEALTH_OK'
  exit 0
fi
if [ "${1:-}" = "--output-last-message" ]; then
  shift
  printf 'HEALTH_OK'
  exit 0
fi
printf 'HEALTH_OK'
EOF
chmod +x "$FAKE_CODEX"

cat >"$WORKSPACE/spec.yaml" <<EOF
name: codex-runtime-health-evidence-smoke
tools:
  bash: true
kernel_engine:
  provider: codex
  mode: single
  codex:
    command: "$FAKE_CODEX"
    timeout_sec: 5
    model: gpt-test
    supervision:
      enabled: true
      restart_policy: on_failure
      max_attempts: 3
      cooldown_sec: 1
EOF

export OPENAI_API_KEY=dummy
export AGENTOS_SESSION_MANAGED=1
export AGENTOS_SESSION_ENTRY=live_appliance
export AGENTOS_CODEX_SUPERVISION_STATE_FILE="$TMP_DIR/codex-launch-supervision.json"
python3 "$ROOT_DIR/scripts/agentos_codex_supervisor.py" --workspace "$WORKSPACE" --json >/dev/null

OUT="$TMP_DIR/codex-runtime-health-evidence.json"
python3 "$ROOT_DIR/scripts/kernel_codex_runtime_health_evidence.py" --workspace "$WORKSPACE" --output "$OUT"
python3 "$ROOT_DIR/scripts/kernel_codex_runtime_health_evidence.py" --validate "$OUT" --json >/dev/null

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
if payload.get('schema_version') != 'agentos-codex-runtime-health-evidence.v1':
    raise SystemExit('expected codex runtime health evidence schema')
if not payload.get('summary', {}).get('ok'):
    raise SystemExit('expected runtime health evidence ok')
if payload.get('summary', {}).get('last_launch_state') != 'succeeded':
    raise SystemExit('expected succeeded last launch state')
print('kernel codex runtime health evidence smoke: PASS')
PY
