#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$(mktemp -d)"
trap 'rm -rf "$WORKSPACE"' EXIT

OUT="$WORKSPACE/inbox-reply-workflow.json"
"$ROOT_DIR/scripts/agentos-kernelctl" inbox-reply-workflow --workspace "$WORKSPACE" --output "$OUT" --json >/tmp/agentos-inbox-reply-workflow.out

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["schema_version"] == "agentos-inbox-reply-workflow.v1"
assert payload["inbox_reply_workflow_ready"] is True
assert payload["reply_draft_ready"] is True
assert payload["summary"]["native_vs_adapter_split_recorded"] is True
assert payload["source_status"]["imap_adapter_ready"] is False
assert payload["source_status"]["imap_adapter_blocked_reason"] == "runtime_credentials_not_configured"
PY

echo "kernel inbox reply workflow smoke: PASS"
