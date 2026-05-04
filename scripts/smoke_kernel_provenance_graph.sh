#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$(mktemp -d)"
trap 'rm -rf "$WORKSPACE"' EXIT
mkdir -p "$WORKSPACE/artifacts"
cat > "$WORKSPACE/spec.yaml" <<'YAML'
name: provenance-smoke
kernel_engine:
  provider: none
  mode: single
runtime:
  workspace_root: ./
YAML
cat > "$WORKSPACE/artifacts/runtime_trace.jsonl" <<'JSONL'
{"timestamp_utc":"2026-04-14T00:00:00+00:00","event":"run_start","payload":{}}
{"timestamp_utc":"2026-04-14T00:00:01+00:00","event":"approval_requested","payload":{"tool_name":"bash","broker":{"correlation":{"approval_id":"approval:test","request_id":"request:test"}}}}
JSONL
cat > "$WORKSPACE/artifacts/os_events.jsonl" <<'JSONL'
{"timestamp_utc":"2026-04-14T00:00:00+00:00","source":"journald","kind":"session.login","actor":{"uid":1000},"object":{"session_id":"agentos:tty1"},"action":"login","decision":{"state":"observed"},"correlation":{"session_id":"agentos:tty1","boot_id":"boot-1"},"raw_ref":{"collector":"journald"}}
{"timestamp_utc":"2026-04-14T00:00:02+00:00","source":"broker","kind":"broker.approval_request","actor":{"component":"agentos-runtime"},"object":{"tool_name":"bash","policy_target":"destructive_action_approval"},"action":"approval_gate","decision":{"state":"requested","request_kind":"approval"},"correlation":{"approval_id":"approval:test","request_id":"request:test","session_id":"agentos:tty1"},"raw_ref":{"component":"broker"}}
{"timestamp_utc":"2026-04-14T00:00:03+00:00","source":"broker","kind":"broker.exec_decision","actor":{"component":"policy-bridge"},"object":{"policy_target":"network_allowlist"},"action":"policy_bridge_reload","decision":{"state":"allowed","request_kind":"operator_control"},"correlation":{"session_id":"agentos:tty1"},"raw_ref":{"component":"broker"}}
JSONL
OUT="$WORKSPACE/provenance.json"
python3 "$ROOT_DIR/scripts/kernel_provenance_graph.py" --workspace "$WORKSPACE" --output "$OUT"
python3 "$ROOT_DIR/scripts/kernel_provenance_graph.py" --validate "$OUT" --json >/tmp/agentos-provenance-graph-validate.json
python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["schema_version"] == "agentos-provenance-graph.v1"
assert payload["summary"]["node_count"] >= 3
assert payload["summary"]["chain_count"] >= 1
PY

echo "smoke_kernel_provenance_graph.sh: PASS"
