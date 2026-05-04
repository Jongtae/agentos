#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT_DIR/src"

python3 - <<'PY'
import tempfile
from pathlib import Path

from kernel.broker import append_broker_events, build_broker_decision, build_broker_request
from kernel.event_fabric.report import query_events

with tempfile.TemporaryDirectory() as td:
    workspace = Path(td)
    request = build_broker_request(
        kind="exec",
        action="managed_exec",
        actor={"component": "agentos-shell"},
        correlation={"request_id": "req-1"},
    )
    decision = build_broker_decision(
        state="allowed",
        reason="ok",
        actor=request.actor,
        correlation=request.correlation,
    )
    append_broker_events(workspace, request=request, decision=decision, request_kind="exec")
    report = query_events(workspace, kind="broker.exec_decision", limit=5)
    if report["returned_events"] != 1:
        raise SystemExit("expected one broker.exec_decision event")

print("broker event fabric smoke ok")
PY
