#!/usr/bin/env bash
# smoke_utm_client.sh — verify utm_client.py CLI interface and backend discovery
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PY="$ROOT_DIR/scripts/utm_client.py"

# ── 1. help flag ──────────────────────────────────────────────────────────────
if ! python3 "$PY" --help >/dev/null 2>&1; then
  echo "[utm-client-smoke] --help failed"
  exit 1
fi

# ── 2. backends subcommand (JSON) ─────────────────────────────────────────────
BACKENDS_OUT="$(python3 "$PY" --json backends 2>&1)"
if ! echo "$BACKENDS_OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert set(d)=={'utm_api','proxy','utmctl'}" 2>/dev/null; then
  echo "[utm-client-smoke] backends --json output unexpected: $BACKENDS_OUT"
  exit 1
fi

# ── 3. dry-run: list command exits non-zero only if no backend is available ───
# We just check the exit code is 0 or 1 (not a crash)
set +e
python3 "$PY" list >/dev/null 2>&1
LIST_EXIT=$?
set -e
if [ "$LIST_EXIT" -gt 1 ]; then
  echo "[utm-client-smoke] utm_client list exited with unexpected code $LIST_EXIT"
  exit 1
fi

# ── 4. utm_proxy_server.py --help ─────────────────────────────────────────────
PROXY_SERVER="$ROOT_DIR/scripts/utm_proxy_server.py"
if ! python3 "$PROXY_SERVER" --help >/dev/null 2>&1; then
  echo "[utm-client-smoke] utm_proxy_server.py --help failed"
  exit 1
fi

echo "utm client smoke: PASS"
