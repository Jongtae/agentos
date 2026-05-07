#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
PAGE_PID=""
cleanup() {
  if [ -n "$PAGE_PID" ] && kill -0 "$PAGE_PID" 2>/dev/null; then
    kill "$PAGE_PID" 2>/dev/null || true
    wait "$PAGE_PID" 2>/dev/null || true
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

WORKSPACE="$TMP_DIR/workspace"
SECRETS="$TMP_DIR/secrets/gmail"
mkdir -p "$WORKSPACE" "$SECRETS"

cat > "$TMP_DIR/credentials-source.json" <<'JSON'
{
  "installed": {
    "client_id": "agentos-smoke-client.apps.googleusercontent.com",
    "project_id": "agentos-smoke",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_secret": "agentos-smoke-client-secret",
    "redirect_uris": ["http://localhost"]
  }
}
JSON

cat > "$SECRETS/token.json" <<'JSON'
{
  "token": "agentos-smoke-access-token",
  "refresh_token": "agentos-smoke-refresh-token",
  "token_uri": "https://oauth2.googleapis.com/token",
  "client_id": "agentos-smoke-client.apps.googleusercontent.com",
  "client_secret": "agentos-smoke-client-secret",
  "scopes": ["https://www.googleapis.com/auth/gmail.readonly"]
}
JSON

cat > "$TMP_DIR/mock-gmail.json" <<'JSON'
{
  "messages": [
    {
      "id": "roadmap-1",
      "from": "Reviewer <reviewer@example.com>",
      "to": "operator@example.com",
      "subject": "Roadmap notes",
      "snippet": "Phase 2 Gmail setup page looks testable.",
      "body": "Phase 2 Gmail setup page looks testable and should remain read-only."
    }
  ]
}
JSON

setup_payload="$(scripts/agentos-kernelctl gmail-setup \
  --workspace "$WORKSPACE" \
  --credentials "$TMP_DIR/credentials-source.json" \
  --credentials-path "$SECRETS/credentials.json" \
  --token-path "$SECRETS/token.json" \
  --json)"

status_payload="$(scripts/agentos-kernelctl gmail-status \
  --workspace "$WORKSPACE" \
  --credentials-path "$SECRETS/credentials.json" \
  --token-path "$SECRETS/token.json" \
  --json || true)"

read_payload="$(scripts/agentos-kernelctl gmail-read \
  --workspace "$WORKSPACE" \
  --credentials-path "$SECRETS/credentials.json" \
  --token-path "$SECRETS/token.json" \
  --mock-response "$TMP_DIR/mock-gmail.json" \
  --query "roadmap" \
  --json)"

python3 - "$setup_payload" "$status_payload" "$read_payload" "$SECRETS" <<'PY'
import json
import os
import stat
import sys
from pathlib import Path

setup = json.loads(sys.argv[1])
status = json.loads(sys.argv[2])
read = json.loads(sys.argv[3])
secrets = Path(sys.argv[4])

assert setup["schema_version"] == "agentos-gmail-setup.v1", setup
assert setup["credentials_registered"] is True, setup
assert setup["proof"]["ok"] is True, setup
assert setup["proof"]["reason"] == "gmail_credentials_registered", setup
assert "client_secret" not in json.dumps(setup, ensure_ascii=True), setup

assert status["schema_version"] == "agentos-gmail-status.v1", status
assert status["credentials_configured"] is True, status
assert status["token_configured"] is True, status
assert status["proof"]["reason"] in {"gmail_ready", "gmail_oauth_dependencies_missing"}, status

assert read["schema_version"] == "agentos-gmail-read.v1", read
assert read["adapter"] == "gmail_oauth_readonly_mock", read
assert read["proof"]["ok"] is True, read
assert read["matched_count"] == 1, read
assert "Roadmap notes" in read["summary"], read
assert "client_secret" not in json.dumps(read, ensure_ascii=True), read

cred_mode = stat.S_IMODE((secrets / "credentials.json").stat().st_mode)
assert cred_mode & stat.S_IRWXG == 0 and cred_mode & stat.S_IRWXO == 0, oct(cred_mode)
PY

URL_FILE="$TMP_DIR/gmail-url"
PAGE_OUT="$TMP_DIR/gmail-page.json"
scripts/agentos-kernelctl gmail-setup \
  --workspace "$WORKSPACE" \
  --credentials-path "$SECRETS/credentials.json" \
  --token-path "$SECRETS/token.json" \
  --serve-http \
  --host 127.0.0.1 \
  --display-host 198.51.100.77 \
  --port 0 \
  --timeout-sec 2 \
  --url-file "$URL_FILE" \
  --json > "$PAGE_OUT" &
PAGE_PID=$!

for _ in $(seq 1 50); do
  [ -f "$URL_FILE" ] && break
  sleep 0.1
done

python3 - "$URL_FILE" "$TMP_DIR/credentials-source.json" <<'PY'
import sys
from pathlib import Path
from urllib import parse, request

url = Path(sys.argv[1]).read_text(encoding="utf-8").strip()
assert url.startswith("http://198.51.100.77:"), url
form = parse.urlencode({"credentials_path": sys.argv[2]}).encode("utf-8")
req = request.Request(url.replace("198.51.100.77", "127.0.0.1"), data=form, method="POST")
with request.urlopen(req, timeout=5) as response:
    body = response.read().decode("utf-8", errors="replace")
assert "AgentOS Gmail Setup" in body, body
assert "client_secret" not in body, body
PY

wait "$PAGE_PID"

python3 - "$PAGE_OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["schema_version"] == "agentos-gmail-setup-page.v1", payload
assert payload["setup_page_started"] is True, payload
assert payload["setup_page_url"].startswith("http://198.51.100.77:"), payload
PY

echo "gmail setup page smoke: PASS"
