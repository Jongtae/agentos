#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/src"

python3 <<'PY'
from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

from kernel.engine.codex_cli import CodexCliEngine

workspace = Path('.').resolve()

results = []

# Case 1: missing API key
with tempfile.TemporaryDirectory() as td:
    fake = Path(td) / "fake-codex.sh"
    fake.write_text("#!/bin/sh\necho FAKE\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    original_key = os.environ.pop("OPENAI_API_KEY", None)
    try:
        engine = CodexCliEngine(workspace_dir=workspace, command=str(fake), timeout_sec=5)
        hc = engine.health_check()
        results.append(("missing_key", (not hc.ok) and hc.reason == "missing_api_key", hc.reason, hc.detail))
    finally:
        if original_key is not None:
            os.environ["OPENAI_API_KEY"] = original_key

# Case 2: missing binary
os.environ.setdefault("OPENAI_API_KEY", "dummy-for-matrix")
engine2 = CodexCliEngine(workspace_dir=workspace, command="codex-not-found", timeout_sec=5)
hc2 = engine2.health_check()
results.append(("missing_binary", (not hc2.ok) and hc2.reason == "binary_not_found", hc2.reason, hc2.detail))

# Case 3: timeout
with tempfile.TemporaryDirectory() as td:
    script = Path(td) / "fake-codex.sh"
    script.write_text("#!/bin/sh\nsleep 5\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)

    os.environ.setdefault("OPENAI_API_KEY", "dummy-for-matrix")
    engine3 = CodexCliEngine(workspace_dir=workspace, command=str(script), timeout_sec=1)
    run = engine3.run_intent("hello")
    results.append(("timeout", (not run.ok) and run.error_type == "timeout", run.error_type, run.error_message))

print("Failure Matrix Results")
print("======================")
all_ok = True
for name, ok, reason, detail in results:
    status = "PASS" if ok else "FAIL"
    print(f"{name:16} {status:4} reason={reason} detail={detail}")
    all_ok = all_ok and ok

if not all_ok:
    raise SystemExit(1)
PY
