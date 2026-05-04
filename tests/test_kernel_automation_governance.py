from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.automation_governance import build_automation_governance_report
from kernel.event_fabric.collectors import append_events_jsonl
from kernel.event_fabric.schema import build_os_event_record, os_event_log_path
from scripts.kernel_automation_governance import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_automation_governance.py"


class KernelAutomationGovernanceTests(unittest.TestCase):
    def test_contract_contains_scheduled_and_background_items(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            (workspace / "artifacts").mkdir(parents=True)
            payload = build_automation_governance_report(workspace)
            self.assertEqual(validate_payload(payload), [])
            self.assertGreaterEqual(len(payload["scheduled_tasks"]), 1)
            self.assertGreaterEqual(len(payload["background_agents"]), 1)

    def test_evidence_reads_override_and_operator_control(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            (workspace / "artifacts").mkdir(parents=True)
            append_events_jsonl(
                os_event_log_path(workspace),
                [
                    build_os_event_record(
                        source="broker",
                        kind="broker.exec_decision",
                        actor={"component": "runtime_autoremediation_stage_orchestrator.py"},
                        object={"policy_target": "destructive_action_approval"},
                        action="scheduled_stage_apply",
                        decision={"state": "allowed", "request_kind": "operator_control"},
                        correlation={"session_id": "agentos:tty1"},
                        raw_ref={"component": "broker"},
                    ),
                    build_os_event_record(
                        source="broker",
                        kind="broker.exec_decision",
                        actor={"component": "runtime_autoremediation_loop.py"},
                        object={"status": "override_active"},
                        action="forced_resume",
                        decision={"state": "override", "request_kind": "override"},
                        correlation={"session_id": "agentos:tty1"},
                        raw_ref={"component": "broker"},
                    ),
                ],
            )
            payload = build_automation_governance_report(workspace)
            self.assertEqual(payload["summary"]["operator_control_events"], 1)
            self.assertEqual(payload["summary"]["override_events"], 1)

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            (workspace / "artifacts").mkdir(parents=True)
            out = Path(td) / "automation-governance.json"
            subprocess.run(["python3", str(SCRIPT), "--workspace", str(workspace), "--output", str(out)], cwd=ROOT_DIR, check=True)
            result = subprocess.run(["python3", str(SCRIPT), "--validate", str(out), "--json"], cwd=ROOT_DIR, check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
