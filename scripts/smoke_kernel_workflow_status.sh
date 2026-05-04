#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$(mktemp -d)"
trap 'rm -rf "$WORKSPACE"' EXIT

mkdir -p "$WORKSPACE/documents" "$WORKSPACE/artifacts/capability-substrate"
cat >"$WORKSPACE/spec.yaml" <<'EOF'
name: workflow-status-smoke
tools:
  bash: true
  file: true
  web: true
EOF
cat >"$WORKSPACE/documents/agentos-first-run.md" <<'EOF'
# First run
EOF

OUT="$WORKSPACE/workflow-status.json"
"$ROOT_DIR/scripts/agentos-kernelctl" workflow-status --workspace "$WORKSPACE" --output "$OUT" --json >/tmp/agentos-workflow-status-smoke.out
"$ROOT_DIR/scripts/kernel_workflow_status.py" --validate "$OUT" --json | python3 -c \
  "import json,sys; payload=json.load(sys.stdin); assert payload['ok'] is True"

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["schema_version"] == "agentos-workflow-status.v1"
assert payload["capability"] == "workflow_status"
assert payload["guided_operator_surface_reachable"] is True
assert payload["summary"]["workflow_status_ready"] is True
assert payload["summary"]["external_secret_blocked"] is True
assert payload["runtime_secret_readiness"]["telegram_secret_source"] == "none"
assert payload["runtime_secret_readiness"]["telegram_live_send_ready"] is False
assert [item["workflow_id"] for item in payload["workflows"]] == [
    "research_request_response",
    "inbox_triage_summary_response",
    "telegram_thread_continuity",
    "inbox_reply_workflow",
    "research_brief_response",
    "live_telegram_reply_send",
]
assert payload["summary"]["telegram_thread_continuity_ready"] is False
assert payload["summary"]["inbox_reply_workflow_ready"] is False
assert payload["summary"]["research_brief_ready"] is False
assert payload["summary"]["brief_artifact_exported"] is False
assert any(item["id"] == "search_and_reply" for item in payload["top_tasks"])
assert any("telegram-live-send" in action for action in payload["next_actions"])
assert any("telegram-thread-status" in action for action in payload["next_actions"])
assert any("inbox-reply-workflow" in action for action in payload["next_actions"])
assert any("research-brief" in action for action in payload["next_actions"])
PY

echo "kernel workflow status smoke: PASS"
