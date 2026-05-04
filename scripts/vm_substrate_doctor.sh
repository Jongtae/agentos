#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/src"

WORKSPACE_DIR="${1:-$ROOT_DIR/workspaces/default}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_DIR="${2:-$ROOT_DIR/artifacts/substrate-doctor/$STAMP}"

mkdir -p "$OUT_DIR"

run_and_capture() {
  local name="$1"
  shift
  set +e
  "$@" >"$OUT_DIR/${name}.stdout" 2>"$OUT_DIR/${name}.stderr"
  local code=$?
  set -e
  printf "%s" "$code" > "$OUT_DIR/${name}.exit"
}

run_and_capture preflight python3 src/main.py --workspace "$WORKSPACE_DIR" --preflight --json --preflight-file "$OUT_DIR/preflight.json"
run_and_capture doctor python3 src/main.py --workspace "$WORKSPACE_DIR" --doctor --json --doctor-file "$OUT_DIR/doctor.json"
run_and_capture status python3 src/main.py --workspace "$WORKSPACE_DIR" --status --json --status-file "$OUT_DIR/status.json"
if [ -x "$ROOT_DIR/scripts/agentos-kernelctl" ]; then
  run_and_capture kernelctl_preflight "$ROOT_DIR/scripts/agentos-kernelctl" preflight --workspace "$WORKSPACE_DIR"
fi

PREFLIGHT_EXIT="$(cat "$OUT_DIR/preflight.exit")"
DOCTOR_EXIT="$(cat "$OUT_DIR/doctor.exit")"
STATUS_EXIT="$(cat "$OUT_DIR/status.exit")"
KERNELCTL_EXIT=0
if [ -f "$OUT_DIR/kernelctl_preflight.exit" ]; then
  KERNELCTL_EXIT="$(cat "$OUT_DIR/kernelctl_preflight.exit")"
fi

OVERALL=0
if [ "$PREFLIGHT_EXIT" -ne 0 ] || [ "$DOCTOR_EXIT" -ne 0 ] || [ "$STATUS_EXIT" -ne 0 ] || [ "$KERNELCTL_EXIT" -ne 0 ]; then
  OVERALL=1
fi

echo "VM Substrate Doctor"
echo "==================="
echo "Workspace: $WORKSPACE_DIR"
echo "Output dir: $OUT_DIR"
echo "preflight: $PREFLIGHT_EXIT"
echo "doctor:    $DOCTOR_EXIT"
echo "status:    $STATUS_EXIT"
if [ -f "$OUT_DIR/kernelctl_preflight.exit" ]; then
  echo "kernelctl: $KERNELCTL_EXIT"
fi

if [ "$OVERALL" -eq 0 ]; then
  echo "Result: PASS"
else
  echo "Result: FAIL"
  echo "See JSON artifacts and *.stderr files under $OUT_DIR"
fi

exit "$OVERALL"
