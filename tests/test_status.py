from __future__ import annotations

import json
import io
import os
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
from pathlib import Path

import yaml

from status import run_status, status_report
from workspace.manager import WorkspaceManager


class StatusTests(unittest.TestCase):
    def _workspace_with_spec(self, spec: dict) -> str:
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        (root / "spec.yaml").write_text(yaml.dump(spec, sort_keys=False), encoding="utf-8")
        self.addCleanup(td.cleanup)
        return td.name

    def test_status_reports_fail_for_missing_binary(self):
        ws = self._workspace_with_spec(
            {
                "name": "status-test",
                "tools": {"bash": True, "file": True, "web": True},
                "kernel_engine": {
                    "provider": "codex",
                    "mode": "single",
                    "codex": {"command": "missing-codex-binary", "timeout_sec": 5, "model": ""},
                },
            }
        )

        wm = WorkspaceManager(ws)
        out = io.StringIO()
        with redirect_stdout(out):
            code = run_status(wm)

        self.assertEqual(code, 1)
        self.assertIn("Engine status: FAIL", out.getvalue())

    def test_status_prints_memory_count(self):
        ws = self._workspace_with_spec(
            {
                "name": "status-test",
                "tools": {"bash": True, "file": True, "web": True},
                "kernel_engine": {
                    "provider": "codex",
                    "mode": "single",
                    "codex": {"command": "missing-codex-binary", "timeout_sec": 5, "model": ""},
                },
            }
        )

        wm = WorkspaceManager(ws)
        out = io.StringIO()
        with redirect_stdout(out):
            run_status(wm)

        self.assertIn("Memory items:", out.getvalue())
        self.assertIn("Engine command:", out.getvalue())
        self.assertIn("Engine timeout sec:", out.getvalue())
        self.assertIn("Browser runtime:", out.getvalue())
        self.assertIn("Setup status:", out.getvalue())
        self.assertIn("Codex runtime contract:", out.getvalue())
        self.assertIn("Codex persistent state:", out.getvalue())
        self.assertIn("Codex launch supervision:", out.getvalue())
        self.assertIn("Recovery to Codex:", out.getvalue())
        self.assertIn("Inbox capability:", out.getvalue())
        self.assertIn("Inbox intake:", out.getvalue())
        self.assertIn("Telegram ingress:", out.getvalue())

    def test_status_json_output(self):
        ws = self._workspace_with_spec(
            {
                "name": "status-test",
                "tools": {"bash": True, "file": True, "web": True},
                "kernel_engine": {
                    "provider": "codex",
                    "mode": "single",
                    "codex": {"command": "missing-codex-binary", "timeout_sec": 5, "model": ""},
                },
            }
        )

        wm = WorkspaceManager(ws)
        out = io.StringIO()
        with patch("status._resolve_tty_path", return_value=""):
            with redirect_stdout(out):
                code = run_status(wm, as_json=True)

        payload = json.loads(out.getvalue().strip())
        self.assertEqual(code, 1)
        self.assertEqual(payload["engine_status"], "FAIL")
        self.assertEqual(payload["engine_reason"], "binary_not_found")
        self.assertEqual(payload["engine_command"], "missing-codex-binary")
        self.assertEqual(payload["engine_timeout_sec"], 5)
        self.assertEqual(payload["engine_model"], "")
        self.assertIn("browser_runtime", payload)
        self.assertIn("service_capability", payload)
        self.assertIn("permission_capability", payload)
        self.assertIn("inbox_capability", payload)
        self.assertIn("inbox_normalized_intake", payload)
        self.assertIn("telegram_ingress", payload)
        self.assertIn("execution_ownership", payload)
        self.assertIn("approval_counters", payload)
        self.assertIn("kernel_policy_ready", payload)
        self.assertFalse(payload["browser_runtime"]["configured"])
        self.assertFalse(payload["browser_runtime"]["runtime_enabled"])
        self.assertEqual(payload["browser_runtime"]["backend_requested"], "worker")
        self.assertEqual(payload["browser_runtime"]["backend_selected"], "worker")
        self.assertEqual(payload["browser_runtime"]["backend_fallback_reason"], "")
        self.assertEqual(payload["browser_runtime"]["policy_allowlist"], [])
        self.assertEqual(payload["browser_runtime"]["policy_denylist"], [])
        self.assertEqual(payload["browser_runtime"]["policy_current_url"], "")
        self.assertEqual(payload["browser_runtime"]["worker_timeout_sec"], 5)
        self.assertEqual(payload["browser_runtime"]["last_policy_decision"], "not_started")
        self.assertEqual(payload["browser_runtime"]["last_policy_reason"], "not_started")
        self.assertEqual(payload["approval_counters"]["requested"], 0)
        self.assertEqual(payload["approval_counters"]["approved"], 0)
        self.assertEqual(payload["approval_counters"]["denied"], 0)
        self.assertEqual(payload["approval_counters"]["blocked"], 0)
        self.assertFalse(payload["approval_counters"]["anomaly_detected"])
        self.assertEqual(payload["approval_counters"]["reason"], "")
        self.assertIn("overall_status", payload["kernel_policy_ready"])
        self.assertIn("ready_for_enforced_pilot", payload["kernel_policy_ready"])
        self.assertIn("setup_state", payload)
        self.assertEqual(payload["setup_state"]["status"], "pending")
        self.assertEqual(payload["setup_state"]["next_managed_entry"], "setup_session")
        self.assertIn("session_origin", payload)
        self.assertEqual(payload["session_origin"]["category"], "noninteractive")
        self.assertFalse(payload["session_origin"]["managed"])
        self.assertEqual(payload["session_origin_compatibility"]["path_family"], "fallback_or_unmanaged")
        self.assertIn("session_contract", payload)
        self.assertIn("session_start_contract", payload)
        self.assertIn("install_later", payload)
        self.assertIn("recovery_path", payload)
        self.assertIn("installed_boot", payload)
        self.assertIn("codex_primary_runtime", payload)
        self.assertIn("codex_persistent_state", payload)
        self.assertIn("codex_runtime_contract", payload)
        self.assertIn("codex_launch_supervision", payload)
        self.assertIn("codex_recovery_to_codex", payload)
        self.assertIn("installed_boot_to_codex", payload)
        self.assertIn("codex_slot_transition_compatibility", payload)
        self.assertIn("session_ownership", payload)
        self.assertIn("session_contract_validation", payload)
        self.assertIn("appliance_platform", payload)
        self.assertIn("state_root_usage", payload)
        self.assertEqual(payload["session_ownership"]["session_phase"], "setup_session")
        self.assertFalse(payload["install_later"]["available"])
        self.assertEqual(payload["install_later"]["target_origin"], "installed_appliance_boot")
        self.assertEqual(payload["recovery_path"]["label"], "AgentOS Recovery")
        self.assertFalse(payload["installed_boot"]["available"])
        self.assertEqual(payload["codex_primary_runtime"]["primary_runtime"], "codex_cli")
        self.assertEqual(payload["codex_primary_runtime"]["expected_provider"], "codex")
        self.assertFalse(payload["codex_primary_runtime"]["command_available"])
        self.assertEqual(payload["codex_runtime_contract"]["primary_runtime"], "codex_cli")
        self.assertEqual(payload["codex_runtime_contract"]["provider_contract"]["expected_provider"], "codex")
        self.assertEqual(
            payload["codex_runtime_contract"]["continuity_contract"]["rejoin_target"],
            "codex_cli_managed_session",
        )
        self.assertEqual(payload["codex_launch_supervision"]["restart_policy"], "on_failure")
        self.assertEqual(payload["codex_launch_supervision"]["runtime_owner"], "codex_cli_managed_session")
        self.assertEqual(payload["codex_persistent_state"]["runtime_owner"], "codex_cli_managed_session")
        self.assertEqual(payload["codex_recovery_to_codex"]["runtime_rejoin_target"], "codex_cli_managed_session")
        self.assertEqual(payload["installed_boot_to_codex"]["runtime_target"], "codex_cli_managed_session")
        self.assertEqual(payload["codex_slot_transition_compatibility"]["runtime_return_target"], "codex_cli_managed_session")
        self.assertIn("Codex CLI Managed Session", payload["codex_recovery_to_codex"]["detailed_rejoin_path"])
        self.assertEqual(
            payload["recovery_path"]["recommended_rejoin_summary"],
            ["AgentOS Recovery", "Return to AgentOS", "ai>"],
        )
        self.assertEqual(payload["appliance_platform"]["platform_model"], "agentos_managed_appliance_os")
        self.assertEqual(payload["appliance_platform"]["update_model"], "image_based_ab_updates")
        self.assertFalse(payload["state_root_usage"]["initialized"])
        self.assertEqual(payload["appliance_platform"]["active_slot"], "A")
        self.assertFalse(payload["appliance_platform"]["next_boot_exists"])
        self.assertIn("slot_recovery", payload["appliance_platform"])
        self.assertIn("next_boot_target", payload["appliance_platform"])
        self.assertTrue(payload["appliance_platform"]["system_images_read_only"])
        self.assertIn("system_image_layout_contract", payload["appliance_platform"])
        self.assertIn("image_release_identity", payload["appliance_platform"])
        self.assertEqual(payload["appliance_platform"]["image_release_identity"]["next_slot"], "B")
        self.assertIn("AgentOS Recovery", payload["recovery_path"]["recommended_rejoin_path"])
        self.assertIn("gates", payload["session_contract_validation"])
        self.assertIn("control_units", payload["service_capability"])
        self.assertIn("recent_permission_events", payload["permission_capability"]["evidence"])
        self.assertIn("message_count", payload["inbox_capability"]["summary"])
        self.assertIn("native_inbox_handled", payload["inbox_capability"]["summary"])
        self.assertIn("message_intake_count", payload["inbox_normalized_intake"]["summary"])
        self.assertIn("session_correlated", payload["inbox_normalized_intake"]["summary"])
        self.assertIn(payload["telegram_ingress"]["status"], {"ready", "watch"})
        self.assertIn("polling", payload["telegram_ingress"])
        self.assertIn("chat_policy", payload["telegram_ingress"])
        self.assertIn("bot_token", payload["telegram_ingress"])
        self.assertIn("native_capability_handler_count", payload["execution_ownership"]["summary"])

    def test_status_reports_setup_configured_when_env_exists(self):
        ws = self._workspace_with_spec(
            {
                "name": "status-test",
                "tools": {"bash": True, "file": True, "web": True},
                "kernel_engine": {
                    "provider": "codex",
                    "mode": "single",
                    "codex": {"command": "missing-codex-binary", "timeout_sec": 5, "model": ""},
                },
            }
        )
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        env_file = Path(td.name) / "agentos.env"
        env_file.write_text('AGENTOS_PROVIDER="ollama"\n', encoding="utf-8")

        wm = WorkspaceManager(ws)
        out = io.StringIO()
        old = os.environ.get("AGENTOS_ENV_FILE")
        os.environ["AGENTOS_ENV_FILE"] = str(env_file)
        self.addCleanup(
            lambda: os.environ.pop("AGENTOS_ENV_FILE", None)
            if old is None
            else os.environ.__setitem__("AGENTOS_ENV_FILE", old)
        )
        with redirect_stdout(out):
            run_status(wm)

        self.assertIn("Setup status: configured", out.getvalue())

    def test_status_reports_local_managed_tty_origin(self):
        ws = self._workspace_with_spec(
            {
                "name": "status-test",
                "tools": {"bash": True, "file": True, "web": True},
                "kernel_engine": {
                    "provider": "codex",
                    "mode": "single",
                    "codex": {"command": "missing-codex-binary", "timeout_sec": 5, "model": ""},
                },
            }
        )

        wm = WorkspaceManager(ws)
        out = io.StringIO()
        old_managed = os.environ.get("AGENTOS_SESSION_MANAGED")
        old_entry = os.environ.get("AGENTOS_SESSION_ENTRY")
        old_banner = os.environ.get("AGENTOS_SESSION_BANNER_VERSION")
        old_session_id = os.environ.get("AGENTOS_SESSION_ID")
        old_boot_id = os.environ.get("AGENTOS_BOOT_ID")
        os.environ["AGENTOS_SESSION_MANAGED"] = "1"
        os.environ["AGENTOS_SESSION_ENTRY"] = "local_tty1"
        os.environ["AGENTOS_SESSION_BANNER_VERSION"] = "phase49-v1"
        os.environ["AGENTOS_SESSION_ID"] = "agentos:tty1"
        os.environ["AGENTOS_BOOT_ID"] = "boot-42"
        self.addCleanup(
            lambda: os.environ.pop("AGENTOS_SESSION_MANAGED", None)
            if old_managed is None
            else os.environ.__setitem__("AGENTOS_SESSION_MANAGED", old_managed)
        )
        self.addCleanup(
            lambda: os.environ.pop("AGENTOS_SESSION_ENTRY", None)
            if old_entry is None
            else os.environ.__setitem__("AGENTOS_SESSION_ENTRY", old_entry)
        )
        self.addCleanup(
            lambda: os.environ.pop("AGENTOS_SESSION_BANNER_VERSION", None)
            if old_banner is None
            else os.environ.__setitem__("AGENTOS_SESSION_BANNER_VERSION", old_banner)
        )
        self.addCleanup(
            lambda: os.environ.pop("AGENTOS_SESSION_ID", None)
            if old_session_id is None
            else os.environ.__setitem__("AGENTOS_SESSION_ID", old_session_id)
        )
        self.addCleanup(
            lambda: os.environ.pop("AGENTOS_BOOT_ID", None)
            if old_boot_id is None
            else os.environ.__setitem__("AGENTOS_BOOT_ID", old_boot_id)
        )
        with redirect_stdout(out):
            run_status(wm)

        text = out.getvalue()
        self.assertIn("Session origin: local_managed_tty1", text)
        self.assertIn("Session path family: legacy_compatibility", text)
        self.assertIn("Install-later path: available=False", text)
        self.assertIn("Recovery path: AgentOS Recovery", text)
        self.assertIn("Installed boot:", text)
        self.assertIn("Codex primary runtime:", text)
        self.assertIn("Appliance platform: agentos_managed_appliance_os", text)
        self.assertIn("State root:", text)
        self.assertIn("Appliance slots: active=A, inactive=B, rollback=A", text)
        self.assertIn("Appliance rollback:", text)
        self.assertIn("summary=AgentOS Recovery -> Return to AgentOS -> ai>", text)
        self.assertIn("Session banner contract: phase49-v1", text)
        self.assertIn("Session ownership: phase=setup_session", text)
        self.assertIn("Session contract: status=", text)

    def test_status_report_live_appliance_origin(self):
        ws = self._workspace_with_spec(
            {
                "name": "status-live-appliance",
                "tools": {"bash": True, "file": True, "web": True},
                "kernel_engine": {
                    "provider": "codex",
                    "mode": "single",
                    "codex": {"command": "missing-codex-binary", "timeout_sec": 5, "model": ""},
                },
            }
        )

        wm = WorkspaceManager(ws)
        old_managed = os.environ.get("AGENTOS_SESSION_MANAGED")
        old_entry = os.environ.get("AGENTOS_SESSION_ENTRY")
        old_live = os.environ.get("AGENTOS_LIVE_APPLIANCE")
        os.environ["AGENTOS_SESSION_MANAGED"] = "1"
        os.environ["AGENTOS_SESSION_ENTRY"] = "live_appliance"
        os.environ["AGENTOS_LIVE_APPLIANCE"] = "1"
        self.addCleanup(
            lambda: os.environ.pop("AGENTOS_SESSION_MANAGED", None)
            if old_managed is None
            else os.environ.__setitem__("AGENTOS_SESSION_MANAGED", old_managed)
        )
        self.addCleanup(
            lambda: os.environ.pop("AGENTOS_SESSION_ENTRY", None)
            if old_entry is None
            else os.environ.__setitem__("AGENTOS_SESSION_ENTRY", old_entry)
        )
        self.addCleanup(
            lambda: os.environ.pop("AGENTOS_LIVE_APPLIANCE", None)
            if old_live is None
            else os.environ.__setitem__("AGENTOS_LIVE_APPLIANCE", old_live)
        )

        payload = status_report(wm)
        self.assertEqual(payload["session_origin"]["category"], "live_appliance_boot")
        self.assertTrue(payload["session_origin"]["live_appliance"])
        self.assertEqual(payload["session_origin_compatibility"]["path_family"], "appliance_first")
        self.assertEqual(payload["session_origin_compatibility"]["label"], "live_appliance")
        self.assertTrue(payload["install_later"]["available"])
        self.assertEqual(payload["install_later"]["source_origin"], "live_appliance_boot")
        self.assertEqual(payload["install_later"]["target_origin"], "installed_appliance_boot")
        self.assertEqual(payload["recovery_path"]["label"], "AgentOS Recovery")
        self.assertFalse(payload["installed_boot"]["available"])
        self.assertEqual(
            payload["install_later"]["post_install_identity_path"],
            ["AgentOS Setup", "AgentOS Managed Session", "ai>"],
        )
        self.assertEqual(payload["runtime_entry"]["preferred_origin"], "live_appliance_boot")

    def test_status_report_installed_appliance_origin(self):
        ws = self._workspace_with_spec(
            {
                "name": "status-installed-appliance",
                "tools": {"bash": True, "file": True, "web": True},
                "kernel_engine": {
                    "provider": "codex",
                    "mode": "single",
                    "codex": {"command": "missing-codex-binary", "timeout_sec": 5, "model": ""},
                },
            }
        )

        wm = WorkspaceManager(ws)
        old_managed = os.environ.get("AGENTOS_SESSION_MANAGED")
        old_entry = os.environ.get("AGENTOS_SESSION_ENTRY")
        old_installed = os.environ.get("AGENTOS_INSTALLED_APPLIANCE")
        os.environ["AGENTOS_SESSION_MANAGED"] = "1"
        os.environ["AGENTOS_SESSION_ENTRY"] = "installed_appliance"
        os.environ["AGENTOS_INSTALLED_APPLIANCE"] = "1"
        self.addCleanup(
            lambda: os.environ.pop("AGENTOS_SESSION_MANAGED", None)
            if old_managed is None
            else os.environ.__setitem__("AGENTOS_SESSION_MANAGED", old_managed)
        )
        self.addCleanup(
            lambda: os.environ.pop("AGENTOS_SESSION_ENTRY", None)
            if old_entry is None
            else os.environ.__setitem__("AGENTOS_SESSION_ENTRY", old_entry)
        )
        self.addCleanup(
            lambda: os.environ.pop("AGENTOS_INSTALLED_APPLIANCE", None)
            if old_installed is None
            else os.environ.__setitem__("AGENTOS_INSTALLED_APPLIANCE", old_installed)
        )

        payload = status_report(wm)
        self.assertEqual(payload["session_origin"]["category"], "installed_appliance_boot")
        self.assertTrue(payload["session_origin"]["installed_appliance"])
        self.assertEqual(payload["session_origin_compatibility"]["path_family"], "appliance_first")
        self.assertEqual(payload["session_origin_compatibility"]["label"], "installed_appliance")
        self.assertFalse(payload["install_later"]["available"])
        self.assertEqual(payload["install_later"]["current_install_path"], "installed_appliance_boot")
        self.assertEqual(payload["recovery_path"]["label"], "AgentOS Recovery")
        self.assertTrue(payload["installed_boot"]["available"])
        self.assertEqual(payload["runtime_entry"]["preferred_installed_origin"], "installed_appliance_boot")
        self.assertTrue(payload["installed_boot"]["available"])
        self.assertEqual(payload["installed_boot"]["origin"], "installed_appliance_boot")


if __name__ == "__main__":
    unittest.main()
