from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kernel.capability_substrate import build_capability_proof_surface
from kernel.control_plane_capabilities import (
    build_execution_ownership_report,
    build_vm_e2e_proof_report,
    classify_execution_path,
)
from kernel.policies.approval_rules import PolicyEngine
from kernel.planner.planner import Step

ROOT_DIR = Path(__file__).resolve().parents[1]
EXECUTION_SCRIPT = ROOT_DIR / "scripts" / "kernel_capability_execution.py"
VM_E2E_SCRIPT = ROOT_DIR / "scripts" / "kernel_vm_e2e_proof.py"


class ControlPlaneCapabilitiesTests(unittest.TestCase):
    def test_classify_execution_path_marks_browser_as_external(self) -> None:
        payload = classify_execution_path(
            Step(tool_name="browser_run", description="open app", args={"action": "navigate", "url": "https://example.com"}),
            PolicyEngine(require_approval=True),
        )
        self.assertEqual(payload["capability_selected_path"], "external_adapter")
        self.assertTrue(payload["external_adapter_required"])
        self.assertEqual(payload["permission_state"], "escalated_only")

    def test_classify_execution_path_marks_risky_bash_as_approval_required(self) -> None:
        payload = classify_execution_path(
            Step(tool_name="bash", description="delete file", args={"command": "rm file.txt"}),
            PolicyEngine(require_approval=True),
        )
        self.assertEqual(payload["capability_selected_path"], "broker_mediated_privileged_path")
        self.assertEqual(payload["permission_state"], "approval_required")
        self.assertTrue(payload["broker_mediated"])

    def test_execution_ownership_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True)
            sample = workspace / "sample.json"
            sample.write_text(
                json.dumps(
                    {
                        "capability_selected_path": "broker_mediated_privileged_path",
                        "permission_state": "approval_required",
                        "broker_mediated": True,
                        "external_adapter_required": False,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            out = workspace / "execution.json"
            subprocess.run(
                ["python3", str(EXECUTION_SCRIPT), "--workspace", str(workspace), "--sample-file", str(sample), "--output", str(out)],
                cwd=ROOT_DIR,
                check=True,
            )
            result = subprocess.run(
                ["python3", str(EXECUTION_SCRIPT), "--validate", str(out), "--json"],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])

    def test_vm_e2e_report_reads_latest_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True)
            proof_root = workspace / "artifacts" / "capability-substrate"
            proof_root.mkdir(parents=True)
            (proof_root / "latest-capability-proof-surface.json").write_text(
                json.dumps(
                    {
                        "schema_version": "agentos-capability-proof-surface.v1",
                        "summary": {
                            "document_native_handled": True,
                            "intake_native_items": 1,
                        },
                        "intake_surface": {"summary": {"ok": True}},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            control_root = workspace / "artifacts" / "control-plane-capabilities"
            control_root.mkdir(parents=True)
            (control_root / "latest-service-capability.json").write_text(
                json.dumps({"proof": {"ok": True, "native_service_handled": True}}) + "\n",
                encoding="utf-8",
            )
            (control_root / "latest-permission-capability.json").write_text(
                json.dumps({"proof": {"ok": True, "native_permission_handled": True}}) + "\n",
                encoding="utf-8",
            )
            (control_root / "latest-execution-ownership.json").write_text(
                json.dumps({"sampled_execution_paths": [{"external_adapter_required": True, "control_escalation_reason": "browser_navigation_required"}]}) + "\n",
                encoding="utf-8",
            )
            payload = build_vm_e2e_proof_report(
                workspace,
                runtime_report={"ok": True},
                capability_proof=json.loads((proof_root / "latest-capability-proof-surface.json").read_text(encoding="utf-8")),
                service_capability=json.loads((control_root / "latest-service-capability.json").read_text(encoding="utf-8")),
                permission_capability=json.loads((control_root / "latest-permission-capability.json").read_text(encoding="utf-8")),
                execution_ownership=json.loads((control_root / "latest-execution-ownership.json").read_text(encoding="utf-8")),
            )
            self.assertTrue(payload["summary"]["vm_e2e_runtime_ok"])
            self.assertTrue(payload["summary"]["vm_e2e_service_permission_ok"])
            self.assertTrue(payload["summary"]["vm_e2e_escalation_integrity_ok"])

    @patch("kernel.capability_substrate.build_web_access_report")
    def test_vm_e2e_report_refreshes_missing_manifests(self, mock_web_access) -> None:
        mock_web_access.return_value = {
            "schema_version": "agentos-web-access.v1",
            "generated_at_utc": "2026-04-19T00:00:00Z",
            "workspace": "",
            "capability_family": "web",
            "capability": "web_access",
            "url": "https://example.com",
            "native_path_default": True,
            "native_handled": False,
            "escalated_handled": True,
            "escalation_reason": "interactive_or_js_heavy",
            "unsupported_or_deferred": False,
            "mediation_cost": "medium",
            "document_class": "html",
            "proof": {"ok": True},
            "artifacts": {},
        }

        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True)
            (workspace / "spec.yaml").write_text("name: refresh-proof\n", encoding="utf-8")
            capability_proof = build_capability_proof_surface(workspace)
            payload = build_vm_e2e_proof_report(
                workspace,
                runtime_report={"ok": True},
                capability_proof=capability_proof,
                service_capability=capability_proof.get("service_capability", {}),
                permission_capability=capability_proof.get("permission_capability", {}),
                execution_ownership=capability_proof.get("execution_ownership", {}),
            )

            self.assertTrue(payload["summary"]["vm_e2e_capability_ok"])
            self.assertTrue(payload["summary"]["vm_e2e_intake_ok"])
            self.assertTrue(payload["summary"]["vm_e2e_service_permission_ok"])
            self.assertTrue(Path(capability_proof["document_access"]["artifacts"]["latest_document_access_manifest_json"]).exists())
            self.assertTrue(Path(capability_proof["intake_surface"]["artifacts"]["latest_intake_surface_manifest_json"]).exists())

    def test_vm_e2e_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "vm-e2e.json"
            subprocess.run(
                ["python3", str(VM_E2E_SCRIPT), "--workspace", "./workspaces/default", "--output", str(out)],
                cwd=ROOT_DIR,
                check=True,
            )
            result = subprocess.run(
                ["python3", str(VM_E2E_SCRIPT), "--validate", str(out), "--json"],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])

    def test_vm_e2e_cli_refresh_manifests_alias_records_refresh_policy(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True)
            out = Path(td) / "vm-e2e-refresh.json"
            subprocess.run(
                [
                    "python3",
                    str(VM_E2E_SCRIPT),
                    "--workspace",
                    str(workspace),
                    "--session-id",
                    "agentos:tty1",
                    "--refresh-manifests",
                    "--output",
                    str(out),
                ],
                cwd=ROOT_DIR,
                check=True,
            )
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(payload["refresh_policy"]["refresh_manifests"])
            self.assertTrue(payload["refresh_policy"]["scenario_refresh_performed"])
            self.assertTrue(payload["summary"]["vm_e2e_runtime_ok"])
            self.assertTrue(payload["summary"]["vm_e2e_service_permission_ok"])
            self.assertTrue(Path(payload["artifacts"]["latest_vm_e2e_proof_manifest_json"]).exists())
            exported = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(exported["summary"]["vm_e2e_runtime_ok"])
            self.assertTrue(exported["summary"]["vm_e2e_capability_ok"])
            self.assertTrue(exported["summary"]["vm_e2e_intake_ok"])
            self.assertTrue(exported["summary"]["vm_e2e_service_permission_ok"])
            self.assertTrue(exported["summary"]["vm_e2e_escalation_integrity_ok"])


if __name__ == "__main__":
    unittest.main()
