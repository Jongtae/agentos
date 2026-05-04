#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/src"

python3 - <<'PY'
from kernel.tools.browser_tool import BrowserIsolationRequest, BrowserWorkerIsolationBoundary

boundary = BrowserWorkerIsolationBoundary(timeout_sec=2)
ok = boundary.run(BrowserIsolationRequest(action="navigate", url="https://example.com"))
if not ok.ok:
    raise SystemExit(f"expected success, got: {ok.detail}")

timeout = boundary.run(BrowserIsolationRequest(action="navigate", url="https://example.com?sleep=3"))
if timeout.ok:
    raise SystemExit("expected timeout failure")
if "timed out" not in timeout.detail:
    raise SystemExit(f"expected timeout detail, got: {timeout.detail}")

blocked = boundary.run(BrowserIsolationRequest(action="navigate", url="http://localhost:3000"))
if blocked.ok:
    raise SystemExit("expected blocked navigation")
if "blocked" not in blocked.detail:
    raise SystemExit(f"expected blocked detail, got: {blocked.detail}")

approval = boundary.run(BrowserIsolationRequest(action="navigate", url="https://another.example.org"))
if approval.ok:
    raise SystemExit("expected approval_required navigation")
if "approval_required" not in approval.detail:
    raise SystemExit(f"expected approval detail, got: {approval.detail}")
PY

echo "browser worker boundary smoke: PASS"
