from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from kernel.event_fabric.session_contract import evaluate_session_contract
from scripts.kernel_session_contract import build_session_contract_report


class KernelSessionContractTests(unittest.TestCase):
    def test_build_session_contract_report_includes_validation_and_modes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "spec.yaml").write_text(
                yaml.dump(
                    {
                        "name": "session-contract-test",
                        "kernel_engine": {
                            "provider": "none",
                            "mode": "single",
                        },
                        "runtime": {"workspace_root": "./"},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            payload = build_session_contract_report(workspace=str(workspace))
            self.assertEqual(payload["schema_version"], "agentos-session-contract-report.v1")
            self.assertEqual(payload["contract"]["schema_version"], "agentos-session-contract.v1")
            self.assertIn("managed_mode", payload["contract"]["mode_contract"])
            self.assertIn("install_later_contract", payload["contract"])
            self.assertIn("platform_reset_contract", payload["contract"])
            self.assertIn("codex_primary_runtime_contract", payload["contract"])
            self.assertIn("codex_runtime_contract_ref", payload["contract"])
            self.assertIn("codex_launch_supervision_contract", payload["contract"])
            self.assertIn("codex_recovery_contract", payload["contract"])
            self.assertIn("recovery_contract", payload["contract"])
            self.assertIn("gates", payload["validation"])
            self.assertIn("health", payload["validation"]["gates"])
            self.assertIn("install_later", payload["runtime_status"])
            self.assertIn("recovery_path", payload["runtime_status"])
            self.assertIn("installed_boot", payload["runtime_status"])
            self.assertIn("session_ownership", payload["runtime_status"])
            self.assertIn("appliance_platform", payload["runtime_status"])
            self.assertIn("state_root_usage", payload["runtime_status"])
            self.assertIn("codex_primary_runtime", payload["runtime_status"])
            self.assertIn("codex_persistent_state", payload["runtime_status"])
            self.assertIn("codex_runtime_contract", payload["runtime_status"])
            self.assertIn("codex_launch_supervision", payload["runtime_status"])
            self.assertIn("codex_recovery_to_codex", payload["runtime_status"])
            self.assertIn("installed_boot_to_codex", payload["runtime_status"])
            self.assertIn("codex_slot_transition_compatibility", payload["runtime_status"])
            self.assertIn("session_origin_compatibility", payload["runtime_status"])
            self.assertEqual(
                payload["contract"]["platform_reset_contract"]["platform_model"],
                "agentos_managed_appliance_os",
            )
            self.assertTrue(payload["contract"]["platform_reset_contract"]["state_partition_required"])

    def test_live_appliance_origin_is_managed_and_eligible(self) -> None:
        payload = evaluate_session_contract(
            runtime_ok=True,
            engine_status="PASS",
            policy_status="pass",
            broker_ok=True,
            broker_artifacts_ready=True,
            session_origin={
                "category": "live_appliance_boot",
                "interactive": True,
                "ssh_active": False,
                "session_entry": "live_appliance",
            },
            setup_state={"next_managed_entry": "setup_session"},
        )
        self.assertTrue(payload["managed_entry_eligible"])
        self.assertEqual(payload["active_mode"], "managed_mode")

    def test_installed_appliance_origin_is_managed_and_eligible(self) -> None:
        payload = evaluate_session_contract(
            runtime_ok=True,
            engine_status="PASS",
            policy_status="pass",
            broker_ok=True,
            broker_artifacts_ready=True,
            session_origin={
                "category": "installed_appliance_boot",
                "interactive": True,
                "ssh_active": False,
                "session_entry": "installed_appliance",
            },
            setup_state={"next_managed_entry": "ai_shell"},
        )
        self.assertTrue(payload["managed_entry_eligible"])
        self.assertEqual(payload["active_mode"], "managed_mode")


if __name__ == "__main__":
    unittest.main()
