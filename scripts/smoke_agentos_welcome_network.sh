#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WELCOME="$ROOT_DIR/image-assets/live/bin/agentos-welcome-shell"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

REQ_SKIP_OUT="$TMP_DIR/required-skip.out"
AUTO_OUT="$TMP_DIR/auto.out"
REQ_CONNECT_OUT="$TMP_DIR/required-connect.out"

AGENTOS_WELCOME_NETWORK_POLICY=required \
AGENTOS_WELCOME_NETWORK_STATUS=offline \
AGENTOS_WELCOME_NETWORK_ACTION=skip \
bash "$WELCOME" continue >"$REQ_SKIP_OUT"

AGENTOS_WELCOME_NETWORK_POLICY=auto \
AGENTOS_WELCOME_NETWORK_STATUS=offline \
bash "$WELCOME" continue >"$AUTO_OUT"

connect_code=0
if AGENTOS_WELCOME_NETWORK_POLICY=required \
  AGENTOS_WELCOME_NETWORK_STATUS=offline \
  AGENTOS_WELCOME_NETWORK_ACTION=connect \
  bash "$WELCOME" continue >"$REQ_CONNECT_OUT"; then
  connect_code=0
else
  connect_code=$?
fi

rg -q 'AgentOS network panel' "$REQ_SKIP_OUT"
rg -q 'Skipping network and continuing with the local AgentOS path' "$REQ_SKIP_OUT"
rg -q 'Launching AgentOS Setup' "$REQ_SKIP_OUT"
rg -q 'Network is offline; continuing with local AgentOS path' "$AUTO_OUT"
test "$connect_code" -eq 31
rg -q 'Retrying network check' "$REQ_CONNECT_OUT"
rg -q 'Network is still offline' "$REQ_CONNECT_OUT"

echo "agentos welcome network smoke: PASS"
