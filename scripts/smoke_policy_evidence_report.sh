#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

WORKSPACE="$TMP_DIR/workspace"
mkdir -p "$WORKSPACE/artifacts"

cat > "$WORKSPACE/artifacts/runtime_trace.jsonl" <<'EOF'
{"timestamp_utc":"2026-04-14T00:00:01+00:00","event":"step_blocked","payload":{"reason":"workspace_boundary","detail":"../outside.txt"}}
{"timestamp_utc":"2026-04-14T00:00:02+00:00","event":"step_blocked","payload":{"reason":"network_allowlist","detail":"blocked.example"}}
{"timestamp_utc":"2026-04-14T00:00:03+00:00","event":"step_blocked","payload":{"reason":"network_allowlist","detail":"blocked-2.example"}}
EOF

WORKSPACE="$WORKSPACE" PYTHONPATH="$ROOT_DIR/src" python3 - <<'PY'
import os
from pathlib import Path

from kernel.event_fabric.collectors import append_events_jsonl, file_access_candidate_event, network_connect_candidate_event

workspace = Path(os.environ["WORKSPACE"])
events = [
    file_access_candidate_event(
        candidate_path="../outside.txt",
        action="read",
        workspace_root=str(workspace),
        actor={"pid": 7, "comm": "bash"},
    ),
    network_connect_candidate_event(
        host="blocked.example",
        port=443,
        allowlist=["openai.com"],
        actor={"pid": 7, "comm": "curl"},
    ),
]
append_events_jsonl(workspace / "artifacts" / "os_events.jsonl", [event for event in events if event is not None])
kernel_policy_dir = workspace / "artifacts" / "kernel-policy"
kernel_policy_dir.mkdir(parents=True, exist_ok=True)
(kernel_policy_dir / "enforced-pilot.json").write_text(
    '{"enabled": true, "policy_target": "fs_workspace_boundary", "updated_at_utc": "2026-04-14T00:00:05+00:00"}\n',
    encoding="utf-8",
)
PY

OUT_JSON="$TMP_DIR/policy-evidence.json"
python3 scripts/kernel_policy_evidence_report.py --workspace "$WORKSPACE" --json > "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
targets = {item["policy_target"]: item for item in payload.get("policy_targets", [])}
if targets["fs_workspace_boundary"]["comparison"]["status"] != "aligned":
    raise SystemExit("expected fs_workspace_boundary alignment")
if targets["fs_workspace_boundary"]["enforced_pilot"]["effective"] is not True:
    raise SystemExit("expected fs_workspace_boundary enforced_pilot.effective=true")
if targets["network_allowlist"]["comparison"]["status"] != "divergent":
    raise SystemExit("expected network_allowlist divergence")
if payload.get("enforced_pilot", {}).get("configured_enabled") is not True:
    raise SystemExit("expected enforced_pilot.configured_enabled=true")
PY

echo "policy evidence report smoke: PASS"
