from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.service_governance import build_service_governance_report
from kernel.event_fabric.collectors import append_events_jsonl
from kernel.event_fabric.schema import build_os_event_record, os_event_log_path
from scripts.kernel_service_governance import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_service_governance.py"


class KernelServiceGovernanceTests(unittest.TestCase):
    def test_contract_contains_managed_units(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            (workspace / "artifacts").mkdir(parents=True)
            payload = build_service_governance_report(workspace)
            self.assertEqual(validate_payload(payload), [])
            units = {item["unit"] for item in payload["inventory"]}
            self.assertIn("agentos-kernel.service", units)
            self.assertIn("agentos-brokerd.service", units)

    def test_evidence_reads_unit_state_events(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            (workspace / "artifacts").mkdir(parents=True)
            append_events_jsonl(
                os_event_log_path(workspace),
                [
                    build_os_event_record(
                        source="journald",
                        kind="systemd.unit_state",
                        actor={"uid": 1000},
                        object={"unit": "agentos-kernel.service", "state": "started"},
                        action="started",
                        decision={"state": "observed"},
                        correlation={"session_id": "agentos:tty1"},
                        raw_ref={"collector": "journald"},
                    ),
                    build_os_event_record(
                        source="broker",
                        kind="broker.exec_decision",
                        actor={"component": "systemctl"},
                        object={"unit": "agentos-kernel.service"},
                        action="service_restart",
                        decision={"state": "allowed", "request_kind": "operator_control"},
                        correlation={"session_id": "agentos:tty1"},
                        raw_ref={"component": "broker"},
                    ),
                ],
            )
            payload = build_service_governance_report(workspace)
            observed = payload["evidence"]["unit_state_events"]["observed_units"]
            self.assertIn("agentos-kernel.service", observed)
            actions = payload["evidence"]["operator_control_actions"]
            self.assertEqual(actions[0]["action"], "service_restart")

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            (workspace / "artifacts").mkdir(parents=True)
            out = Path(td) / "service-governance.json"
            subprocess.run(["python3", str(SCRIPT), "--workspace", str(workspace), "--output", str(out)], cwd=ROOT_DIR, check=True)
            result = subprocess.run(["python3", str(SCRIPT), "--validate", str(out), "--json"], cwd=ROOT_DIR, check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
