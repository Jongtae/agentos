#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

BROKEN_ROOT="$TMP_DIR/broken-go-root"
BROKEN_BIN="$TMP_DIR/bin/go"
mkdir -p "$TMP_DIR/bin" "$BROKEN_ROOT/src/context" "$BROKEN_ROOT/src/fmt"
cat > "$BROKEN_BIN" <<SH
#!/usr/bin/env bash
set -euo pipefail
if [ "\${1:-}" = "env" ] && [ "\${2:-}" = "GOROOT" ]; then
  printf '%s\n' "$BROKEN_ROOT"
  exit 0
fi
if [ "\${1:-}" = "list" ] && [ "\${2:-}" = "std" ]; then
  exit 1
fi
echo "broken fake go invoked: \$*" >&2
exit 1
SH
chmod +x "$BROKEN_BIN"

if AGENTOS_GO_BIN="$BROKEN_BIN" scripts/build_agentos_operator_tui.sh "$TMP_DIR/operator-tui" >"$TMP_DIR/operator.out" 2>"$TMP_DIR/operator.err"; then
  echo "operator tui build unexpectedly accepted a broken Go toolchain" >&2
  exit 1
fi
rg -q "Go toolchain is incomplete or corrupted" "$TMP_DIR/operator.err"

FAKE_BUILD="$TMP_DIR/fake-build-agentos-iso.sh"
cat > "$FAKE_BUILD" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
if [ -z "${AGENTOS_GO_BIN:-}" ]; then
  echo "AGENTOS_GO_BIN was not selected" >&2
  exit 1
fi
if [ "$AGENTOS_GO_BIN" = "__BROKEN_BIN__" ]; then
  echo "broken Go toolchain was selected" >&2
  exit 1
fi
"$AGENTOS_GO_BIN" env GOROOT >/dev/null
printf '%s\n' "$AGENTOS_GO_BIN" > "__SELECTED_GO_FILE__"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --version)
      shift
      version="${1:-}"
      ;;
    --output-dir)
      shift
      output_dir="${1:-}"
      ;;
  esac
  shift || true
done
mkdir -p "$output_dir"
printf 'fake iso\n' > "$output_dir/agentos-${version:-0.0.0}-arm64.iso"
printf 'fake sha\n' > "$output_dir/SHA256SUMS"
printf '{"ok":true}\n' > "$output_dir/agentos-release-metadata.json"
SH
python3 - "$FAKE_BUILD" "$BROKEN_BIN" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace("__BROKEN_BIN__", sys.argv[2])
text = text.replace("__SELECTED_GO_FILE__", str(path.parent / "selected-go.txt"))
path.write_text(text, encoding="utf-8")
PY
chmod +x "$FAKE_BUILD"

FAKE_TOOLS="$TMP_DIR/fake-tools"
mkdir -p "$FAKE_TOOLS"
cat > "$FAKE_TOOLS/curl" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
out=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o)
      shift
      out="${1:-}"
      ;;
  esac
  shift || true
done
[ -n "$out" ]
printf 'fake archive\n' > "$out"
SH
cat > "$FAKE_TOOLS/tar" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
target=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -C)
      shift
      target="${1:-}"
      ;;
  esac
  shift || true
done
[ -n "$target" ]
mkdir -p "$target/go/bin" "$target/go/src/context" "$target/go/src/fmt"
printf 'package context\n' > "$target/go/src/context/context.go"
printf 'package fmt\n' > "$target/go/src/fmt/print.go"
cat > "$target/go/bin/go" <<GO
#!/usr/bin/env bash
set -euo pipefail
if [ "\${1:-}" = "env" ] && [ "\${2:-}" = "GOROOT" ]; then
  printf '%s\n' "$target/go"
  exit 0
fi
if [ "\${1:-}" = "list" ] && [ "\${2:-}" = "std" ]; then
  printf 'context\nfmt\n'
  exit 0
fi
exit 0
GO
chmod +x "$target/go/bin/go"
SH
chmod +x "$FAKE_TOOLS/curl" "$FAKE_TOOLS/tar"

set +e
PATH="$TMP_DIR/bin:$FAKE_TOOLS:$PATH" \
AGENTOS_GO_CACHE_ROOT="$TMP_DIR/cache" \
AGENTOS_BUILD_AGENTOS_ISO_CMD="$FAKE_BUILD" \
scripts/build_latest_agentos_iso.sh \
  --version 9.9.9 \
  --output-dir "$TMP_DIR/release" \
  --base-image "$ROOT_DIR/README.md" \
  --arch arm64 \
  --skip-smoke \
  --skip-cleanup >"$TMP_DIR/latest.out" 2>"$TMP_DIR/latest.err"
latest_status=$?
set -e

if [ "$latest_status" -eq 0 ]; then
  rg -q "AgentOS ISO ready" "$TMP_DIR/latest.out"
fi
selected_go="$(cat "$TMP_DIR/selected-go.txt")"
if [ "$selected_go" = "$BROKEN_BIN" ]; then
  echo "broken Go toolchain was selected by build_latest_agentos_iso.sh" >&2
  exit 1
fi
"$selected_go" list std >/dev/null

echo "go toolchain selection smoke: PASS"
