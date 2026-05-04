#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

LIVE_ROOT="$TMP_DIR/live-root"
mkdir -p \
  "$LIVE_ROOT/usr/local/bin" \
  "$LIVE_ROOT/etc/systemd/system" \
  "$LIVE_ROOT/etc/systemd/system/multi-user.target.wants"

install -m 0755 "$ROOT_DIR/scripts/agentos-operator-console" "$LIVE_ROOT/usr/local/bin/agentos-operator-console"
printf '#!/bin/sh\nexit 1\n' > "$LIVE_ROOT/usr/local/bin/agentos-operator-tui"
chmod 0755 "$LIVE_ROOT/usr/local/bin/agentos-operator-tui"
install -m 0644 "$ROOT_DIR/deploy/systemd/agentos-operator-tty1.service" "$LIVE_ROOT/etc/systemd/system/agentos-operator-tty1.service"
ln -sf ../agentos-operator-tty1.service "$LIVE_ROOT/etc/systemd/system/multi-user.target.wants/agentos-operator-tty1.service"

test -x "$LIVE_ROOT/usr/local/bin/agentos-operator-console"
test -x "$LIVE_ROOT/usr/local/bin/agentos-operator-tui"
test -L "$LIVE_ROOT/etc/systemd/system/multi-user.target.wants/agentos-operator-tty1.service"
rg -q 'TTYPath=/dev/tty1' "$LIVE_ROOT/etc/systemd/system/agentos-operator-tty1.service"
rg -q 'User=root' "$LIVE_ROOT/etc/systemd/system/agentos-operator-tty1.service"
rg -q 'AGENTOS_OPERATOR_USER=ubuntu' "$LIVE_ROOT/etc/systemd/system/agentos-operator-tty1.service"
rg -q 'StandardInput=tty' "$LIVE_ROOT/etc/systemd/system/agentos-operator-tty1.service"
rg -q 'StandardOutput=tty' "$LIVE_ROOT/etc/systemd/system/agentos-operator-tty1.service"
rg -q 'TTYVTDisallocate=yes' "$LIVE_ROOT/etc/systemd/system/agentos-operator-tty1.service"
rg -q 'AgentOS' "$LIVE_ROOT/usr/local/bin/agentos-operator-console"
rg -q 'agentos-operator-tui --workspace' "$LIVE_ROOT/usr/local/bin/agentos-operator-console"
rg -q 'AGENTOS_OPERATOR_DROP_PRIVILEGES=0' "$LIVE_ROOT/usr/local/bin/agentos-operator-console"
rg -q 'guided-operator' "$LIVE_ROOT/usr/local/bin/agentos-operator-console"
rg -q 'agentos-telegram-live-loop.service' "$LIVE_ROOT/usr/local/bin/agentos-operator-console"
rg -q 'agentos-telegram-webhookd.service' "$LIVE_ROOT/usr/local/bin/agentos-operator-console"

echo "operator tty1 handoff smoke: PASS"
