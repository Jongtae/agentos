#!/usr/bin/env bash
set -euo pipefail

INSTALL_HINT="Install Codex CLI first, then re-run this script."

if ! command -v codex >/dev/null 2>&1; then
  echo "[FAIL] codex binary not found on PATH."
  echo "Hint: $INSTALL_HINT"
  exit 1
fi

echo "[PASS] codex binary found: $(command -v codex)"

if ! codex --version >/tmp/codex-version.out 2>/tmp/codex-version.err; then
  echo "[FAIL] codex exists but '--version' failed."
  cat /tmp/codex-version.err || true
  exit 2
fi

echo "[PASS] codex version: $(cat /tmp/codex-version.out | tr -d '\n')"

if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "[WARN] OPENAI_API_KEY is not set."
  echo "Hint: export OPENAI_API_KEY=<your_api_key>"
else
  echo "[PASS] OPENAI_API_KEY is set."
fi

echo "Codex CLI bootstrap check: PASS"
