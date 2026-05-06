#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

FIXTURE="$TMP_DIR/gmail-fixture.json"
cat >"$FIXTURE" <<'JSON'
{
  "messages": [
    {
      "id": "msg-1",
      "from": "Mina <mina@example.com>",
      "to": "operator@example.com",
      "subject": "AgentOS roadmap review",
      "body": "Can you review the Phase 2 roadmap and send me a concise draft reply?",
      "labels": ["INBOX", "IMPORTANT"]
    },
    {
      "id": "msg-2",
      "from": "Ops <ops@example.com>",
      "to": "operator@example.com",
      "subject": "Build logs",
      "body": "The latest smoke logs are attached for local review.",
      "labels": ["INBOX"]
    }
  ]
}
JSON

OUT="$TMP_DIR/result.json"
PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR" python3 scripts/kernel_phase2_gmail_fixture.py \
  --fixture "$FIXTURE" \
  --query roadmap \
  --action draft \
  --json >"$OUT"

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-phase2-gmail-fixture.v1"
assert payload["adapter"] == "gmail_fixture"
assert payload["real_gmail_credentials_used"] is False
assert payload["matched_count"] == 1
assert payload["messages"][0]["id"] == "msg-1"
assert payload["draft"]["requires_confirmation"] is True
assert payload["draft"]["send_allowed"] is False
assert "send" in payload["blocked_actions"]
assert payload["proof"]["ok"] is True
assert payload["proof"]["blocker"] == "real_gmail_oauth_not_configured"
PY

echo "phase2 gmail fixture smoke: PASS"
