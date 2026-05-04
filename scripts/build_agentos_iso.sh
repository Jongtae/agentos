#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VERSION=""
OUTPUT_DIR=""
BASE_IMAGE="${AGENTOS_BASE_IMAGE:-}"
ARCH="amd64"
DOWNLOAD_BASE_IMAGE=0
PREPARE_ASSETS_CMD="${AGENTOS_PREPARE_ISO_ASSETS_CMD:-$ROOT_DIR/scripts/prepare_iso_assets.sh}"
FETCH_BASE_IMAGE_CMD="${AGENTOS_FETCH_BASE_IMAGE_CMD:-$ROOT_DIR/scripts/fetch_ubuntu_base_iso.sh}"
REMASTER_ENV_CMD="${AGENTOS_CHECK_REMASTER_ENV_CMD:-$ROOT_DIR/scripts/check_iso_remaster_environment.py}"
REMASTER_ISO_CMD="${AGENTOS_REMASTER_ISO_CMD:-$ROOT_DIR/scripts/remaster_agentos_iso.sh}"
ALLOW_SERVER_INSTALLER_COMPAT=0
HEADLESS_ACCEPTANCE_BASE=0
ALLOW_FOUNDATION_COPY_COMPAT="${AGENTOS_ALLOW_FOUNDATION_COPY_COMPAT:-1}"

usage() {
  cat <<USAGE
Usage:
  scripts/build_agentos_iso.sh --version <v> --output-dir <dir> [--arch amd64|arm64] [--base-image <path> | --download-base-image] [--allow-server-installer-compat] [--headless-acceptance-base]

Notes:
  - Default path now expects an Ubuntu Desktop live ISO so the VM first-run path does not drop into the Ubuntu server installer.
  - Ubuntu live-server ISO remains migration-only compatibility and must be explicitly allowed.
  - --headless-acceptance-base truthfully labels a live-server ISO as the lightweight TTY/systemd acceptance base.
  - Phase 155 prefers a real remaster pipeline when the supported Linux remaster toolchain is available.
  - Unsupported hosts may still fall back to foundation-copy compatibility unless AGENTOS_ALLOW_FOUNDATION_COPY_COMPAT=0.
USAGE
}

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
      ARCH="${1:-}"
      ;;
    --base-image)
      shift
      BASE_IMAGE="${1:-}"
      ;;
    --download-base-image)
      DOWNLOAD_BASE_IMAGE=1
      ;;
    --allow-server-installer-compat)
      ALLOW_SERVER_INSTALLER_COMPAT=1
      ;;
    --headless-acceptance-base)
      HEADLESS_ACCEPTANCE_BASE=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift || true
done

if [ -z "$VERSION" ] || [ -z "$OUTPUT_DIR" ]; then
  echo "--version and --output-dir are required." >&2
  usage >&2
  exit 2
fi

if ! [[ "$VERSION" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "Invalid --version '$VERSION'. Allowed: letters, numbers, dot, underscore, hyphen." >&2
  exit 2
fi

case "$ARCH" in
  amd64|arm64) ;;
  *)
    echo "Invalid --arch '$ARCH'. Supported: amd64, arm64." >&2
    exit 2
    ;;
esac

if [ -z "$BASE_IMAGE" ] && [ "$DOWNLOAD_BASE_IMAGE" -eq 1 ]; then
  if [ ! -x "$FETCH_BASE_IMAGE_CMD" ] && ! command -v "$FETCH_BASE_IMAGE_CMD" >/dev/null 2>&1; then
    echo "Base image fetch tool not found: $FETCH_BASE_IMAGE_CMD" >&2
    exit 1
  fi
  BASE_IMAGE="$($FETCH_BASE_IMAGE_CMD --arch "$ARCH" --print-path)"
fi

if [ -z "$BASE_IMAGE" ]; then
  echo "Missing base image. Set --base-image, AGENTOS_BASE_IMAGE, or use --download-base-image." >&2
  exit 2
fi

if [ ! -f "$BASE_IMAGE" ]; then
  echo "Base image not found: $BASE_IMAGE" >&2
  exit 1
fi

BASE_IMAGE_NAME="$(basename "$BASE_IMAGE")"
BASE_IMAGE_KIND="desktop-live"
BASE_IMAGE_TYPE="desktop-live-iso"
case "$BASE_IMAGE_NAME" in
  *live-server*)
    BASE_IMAGE_KIND="live-server"
    ;;
  *desktop*)
    BASE_IMAGE_KIND="desktop-live"
    ;;
esac

if [ "$BASE_IMAGE_KIND" = "live-server" ] && [ "$HEADLESS_ACCEPTANCE_BASE" -eq 1 ]; then
  BASE_IMAGE_TYPE="headless-live-server-iso"
fi

if [ "$BASE_IMAGE_KIND" = "live-server" ] && [ "$ALLOW_SERVER_INSTALLER_COMPAT" -eq 1 ]; then
  BASE_IMAGE_TYPE="headless-live-server-iso"
fi

if [ "$BASE_IMAGE_KIND" = "live-server" ] && [ "$ALLOW_SERVER_INSTALLER_COMPAT" -ne 1 ] && [ "$HEADLESS_ACCEPTANCE_BASE" -ne 1 ]; then
  echo "Refusing Ubuntu live-server base image for the default AgentOS path: $BASE_IMAGE" >&2
  echo "This server installer path still exposes Ubuntu mirror/network/install screens." >&2
  echo "Use an Ubuntu Desktop live ISO instead, or pass --headless-acceptance-base for lightweight TTY/systemd acceptance." >&2
  exit 1
fi

if command -v sha256sum >/dev/null 2>&1; then
  SHA256_TOOL=(sha256sum)
elif command -v shasum >/dev/null 2>&1; then
  SHA256_TOOL=(shasum -a 256)
else
  echo "sha256sum or shasum is required on PATH." >&2
  exit 1
fi

ASSET_USER_DATA="$ROOT_DIR/autoinstall/user-data"
ASSET_META_DATA="$ROOT_DIR/autoinstall/meta-data"
ASSET_POSTINSTALL="$ROOT_DIR/image-assets/postinstall/agentos-postinstall.sh"
ASSET_POLICY="$ROOT_DIR/image-assets/postinstall/apt-packages.policy"

for f in "$ASSET_USER_DATA" "$ASSET_META_DATA" "$ASSET_POSTINSTALL" "$ASSET_POLICY"; do
  if [ ! -f "$f" ]; then
    echo "Required asset missing: $f" >&2
    exit 1
  fi
done

if [ ! -x "$PREPARE_ASSETS_CMD" ] && ! command -v "$PREPARE_ASSETS_CMD" >/dev/null 2>&1; then
  echo "ISO asset prepare tool not found: $PREPARE_ASSETS_CMD" >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"
mkdir -p "$ROOT_DIR/build-output"

ISO_NAME="agentos-${VERSION}-${ARCH}.iso"
ISO_PATH="$OUTPUT_DIR/$ISO_NAME"
SHA_PATH="$OUTPUT_DIR/SHA256SUMS"
SHA_FILE_NAME="$(basename "$SHA_PATH")"
RELEASE_METADATA_PATH="$OUTPUT_DIR/agentos-release-metadata.json"
ASSET_OUT_DIR="$ROOT_DIR/build-output/iso-assets"
REMASTER_WORK_DIR="${AGENTOS_REMASTER_WORK_DIR:-$ROOT_DIR/build-output/remaster-$VERSION}"
MANIFEST="$ROOT_DIR/build-output/manifest-${VERSION}.txt"
INSTALLER_HIDDEN_DEFAULT_PATH="false"
BOOT_TARGET_ACTIVATED="false"
BOOT_FLOW_PROOF_INCLUDED="false"
VM_FIRST_SCREEN_EVIDENCE_INCLUDED="false"

manifest_value() {
  local key="$1"
  local path="$2"
  if [ ! -f "$path" ]; then
    return 1
  fi
  sed -n "s/^${key}=//p" "$path" | tail -n1
}

prepare_output="$($PREPARE_ASSETS_CMD --version "$VERSION" --output-dir "$ASSET_OUT_DIR")"
asset_bundle_path="$(printf "%s\n" "$prepare_output" | sed -n 's/^bundle:[[:space:]]*//p' | tail -n1)"
asset_manifest_path="$(printf "%s\n" "$prepare_output" | sed -n 's/^manifest:[[:space:]]*//p' | tail -n1)"

if [ -z "$asset_bundle_path" ] || [ ! -f "$asset_bundle_path" ]; then
  echo "failed to produce ISO asset bundle from $PREPARE_ASSETS_CMD" >&2
  printf "%s\n" "$prepare_output" >&2
  exit 1
fi

if [ -z "$asset_manifest_path" ] || [ ! -f "$asset_manifest_path" ]; then
  echo "failed to produce ISO asset manifest from $PREPARE_ASSETS_CMD" >&2
  printf "%s\n" "$prepare_output" >&2
  exit 1
fi

REMASTER_OK=0
REMASTER_REPORT='{}'
if [ -x "$REMASTER_ENV_CMD" ] || command -v "$REMASTER_ENV_CMD" >/dev/null 2>&1; then
  if REMASTER_REPORT="$(python3 "$REMASTER_ENV_CMD" --json 2>/dev/null || true)"; then
    if printf '%s' "$REMASTER_REPORT" | python3 -c 'import json,sys; data=json.load(sys.stdin); raise SystemExit(0 if data.get("ok") else 1)' >/dev/null 2>&1; then
      REMASTER_OK=1
    fi
  fi
fi

BUILD_MODE="foundation_copy_compat"
if [ "$REMASTER_OK" -eq 1 ]; then
  "$REMASTER_ISO_CMD"     --base-image "$BASE_IMAGE"     --asset-bundle "$asset_bundle_path"     --asset-manifest "$asset_manifest_path"     --output-iso "$ISO_PATH"     --work-dir "$REMASTER_WORK_DIR"     --version "$VERSION"     --arch "$ARCH"     --build-manifest "$MANIFEST" >/dev/null
  {
    echo "base_image_kind=$BASE_IMAGE_KIND"
    echo "base_image_type=$BASE_IMAGE_TYPE"
  } >> "$MANIFEST"
  BUILD_MODE="remaster_pipeline"
  INSTALLER_HIDDEN_DEFAULT_PATH="$(sed -n 's/^installer_hidden_default_path=//p' "$MANIFEST" | tail -n1)"
else
  if [ "$ALLOW_FOUNDATION_COPY_COMPAT" != "1" ]; then
    echo "supported remaster environment unavailable and foundation copy compatibility is disabled" >&2
    echo "$REMASTER_REPORT" >&2
    exit 1
  fi
  cp "$BASE_IMAGE" "$ISO_PATH"
  {
    echo "agentos_version=$VERSION"
    echo "arch=$ARCH"
    echo "toolchain=ubuntu-image+autoinstall"
    echo "build_mode=foundation_copy_compat"
    echo "base_image=$BASE_IMAGE"
    echo "base_image_kind=$BASE_IMAGE_KIND"
    echo "base_image_type=$BASE_IMAGE_TYPE"
    echo "remaster_mode=required_for_product_path"
    echo "welcome_shell_contract=agentos_welcome_shell.v1"
    echo "recovery_shell_contract=agentos_recovery_shell.v1"
    echo "installer_hidden_default_path=false"
    echo "output_iso=$ISO_PATH"
    echo "asset_bundle=$asset_bundle_path"
    echo "asset_manifest=$asset_manifest_path"
    echo "utc_built=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "$MANIFEST"
fi

if [ -z "$INSTALLER_HIDDEN_DEFAULT_PATH" ]; then
  INSTALLER_HIDDEN_DEFAULT_PATH="false"
fi
BOOT_TARGET_ACTIVATED="$(manifest_value boot_target_activated "$MANIFEST" || true)"
BOOT_FLOW_PROOF_INCLUDED="$(manifest_value boot_flow_proof_included "$MANIFEST" || true)"
VM_FIRST_SCREEN_EVIDENCE_INCLUDED="$(manifest_value vm_first_screen_evidence_included "$MANIFEST" || true)"
UBUNTU_INSTALLER_MASKED="$(manifest_value ubuntu_installer_masked "$MANIFEST" || true)"
AGENTOS_WELCOME_ASSETS_STAGED="$(manifest_value agentos_welcome_assets_staged "$MANIFEST" || true)"
AGENTOS_WELCOME_OWNS_FIRST_SCREEN="$(manifest_value agentos_welcome_owns_first_screen "$MANIFEST" || true)"
AGENTOS_WELCOME_RUNTIME_OBSERVED="false"
LIVE_GUEST_AGENT_BOOTSTRAP_STAGED="$(manifest_value live_guest_agent_bootstrap_staged "$MANIFEST" || true)"
LIVE_GUEST_AGENT_PRESTAGED="$(manifest_value live_guest_agent_prestaged "$MANIFEST" || true)"
LIVE_GUEST_AGENT_REACHABILITY_PATH="$(manifest_value live_guest_agent_reachability_path "$MANIFEST" || true)"
BUNDLED_LOCAL_PROVIDER_STAGED="$(manifest_value bundled_local_provider_staged "$MANIFEST" || true)"
BUNDLED_LOCAL_MODEL_STAGED="$(manifest_value bundled_local_model_staged "$MANIFEST" || true)"
BUNDLED_LOCAL_SERVICE_STAGED="$(manifest_value bundled_local_service_staged "$MANIFEST" || true)"
BUNDLED_LOCAL_FIRSTRUN_SERVICE_STAGED="$(manifest_value bundled_local_firstrun_service_staged "$MANIFEST" || true)"
BOOT_TARGET_ACTIVATED="${BOOT_TARGET_ACTIVATED:-false}"
BOOT_FLOW_PROOF_INCLUDED="${BOOT_FLOW_PROOF_INCLUDED:-false}"
VM_FIRST_SCREEN_EVIDENCE_INCLUDED="${VM_FIRST_SCREEN_EVIDENCE_INCLUDED:-false}"
UBUNTU_INSTALLER_MASKED="${UBUNTU_INSTALLER_MASKED:-false}"
AGENTOS_WELCOME_OWNS_FIRST_SCREEN="${AGENTOS_WELCOME_OWNS_FIRST_SCREEN:-false}"
AGENTOS_WELCOME_ASSETS_STAGED="${AGENTOS_WELCOME_ASSETS_STAGED:-false}"
AGENTOS_WELCOME_RUNTIME_OBSERVED="${AGENTOS_WELCOME_RUNTIME_OBSERVED:-false}"
LIVE_GUEST_AGENT_BOOTSTRAP_STAGED="${LIVE_GUEST_AGENT_BOOTSTRAP_STAGED:-false}"
LIVE_GUEST_AGENT_PRESTAGED="${LIVE_GUEST_AGENT_PRESTAGED:-false}"
LIVE_GUEST_AGENT_REACHABILITY_PATH="${LIVE_GUEST_AGENT_REACHABILITY_PATH:-unstaged}"
BUNDLED_LOCAL_PROVIDER_STAGED="${BUNDLED_LOCAL_PROVIDER_STAGED:-false}"
BUNDLED_LOCAL_MODEL_STAGED="${BUNDLED_LOCAL_MODEL_STAGED:-false}"
BUNDLED_LOCAL_SERVICE_STAGED="${BUNDLED_LOCAL_SERVICE_STAGED:-false}"
BUNDLED_LOCAL_FIRSTRUN_SERVICE_STAGED="${BUNDLED_LOCAL_FIRSTRUN_SERVICE_STAGED:-false}"

(
  cd "$OUTPUT_DIR"
  "${SHA256_TOOL[@]}" "$ISO_NAME" > "$SHA_FILE_NAME"
)

manifest_write_cmd=(
  python3 "$ROOT_DIR/scripts/release_identity_manifest.py" write
  --output "$RELEASE_METADATA_PATH"
  --artifact-type iso
  --agentos-version "$VERSION"
  --arch "$ARCH"
  --output-path "$ISO_PATH"
  --sha256sums-path "$SHA_PATH"
  --build-manifest-path "$MANIFEST"
  --base-image-path "$BASE_IMAGE"
  --asset-bundle-path "$asset_bundle_path"
  --asset-manifest-path "$asset_manifest_path"
  --boot-experience-contract agentos_direct_ai_boot
  --iso-default-boot-path continue_to_agentos_default_path
  --iso-fallback-boot-path installer_heavy_compatibility
  --grub-theme-contract agentos_minimal_appliance_grub.v1
  --splash-theme-contract agentos_minimal_appliance_splash.v1
  --base-image-type "$BASE_IMAGE_TYPE"
  --remaster-mode required_for_product_path
  --welcome-shell-contract agentos_welcome_shell.v1
  --recovery-shell-contract agentos_recovery_shell.v1
  --boot-flow-proof-contract agentos-remastered-boot-flow-proof.v1
  --default-boot-target-contract agentos_continue_boot_target.v1
  --default-boot-target-label "Continue to AgentOS"
  --vm-first-screen-evidence-contract agentos_vm_first_screen_evidence.v1
)
if [ "$INSTALLER_HIDDEN_DEFAULT_PATH" = "true" ]; then
  manifest_write_cmd+=(--installer-hidden-default-path)
fi
if [ "$BOOT_TARGET_ACTIVATED" = "true" ]; then
  manifest_write_cmd+=(--boot-target-activated)
fi
if [ "$VM_FIRST_SCREEN_EVIDENCE_INCLUDED" = "true" ]; then
  manifest_write_cmd+=(--vm-first-screen-evidence-included)
fi
if [ "$BOOT_FLOW_PROOF_INCLUDED" = "true" ]; then
  manifest_write_cmd+=(--boot-flow-proof-included)
fi
if [ "$UBUNTU_INSTALLER_MASKED" = "true" ]; then
  manifest_write_cmd+=(--ubuntu-installer-masked)
fi
if [ "$AGENTOS_WELCOME_ASSETS_STAGED" = "true" ]; then
  manifest_write_cmd+=(--agentos-welcome-assets-staged)
fi
if [ "$AGENTOS_WELCOME_RUNTIME_OBSERVED" = "true" ]; then
  manifest_write_cmd+=(--agentos-welcome-runtime-observed)
fi
if [ "$AGENTOS_WELCOME_OWNS_FIRST_SCREEN" = "true" ] && [ "$AGENTOS_WELCOME_RUNTIME_OBSERVED" = "true" ]; then
  manifest_write_cmd+=(--agentos-welcome-owns-first-screen)
fi
if [ "$LIVE_GUEST_AGENT_BOOTSTRAP_STAGED" = "true" ]; then
  manifest_write_cmd+=(--live-guest-agent-bootstrap-staged)
fi
if [ "$LIVE_GUEST_AGENT_PRESTAGED" = "true" ]; then
  manifest_write_cmd+=(--live-guest-agent-prestaged)
fi
manifest_write_cmd+=(--live-guest-agent-reachability-path "$LIVE_GUEST_AGENT_REACHABILITY_PATH")
if [ "$BUNDLED_LOCAL_PROVIDER_STAGED" = "true" ]; then
  manifest_write_cmd+=(--bundled-local-provider-staged)
fi
if [ "$BUNDLED_LOCAL_MODEL_STAGED" = "true" ]; then
  manifest_write_cmd+=(--bundled-local-model-staged)
fi
if [ "$BUNDLED_LOCAL_SERVICE_STAGED" = "true" ]; then
  manifest_write_cmd+=(--bundled-local-service-staged)
fi
if [ "$BUNDLED_LOCAL_FIRSTRUN_SERVICE_STAGED" = "true" ]; then
  manifest_write_cmd+=(--bundled-local-firstrun-service-staged)
fi
"${manifest_write_cmd[@]}" >/dev/null

echo "AgentOS ISO build complete."
echo "Artifact type: iso"
echo "Build mode: $BUILD_MODE"
echo "Base image: $BASE_IMAGE"
echo "Base image kind: $BASE_IMAGE_KIND"
echo "Base image type: $BASE_IMAGE_TYPE"
echo "Artifact: $ISO_PATH"
if [ "$BUILD_MODE" = "remaster_pipeline" ]; then
  if [ "$BASE_IMAGE_TYPE" = "headless-live-server-iso" ]; then
    echo "Default boot path: remastered headless TTY/systemd acceptance path"
  else
    echo "Default boot path: remastered desktop-live product path"
  fi
  echo "Installer hidden in default path: $INSTALLER_HIDDEN_DEFAULT_PATH"
else
  echo "Default boot path: $BASE_IMAGE_TYPE compatibility"
  echo "Remaster mode: required_for_product_path (host fell back to compatibility mode)"
  echo "Installer hidden in default path: false (compatibility mode preserves substrate path)"
fi
echo "Welcome shell contract: agentos_welcome_shell.v1"
echo "Recovery shell contract: agentos_recovery_shell.v1"
echo "Boot flow proof contract: agentos-remastered-boot-flow-proof.v1"
echo "Default boot target contract: agentos_continue_boot_target.v1"
echo "Default boot target label: Continue to AgentOS"
echo "VM first-screen evidence contract: agentos_vm_first_screen_evidence.v1"
echo "Fallback boot path: server-installer migration compatibility"
echo "GRUB theme contract: agentos_minimal_appliance_grub.v1"
echo "Splash theme contract: agentos_minimal_appliance_splash.v1"
echo "SHA256SUMS: $SHA_PATH"
echo "Manifest: $MANIFEST"
echo "Release metadata: $RELEASE_METADATA_PATH"
echo "Asset bundle: $asset_bundle_path"
