#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

INSTALL_ROOT="$TMP_DIR/root"
WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE"

FAKE_CODEX="$TMP_DIR/fake-codex.sh"
cat > "$FAKE_CODEX" <<'EOS'
#!/bin/sh
set -eu
out_file=""
prompt=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output-last-message)
      shift
      out_file="$1"
      ;;
    *)
      prompt="$1"
      ;;
  esac
  shift
done
if echo "$prompt" | grep -q 'Reply with exactly: HEALTH_OK'; then
  msg='HEALTH_OK'
else
  msg='{"summary":"noop","steps":[]}'
fi
if [ -n "$out_file" ]; then
  printf "%s" "$msg" > "$out_file"
fi
printf "%s\n" "$msg"
EOS
chmod +x "$FAKE_CODEX"

cat > "$WORKSPACE/spec.yaml" <<EOS
name: "kernel-audit-smoke"
ai_model:
  provider: "openai"
  model: "gpt-4o-mini"
kernel_engine:
  provider: "codex"
  mode: "single"
  codex:
    command: "$FAKE_CODEX"
    timeout_sec: 10
    model: ""
tools:
  bash: true
  file: true
  web: true
permissions:
  require_approval: true
memory:
  checkpointer: "sqlite"
  db_path: "./data/session.sqlite"
  store_path: "./data/memory.sqlite"
runtime:
  max_steps: 4
  max_message_window: 20
  workspace_root: "./"
EOS

mkdir -p "$WORKSPACE/artifacts"
cat > "$WORKSPACE/artifacts/runtime_trace.jsonl" <<'EOF'
{"timestamp_utc":"2026-01-01T00:00:00Z","event":"step_blocked","payload":{"reason":"workspace_boundary","detail":"../outside.txt"}}
{"timestamp_utc":"2026-01-01T00:00:01Z","event":"approval_requested","payload":{"tool_name":"bash","risk_reason":"destructive command","broker":{"kind":"approval"}}}
EOF
cat > "$WORKSPACE/artifacts/kernel-shadow-events.jsonl" <<'EOF'
{"timestamp_utc":"2026-01-01T00:00:00Z","event":"kernel.shadow.fs_outside_workspace.v1","payload":{"policy_target":"fs_workspace_boundary","path":"../outside.txt","action":"read"}}
{"timestamp_utc":"2026-01-01T00:00:01Z","event":"kernel.shadow.destructive_action.v1","payload":{"policy_target":"destructive_action_approval","approval_id":"approval:test","action":"approval_gate"}}
EOF
cat > "$WORKSPACE/artifacts/os_events.jsonl" <<'EOF'
{"timestamp_utc":"2026-01-01T00:00:00Z","source":"kernel","kind":"file.outside_workspace_candidate","actor":{"pid":7},"object":{"path":"../outside.txt","workspace_root":"./"},"action":"read","decision":{"state":"candidate","policy_target":"fs_workspace_boundary"},"correlation":{},"raw_ref":{"collector":"file_access_candidate"}}
{"timestamp_utc":"2026-01-01T00:00:01Z","source":"broker","kind":"broker.approval_request","actor":{"component":"agentos-runtime"},"object":{"policy_target":"destructive_action_approval","tool_name":"bash"},"action":"approval_gate","decision":{"state":"requested","request_kind":"approval"},"correlation":{"approval_id":"approval:test"},"raw_ref":{"component":"broker"}}
EOF

AGENTOS_INSTALL_ROOT="$INSTALL_ROOT" \
AGENTOS_ENABLE_SYSTEMD=0 \
DEFAULT_WORKSPACE="$WORKSPACE" \
"$ROOT_DIR/scripts/install_kernel_boot_integration.sh"

OUT_JSON="$TMP_DIR/audit-ok.json"
"$ROOT_DIR/scripts/agentos-kernelctl" audit --workspace "$WORKSPACE" --install-root "$INSTALL_ROOT" --json > "$OUT_JSON"
python3 - "$OUT_JSON" <<'PY'
import json
import sys
payload = json.loads(open(sys.argv[1], 'r', encoding='utf-8').read())
if not payload.get('ok', False):
    raise SystemExit('expected audit ok=true')
shadow = payload.get("shadow_mode", {}) or {}
if not shadow.get("available", False):
    raise SystemExit("expected shadow_mode.available=true")
if not shadow.get("aligned", False):
    raise SystemExit("expected shadow_mode.aligned=true")
coverage = shadow.get("coverage_summary", {}) or {}
if int(coverage.get("policy_target_count", 0)) != 3:
    raise SystemExit("expected shadow coverage for three policy targets")
if len(shadow.get("policy_targets", []) or []) != 3:
    raise SystemExit("expected shadow_mode.policy_targets length 3")
event_fabric = payload.get("event_fabric", {}) or {}
if not event_fabric.get("available", False):
    raise SystemExit("expected event_fabric.available=true")
if not event_fabric.get("event_file_exists", False):
    raise SystemExit("expected event_fabric.event_file_exists=true")
if int(event_fabric.get("total_events", 0)) < 1:
    raise SystemExit("expected event_fabric.total_events >= 1")
if event_fabric.get("next_policy_target") != "destructive_action_approval":
    raise SystemExit("expected event_fabric.next_policy_target=destructive_action_approval")
if "destructive_action_approval" not in event_fabric.get("supported_policy_targets", []):
    raise SystemExit("expected supported_policy_targets to include destructive_action_approval")
PY

# mutate one managed file to ensure audit failure is detected
python3 - "$INSTALL_ROOT/etc/systemd/system/agentos-kernel.service" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
body = p.read_text(encoding='utf-8')
body = body.replace('--preflight', '--prefight')
p.write_text(body, encoding='utf-8')
PY

set +e
"$ROOT_DIR/scripts/agentos-kernelctl" audit --workspace "$WORKSPACE" --install-root "$INSTALL_ROOT" --json >/dev/null
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
  echo "[kernel-audit-smoke] expected non-zero for drifted service template"
  exit 1
fi

echo "kernelctl audit smoke: PASS"
