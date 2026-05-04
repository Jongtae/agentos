from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from kernel.provenance_graph import build_provenance_graph
from scripts.kernel_provenance_graph import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_provenance_graph.py"


class KernelProvenanceGraphTests(unittest.TestCase):
    def test_graph_contains_nodes_edges_and_chains(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "artifacts").mkdir(parents=True, exist_ok=True)
            (workspace / "spec.yaml").write_text(
                yaml.dump(
                    {
                        "name": "provenance-test",
                        "kernel_engine": {"provider": "none", "mode": "single"},
                        "runtime": {"workspace_root": "./"},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            (workspace / "artifacts" / "runtime_trace.jsonl").write_text(
                "\n".join(
                    [
                        '{"timestamp_utc":"2026-04-14T00:00:00+00:00","event":"run_start","payload":{}}',
                        '{"timestamp_utc":"2026-04-14T00:00:01+00:00","event":"approval_requested","payload":{"tool_name":"bash","broker":{"correlation":{"approval_id":"approval:test","request_id":"request:test"}}}}',
                    ]
                ) + "\n",
                encoding="utf-8",
            )
            (workspace / "artifacts" / "os_events.jsonl").write_text(
                "\n".join(
                    [
                        '{"timestamp_utc":"2026-04-14T00:00:00+00:00","source":"journald","kind":"session.login","actor":{"uid":1000},"object":{"session_id":"agentos:tty1"},"action":"login","decision":{"state":"observed"},"correlation":{"session_id":"agentos:tty1","boot_id":"boot-1"},"raw_ref":{"collector":"journald"}}',
                        '{"timestamp_utc":"2026-04-14T00:00:02+00:00","source":"broker","kind":"broker.approval_request","actor":{"component":"agentos-runtime"},"object":{"tool_name":"bash","policy_target":"destructive_action_approval"},"action":"approval_gate","decision":{"state":"requested","request_kind":"approval"},"correlation":{"approval_id":"approval:test","request_id":"request:test","session_id":"agentos:tty1"},"raw_ref":{"component":"broker"}}',
                        '{"timestamp_utc":"2026-04-14T00:00:03+00:00","source":"broker","kind":"broker.exec_decision","actor":{"component":"policy-bridge"},"object":{"policy_target":"network_allowlist"},"action":"policy_bridge_reload","decision":{"state":"allowed","request_kind":"operator_control"},"correlation":{"session_id":"agentos:tty1"},"raw_ref":{"component":"broker"}}',
                    ]
                ) + "\n",
                encoding="utf-8",
            )
            payload = build_provenance_graph(workspace=str(workspace), limit=20)
            self.assertEqual(validate_payload(payload), [])
            self.assertGreaterEqual(payload["summary"]["node_count"], 3)
            self.assertGreaterEqual(payload["summary"]["chain_count"], 1)

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "artifacts").mkdir(parents=True, exist_ok=True)
            out = Path(td) / "provenance.json"
            subprocess.run(["python3", str(SCRIPT), "--workspace", str(workspace), "--output", str(out)], cwd=ROOT_DIR, check=True)
            result = subprocess.run(["python3", str(SCRIPT), "--validate", str(out), "--json"], cwd=ROOT_DIR, check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
