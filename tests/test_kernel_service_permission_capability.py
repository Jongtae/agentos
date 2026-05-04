from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from kernel.service_permission_capability import (
    build_permission_capability_report,
    build_service_capability_report,
    build_service_permission_capability_surface,
)
from scripts.kernel_service_permission_capability_surface import validate_payload

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_service_permission_capability_surface.py"


class KernelServicePermissionCapabilityTests(unittest.TestCase):
    def test_service_capability_classifies_broker_and_escalated_units(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            artifacts = workspace / "artifacts"
            artifacts.mkdir(parents=True)
            (artifacts / "os_events.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "timestamp_utc": "2026-04-19T00:00:00Z",
                                "source": "journald",
                                "kind": "systemd.unit_state",
                                "object": {"unit": "agentos-kernel.service", "state": "started"},
                                "action": "started",
                                "decision": {"state": "observed"},
                                "correlation": {"session_id": "agentos:tty1"},
                                "raw_ref": {"collector": "journald"},
                            }
                        ),
                        json.dumps(
                            {
                                "timestamp_utc": "2026-04-19T00:00:01Z",
                                "source": "broker",
                                "kind": "broker.exec_decision",
                                "object": {"unit": "agentos-eventd.service", "policy_target": "operator_control_change"},
                                "action": "service_restart",
                                "decision": {"state": "allowed", "request_kind": "operator_control"},
                                "correlation": {"session_id": "agentos:tty1"},
                                "raw_ref": {"component": "broker"},
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            payload = build_service_capability_report(workspace)

            self.assertEqual(payload["summary"]["broker_mediated_control_units"], 5)
            self.assertEqual(payload["summary"]["escalated_control_units"], 2)
            eventd = next(item for item in payload["control_units"] if item["unit"] == "agentos-eventd.service")
            self.assertEqual(eventd["control_handling"], "broker_escalated_approval")
            self.assertTrue(eventd["escalated_control_required"])
            self.assertEqual(payload["evidence"]["operator_control_actions"][0]["control_handling"], "broker_escalated_approval")

    def test_permission_capability_summarizes_native_and_broker_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            artifacts = workspace / "artifacts"
            artifacts.mkdir(parents=True)
            (artifacts / "runtime_trace.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "timestamp_utc": "2026-04-19T00:00:00Z",
                                "event": "approval_requested",
                                "payload": {
                                    "tool_name": "bash",
                                    "risk_reason": "destructive command",
                                    "broker": {"correlation": {"request_id": "req-1", "approval_id": "approval:req-1"}},
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "timestamp_utc": "2026-04-19T00:00:01Z",
                                "event": "approval_decision",
                                "payload": {
                                    "tool_name": "bash",
                                    "approved": False,
                                    "broker": {"correlation": {"request_id": "req-1", "approval_id": "approval:req-1"}},
                                },
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (artifacts / "os_events.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "timestamp_utc": "2026-04-19T00:00:00Z",
                                "source": "broker",
                                "kind": "broker.approval_request",
                                "object": {"tool_name": "bash", "policy_target": "destructive_action_approval"},
                                "action": "approval_gate",
                                "decision": {"state": "requested", "request_kind": "approval"},
                                "correlation": {"request_id": "req-1", "approval_id": "approval:req-1", "session_id": "agentos:tty1"},
                                "raw_ref": {"component": "broker"},
                            }
                        ),
                        json.dumps(
                            {
                                "timestamp_utc": "2026-04-19T00:00:01Z",
                                "source": "broker",
                                "kind": "broker.approval_decision",
                                "object": {"tool_name": "bash", "policy_target": "destructive_action_approval"},
                                "action": "decision",
                                "decision": {"state": "denied", "reason": "approval denied by approver", "request_kind": "approval"},
                                "correlation": {"request_id": "req-1", "approval_id": "approval:req-1", "session_id": "agentos:tty1"},
                                "raw_ref": {"component": "broker"},
                            }
                        ),
                        json.dumps(
                            {
                                "timestamp_utc": "2026-04-19T00:00:02Z",
                                "source": "broker",
                                "kind": "broker.exec_decision",
                                "object": {"status": "override_active"},
                                "action": "install_kernel_boot_integration",
                                "decision": {"state": "override", "reason": "operator override active", "request_kind": "override"},
                                "correlation": {"request_id": "req-override", "session_id": "agentos:tty1"},
                                "raw_ref": {"component": "broker"},
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            payload = build_permission_capability_report(workspace, limit=20)

            self.assertEqual(payload["summary"]["approval_requested"], 1)
            self.assertEqual(payload["summary"]["broker_override_count"], 1)
            self.assertEqual(payload["summary"]["native_policy_signal_events"], 2)
            self.assertEqual(payload["summary"]["escalated_permission_events"], 3)
            self.assertIn("broker_approval_gate", payload["summary"]["control_mode_counts"])
            self.assertIn("native_policy_signal", payload["summary"]["control_mode_counts"])

    def test_combined_surface_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True)
            payload = build_service_permission_capability_surface(workspace)
            self.assertEqual(validate_payload(payload), [])

            out = Path(td) / "service-permission-capability.json"
            subprocess.run(
                ["python3", str(SCRIPT), "--workspace", str(workspace), "--output", str(out)],
                cwd=ROOT_DIR,
                check=True,
            )
            result = subprocess.run(
                ["python3", str(SCRIPT), "--validate", str(out), "--json"],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
            validated = json.loads(result.stdout)
            self.assertTrue(validated["ok"])


if __name__ == "__main__":
    unittest.main()
