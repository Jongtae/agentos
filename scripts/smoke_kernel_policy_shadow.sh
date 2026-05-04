#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE/artifacts"

cat > "$WORKSPACE/spec.yaml" <<'EOF'
name: "kernel-policy-shadow-smoke"
ai_model:
  provider: "openai"
  model: "gpt-4o-mini"
kernel_engine:
  provider: "none"
  mode: "single"
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
EOF

cat > "$WORKSPACE/artifacts/runtime_trace.jsonl" <<'EOF'
{"timestamp_utc":"2026-01-01T00:00:00Z","event":"step_blocked","payload":{"reason":"workspace_boundary","detail":"../outside.txt"}}
{"timestamp_utc":"2026-01-01T00:00:01Z","event":"step_blocked","payload":{"reason":"workspace_boundary","detail":"../outside2.txt"}}
{"timestamp_utc":"2026-01-01T00:00:02Z","event":"step_blocked","payload":{"reason":"network_allowlist","detail":"blocked.example"}}
{"timestamp_utc":"2026-01-01T00:00:03Z","event":"approval_requested","payload":{"tool_name":"bash","risk_reason":"destructive command"}}
EOF

cat > "$WORKSPACE/artifacts/kernel-shadow-events.jsonl" <<'EOF'
{"timestamp_utc":"2026-01-01T00:00:00Z","event":"kernel.shadow.fs_outside_workspace.v1","payload":{"policy_target":"fs_workspace_boundary","path":"../outside.txt","action":"read"}}
{"timestamp_utc":"2026-01-01T00:00:01Z","event":"kernel.shadow.fs_outside_workspace.v1","payload":{"policy_target":"fs_workspace_boundary","path":"../outside2.txt","action":"write"}}
{"timestamp_utc":"2026-01-01T00:00:02Z","event":"kernel.shadow.net_allowlist_violation.v1","payload":{"policy_target":"network_allowlist","host":"blocked.example","port":443,"action":"connect"}}
{"timestamp_utc":"2026-01-01T00:00:03Z","event":"kernel.shadow.destructive_action.v1","payload":{"policy_target":"destructive_action_approval","approval_id":"approval:test","action":"approval_gate"}}
EOF

OUT_JSON="$TMP_DIR/shadow.json"
scripts/agentos-kernelctl policy-shadow --workspace "$WORKSPACE" --out-dir "$OUT_JSON" --json > /dev/null

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("policy_target") != "fs_workspace_boundary":
    raise SystemExit("unexpected policy_target")
if payload.get("primary_policy_target") != "fs_workspace_boundary":
    raise SystemExit("unexpected primary_policy_target")
if payload.get("user_space_blocked_count") != 2:
    raise SystemExit("expected user_space_blocked_count=2")
if payload.get("shadow_detected_count") != 2:
    raise SystemExit("expected shadow_detected_count=2")
if not payload.get("comparison", {}).get("aligned", False):
    raise SystemExit("expected aligned comparison=true")
if payload.get("coverage_summary", {}).get("policy_target_count") != 3:
    raise SystemExit("expected coverage_summary.policy_target_count=3")
targets = {item["policy_target"]: item for item in payload.get("policy_targets", [])}
network = targets.get("network_allowlist", {})
if network.get("shadow_detected_count") != 1:
    raise SystemExit("expected network shadow_detected_count=1")
if network.get("comparison", {}).get("status") != "aligned":
    raise SystemExit("expected network status=aligned")
approval = targets.get("destructive_action_approval", {})
if approval.get("shadow_detected_count") != 1:
    raise SystemExit("expected approval shadow_detected_count=1")
if approval.get("comparison", {}).get("status") != "aligned":
    raise SystemExit("expected approval status=aligned")
if not payload.get("overall_aligned", False):
    raise SystemExit("expected overall_aligned=true")
PY

echo "kernel policy shadow smoke: PASS"
