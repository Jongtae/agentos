#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
USER_ROOT="$TMP_DIR/user"
SECRETS="$TMP_DIR/secrets/gmail"
mkdir -p "$WORKSPACE" "$USER_ROOT" "$SECRETS"
cat > "$TMP_DIR/mock-gmail.json" <<'JSON'
{
  "messages": [
    {
      "id": "roadmap-2",
      "from": "Reviewer <reviewer@example.com>",
      "subject": "AgentOS roadmap",
      "snippet": "The live Gmail adapter mock path proves the Phase 2 loop can store a read-only summary.",
      "body": "The live Gmail adapter mock path proves the Phase 2 loop can store a read-only summary."
    }
  ]
}
JSON

AGENTOS_GMAIL_SETUP_URL="http://127.0.0.1:8789/setup" \
scripts/agentos-kernelctl phase2-run \
  --workspace "$WORKSPACE" \
  --user-root "$USER_ROOT" \
  --gmail-live \
  --gmail-credentials "$SECRETS/credentials.json" \
  --gmail-token "$SECRETS/token.json" \
  --message "summarize my latest Gmail roadmap email" \
  --json > "$TMP_DIR/phase2-gmail-live.json"

python3 - "$TMP_DIR/phase2-gmail-live.json" "$USER_ROOT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
user_root = Path(sys.argv[2])

assert payload["schema_version"] == "agentos-phase2-run.v1", payload
assert payload["intent"] == "gmail_read_or_draft", payload
assert payload["capability"] == "gmail_read_or_draft", payload
assert payload["status"] == "blocked", payload
assert payload["proof"]["ok"] is True, payload
assert payload["proof"]["gmail_fixture_mode"] is False, payload
assert payload["proof"]["live_gmail_oauth_completed"] is False, payload
assert payload["blockers"][0]["id"] == "gmail-live-oauth-required", payload
assert payload["blockers"][0]["setup_page_url"] == "http://127.0.0.1:8789/setup", payload
assert "gmail-setup --serve-http" in payload["blockers"][0]["recovery_action"], payload
assert Path(payload["artifacts"]["record_path"]).exists(), payload
assert (user_root / "records" / "records.jsonl").exists(), payload
assert "refresh_token" not in json.dumps(payload, ensure_ascii=True), payload
PY

scripts/agentos-kernelctl phase2-run \
  --workspace "$WORKSPACE" \
  --user-root "$USER_ROOT" \
  --gmail-live \
  --gmail-mock-response "$TMP_DIR/mock-gmail.json" \
  --message "summarize my latest Gmail roadmap email" \
  --json > "$TMP_DIR/phase2-gmail-live-mock.json"

python3 - "$TMP_DIR/phase2-gmail-live-mock.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

assert payload["schema_version"] == "agentos-phase2-run.v1", payload
assert payload["status"] == "completed", payload
assert payload["proof"]["gmail_fixture_mode"] is False, payload
assert payload["proof"]["gmail_live_read_completed"] is True, payload
assert payload["proof"]["live_gmail_oauth_completed"] is False, payload
assert payload["capability_result"]["adapter"] == "gmail_oauth_readonly_mock", payload
assert "Gmail read-only summary" in payload["response"], payload
assert Path(payload["artifacts"]["record_path"]).exists(), payload
PY

echo "phase2 gmail live blocked smoke: PASS"
