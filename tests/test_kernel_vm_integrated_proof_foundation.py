from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from kernel.vm_integrated_proof import (
    SCHEMA_VERSION,
    build_vm_integrated_proof_foundation,
    validate_vm_integrated_proof_foundation,
)

SCRIPT = ROOT_DIR / "scripts" / "kernel_vm_integrated_proof_foundation.py"


class KernelVmIntegratedProofFoundationTests(unittest.TestCase):
    def _write_inputs(self, root: Path) -> dict[str, Path]:
        runtime = root / "runtime.json"
        capability = root / "capability.json"
        intake = root / "intake.json"
        service_permission = root / "service-permission.json"

        runtime.write_text(
            json.dumps(
                {
                    "schema_version": "agentos-appliance-boot-signoff-pack.v1",
                    "summary": {
                        "ok": True,
                        "expected_primary_path": "Continue to AgentOS -> AgentOS Welcome -> AgentOS Setup -> ai>",
                        "expected_installed_path": "Installed AgentOS Boot -> AgentOS Setup -> AgentOS Managed Session -> ai>",
                        "expected_recovery_path": "AgentOS Recovery -> Return to AgentOS -> ai>",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        capability.write_text(
            json.dumps(
                {
                    "schema_version": "agentos-capability-proof-surface.v1",
                    "web_access": {
                        "native_handled": False,
                        "escalated_handled": True,
                        "escalation_reason": "interactive_or_js_heavy",
                    },
                    "summary": {
                        "document_native_handled": True,
                        "web_native_handled": False,
                        "web_escalated_handled": True,
                        "intake_native_items": 2,
                        "intake_escalated_items": 0,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        intake.write_text(
            json.dumps(
                {
                    "schema_version": "agentos-intake-surface.v1",
                    "summary": {
                        "ok": True,
                        "total_items": 2,
                        "native_intake_items": 2,
                        "escalated_intake_items": 0,
                    },
                    "intake_items": [
                        {
                            "intake_id": "event:1",
                            "intake_escalation_reason": "",
                            "correlation": {
                                "session_id": "agentos:tty1",
                                "request_id": "req-1",
                                "boot_id": "boot-1",
                            },
                        }
                    ],
                    "session_correlation": {
                        "session_id": "agentos:tty1",
                        "trace_id": "trace-1",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        service_permission.write_text(
            json.dumps(
                {
                    "schema_version": "agentos-service-governance.v1",
                    "inventory": [
                        {"unit": "agentos-kernel.service"},
                        {"unit": "agentos-brokerd.service"},
                    ],
                    "summary": {
                        "mandatory_broker_units": ["agentos-kernel.service", "agentos-brokerd.service"],
                        "approval_gated_units": ["agentos-eventd.service"],
                    },
                    "permission_evidence": {
                        "escalation_reasons": ["operator_control_change"],
                        "approval_id": "approval-9",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return {
            "runtime": runtime,
            "capability": capability,
            "intake": intake,
            "service_permission": service_permission,
        }

    def test_build_helper_aggregates_escalation_and_correlation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inputs = self._write_inputs(root)

            payload = build_vm_integrated_proof_foundation(
                report_dir=str(root / "reports"),
                snapshot_label="fixture",
                runtime_proof=str(inputs["runtime"]),
                capability_proof=str(inputs["capability"]),
                intake_proof=str(inputs["intake"]),
                service_permission_proof=str(inputs["service_permission"]),
            )

            self.assertEqual(payload["schema_version"], SCHEMA_VERSION)
            self.assertEqual(validate_vm_integrated_proof_foundation(payload), [])
            self.assertTrue(payload["summary"]["ok"])
            self.assertIn("interactive_or_js_heavy", payload["summary"]["escalation_reasons"])
            self.assertIn("operator_control_change", payload["summary"]["escalation_reasons"])
            self.assertTrue(payload["summary"]["correlation_evidence_present"])
            self.assertTrue(Path(payload["artifacts"]["vm_integrated_proof_foundation_json"]).exists())

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inputs = self._write_inputs(root)
            out = root / "vm-integrated-proof-foundation.json"
            subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--report-dir",
                    str(root / "reports"),
                    "--runtime-proof",
                    str(inputs["runtime"]),
                    "--capability-proof",
                    str(inputs["capability"]),
                    "--intake-proof",
                    str(inputs["intake"]),
                    "--service-permission-proof",
                    str(inputs["service_permission"]),
                    "--output",
                    str(out),
                ],
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
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
