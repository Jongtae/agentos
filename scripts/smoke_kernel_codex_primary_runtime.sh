#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

FAKE_CODEX="$TMP_DIR/fake-codex.sh"
cat > "$FAKE_CODEX" <<'EOF'
#!/usr/bin/env bash
OUT=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output-last-message)
      OUT="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done
if [ -n "$OUT" ]; then
  printf '%s\n' 'HEALTH_OK' > "$OUT"
else
  printf '%s\n' 'HEALTH_OK'
fi
exit 0
EOF
chmod +x "$FAKE_CODEX"

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"
cat > "$WORKSPACE/spec.yaml" <<EOF
name: codex-primary-runtime-smoke
tools:
  bash: true
kernel_engine:
  provider: codex
  mode: single
  codex:
    command: "$FAKE_CODEX"
    timeout_sec: 5
    model: "gpt-smoke"
EOF

OUT="$TMP_DIR/codex-primary-runtime.json"
OPENAI_API_KEY=dummy \
AGENTOS_SESSION_MANAGED=1 \
AGENTOS_SESSION_ENTRY=live_appliance \
python3 "$ROOT_DIR/scripts/kernel_codex_primary_runtime.py" --workspace "$WORKSPACE" --output "$OUT"

python3 "$ROOT_DIR/scripts/kernel_codex_primary_runtime.py" --validate "$OUT" --json >/dev/null

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
if payload.get('schema_version') != 'agentos-codex-primary-runtime.v1':
    raise SystemExit('expected codex primary runtime schema')
if payload.get('primary_runtime') != 'codex_cli':
    raise SystemExit('expected codex_cli primary runtime')
if payload.get('configured_provider') != 'codex':
    raise SystemExit('expected configured provider codex')
if payload.get('command_available') is not True:
    raise SystemExit('expected command_available true')
if payload.get('proof_status') != 'ready':
    raise SystemExit('expected proof_status ready')
if 'Codex CLI Managed Session' not in payload.get('launch_path', []):
    raise SystemExit('expected Codex CLI managed session in launch path')
print('kernel codex primary runtime smoke: PASS')
PY
