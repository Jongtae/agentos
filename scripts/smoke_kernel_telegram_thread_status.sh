#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$(mktemp -d)"
trap 'rm -rf "$WORKSPACE"' EXIT

"$ROOT_DIR/scripts/agentos-kernelctl" telegram-thread-status \
  --workspace "$WORKSPACE" \
  --message-text "search agentos roadmap" \
  --chat-id 1001 \
  --request-id r1 \
  --json >/tmp/agentos-telegram-thread-first.json

"$ROOT_DIR/scripts/agentos-kernelctl" telegram-thread-status \
  --workspace "$WORKSPACE" \
  --message-text "summarize that" \
  --chat-id 1001 \
  --request-id r2 \
  --follow-up \
  --json >/tmp/agentos-telegram-thread-followup.json

python3 - /tmp/agentos-telegram-thread-followup.json <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["schema_version"] == "agentos-telegram-thread-status.v1"
assert payload["follow_up_linked"] is True
assert payload["rejoin_lookup_succeeded"] is True
assert payload["telegram_thread_continuity_ready"] is True
assert payload["previous_context"]["request_id"] == "r1"
PY

echo "kernel telegram thread status smoke: PASS"
