#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$TMP_DIR/status.json" <<'JSON'
{
  "schema_version": "agentos-gmail-status.v1",
  "credentials_path": "/tmp/credentials.json",
  "token_path": "/tmp/token.json",
  "secrets_redacted": true,
  "live_read_ready": false,
  "proof": {"ok": false, "reason": "gmail_token_missing"}
}
JSON

cat > "$TMP_DIR/read-mock.json" <<'JSON'
{
  "schema_version": "agentos-gmail-read.v1",
  "credentials_path": "/tmp/credentials.json",
  "token_path": "/tmp/token.json",
  "secrets_redacted": true,
  "adapter": "gmail_oauth_readonly_mock",
  "matched_count": 1,
  "messages": [{"id": "msg-1", "subject": "Roadmap"}],
  "proof": {"ok": true, "reason": "mock_gmail_response_used"}
}
JSON

OUT="$TMP_DIR/acceptance.json"
python3 scripts/kernel_gmail_live_acceptance.py \
  --workspace "$TMP_DIR/workspace" \
  --status-json "$TMP_DIR/status.json" \
  --read-json "$TMP_DIR/read-mock.json" \
  --query roadmap \
  --output "$OUT"

python3 scripts/kernel_gmail_live_acceptance.py --validate "$OUT" --json >/dev/null

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-gmail-live-acceptance.v1", payload
assert payload["proof"]["manual_acceptance_pack_completed"] is True, payload
assert payload["proof"]["live_gmail_oauth_completed"] is False, payload
assert payload["proof"]["gmail_mutation_executed"] is False, payload
assert payload["validation"]["mock_used"] is True, payload
assert payload["blockers"][0]["id"] == "gmail-live-oauth-proof-not-observed", payload
assert "refresh_token" not in json.dumps(payload, ensure_ascii=True), payload
PY

cat > "$TMP_DIR/status-live.json" <<'JSON'
{
  "schema_version": "agentos-gmail-status.v1",
  "credentials_path": "/tmp/credentials.json",
  "token_path": "/tmp/token.json",
  "secrets_redacted": true,
  "live_read_ready": true,
  "proof": {"ok": true, "reason": "gmail_ready"}
}
JSON

cat > "$TMP_DIR/read-live.json" <<'JSON'
{
  "schema_version": "agentos-gmail-read.v1",
  "credentials_path": "/tmp/credentials.json",
  "token_path": "/tmp/token.json",
  "secrets_redacted": true,
  "adapter": "gmail_oauth_readonly",
  "matched_count": 1,
  "messages": [{"id": "live-1", "subject": "Roadmap"}],
  "proof": {"ok": true, "reason": "gmail_live_read_ok"}
}
JSON

LIVE_OUT="$TMP_DIR/acceptance-live.json"
python3 scripts/kernel_gmail_live_acceptance.py \
  --workspace "$TMP_DIR/workspace" \
  --status-json "$TMP_DIR/status-live.json" \
  --read-json "$TMP_DIR/read-live.json" \
  --query roadmap \
  --output "$LIVE_OUT"
python3 scripts/kernel_gmail_live_acceptance.py --validate "$LIVE_OUT" --require-live --json >/dev/null

echo "gmail live acceptance pack smoke: PASS"
