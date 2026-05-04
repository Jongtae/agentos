from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
KERNELCTL = ROOT_DIR / "scripts" / "agentos-kernelctl"
SCRIPT = ROOT_DIR / "scripts" / "kernel_telegram_thread_status.py"


class TelegramThreadStatusTests(unittest.TestCase):
    def test_thread_context_links_follow_up(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            workspace.mkdir(parents=True)
            first = subprocess.run(
                [
                    str(KERNELCTL),
                    "telegram-thread-status",
                    "--workspace",
                    str(workspace),
                    "--message-text",
                    "search agentos roadmap",
                    "--chat-id",
                    "1001",
                    "--request-id",
                    "r1",
                    "--json",
                ],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
            second = subprocess.run(
                [
                    str(KERNELCTL),
                    "telegram-thread-status",
                    "--workspace",
                    str(workspace),
                    "--message-text",
                    "summarize that",
                    "--chat-id",
                    "1001",
                    "--request-id",
                    "r2",
                    "--follow-up",
                    "--json",
                ],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
            first_payload = json.loads(first.stdout)
            second_payload = json.loads(second.stdout)

        self.assertTrue(first_payload["first_request_created"])
        self.assertTrue(second_payload["follow_up_linked"])
        self.assertTrue(second_payload["rejoin_lookup_succeeded"])
        self.assertTrue(second_payload["telegram_thread_continuity_ready"])
        self.assertEqual(second_payload["previous_context"]["request_id"], "r1")

    def test_validate_reports_success(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            out = Path(td) / "thread.json"
            subprocess.run(
                [str(SCRIPT), "--workspace", str(workspace), "--chat-id", "1001", "--request-id", "r1", "--output", str(out)],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
            proc = subprocess.run(
                [str(SCRIPT), "--validate", str(out), "--json"],
                cwd=ROOT_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
        self.assertTrue(json.loads(proc.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
