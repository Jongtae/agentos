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
printf 'HEALTH_OK'
EOF
chmod +x "$FAKE_CODEX"

cat >"$WORKSPACE/spec.yaml" <<EOF
name: codex-launch-supervision-smoke
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
export AGENTOS_CODEX_SUPERVISION_STATE_FILE="$TMP_DIR/codex-launch-supervision.json"
python3 "$ROOT_DIR/scripts/agentos_codex_supervisor.py" --workspace "$WORKSPACE" --json >/dev/null

OUT="$TMP_DIR/codex-launch-supervision-report.json"
python3 "$ROOT_DIR/scripts/kernel_codex_launch_supervision.py" --workspace "$WORKSPACE" --output "$OUT"
python3 "$ROOT_DIR/scripts/kernel_codex_launch_supervision.py" --validate "$OUT" --json >/dev/null

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
if payload.get('schema_version') != 'agentos-codex-launch-supervision.v1':
    raise SystemExit('expected codex launch supervision schema')
if payload.get('restart_policy') != 'on_failure':
    raise SystemExit('expected on_failure restart policy')
if payload.get('last_launch_state') != 'succeeded':
    raise SystemExit('expected succeeded launch state')
if payload.get('runtime_owner') != 'codex_cli_managed_session':
    raise SystemExit('expected managed runtime owner')
print('kernel codex launch supervision smoke: PASS')
PY
