#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE/artifacts"

scripts/vm_demo_flow.sh --workspace "$WORKSPACE" --dry-run > "$TMP_DIR/vm-flow.txt"
if ! rg -q "AgentOS Setup" "$TMP_DIR/vm-flow.txt"; then
  echo "expected AgentOS Setup in vm demo flow"
  exit 1
fi

cat > "$WORKSPACE/spec.yaml" <<'EOF'
name: "vm-session-replay-smoke"
kernel_engine:
  provider: "none"
  mode: "single"
runtime:
  workspace_root: "./"
EOF

cat > "$WORKSPACE/artifacts/runtime_trace.jsonl" <<'EOF'
{"timestamp_utc":"2026-04-14T00:00:00+00:00","event":"run_start","payload":{}}
{"timestamp_utc":"2026-04-14T00:00:01+00:00","event":"approval_requested","payload":{"tool_name":"bash"}}
{"timestamp_utc":"2026-04-14T00:00:02+00:00","event":"step_blocked","payload":{"reason":"workspace_boundary","detail":"../outside.txt"}}
EOF

cat > "$WORKSPACE/artifacts/os_events.jsonl" <<'EOF'
{"timestamp_utc":"2026-04-14T00:00:01+00:00","source":"broker","kind":"broker.approval_request","actor":{"component":"agentos-runtime"},"object":{"policy_target":"destructive_action_approval","tool_name":"bash"},"action":"approval_gate","decision":{"state":"requested","request_kind":"approval"},"correlation":{"approval_id":"approval:test","session_id":"agentos:tty1","boot_id":"boot-1"},"raw_ref":{"component":"broker"}}
{"timestamp_utc":"2026-04-14T00:00:03+00:00","source":"journald","kind":"session.login","actor":{"uid":1000},"object":{"session_id":"agentos:tty1"},"action":"login","decision":{"state":"observed"},"correlation":{"session_id":"agentos:tty1","boot_id":"boot-1","session_origin":"local_managed_tty1","next_managed_entry":"setup_session"},"raw_ref":{"collector":"journald"}}
{"timestamp_utc":"2026-04-14T00:00:04+00:00","source":"journald","kind":"systemd.unit_state","actor":{"uid":0},"object":{"unit":"agentos-kernel.service","session_id":"agentos:tty1"},"action":"started","decision":{"state":"active"},"correlation":{"session_id":"agentos:tty1","boot_id":"boot-1","session_origin":"local_managed_tty1","next_managed_entry":"ai_shell"},"raw_ref":{"collector":"journald"}}
EOF

OUT_JSON="$TMP_DIR/vm-replay.json"
scripts/agentos-kernelctl replay --workspace "$WORKSPACE" --session-id agentos:tty1 --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
ownership = payload.get("ownership_summary", {})
if ownership.get("session_origin") != "local_managed_tty1":
    raise SystemExit("expected local_managed_tty1 origin")
milestones = [item.get("milestone") for item in payload.get("milestones", [])]
for expected in ("run_start", "broker.approval_request", "session.login", "systemd.unit_state"):
    if expected not in milestones:
        raise SystemExit(f"missing milestone {expected}")
PY

echo "vm session replay smoke: PASS"
