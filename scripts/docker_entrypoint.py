#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def ensure_default_workspace() -> None:
    workspace = Path(os.environ.get("DEFAULT_WORKSPACE", ROOT_DIR / "workspaces" / "default")).expanduser()
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "data").mkdir(parents=True, exist_ok=True)
    spec_path = workspace / "spec.yaml"
    seed_spec = ROOT_DIR / "spec.yaml"
    if not spec_path.exists() and seed_spec.exists():
        spec_path.write_text(seed_spec.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> int:
    ensure_default_workspace()
    args = sys.argv[1:]
    if not args or args[0] in {"serve", "web", "preview"}:
        forwarded = args[1:] if args else []
        command = [sys.executable, str(ROOT_DIR / "scripts" / "docker_runtime_preview.py"), *forwarded]
    elif args[0].startswith("--"):
        command = [sys.executable, str(ROOT_DIR / "scripts" / "kernel_phase2_run.py"), "--json", *args]
    else:
        command = args
    os.execvp(command[0], command)
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
