#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE/artifacts"

cat > "$WORKSPACE/artifacts/runtime_trace.jsonl" <<'EOF'
{"timestamp_utc":"2026-04-14T00:00:00+00:00","event":"approval_requested","payload":{"tool_name":"bash","risk_reason":"destructive command","broker":{"kind":"approval"}}}
{"timestamp_utc":"2026-04-14T00:00:01+00:00","event":"approval_decision","payload":{"tool_name":"bash","approved":false,"broker":{"state":"denied"}}}
EOF

cat > "$WORKSPACE/artifacts/kernel-shadow-events.jsonl" <<'EOF'
{"timestamp_utc":"2026-04-14T00:00:00+00:00","event":"kernel.shadow.destructive_action.v1","payload":{"policy_target":"destructive_action_approval","approval_id":"approval:test","action":"approval_gate"}}
EOF

cat > "$WORKSPACE/artifacts/os_events.jsonl" <<'EOF'
{"timestamp_utc":"2026-04-14T00:00:00+00:00","source":"broker","kind":"broker.approval_request","actor":{"component":"agentos-runtime"},"object":{"policy_target":"destructive_action_approval","tool_name":"bash"},"action":"approval_gate","decision":{"state":"requested","request_kind":"approval"},"correlation":{"approval_id":"approval:test"},"raw_ref":{"component":"broker"}}
{"timestamp_utc":"2026-04-14T00:00:01+00:00","source":"broker","kind":"broker.approval_decision","actor":{"component":"agentos-runtime"},"object":{"policy_target":"destructive_action_approval","tool_name":"bash"},"action":"decision","decision":{"state":"denied","request_kind":"approval"},"correlation":{"approval_id":"approval:test"},"raw_ref":{"component":"broker"}}
EOF

OUT_SHADOW="$TMP_DIR/shadow.json"
python3 scripts/kernel_policy_shadow_report.py --workspace "$WORKSPACE" --json > "$OUT_SHADOW"

python3 - "$OUT_SHADOW" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
target = next(item for item in payload["policy_targets"] if item["policy_target"] == "destructive_action_approval")
if target["comparison"]["status"] != "aligned":
    raise SystemExit("expected destructive_action_approval shadow alignment")
if payload.get("next_policy_target") != "destructive_action_approval":
    raise SystemExit("expected next_policy_target=destructive_action_approval")
PY

OUT_POLICY="$TMP_DIR/policy.json"
scripts/agentos-kernelctl policy-correlation --workspace "$WORKSPACE" --json > "$OUT_POLICY"

python3 - "$OUT_POLICY" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
target = next(item for item in payload["policy_targets"] if item["policy_target"] == "destructive_action_approval")
if target["comparison"]["status"] != "aligned":
    raise SystemExit("expected destructive_action_approval policy evidence alignment")
if target["evidence_kind"] != "broker.approval_request":
    raise SystemExit("expected broker.approval_request evidence kind")
PY

echo "kernel policy approval candidate smoke: PASS"
