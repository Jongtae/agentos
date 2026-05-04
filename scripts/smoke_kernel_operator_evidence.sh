#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE/artifacts"

cat > "$WORKSPACE/spec.yaml" <<'EOF'
name: "operator-evidence-smoke"
kernel_engine:
  provider: "none"
  mode: "single"
runtime:
  workspace_root: "./"
EOF

cat > "$WORKSPACE/artifacts/runtime_trace.jsonl" <<'EOF'
{"timestamp_utc":"2026-04-14T00:00:00+00:00","event":"approval_requested","payload":{"tool_name":"bash"}}
{"timestamp_utc":"2026-04-14T00:00:01+00:00","event":"step_blocked","payload":{"reason":"workspace_boundary","detail":"../outside.txt"}}
EOF

cat > "$WORKSPACE/artifacts/os_events.jsonl" <<'EOF'
{"timestamp_utc":"2026-04-14T00:00:00+00:00","source":"broker","kind":"broker.approval_request","actor":{"component":"agentos-runtime"},"object":{"policy_target":"destructive_action_approval","tool_name":"bash"},"action":"approval_gate","decision":{"state":"requested","request_kind":"approval"},"correlation":{"approval_id":"approval:test"},"raw_ref":{"component":"broker"}}
{"timestamp_utc":"2026-04-14T00:00:01+00:00","source":"kernel","kind":"file.outside_workspace_candidate","actor":{"pid":7},"object":{"path":"../outside.txt","workspace_root":"./"},"action":"read","decision":{"state":"candidate","policy_target":"fs_workspace_boundary"},"correlation":{"session_id":"agentos:tty1"},"raw_ref":{"collector":"file_access_candidate"}}
{"timestamp_utc":"2026-04-14T00:00:02+00:00","source":"journald","kind":"session.login","actor":{"uid":1000},"object":{"session_id":"agentos:tty1"},"action":"login","decision":{"state":"observed"},"correlation":{"session_id":"agentos:tty1","boot_id":"boot-1"},"raw_ref":{"collector":"journald"}}
EOF

OUT_JSON="$TMP_DIR/evidence.json"
scripts/agentos-kernelctl evidence --workspace "$WORKSPACE" --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if not payload.get("ok", False):
    raise SystemExit("expected evidence ok=true")
summary = payload.get("summary", {})
if "destructive_action_approval" not in [item.get("policy_target") for item in summary.get("policy_targets", [])]:
    raise SystemExit("expected destructive_action_approval in summary policy targets")
if not isinstance(payload.get("broker_status", {}).get("activity", {}), dict):
    raise SystemExit("expected broker activity summary")
handoff = payload.get("handoff", {})
if handoff.get("default_artifact") != "review_bundle":
    raise SystemExit("expected review_bundle as default handoff artifact")
if "review-bundle" not in handoff.get("recommended_command", ""):
    raise SystemExit("expected review-bundle command in handoff")
if payload.get("install_validation", {}).get("available") is not False:
    raise SystemExit("expected install validation unavailable without install-root")
PY

echo "kernel operator evidence smoke: PASS"
