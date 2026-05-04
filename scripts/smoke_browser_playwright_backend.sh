#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/src"

python3 - <<'PY'
import importlib.util
import os
import sys
from pathlib import Path

from kernel.tools.browser_tool import BrowserIsolationRequest, BrowserPlaywrightIsolationBoundary, resolve_browser_backend

if importlib.util.find_spec("playwright") is None:
    print("browser playwright backend smoke: SKIP (playwright not installed)")
    raise SystemExit(0)

os.environ["AGENTOS_BROWSER_BACKEND"] = "playwright"
backend = resolve_browser_backend()
if backend.selected != "playwright":
    raise SystemExit(f"expected playwright backend, got {backend}")

worker = Path("scripts/browser_worker_playwright.py").resolve()
boundary = BrowserPlaywrightIsolationBoundary(worker_cmd=[sys.executable, str(worker)], timeout_sec=10)
result = boundary.run(BrowserIsolationRequest(action="extract_text", url="https://example.com"))
if not result.ok:
    raise SystemExit(f"playwright run failed: {result.detail}")
if "playwright extract_text ok" not in result.detail:
    raise SystemExit(f"unexpected detail: {result.detail}")

print("browser playwright backend smoke: PASS")
PY
