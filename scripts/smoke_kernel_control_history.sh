#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
POLICY_DIR="$WORKSPACE/artifacts/kernel-policy"
mkdir -p "$POLICY_DIR"

cat > "$WORKSPACE/spec.yaml" <<'YAML'
name: control-history-smoke
kernel_engine:
  provider: none
  mode: single
runtime:
  workspace_root: ./
YAML

cat > "$WORKSPACE/artifacts/os_events.jsonl" <<'JSONL'
{"timestamp_utc":"2026-04-14T00:00:00+00:00","source":"journald","kind":"session.login","actor":{"uid":1000},"object":{"session_id":"agentos:tty1"},"action":"login","decision":{"state":"observed"},"correlation":{"session_id":"agentos:tty1","session_origin":"local_managed_tty1","next_managed_entry":"ai_shell"},"raw_ref":{"collector":"journald"}}
{"timestamp_utc":"2026-04-14T00:00:01+00:00","source":"broker","kind":"broker.exec_decision","actor":{"component":"kernel_policy_bridge.py"},"object":{"workspace_root":"./"},"action":"policy_bridge_reload","decision":{"state":"allowed","request_kind":"operator_control","reason":"profile reload succeeded"},"correlation":{"session_id":"agentos:tty1"},"raw_ref":{"component":"broker"}}
{"timestamp_utc":"2026-04-14T00:00:02+00:00","source":"broker","kind":"broker.exec_decision","actor":{"component":"kernel_policy_enforced_pilot.py"},"object":{"policy_target":"network_allowlist"},"action":"policy_enforce_enable","decision":{"state":"allowed","request_kind":"operator_control","reason":"kernel ready"},"correlation":{"session_id":"agentos:tty1"},"raw_ref":{"component":"broker"}}
{"timestamp_utc":"2026-04-14T00:00:03+00:00","source":"broker","kind":"broker.exec_decision","actor":{"component":"install_kernel_boot_integration.sh"},"object":{"status":"override_active"},"action":"emergency_recovery","decision":{"state":"override","request_kind":"override","reason":"operator forced recovery bypass"},"correlation":{"session_id":"agentos:tty1"},"raw_ref":{"component":"broker"}}
JSONL

cat > "$POLICY_DIR/profile-lifecycle.json" <<'JSON'
{"bridge_state":"reloaded","reload_state":"applied","disable_state":"inactive","operator_state":"ready"}
JSON
cat > "$POLICY_DIR/enforced-pilot.json" <<'JSON'
{"enabled":true,"policy_target":"network_allowlist"}
JSON

OUT_JSON="$TMP_DIR/control-history.json"
python3 scripts/kernel_control_history.py --workspace "$WORKSPACE" --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("schema_version") != "agentos-control-history.v1":
    raise SystemExit("expected control history schema_version")
summary = payload.get("summary", {})
if "bridge" not in summary.get("categories", []):
    raise SystemExit("expected bridge category")
if "override" not in summary.get("categories", []):
    raise SystemExit("expected override category")
if payload.get("current_state", {}).get("enforce_policy_target") != "network_allowlist":
    raise SystemExit("expected current enforce policy target")
print("kernel control history smoke: PASS")
PY
