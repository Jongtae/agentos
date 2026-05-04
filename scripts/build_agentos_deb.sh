#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/build_agentos_deb.sh --version <v> --output-dir <dir> [--arch <amd64>] [--package-version <semver>]

Notes:
  - Requires dpkg-deb on the build host.
  - Produces:
    - agentos_<package-version>_<arch>.deb
    - SHA256SUMS
USAGE
}

VERSION=""
OUTPUT_DIR=""
ARCH="amd64"
PACKAGE_VERSION=""
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --version)
      shift
      VERSION="${1:-}"
      ;;
    --output-dir)
      shift
      OUTPUT_DIR="${1:-}"
      ;;
    --arch)
      shift
      ARCH="${1:-amd64}"
      ;;
    --package-version)
      shift
      PACKAGE_VERSION="${1:-}"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
  shift || true
done

if [ -z "$VERSION" ] || [ -z "$OUTPUT_DIR" ]; then
  echo "--version and --output-dir are required" >&2
  usage
  exit 2
fi

if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo "dpkg-deb is required but not found in PATH" >&2
  exit 1
fi

if [ -z "$PACKAGE_VERSION" ]; then
  PACKAGE_VERSION="${VERSION#v}"
fi

if ! [[ "$PACKAGE_VERSION" =~ ^[0-9]+(\.[0-9]+){1,2}([.-][A-Za-z0-9]+)?$ ]]; then
  echo "invalid --package-version: $PACKAGE_VERSION" >&2
  exit 2
fi

mkdir -p "$OUTPUT_DIR"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

PKG_ROOT="$TMP_DIR/pkgroot"
DEBIAN_DIR="$PKG_ROOT/DEBIAN"
APP_ROOT="$PKG_ROOT/usr/lib/agentos"

mkdir -p "$DEBIAN_DIR" "$APP_ROOT"

# Runtime payload needed by install_kernel_boot_integration.sh and launcher scripts.
cp -R "$ROOT_DIR/src" "$APP_ROOT/src"
cp -R "$ROOT_DIR/scripts" "$APP_ROOT/scripts"
cp -R "$ROOT_DIR/deploy" "$APP_ROOT/deploy"
cp "$ROOT_DIR/requirements.txt" "$APP_ROOT/requirements.txt"
if [ -f "$ROOT_DIR/README.md" ]; then
  cp "$ROOT_DIR/README.md" "$APP_ROOT/README.md"
fi

cat > "$DEBIAN_DIR/control" <<EOF
Package: agentos
Version: $PACKAGE_VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: AgentOS Maintainers <agentos@example.com>
Depends: bash, python3, systemd
Description: AgentOS kernel-mode runtime integration package
 Installs AgentOS runtime assets under /usr/lib/agentos and
 configures boot integration using install_kernel_boot_integration.sh.
EOF

cat > "$DEBIAN_DIR/postinst" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

AGENTOS_REPO_ROOT="/usr/lib/agentos"
DEFAULT_WORKSPACE="/var/lib/agentos/workspaces/default"

mkdir -p "$DEFAULT_WORKSPACE"
if [ ! -f "$DEFAULT_WORKSPACE/spec.yaml" ]; then
  cat > "$DEFAULT_WORKSPACE/spec.yaml" <<'SPEC'
name: "agentos-default"
ai_model:
  provider: "openai"
  model: "gpt-4o-mini"
kernel_engine:
  provider: "none"
  mode: "single"
tools:
  bash: true
  file: true
  web: true
permissions:
  require_approval: true
memory:
  checkpointer: "sqlite"
  db_path: "./data/session.sqlite"
  store_path: "./data/memory.sqlite"
runtime:
  max_steps: 12
  max_message_window: 20
  workspace_root: "./"
SPEC
fi

AGENTOS_REPO_ROOT="$AGENTOS_REPO_ROOT" \
DEFAULT_WORKSPACE="$DEFAULT_WORKSPACE" \
AGENTOS_ENABLE_SYSTEMD=1 \
"$AGENTOS_REPO_ROOT/scripts/install_kernel_boot_integration.sh"
EOF

cat > "$DEBIAN_DIR/prerm" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

if [ "$1" = "remove" ] || [ "$1" = "deconfigure" ]; then
  if [ -x /usr/lib/agentos/scripts/uninstall_kernel_boot_integration.sh ]; then
    /usr/lib/agentos/scripts/uninstall_kernel_boot_integration.sh || true
  fi
fi
EOF

chmod 0755 "$DEBIAN_DIR/postinst" "$DEBIAN_DIR/prerm"

DEB_NAME="agentos_${PACKAGE_VERSION}_${ARCH}.deb"
DEB_PATH="$OUTPUT_DIR/$DEB_NAME"
RELEASE_METADATA_PATH="$OUTPUT_DIR/agentos-release-metadata.json"

dpkg-deb --build "$PKG_ROOT" "$DEB_PATH" >/dev/null

(
  cd "$OUTPUT_DIR"
  sha256sum "$DEB_NAME" > SHA256SUMS
)

python3 "$ROOT_DIR/scripts/release_identity_manifest.py" write \
  --output "$RELEASE_METADATA_PATH" \
  --artifact-type deb \
  --agentos-version "$VERSION" \
  --package-version "$PACKAGE_VERSION" \
  --arch "$ARCH" \
  --output-path "$DEB_PATH" \
  --sha256sums-path "$OUTPUT_DIR/SHA256SUMS" \
  --install-root /usr/lib/agentos \
  --default-workspace /var/lib/agentos/workspaces/default >/dev/null

echo "AgentOS deb foundation build complete."
echo "Artifact type: deb"
echo "Artifact: $DEB_PATH"
echo "SHA256SUMS: $OUTPUT_DIR/SHA256SUMS"
echo "Version: $VERSION"
echo "Package version: $PACKAGE_VERSION"
echo "Arch: $ARCH"
echo "Release metadata: $RELEASE_METADATA_PATH"
