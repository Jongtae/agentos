from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = ROOT_DIR / "scripts" / "kernel_workflow_status.py"
KERNELCTL = ROOT_DIR / "scripts" / "agentos-kernelctl"


class WorkflowStatusTests(unittest.TestCase):
    def _workspace(self) -> Path:
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        workspace = Path(td.name) / "workspace"
        (workspace / "documents").mkdir(parents=True, exist_ok=True)
        (workspace / "artifacts" / "capability-substrate").mkdir(parents=True, exist_ok=True)
        (workspace / "documents" / "agentos-first-run.md").write_text("# First run\n", encoding="utf-8")
        (workspace / "spec.yaml").write_text(
            "name: workflow-status-test\n"
            "tools:\n"
            "  bash: true\n"
            "  file: true\n"
            "  web: true\n",
            encoding="utf-8",
        )
        return workspace

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        for key in list(env):
            if key.startswith("AGENTOS_TELEGRAM_") or key.startswith("TELEGRAM_") or key == "AGENTOS_ENV_FILE":
                env.pop(key, None)
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        env["HOME"] = td.name
        return env

    def test_workflow_status_shape_and_external_secret_gate(self) -> None:
        workspace = self._workspace()
        proc = subprocess.run(
            [str(SCRIPT), "--workspace", str(workspace), "--json"],
            cwd=ROOT_DIR,
            env=self._env(),
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(proc.stdout)

        self.assertEqual(payload["schema_version"], "agentos-workflow-status.v1")
        self.assertEqual(payload["capability"], "workflow_status")
        self.assertTrue(payload["guided_operator_surface_reachable"])
        self.assertIn("top_tasks", payload)
        self.assertIn("workflows", payload)
        self.assertEqual(
            [workflow["workflow_id"] for workflow in payload["workflows"]],
            [
                "research_request_response",
                "inbox_triage_summary_response",
                "telegram_thread_continuity",
                "inbox_reply_workflow",
                "research_brief_response",
                "live_telegram_reply_send",
            ],
        )
        self.assertTrue(payload["summary"]["workflow_status_ready"])
        self.assertTrue(payload["summary"]["external_secret_blocked"])
        self.assertFalse(payload["summary"]["telegram_thread_continuity_ready"])
        self.assertFalse(payload["summary"]["inbox_reply_workflow_ready"])
        self.assertFalse(payload["summary"]["research_brief_ready"])
        self.assertFalse(payload["summary"]["brief_artifact_exported"])
        self.assertFalse(payload["summary"]["telegram_polling_attempted"])
        self.assertFalse(payload["summary"]["telegram_webhook_update_received"])
        self.assertFalse(payload["summary"]["telegram_webhook_search_success"])
        self.assertFalse(payload["summary"]["telegram_live_update_received"])
        self.assertFalse(payload["summary"]["telegram_live_search_success"])
        self.assertFalse(payload["summary"]["telegram_update_offset_persisted"])
        self.assertFalse(payload["summary"]["telegram_reply_sent"])
        self.assertEqual(payload["runtime_secret_readiness"]["telegram_secret_source"], "none")
        self.assertFalse(payload["runtime_secret_readiness"]["telegram_token_configured"])
        self.assertFalse(payload["runtime_secret_readiness"]["telegram_allowed_chat_configured"])
        self.assertFalse(payload["runtime_secret_readiness"]["telegram_live_send_ready"])
        self.assertTrue(any("agentos-telegram-webhookd.service" in item for item in payload["next_actions"]))
        self.assertTrue(any("telegram-live-loop" in item for item in payload["next_actions"]))
        self.assertTrue(any("telegram-thread-status" in item for item in payload["next_actions"]))
        self.assertTrue(any("inbox-reply-workflow" in item for item in payload["next_actions"]))
        self.assertTrue(any("research-brief" in item for item in payload["next_actions"]))

    def test_workflow_status_reads_stage70_72_artifacts(self) -> None:
        workspace = self._workspace()
        artifact_dir = workspace / "artifacts" / "capability-substrate"
        (artifact_dir / "latest-telegram-thread-status.json").write_text(
            json.dumps({"telegram_thread_continuity_ready": True}) + "\n",
            encoding="utf-8",
        )
        (artifact_dir / "latest-inbox-reply-workflow.json").write_text(
            json.dumps({"inbox_reply_workflow_ready": True}) + "\n",
            encoding="utf-8",
        )
        (artifact_dir / "latest-research-brief-response.json").write_text(
            json.dumps(
                {
                    "research_brief_ready": True,
                    "internal_web_query_success": True,
                    "brief_artifact_exported": True,
                    "telegram_reply_ready": True,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (artifact_dir / "latest-telegram-live-loop.json").write_text(
            json.dumps(
                {
                    "summary": {
                        "telegram_polling_attempted": True,
                        "telegram_live_update_received": True,
                        "telegram_live_message_routed": True,
                        "telegram_live_search_success": True,
                        "telegram_update_offset_persisted": True,
                        "telegram_reply_sent": True,
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )

        proc = subprocess.run(
            [str(SCRIPT), "--workspace", str(workspace), "--json"],
            cwd=ROOT_DIR,
            env=self._env(),
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(proc.stdout)

        self.assertTrue(payload["summary"]["telegram_thread_continuity_ready"])
        self.assertTrue(payload["summary"]["inbox_reply_workflow_ready"])
        self.assertTrue(payload["summary"]["research_brief_ready"])
        self.assertTrue(payload["summary"]["brief_artifact_exported"])
        self.assertIn("telegram_thread_continuity", payload["summary"]["ready_workflows"])
        self.assertIn("inbox_reply_workflow", payload["summary"]["ready_workflows"])
        self.assertIn("research_brief_response", payload["summary"]["ready_workflows"])
        self.assertIn("live_telegram_reply_send", payload["summary"]["ready_workflows"])
        self.assertTrue(payload["summary"]["telegram_polling_attempted"])
        self.assertTrue(payload["summary"]["telegram_live_update_received"])
        self.assertTrue(payload["summary"]["telegram_live_message_routed"])
        self.assertTrue(payload["summary"]["telegram_live_search_success"])
        self.assertTrue(payload["summary"]["telegram_update_offset_persisted"])
        self.assertTrue(payload["summary"]["telegram_reply_sent"])

    def test_workflow_status_reads_webhook_artifact_as_live_reply(self) -> None:
        workspace = self._workspace()
        artifact_dir = workspace / "artifacts" / "capability-substrate"
        (artifact_dir / "latest-telegram-webhookd.json").write_text(
            json.dumps(
                {
                    "summary": {
                        "telegram_webhook_update_received": True,
                        "telegram_webhook_message_routed": True,
                        "telegram_webhook_search_success": True,
                        "telegram_reply_sent": True,
                        "telegram_update_offset_persisted": True,
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )

        proc = subprocess.run(
            [str(SCRIPT), "--workspace", str(workspace), "--json"],
            cwd=ROOT_DIR,
            env=self._env(),
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(proc.stdout)

        self.assertIn("live_telegram_reply_send", payload["summary"]["ready_workflows"])
        self.assertTrue(payload["summary"]["telegram_webhook_update_received"])
        self.assertTrue(payload["summary"]["telegram_webhook_message_routed"])
        self.assertTrue(payload["summary"]["telegram_webhook_search_success"])
        self.assertFalse(payload["summary"]["telegram_polling_attempted"])
        self.assertTrue(payload["summary"]["telegram_update_offset_persisted"])
        self.assertTrue(payload["summary"]["telegram_reply_sent"])
        live_workflow = next(item for item in payload["workflows"] if item["workflow_id"] == "live_telegram_reply_send")
        self.assertEqual(live_workflow["native_default"], "telegram_webhook_internal_web_send_message")
        self.assertIn("agentos-telegram-webhookd.service", live_workflow["command_hint"])

    def test_validate_roundtrip_and_kernelctl_surface(self) -> None:
        workspace = self._workspace()
        out = workspace / "workflow-status.json"
        subprocess.run(
            [str(KERNELCTL), "workflow-status", "--workspace", str(workspace), "--output", str(out), "--json"],
            cwd=ROOT_DIR,
            env=self._env(),
            check=True,
            capture_output=True,
            text=True,
        )
        validate = subprocess.run(
            [str(SCRIPT), "--validate", str(out), "--json"],
            cwd=ROOT_DIR,
            env=self._env(),
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(validate.stdout), {"ok": True, "errors": [], "schema_version": "agentos-workflow-status.v1"})


if __name__ == "__main__":
    unittest.main()
