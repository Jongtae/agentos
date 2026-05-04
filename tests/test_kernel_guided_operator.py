from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_guided_operator.py"
KERNELCTL = ROOT_DIR / "scripts" / "agentos-kernelctl"
if str(ROOT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "src"))
if str(ROOT_DIR / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "scripts"))

from kernel_guided_operator import build_payload, validate_payload
from workspace.manager import WorkspaceManager


class KernelGuidedOperatorTests(unittest.TestCase):
    def _workspace(self) -> str:
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        (root / "documents").mkdir(parents=True, exist_ok=True)
        (root / "data").mkdir(parents=True, exist_ok=True)
        (root / "documents" / "agentos-first-run.md").write_text("# First run\n", encoding="utf-8")
        (root / "spec.yaml").write_text(
            yaml.dump(
                {
                    "name": "guided-operator-test",
                    "tools": {"bash": True, "file": True, "web": True},
                    "kernel_engine": {
                        "provider": "ollama",
                        "mode": "single",
                        "ollama": {
                            "command": "missing-ollama-binary",
                            "timeout_sec": 10,
                            "model": "smollm2:135m-instruct-q5_K_M",
                        },
                    },
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        self.addCleanup(td.cleanup)
        return td.name

    def _build_payload_with_status_report(self, report_overrides: dict) -> dict:
        wm = WorkspaceManager(self._workspace())
        import kernel_guided_operator as module

        original_status_report = module.status_report
        base_report = {
            "workspace": str(wm.workspace_dir),
            "kernel_engine_provider": "ollama",
            "checked_provider": "ollama",
            "engine_model": "smollm2:135m-instruct-q5_K_M",
            "engine_status": "PASS",
            "tools_enabled": ["bash", "file", "web"],
            "inbox_capability": {"summary": {"inbox_execution_ready": True}},
            "telegram_ingress": {
                "summary": {
                    "ingress_ready": True,
                    "polling_enabled": True,
                    "bot_token_configured": True,
                    "poll_interval_sec": 30,
                    "messages_visible": 2,
                    "threads_visible": 1,
                    "visibility_label": "telegram inbox",
                }
            },
            "recovery_path": {},
            "session_origin": {"category": ""},
            "setup_state": {"next_managed_entry": ""},
            "user_space_sovereignty": {"summary": {"priority_actions": []}},
            "operator_mode": {"current_mode": "", "recommended_surface": ""},
        }
        base_report.update(report_overrides)

        module.status_report = lambda _workspace: base_report
        try:
            return build_payload(wm)
        finally:
            module.status_report = original_status_report

    def test_build_payload_exports_contract_shape(self) -> None:
        wm = WorkspaceManager(self._workspace())
        payload = build_payload(wm)
        self.assertEqual(payload["schema_version"], "agentos-guided-operator-surface.v1")
        self.assertEqual(payload["task_vocabulary_version"], "agentos-task-centric-runtime.v1")
        self.assertEqual(payload["state_summary_version"], "agentos-state-summary.v1")
        self.assertTrue(payload["guided_operator_surface_reachable"])
        self.assertEqual(payload["runtime_entry_mode"], "noninteractive")
        self.assertTrue(payload["workspace_writable"])
        self.assertTrue(payload["recovery_affordance_visible"])
        self.assertEqual(
            [item["label"] for item in payload["top_tasks"]],
            [
                "Ask",
                "Open Document",
                "Fetch Web",
                "Review Inbox",
                "Export Proof",
                "Recover / Rejoin",
                "Ask from Telegram",
                "Search and Reply",
                "Review Telegram ingress status",
            ],
        )
        self.assertEqual(
            [item["id"] for item in payload["top_tasks"]],
            [
                "ask",
                "open_document",
                "fetch_web",
                "review_inbox",
                "export_proof",
                "recover_rejoin",
                "ask_from_telegram",
                "search_and_reply",
                "review_telegram_ingress",
            ],
        )
        self.assertEqual(
            [item["task_kind"] for item in payload["top_tasks"]],
            [
                "ask",
                "document",
                "web",
                "inbox",
                "proof",
                "recovery",
                "telegram_ask",
                "telegram_search_reply",
                "telegram_ingress_status",
            ],
        )
        self.assertEqual(
            [item["surface"] for item in payload["top_tasks"]],
            [
                "managed_session",
                "document_access",
                "web_access",
                "inbox_workflow",
                "proof_export",
                "recovery_path",
                "telegram_ask",
                "research_workflow",
                "telegram_ingress_status",
            ],
        )
        self.assertEqual(
            [item["execution_mode"] for item in payload["top_tasks"]],
            [
                "managed_interactive",
                "tool_call",
                "tool_call",
                "tool_call",
                "tool_call",
                "tool_call",
                "managed_interactive",
                "tool_call",
                "tool_call",
            ],
        )
        self.assertEqual(payload["top_tasks"][0]["handoff"]["target_surface"], "managed_session")
        self.assertEqual(payload["top_tasks"][0]["handoff"]["managed_runtime_target"], "codex_cli_managed_session")
        self.assertEqual(payload["top_tasks"][0]["handoff"]["continuity"], "same_workspace")
        self.assertEqual(payload["top_tasks"][1]["handoff"]["target_surface"], "document_access")
        self.assertEqual(payload["top_tasks"][2]["handoff"]["target_surface"], "web_access")
        self.assertEqual(payload["top_tasks"][5]["handoff"]["continuity"], "rejoin_path")
        self.assertEqual(payload["recovery_affordance"]["label"], "AgentOS Recovery")
        self.assertEqual(payload["recovery_affordance"]["rejoin_target"], "setup_session")
        self.assertEqual(payload["recovery_affordance"]["runtime_rejoin_target"], "codex_cli_managed_session")
        self.assertEqual(payload["recovery_affordance"]["default_action_label"], "Return to AgentOS")
        self.assertEqual(payload["recovery_affordance"]["default_action_command"], "agentos-kernelctl runtime-entry --json")
        self.assertIn("safe shell", payload["recovery_affordance"]["description"])
        self.assertTrue(payload["recovery_affordance"]["entry_points"])
        self.assertEqual(
            [item["status"] for item in payload["top_tasks"]],
            ["ready" if item["ready"] else "blocked" for item in payload["top_tasks"]],
        )
        self.assertEqual(payload["top_tasks"][0]["command_argv"][:2], ["agentos-shell", "--workspace"])
        self.assertEqual(payload["top_tasks"][0]["command_argv"][-1], "--managed-runtime")
        self.assertEqual(
            payload["top_tasks"][0]["command_hint"],
            f"agentos-shell --workspace {wm.workspace_dir} --managed-runtime",
        )
        self.assertEqual(
            payload["top_tasks"][1]["command_hint"],
            f"agentos-kernelctl document-access --workspace {wm.workspace_dir} --path documents/agentos-first-run.md --json",
        )
        self.assertEqual(
            payload["top_tasks"][2]["command_hint"],
            f"agentos-kernelctl web-access --workspace {wm.workspace_dir} --url https://example.com --json",
        )
        self.assertEqual(
            payload["top_tasks"][3]["command_hint"],
            f"agentos-kernelctl inbox-workflow --workspace {wm.workspace_dir} --json",
        )
        self.assertEqual(payload["top_tasks"][3]["handoff"]["target_surface"], "inbox_workflow")
        self.assertIn("agentos-shell --workspace", payload["top_tasks"][6]["command_hint"])
        self.assertIn("--telegram-ask", payload["top_tasks"][6]["command_hint"])
        self.assertIn("agentos-kernelctl research-workflow", payload["top_tasks"][7]["command_hint"])
        self.assertIn("--message-text 'search agentos roadmap'", payload["top_tasks"][7]["command_hint"])
        self.assertEqual(payload["top_tasks"][7]["handoff"]["target_surface"], "research_workflow")
        self.assertEqual(payload["top_tasks"][7]["handoff"]["launch_mode"], "tool_call")
        self.assertIn("agentos-shell --workspace", payload["top_tasks"][8]["command_hint"])
        self.assertIn("--telegram-ingress-status", payload["top_tasks"][8]["command_hint"])
        self.assertEqual(payload["top_tasks"][2]["command_input"]["required"], ["url"])
        self.assertIn("task_readiness_hint", payload)
        self.assertIn("state_summary", payload)
        self.assertEqual(payload["state_summary"]["schema_version"], "agentos-state-summary.v1")
        self.assertEqual(payload["state_summary"]["operator_visible_state"], payload["state"])
        self.assertEqual(payload["state_summary"]["runtime_entry_mode"], payload["runtime_entry_mode"])
        self.assertEqual(payload["state_summary"]["session_origin"], payload["operator_context"]["session_origin"])
        self.assertEqual(payload["state_summary"]["next_managed_entry"], payload["operator_context"]["next_managed_entry"])
        self.assertEqual(payload["state_summary"]["workspace_writable"], payload["workspace_writable"])
        self.assertEqual(payload["runtime_summary"]["telegram_ingress_ready"], True)
        self.assertEqual(payload["state_summary"]["telegram_ingress_ready"], True)
        self.assertEqual(payload["task_readiness_hint"]["telegram_ingress_ready"], True)
        self.assertIsInstance(payload["runtime_summary"]["telegram_messages_visible"], int)
        self.assertIsInstance(payload["state_summary"]["telegram_threads_visible"], int)
        self.assertIsInstance(payload["task_readiness_hint"]["telegram_poll_interval_sec"], int)
        self.assertEqual(payload["task_vocabulary"]["execution_modes"][0], "managed_interactive")
        self.assertEqual(
            payload["task_vocabulary"]["telegram_task_kinds"],
            ["telegram_ask", "telegram_search_reply", "telegram_ingress_status"],
        )
        self.assertEqual(
            payload["task_vocabulary"]["telegram_task_ids"],
            ["ask_from_telegram", "search_and_reply", "review_telegram_ingress"],
        )
        self.assertIn(payload["state"], {"runtime_ready", "provider_unavailable"})
        self.assertEqual(validate_payload(payload), [])

    def test_build_payload_derives_top_task_success(self) -> None:
        payload = self._build_payload_with_status_report(
            {"engine_status": "FAIL", "setup_state": {"next_managed_entry": "runtime-entry"}}
        )
        top_task_success = all(task["status"] == "ready" for task in payload["top_tasks"])
        self.assertFalse(top_task_success)
        self.assertIn(payload["state"], {"provider_unavailable", "workspace_blocked", "proof_export_unavailable", "runtime_degraded"})
        self.assertEqual(top_task_success, payload["state"] == "runtime_ready")

    def test_build_payload_reflects_telegram_ingress_summary(self) -> None:
        payload = self._build_payload_with_status_report(
            {
                "telegram_ingress": {
                    "summary": {
                        "ingress_ready": False,
                        "polling_enabled": False,
                        "bot_token_configured": False,
                        "poll_interval_sec": 0,
                        "messages_visible": 0,
                        "threads_visible": 0,
                        "visibility_label": "telegram disabled",
                    },
                }
            }
        )
        self.assertFalse(payload["state_summary"]["telegram_ingress_ready"])
        self.assertEqual(payload["state_summary"]["telegram_ingress_visibility_label"], "telegram disabled")
        ask_task = next(
            task for task in payload["top_tasks"] if task["id"] == "ask_from_telegram"
        )
        search_task = next(
            task for task in payload["top_tasks"] if task["id"] == "search_and_reply"
        )
        self.assertFalse(ask_task["ready"])
        self.assertFalse(search_task["ready"])

    def test_recovery_visibility_controls_recover_task_readiness(self) -> None:
        hidden_recovery = self._build_payload_with_status_report(
            {"engine_status": "PASS", "recovery_path": {}, "user_space_sovereignty": {"summary": {"priority_actions": []}}}
        )
        self.assertFalse(hidden_recovery["recovery_affordance_visible"])
        self.assertFalse(hidden_recovery["recovery_affordance"]["visible"])
        self.assertEqual(
            hidden_recovery["state_summary"]["recovery_path_available"],
            hidden_recovery["recovery_affordance_visible"],
        )
        hidden_recovery_task = next(
            task for task in hidden_recovery["top_tasks"] if task["id"] == "recover_rejoin"
        )
        self.assertFalse(hidden_recovery_task["ready"])

        visible_recovery = self._build_payload_with_status_report(
            {
                "engine_status": "PASS",
                "recovery_path": {
                    "label": "Rejoin Path",
                    "recommended_rejoin_path": ["recovery", "managed_runtime"],
                },
                "user_space_sovereignty": {"summary": {"priority_actions": []}},
            }
        )
        self.assertTrue(visible_recovery["recovery_affordance_visible"])
        self.assertTrue(visible_recovery["recovery_affordance"]["visible"])
        self.assertEqual(
            visible_recovery["state_summary"]["recovery_path_available"],
            visible_recovery["recovery_affordance_visible"],
        )
        visible_recovery_task = next(
            task for task in visible_recovery["top_tasks"] if task["id"] == "recover_rejoin"
        )
        self.assertTrue(visible_recovery_task["ready"])
        self.assertEqual(visible_recovery["recovery_affordance"]["rejoin_target"], "")

    def test_build_payload_reports_tty_managed_entry(self) -> None:
        wm = WorkspaceManager(self._workspace())
        old_managed = os.environ.get("AGENTOS_SESSION_MANAGED")
        old_entry = os.environ.get("AGENTOS_SESSION_ENTRY")
        os.environ["AGENTOS_SESSION_MANAGED"] = "1"
        os.environ["AGENTOS_SESSION_ENTRY"] = "local_tty1"
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
        payload = build_payload(wm)
        self.assertEqual(payload["runtime_entry_mode"], "tty")
        self.assertEqual(payload["state_summary"]["session_origin"], "local_managed_tty1")
        self.assertEqual(payload["operator_context"]["session_origin"], "local_managed_tty1")
        self.assertEqual(payload["state_summary"]["runtime_entry_mode"], payload["runtime_entry_mode"])

    def test_cli_validate_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "guided-operator.json"
            subprocess.run(
                ["python3", str(SCRIPT), "--workspace", self._workspace(), "--output", str(out)],
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

    def test_kernelctl_guided_operator_json(self) -> None:
        env = os.environ.copy()
        env["AGENTOS_SESSION_MANAGED"] = "1"
        env["AGENTOS_SESSION_ENTRY"] = "local_tty1"
        result = subprocess.run(
            [str(KERNELCTL), "guided-operator", "--workspace", self._workspace(), "--json"],
            cwd=ROOT_DIR,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        payload = json.loads(result.stdout)
        self.assertTrue(payload["guided_operator_surface_reachable"])
        self.assertEqual(payload["runtime_entry_mode"], "tty")
        self.assertIn("runtime_summary", payload)
        self.assertIn("state_summary", payload)
        self.assertEqual(payload["state_summary"]["runtime_entry_mode"], payload["runtime_entry_mode"])
        self.assertEqual(payload["state_summary"]["session_origin"], "local_managed_tty1")
        self.assertEqual(payload["operator_context"]["session_origin"], "local_managed_tty1")
        self.assertEqual(payload["top_tasks"][0]["handoff"]["target_surface"], "managed_session")
        self.assertEqual(payload["top_tasks"][0]["handoff"]["managed_runtime_target"], "codex_cli_managed_session")
        self.assertIn("recovery_affordance", payload)
        self.assertEqual(payload["task_vocabulary"]["baseline_task_kinds"], ["ask", "document", "web", "inbox", "proof", "recovery"])
        self.assertEqual(
            payload["task_vocabulary"]["telegram_task_kinds"],
            ["telegram_ask", "telegram_search_reply", "telegram_ingress_status"],
        )


if __name__ == "__main__":
    unittest.main()
