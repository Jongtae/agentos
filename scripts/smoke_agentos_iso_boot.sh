#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage:
  scripts/smoke_agentos_iso_boot.sh --iso <path> [--timeout-sec N] [--memory-mb N] [--cpus N] [--require-qemu] [--kernel-ready-gate] [--kernel-ready-strict]

Notes:
  - This is a QEMU boot smoke for nightly/release gates.
  - If qemu is unavailable, the script exits 0 with SKIP unless --require-qemu is set.
USAGE
}

ISO_PATH=""
TIMEOUT_SEC=180
MEMORY_MB=2048
CPUS=2
REQUIRE_QEMU=0
KERNEL_READY_GATE=0
KERNEL_READY_STRICT=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --iso)
      shift
      ISO_PATH="${1:-}"
      ;;
    --timeout-sec)
      shift
      TIMEOUT_SEC="${1:-180}"
      ;;
    --memory-mb)
      shift
      MEMORY_MB="${1:-2048}"
      ;;
    --cpus)
      shift
      CPUS="${1:-2}"
      ;;
    --require-qemu)
      REQUIRE_QEMU=1
      ;;
    --kernel-ready-gate)
      KERNEL_READY_GATE=1
      ;;
    --kernel-ready-strict)
      KERNEL_READY_GATE=1
      KERNEL_READY_STRICT=1
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

if [ -z "$ISO_PATH" ]; then
  echo "--iso is required" >&2
  usage
  exit 2
fi

if [ ! -f "$ISO_PATH" ]; then
  echo "iso not found: $ISO_PATH" >&2
  exit 1
fi

if ! [[ "$TIMEOUT_SEC" =~ ^[0-9]+$ ]] || [ "$TIMEOUT_SEC" -lt 30 ]; then
  echo "--timeout-sec must be an integer >= 30" >&2
  exit 2
fi

if [ "$KERNEL_READY_GATE" = "1" ]; then
  if [ "$KERNEL_READY_STRICT" = "1" ]; then
    scripts/smoke_kernel_policy_enforce_require_ready.sh --strict-apparmor
  else
    scripts/smoke_kernel_policy_enforce_require_ready.sh
  fi
fi

QEMU_BIN="$(command -v qemu-system-x86_64 || true)"
if [ -z "$QEMU_BIN" ]; then
  if [ "$REQUIRE_QEMU" = "1" ]; then
    echo "qemu-system-x86_64 not found (required)"
    exit 1
  fi
  echo "ISO boot smoke: SKIP (qemu-system-x86_64 not found)"
  exit 0
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
LOG_FILE="$TMP_DIR/qemu-boot.log"

python3 - "$QEMU_BIN" "$ISO_PATH" "$TIMEOUT_SEC" "$MEMORY_MB" "$CPUS" "$LOG_FILE" <<'PY'
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

qemu_bin = sys.argv[1]
iso_path = sys.argv[2]
timeout_sec = int(sys.argv[3])
memory_mb = int(sys.argv[4])
cpus = int(sys.argv[5])
log_file = Path(sys.argv[6])

cmd = [
    qemu_bin,
    "-machine", "q35,accel=tcg",
    "-m", str(memory_mb),
    "-smp", str(cpus),
    "-cdrom", iso_path,
    "-boot", "d",
    "-display", "none",
    "-serial", "stdio",
    "-no-reboot",
]

with log_file.open("w", encoding="utf-8") as out:
    proc = subprocess.Popen(
        cmd,
        stdout=out,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid if hasattr(os, "setsid") else None,
    )
    deadline = time.time() + timeout_sec
    early_exit = None

    while time.time() < deadline:
        rc = proc.poll()
        if rc is not None:
            early_exit = rc
            break
        time.sleep(1.0)

    if early_exit is not None:
        print(f"ISO boot smoke: FAIL (qemu exited early: rc={early_exit})")
        print(f"qemu log: {log_file}")
        raise SystemExit(1)

    try:
        if hasattr(os, "killpg"):
            os.killpg(proc.pid, signal.SIGTERM)
        else:
            proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        try:
            if hasattr(os, "killpg"):
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except Exception:
            pass

print("ISO boot smoke: PASS")
print(f"qemu log: {log_file}")
PY
