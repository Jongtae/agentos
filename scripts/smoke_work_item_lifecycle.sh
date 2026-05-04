#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

python3 - <<'PY' "$ROOT_DIR"
import json
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])

start = subprocess.run(
    [
        "python3",
        str(root / "scripts" / "work_item_lifecycle.py"),
        "start",
        "--kind",
        "phase",
        "--stage",
        "27",
        "--phase",
        "172",
        "--title",
        "Remastered VM Boot Checklist",
        "--dry-run",
        "--allow-dirty",
    ],
    cwd=root,
    check=True,
    capture_output=True,
    text=True,
)
start_payload = json.loads(start.stdout.strip())
if start_payload["issue_title"] != "EPIC: Stage 27 / Phase 172 Remastered VM Boot Checklist":
    raise SystemExit("unexpected start issue title")
if start_payload["branch"] != "codex/stage27-phase172-remastered-vm-boot-checklist":
    raise SystemExit("unexpected phase branch")

close = subprocess.run(
    [
        "python3",
        str(root / "scripts" / "work_item_lifecycle.py"),
        "close",
        "--issue",
        "172",
        "--branch",
        "codex/stage27-phase172-remastered-vm-boot-checklist",
        "--merge-target",
        "codex/stage27-vm-end-to-end-boot-proof",
        "--commit",
        "abc1234",
        "--dry-run",
        "--allow-dirty",
    ],
    cwd=root,
    check=True,
    capture_output=True,
    text=True,
)
close_payload = json.loads(close.stdout.strip())
if close_payload["merge_target"] != "codex/stage27-vm-end-to-end-boot-proof":
    raise SystemExit("unexpected merge target")
PY

echo "work item lifecycle smoke: PASS"
