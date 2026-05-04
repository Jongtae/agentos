#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/src"

python3 - <<'PY'
import sys
from pathlib import Path

from kernel.tools.browser_tool import BrowserIsolationRequest, BrowserWorkerIsolationBoundary

worker = Path("scripts/browser_worker_stub.py").resolve()
boundary = BrowserWorkerIsolationBoundary(worker_cmd=[sys.executable, str(worker)], timeout_sec=2)

cases = [
    ("navigate", "fixture:navigate_ok", {"url": "https://example.com"}),
    ("click", "fixture:click_ok", {"url": "https://example.com", "selector": "#login"}),
    ("fill", "fixture:fill_ok", {"url": "https://example.com", "selector": "#email", "value": "user@example.com"}),
    ("screenshot", "fixture:screenshot_ok", {"url": "https://example.com"}),
    ("extract_text", "fixture:extract_text_ok", {"url": "https://example.com", "selector": "h1"}),
]

for action, marker, fields in cases:
    result = boundary.run(BrowserIsolationRequest(action=action, **fields))
    if not result.ok:
        raise SystemExit(f"{action} expected ok, got: {result.detail}")
    if marker not in result.detail:
        raise SystemExit(f"{action} expected marker {marker}, got: {result.detail}")

print("browser action matrix smoke: PASS")
PY
