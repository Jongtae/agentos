#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ARCH="arm64"
VERSION=""
OUTPUT_DIR="$ROOT_DIR/build-output/release"
BASE_IMAGE=""
DOWNLOAD_BASE_IMAGE=1
CLEANUP=1
RUN_SMOKE=1
LOG_DIR="$ROOT_DIR/build-output/logs"
TOTAL_STEPS=7

usage() {
  cat <<USAGE
Usage:
  scripts/build_latest_agentos_iso.sh [options]

Options:
  --version <0.36.103>     Build this AgentOS version. Defaults to next patch.
  --arch <arm64|amd64>     Target architecture. Defaults to arm64.
  --output-dir <dir>       Release output directory. Defaults to build-output/release.
  --base-image <path>      Use an explicit Ubuntu base ISO.
  --no-download            Do not auto-download/reuse the Ubuntu base ISO.
  --skip-smoke             Skip pre-build smoke_build_agentos_iso.sh.
  --skip-cleanup           Skip cleanup checks before/after build.
  -h, --help               Show this help.

Examples:
  scripts/build_latest_agentos_iso.sh
  scripts/build_latest_agentos_iso.sh --version 0.36.103
  scripts/build_latest_agentos_iso.sh --base-image ~/Downloads/ubuntu-24.04.2-live-server-arm64.iso --arch arm64
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --version)
      shift
      VERSION="${1:-}"
      ;;
    --arch)
      shift
      ARCH="${1:-}"
      ;;
    --output-dir)
      shift
      OUTPUT_DIR="${1:-}"
      ;;
    --base-image)
      shift
      BASE_IMAGE="${1:-}"
      DOWNLOAD_BASE_IMAGE=0
      ;;
    --no-download)
      DOWNLOAD_BASE_IMAGE=0
      ;;
    --skip-smoke)
      RUN_SMOKE=0
      ;;
    --skip-cleanup)
      CLEANUP=0
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

case "$ARCH" in
  amd64|arm64) ;;
  *)
    echo "Invalid --arch '$ARCH'. Supported: amd64, arm64." >&2
    exit 2
    ;;
esac

next_version() {
  python3 - "$ROOT_DIR" <<'PY'
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
candidates = []
for pattern in ("build-output/release/agentos-*-*.iso", "build-output/manifest-*.txt"):
    for path in root.glob(pattern):
        match = re.search(r"(?:agentos-|manifest-)(?:v)?(\d+)\.(\d+)\.(\d+)", path.name)
        if match:
            candidates.append(tuple(int(part) for part in match.groups()))
if not candidates:
    print("0.36.0")
else:
    major, minor, patch = max(candidates)
    print(f"{major}.{minor}.{patch + 1}")
PY
}

if [ -z "$VERSION" ]; then
  VERSION="$(next_version)"
fi
VERSION="${VERSION#v}"

if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Invalid --version '$VERSION'. Expected MAJOR.MINOR.PATCH, for example 0.36.103." >&2
  exit 2
fi

format_elapsed() {
  local elapsed="$1"
  printf "%02d:%02d" $((elapsed / 60)) $((elapsed % 60))
}

progress_bar() {
  local step="$1"
  local status="$2"
  local width=18
  local units="$step"
  if [ "$status" = "running" ] && [ "$units" -gt 0 ]; then
    units=$((units - 1))
  fi
  local filled=$((units * width / TOTAL_STEPS))
  local empty=$((width - filled))
  printf "%*s" "$filled" "" | tr " " "#"
  printf "%*s" "$empty" "" | tr " " "-"
}

progress_line() {
  local step="$1"
  local label="$2"
  local status="$3"
  local detail="${4:-}"
  local bar
  bar="$(progress_bar "$step" "$status")"
  if [ -n "$detail" ]; then
    printf "[agentos-build] [%d/%d] %-22s [%s] %s | %s\n" "$step" "$TOTAL_STEPS" "$label" "$bar" "$status" "$detail"
  else
    printf "[agentos-build] [%d/%d] %-22s [%s] %s\n" "$step" "$TOTAL_STEPS" "$label" "$bar" "$status"
  fi
}

if [ "$CLEANUP" -eq 1 ]; then
  progress_line 1 "cleanup" "running" "temp/build artifacts"
  python3 "$ROOT_DIR/scripts/cleanup_temp_artifacts.py" --delete --json >/dev/null
  python3 "$ROOT_DIR/scripts/cleanup_build_artifacts.py" --delete --json >/dev/null
  progress_line 1 "cleanup" "done"
else
  progress_line 1 "cleanup" "skipped"
fi

if [ "$RUN_SMOKE" -eq 1 ]; then
  progress_line 2 "smoke checks" "running" "ISO asset/build contract"
  bash "$ROOT_DIR/scripts/smoke_build_agentos_iso.sh" >/dev/null
  progress_line 2 "smoke checks" "done"
else
  progress_line 2 "smoke checks" "skipped"
fi

progress_line 3 "build environment" "running" "version=$VERSION arch=$ARCH"
if [ -z "${AGENTOS_GO_BIN:-}" ]; then
  if [ -x "/tmp/agentos-go-1.26.2/go/bin/go" ]; then
    export AGENTOS_GO_BIN="/tmp/agentos-go-1.26.2/go/bin/go"
  elif command -v go >/dev/null 2>&1; then
    export AGENTOS_GO_BIN="$(command -v go)"
  fi
fi
export AGENTOS_OPERATOR_TUI_GOARCH="$ARCH"
mkdir -p "$LOG_DIR"
BUILD_LOG="$LOG_DIR/build-agentos-${VERSION}-${ARCH}.log"
progress_line 3 "build environment" "done"

build_cmd=(
  "$ROOT_DIR/scripts/build_agentos_iso.sh"
  --version "$VERSION"
  --output-dir "$OUTPUT_DIR"
  --arch "$ARCH"
)

if [ -n "$BASE_IMAGE" ]; then
  build_cmd+=(--base-image "$BASE_IMAGE")
elif [ "$DOWNLOAD_BASE_IMAGE" -eq 1 ]; then
  build_cmd+=(--download-base-image)
else
  echo "No base image supplied and --no-download was set." >&2
  exit 2
fi

if [ "$ARCH" = "arm64" ]; then
  build_cmd+=(--headless-acceptance-base)
fi

progress_line 4 "remaster/build ISO" "running" "log: $BUILD_LOG"
set +e
"${build_cmd[@]}" >"$BUILD_LOG" 2>&1 &
build_pid=$!
elapsed=0
while kill -0 "$build_pid" 2>/dev/null; do
  sleep 10
  elapsed=$((elapsed + 10))
  if [ "$elapsed" -eq 10 ] || [ $((elapsed % 60)) -eq 0 ]; then
    progress_line 4 "remaster/build ISO" "running" "$(format_elapsed "$elapsed") elapsed; log: $BUILD_LOG"
  fi
done
wait "$build_pid"
build_status=$?
set -e
if [ "$build_status" -ne 0 ]; then
  progress_line 4 "remaster/build ISO" "failed" "see log: $BUILD_LOG" >&2
  echo "[agentos-build] build failed; last log lines:" >&2
  tail -n 80 "$BUILD_LOG" >&2 || true
  echo "[agentos-build] full log: $BUILD_LOG" >&2
  exit "$build_status"
fi
progress_line 4 "remaster/build ISO" "done"

ISO_PATH="$OUTPUT_DIR/agentos-${VERSION}-${ARCH}.iso"
METADATA_PATH="$OUTPUT_DIR/agentos-release-metadata.json"
SHA_PATH="$OUTPUT_DIR/SHA256SUMS"
MANIFEST_PATH="$ROOT_DIR/build-output/manifest-${VERSION}.txt"

progress_line 5 "release validation" "running" "metadata, identity, ISO manifest"
python3 "$ROOT_DIR/scripts/release_identity_manifest.py" validate --input "$METADATA_PATH" --json >/dev/null
python3 "$ROOT_DIR/scripts/verify_release_identity_contract.py" --metadata "$METADATA_PATH" --json >/dev/null
python3 "$ROOT_DIR/scripts/verify_iso_release_metadata.py" \
  --iso "$ISO_PATH" \
  --sha256sums "$SHA_PATH" \
  --manifest "$MANIFEST_PATH" \
  --json >/dev/null
progress_line 5 "release validation" "done"

if [ "$CLEANUP" -eq 1 ]; then
  progress_line 6 "post-build cleanup" "running"
  python3 "$ROOT_DIR/scripts/cleanup_temp_artifacts.py" --delete --json >/dev/null
  python3 "$ROOT_DIR/scripts/cleanup_build_artifacts.py" --delete --json >/dev/null
  progress_line 6 "post-build cleanup" "done"
else
  progress_line 6 "post-build cleanup" "skipped"
fi

progress_line 7 "release ready" "done"
echo
echo "AgentOS ISO ready:"
echo "  ISO:      $ISO_PATH"
echo "  SHA256:   $SHA_PATH"
echo "  Manifest: $MANIFEST_PATH"
echo "  Metadata: $METADATA_PATH"
