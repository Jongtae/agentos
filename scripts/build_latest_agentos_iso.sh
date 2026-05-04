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
RENDERED_PROGRESS_LINES=0
STEP_LABELS=(
  "cleanup"
  "smoke checks"
  "prepare assets"
  "remaster filesystem"
  "write ISO"
  "verify metadata"
  "cleanup"
)
STEP_STATUS=(
  "pending"
  "pending"
  "pending"
  "pending"
  "pending"
  "pending"
  "pending"
)
STEP_DETAIL=("" "" "" "" "" "" "")
SPINNER_CHARS=("|" "/" "-" "\\")
SPINNER_INDEX=0

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
  local status="$1"
  local width=10
  local filled=7
  if [ "$status" != "running" ]; then
    return
  fi
  local empty=$((width - filled))
  local i
  for ((i = 0; i < filled; i++)); do
    printf "█"
  done
  for ((i = 0; i < empty; i++)); do
    printf "░"
  done
}

progress_status_text() {
  local status="$1"
  local detail="${2:-}"
  if [ "$status" = "running" ] && [ -n "$detail" ]; then
    printf "running %s" "$detail"
    return
  fi
  printf "%s" "$status"
}

spinner() {
  printf "%s" "${SPINNER_CHARS[$SPINNER_INDEX]}"
}

render_progress() {
  if [ -t 1 ] && [ "$RENDERED_PROGRESS_LINES" -gt 0 ]; then
    printf "\033[%dA" "$RENDERED_PROGRESS_LINES"
    local i
    for ((i = 0; i < RENDERED_PROGRESS_LINES; i++)); do
      printf "\033[2K\r"
      if [ "$i" -lt $((RENDERED_PROGRESS_LINES - 1)) ]; then
        printf "\033[1B"
      fi
    done
    printf "\033[%dA" $((RENDERED_PROGRESS_LINES - 1))
  fi

  printf "AgentOS ISO build progress\n"
  local idx
  for idx in 1 2 3 4 5 6 7; do
    local label="${STEP_LABELS[$((idx - 1))]}"
    local status="${STEP_STATUS[$((idx - 1))]}"
    local detail="${STEP_DETAIL[$((idx - 1))]}"
    local bar
    bar="$(progress_bar "$status")"
    if [ -n "$bar" ]; then
      printf "[%d/%d] %-19s %s %s %s\n" \
        "$idx" "$TOTAL_STEPS" "$label" "$bar" "$(spinner)" "$(progress_status_text "$status" "$detail")"
    else
      printf "[%d/%d] %-19s %s\n" \
        "$idx" "$TOTAL_STEPS" "$label" "$(progress_status_text "$status" "$detail")"
    fi
  done
  printf "Log: %s\n" "${BUILD_LOG:-not created yet}"
  RENDERED_PROGRESS_LINES=9
}

set_step() {
  local step="$1"
  local status="$2"
  local detail="${3:-}"
  STEP_STATUS[$((step - 1))]="$status"
  STEP_DETAIL[$((step - 1))]="$detail"
  SPINNER_INDEX=$(((SPINNER_INDEX + 1) % ${#SPINNER_CHARS[@]}))
  render_progress
}

if [ "$CLEANUP" -eq 1 ]; then
  set_step 1 "running" ""
  python3 "$ROOT_DIR/scripts/cleanup_temp_artifacts.py" --delete --json >/dev/null
  python3 "$ROOT_DIR/scripts/cleanup_build_artifacts.py" --delete --json >/dev/null
  set_step 1 "done" ""
else
  set_step 1 "skipped" ""
fi

if [ "$RUN_SMOKE" -eq 1 ]; then
  set_step 2 "running" ""
  bash "$ROOT_DIR/scripts/smoke_build_agentos_iso.sh" >/dev/null
  set_step 2 "done" ""
else
  set_step 2 "skipped" ""
fi

set_step 3 "running" "version=$VERSION arch=$ARCH"
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
set_step 3 "done" ""

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

set_step 4 "running" "00:00"
set +e
"${build_cmd[@]}" >"$BUILD_LOG" 2>&1 &
build_pid=$!
elapsed=0
while kill -0 "$build_pid" 2>/dev/null; do
  sleep 2
  elapsed=$((elapsed + 2))
  set_step 4 "running" "$(format_elapsed "$elapsed")"
done
wait "$build_pid"
build_status=$?
set -e
if [ "$build_status" -ne 0 ]; then
  set_step 4 "failed" ""
  echo "[agentos-build] build failed; last log lines:" >&2
  tail -n 80 "$BUILD_LOG" >&2 || true
  echo "[agentos-build] full log: $BUILD_LOG" >&2
  exit "$build_status"
fi
set_step 4 "done" ""
set_step 5 "done" ""

ISO_PATH="$OUTPUT_DIR/agentos-${VERSION}-${ARCH}.iso"
METADATA_PATH="$OUTPUT_DIR/agentos-release-metadata.json"
SHA_PATH="$OUTPUT_DIR/SHA256SUMS"
MANIFEST_PATH="$ROOT_DIR/build-output/manifest-${VERSION}.txt"

set_step 6 "running" ""
python3 "$ROOT_DIR/scripts/release_identity_manifest.py" validate --input "$METADATA_PATH" --json >/dev/null
python3 "$ROOT_DIR/scripts/verify_release_identity_contract.py" --metadata "$METADATA_PATH" --json >/dev/null
python3 "$ROOT_DIR/scripts/verify_iso_release_metadata.py" \
  --iso "$ISO_PATH" \
  --sha256sums "$SHA_PATH" \
  --manifest "$MANIFEST_PATH" \
  --json >/dev/null
set_step 6 "done" ""

if [ "$CLEANUP" -eq 1 ]; then
  set_step 7 "running" ""
  python3 "$ROOT_DIR/scripts/cleanup_temp_artifacts.py" --delete --json >/dev/null
  python3 "$ROOT_DIR/scripts/cleanup_build_artifacts.py" --delete --json >/dev/null
  set_step 7 "done" ""
else
  set_step 7 "skipped" ""
fi

render_progress
echo
echo "AgentOS ISO ready:"
echo "  ISO:      $ISO_PATH"
echo "  SHA256:   $SHA_PATH"
echo "  Manifest: $MANIFEST_PATH"
echo "  Metadata: $METADATA_PATH"
