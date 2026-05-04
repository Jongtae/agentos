#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

POSTINSTALL_DIR="$TMP_DIR/postinstall"
RUNTIME_DIR="$TMP_DIR/runtime/agentos"
FAKE_BIN_DIR="$TMP_DIR/bin"
mkdir -p "$POSTINSTALL_DIR" "$RUNTIME_DIR" "$FAKE_BIN_DIR"

cp "$ROOT_DIR/image-assets/postinstall/agentos-postinstall.sh" "$POSTINSTALL_DIR/agentos-postinstall.sh"
cp "$ROOT_DIR/image-assets/postinstall/apt-packages.policy" "$POSTINSTALL_DIR/apt-packages.policy"
chmod +x "$POSTINSTALL_DIR/agentos-postinstall.sh"
cp -R "$ROOT_DIR/src" "$RUNTIME_DIR/src"
cp -R "$ROOT_DIR/scripts" "$RUNTIME_DIR/scripts"
cp -R "$ROOT_DIR/deploy" "$RUNTIME_DIR/deploy"
mkdir -p "$RUNTIME_DIR/image-assets/live"
cp -R "$ROOT_DIR/image-assets/boot" "$RUNTIME_DIR/image-assets/boot"
cp -R "$ROOT_DIR/image-assets/live/bin" "$RUNTIME_DIR/image-assets/live/bin"
cp "$ROOT_DIR/requirements.txt" "$RUNTIME_DIR/requirements.txt"

cat > "$FAKE_BIN_DIR/apt-get" <<'EOS'
#!/usr/bin/env sh
exit 0
EOS

cat > "$FAKE_BIN_DIR/dpkg-query" <<'EOS'
#!/usr/bin/env sh
pkg=""
for arg in "$@"; do
  pkg="$arg"
done
case "$pkg" in
  ca-certificates) printf "20240203\n" ;;
  curl) printf "8.5.0\n" ;;
  git) printf "2.43.0\n" ;;
  jq) printf "1.7\n" ;;
  python3) printf "3.12.2\n" ;;
  python3-pip) printf "23.0\n" ;;
  python3-venv) printf "3.12.2\n" ;;
  qrencode) printf "4.1.1\n" ;;
  ripgrep) printf "14.0\n" ;;
  zstd) printf "1.5.5\n" ;;
  plymouth) printf "24.004.60\n" ;;
  qemu-guest-agent) printf "1:8.2\n" ;;
  ollama) exit 1 ;;
  *) exit 1 ;;
esac
EOS

cat > "$FAKE_BIN_DIR/dpkg" <<'EOS'
#!/usr/bin/env sh
if [ "$1" = "--compare-versions" ]; then
  left="$2"
  op="$3"
  right="$4"
  if [ "$op" = "ge" ]; then
    if [ "$left" = "$right" ]; then
      exit 0
    fi
    if [ "$(printf '%s\n%s\n' "$left" "$right" | sort -V | tail -n1)" = "$left" ]; then
      exit 0
    fi
  fi
fi
exit 1
EOS

cat > "$FAKE_BIN_DIR/git" <<'EOS'
#!/usr/bin/env sh
echo "git should not be called by repo-free postinstall" >&2
exit 1
EOS

cat > "$FAKE_BIN_DIR/python3" <<'EOS'
#!/usr/bin/env sh
exit 0
EOS

chmod +x "$FAKE_BIN_DIR/apt-get" "$FAKE_BIN_DIR/dpkg-query" "$FAKE_BIN_DIR/dpkg" "$FAKE_BIN_DIR/git" "$FAKE_BIN_DIR/python3"

OUT_FILE="$TMP_DIR/out.log"
if ! PATH="$FAKE_BIN_DIR:$PATH" \
  AGENTOS_INSTALL_PREFIX="$TMP_DIR/install-root" \
  AGENTOS_INSTALL_ROOT="$TMP_DIR" \
  AGENTOS_APP_ROOT="$TMP_DIR/usr/lib/agentos" \
  AGENTOS_DEFAULT_WORKSPACE="$TMP_DIR/home/ubuntu/agentos-ws" \
  AGENTOS_SEED_WORKSPACE="$TMP_DIR/var/lib/agentos/workspaces/default" \
  AGENTOS_RUNTIME_BUNDLE_DIR="$RUNTIME_DIR" \
  "$POSTINSTALL_DIR/agentos-postinstall.sh" > "$OUT_FILE" 2>&1; then
  echo "[iso-postinstall-policy] postinstall script failed"
  cat "$OUT_FILE"
  exit 1
fi

if ! rg -q "optional package not installed: ollama" "$OUT_FILE"; then
  echo "[iso-postinstall-policy] expected optional ollama guidance"
  cat "$OUT_FILE"
  exit 1
fi

if [ ! -f "$TMP_DIR/usr/lib/agentos/src/main.py" ]; then
  echo "[iso-postinstall-policy] runtime bundle was not installed"
  exit 1
fi

if [ ! -f "$TMP_DIR/var/lib/agentos/workspaces/default/documents/agentos-first-run.md" ]; then
  echo "[iso-postinstall-policy] seed first-run document missing"
  exit 1
fi

if [ ! -f "$TMP_DIR/home/ubuntu/agentos-ws/documents/agentos-first-run.md" ]; then
  echo "[iso-postinstall-policy] interactive first-run document missing"
  exit 1
fi

SERVICE_FILE="$TMP_DIR/etc/systemd/system/agentos-engine-availability.service"
if [ ! -f "$SERVICE_FILE" ]; then
  echo "[iso-postinstall-policy] engine availability service missing"
  exit 1
fi

if ! rg -q '^Environment=AGENTOS_DEFAULT_WORKSPACE=/var/lib/agentos/workspaces/default$' "$SERVICE_FILE"; then
  echo "[iso-postinstall-policy] engine availability service should refresh the seed workspace, not the interactive workspace"
  cat "$SERVICE_FILE"
  exit 1
fi

python3 - "$TMP_DIR/home/ubuntu/agentos-ws" <<'PY'
import os
import stat
import sys
from pathlib import Path

workspace = Path(sys.argv[1])
mode = workspace.stat().st_mode
required = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
if mode & required != required:
    raise SystemExit(f"interactive workspace mode is not repo-free writable: {oct(mode)}")
PY

echo "iso postinstall policy smoke: PASS"
