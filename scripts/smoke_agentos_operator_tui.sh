#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

GO_BIN="${AGENTOS_GO_BIN:-go}"
if ! command -v "$GO_BIN" >/dev/null 2>&1; then
  echo "operator tui smoke: SKIP (Go toolchain not found; set AGENTOS_GO_BIN)"
  exit 0
fi

FAKE_KERNELCTL="$TMP_DIR/agentos-kernelctl"
cat > "$FAKE_KERNELCTL" <<'SH'
#!/bin/sh
set -eu
case "$1" in
  workflow-status)
    printf '{"workspace":"/tmp/agentos-ws","runtime_entry_mode":"tty","operator_visible_state":"ready","guided_operator_surface_reachable":true,"runtime_secret_readiness":{"telegram_token_configured":false,"telegram_allowed_chat_configured":false,"telegram_live_send_ready":false,"telegram_secret_source":"none"},"summary":{"workflow_status_ready":true,"external_secret_blocked":true},"top_tasks":[{"id":"ask","label":"Ask","ready":true,"surface":"agentos-shell"}],"workflows":[]}\n'
    ;;
  ask)
    printf '{"schema_version":"agentos-ask-response.v1","capability":"ask","ok":true,"message":"hello","response":"hello from fake AgentOS","provider":"ollama","model":"fake","workspace":"/tmp/agentos-ws","failure_class":""}\n'
    ;;
  *)
    printf '{"ok":true,"summary":{"command":"%s"}}\n' "$1"
    ;;
esac
SH
chmod 0755 "$FAKE_KERNELCTL"

OUT_BIN="$TMP_DIR/agentos-operator-tui"
AGENTOS_GO_BIN="$GO_BIN" AGENTOS_OPERATOR_TUI_GOOS="$("$GO_BIN" env GOOS)" AGENTOS_OPERATOR_TUI_GOARCH="$("$GO_BIN" env GOARCH)" \
  "$ROOT_DIR/scripts/build_agentos_operator_tui.sh" "$OUT_BIN" >/dev/null

"$OUT_BIN" --workspace "$TMP_DIR/ws" --kernelctl "$FAKE_KERNELCTL" --self-test > "$TMP_DIR/render.txt"
grep -q 'AgentOS' "$TMP_DIR/render.txt"
grep -q 'Actions:' "$TMP_DIR/render.txt"
grep -q 'Ask AgentOS' "$TMP_DIR/render.txt"

echo "operator tui smoke: PASS"
