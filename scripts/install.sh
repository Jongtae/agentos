#!/bin/sh
# Personal AgentOS one-line installer for macOS, Linux and Windows (WSL2) (#1167).
#
#   curl -LsSf https://raw.githubusercontent.com/Jongtae/agentos/main/scripts/install.sh | sh
#
# Adopted, not built: the official uv installer fetches uv and uv fetches a
# managed Python, so no Homebrew, Xcode tools, system Python or git is needed.
# This script only pins what it installs, and checks each pin before running
# it: the uv release installer (which itself carries the checksums of the uv
# binaries it downloads) and the published AgentOS release, which is the same
# GitHub tag archive the Homebrew formula uses, against the SHA-256 recorded
# in docs/release-manifest.json.
# tests/test_install_script.py keeps these pins equal to the newest published
# release; docs/release.en.md step 9 updates them with each release.
set -eu

AGENTOS_VERSION="1.1.1"
AGENTOS_ARCHIVE_SHA256="fbd95903819ecaff4ac1f0d5bfa0e4131008657edae03465014cda8325c25510"
UV_VERSION="0.12.23"
UV_INSTALLER_SHA256="b8e6c43099ee9f9a550984d3ad56948457c689e7a99c090b35377234ac241491"
PYTHON_VERSION="3.13"

say() { printf '%s\n' "$*"; }
fail() { printf 'AgentOS install: %s\n' "$*" >&2; exit 1; }

case "$(uname -s)" in
  Darwin|Linux) ;;
  MINGW*|MSYS*|CYGWIN*)
    fail "Windows runs AgentOS inside WSL2. In PowerShell run 'wsl --install', restart, open Ubuntu and run this command there. See QUICKSTART.md (Windows)." ;;
  *) fail "unsupported system $(uname -s); AgentOS supports macOS, Linux and Windows through WSL2." ;;
esac

download() { # url destination
  if command -v curl >/dev/null 2>&1; then curl -LsSf "$1" -o "$2"
  elif command -v wget >/dev/null 2>&1; then wget -q "$1" -O "$2"
  else fail "curl or wget is required."; fi
}

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | cut -d' ' -f1
  else fail "sha256sum or shasum is required."; fi
}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT INT TERM

if command -v uv >/dev/null 2>&1; then
  UV=$(command -v uv)
else
  say "Installing uv $UV_VERSION (Python package manager by Astral)..."
  download "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-installer.sh" "$work/uv-install.sh"
  [ "$(sha256_of "$work/uv-install.sh")" = "$UV_INSTALLER_SHA256" ] \
    || fail "checksum mismatch for the uv $UV_VERSION installer; nothing was installed."
  sh "$work/uv-install.sh" >/dev/null || fail "the uv installer failed."
  UV="${UV_INSTALL_DIR:-${XDG_BIN_HOME:-$HOME/.local/bin}}/uv"
  [ -x "$UV" ] || fail "uv was installed but not found at $UV."
fi

archive="$work/agentos-$AGENTOS_VERSION.tar.gz"
say "Downloading AgentOS $AGENTOS_VERSION..."
download "https://github.com/Jongtae/agentos/archive/refs/tags/v$AGENTOS_VERSION.tar.gz" "$archive"
[ "$(sha256_of "$archive")" = "$AGENTOS_ARCHIVE_SHA256" ] \
  || fail "checksum mismatch for v$AGENTOS_VERSION; nothing was installed."

say "Installing AgentOS $AGENTOS_VERSION..."
"$UV" tool install --force --quiet --python "$PYTHON_VERSION" "personal-agentos[mcp-host] @ $archive" \
  || fail "uv could not install AgentOS."
"$UV" tool update-shell >/dev/null 2>&1 || true
bin_dir=$("$UV" tool dir --bin)

say ""
say "AgentOS $AGENTOS_VERSION is installed. Next time, open a new terminal and run: agentos start"
if [ "${AGENTOS_NO_START:-0}" = "1" ]; then exit 0; fi
say "Starting AgentOS now. Setup opens at http://127.0.0.1:8787 (press Ctrl-C to stop)."
rm -rf "$work"; trap - EXIT INT TERM
exec "$bin_dir/agentos" start </dev/null
