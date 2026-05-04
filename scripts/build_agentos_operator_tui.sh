#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT_DIR/build-output/bin/agentos-operator-tui}"
GO_BIN="${AGENTOS_GO_BIN:-go}"
TARGET_OS="${AGENTOS_OPERATOR_TUI_GOOS:-linux}"
TARGET_ARCH="${AGENTOS_OPERATOR_TUI_GOARCH:-arm64}"

if [ -n "${AGENTOS_OPERATOR_TUI_BIN:-}" ]; then
  if [ ! -x "$AGENTOS_OPERATOR_TUI_BIN" ]; then
    echo "AGENTOS_OPERATOR_TUI_BIN is not executable: $AGENTOS_OPERATOR_TUI_BIN" >&2
    exit 1
  fi
  mkdir -p "$(dirname "$OUT")"
  install -m 0755 "$AGENTOS_OPERATOR_TUI_BIN" "$OUT"
  printf '%s\n' "$OUT"
  exit 0
fi

if ! command -v "$GO_BIN" >/dev/null 2>&1; then
  echo "Go toolchain not found. Set AGENTOS_GO_BIN or AGENTOS_OPERATOR_TUI_BIN." >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"
(
  cd "$ROOT_DIR"
  GOOS="$TARGET_OS" GOARCH="$TARGET_ARCH" CGO_ENABLED=0 "$GO_BIN" build \
    -trimpath \
    -ldflags="-s -w" \
    -o "$OUT" \
    ./cmd/agentos-operator-tui
)
printf '%s\n' "$OUT"
