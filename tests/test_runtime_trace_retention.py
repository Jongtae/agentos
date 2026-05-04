from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from kernel.runtime.retention import (
    apply_trace_retention,
    is_path_within_dir,
    plan_trace_retention,
    retention_health_summary,
    retention_policy_from_env,
)


class RuntimeTraceRetentionTests(unittest.TestCase):
    def test_plan_prefers_age_and_keep_rules(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            trace = root / "runtime_trace.jsonl"
            a1 = root / "runtime_trace.jsonl.1"
            a2 = root / "runtime_trace.jsonl.2"
            a3 = root / "runtime_trace.jsonl.3"

            trace.write_text("", encoding="utf-8")
            a1.write_text("a1", encoding="utf-8")
            a2.write_text("a2", encoding="utf-8")
            a3.write_text("a3", encoding="utf-8")

            now = datetime.now(timezone.utc)
            os.utime(a1, (now.timestamp(), now.timestamp()))
            old = now - timedelta(days=10)
            mid = now - timedelta(days=2)
            os.utime(a2, (mid.timestamp(), mid.timestamp()))
            os.utime(a3, (old.timestamp(), old.timestamp()))

            actions = plan_trace_retention(trace, retention_days=7, keep_archives=1, now=now)
            action_map = {Path(a.path).name: a.reason for a in actions}
            self.assertEqual(action_map.get("runtime_trace.jsonl.2"), "exceeds_keep_archives")
            self.assertEqual(action_map.get("runtime_trace.jsonl.3"), "older_than_retention_days")
            self.assertNotIn("runtime_trace.jsonl.1", action_map)

    def test_apply_retention_deletes_files(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "runtime_trace.jsonl.1"
            p.write_text("x", encoding="utf-8")
            actions = plan_trace_retention(Path(td) / "runtime_trace.jsonl", retention_days=0, keep_archives=0)
            summary = apply_trace_retention(actions, apply=True)
            self.assertEqual(summary["deleted"], 1)
            self.assertFalse(p.exists())

    def test_cli_rejects_trace_outside_workspace_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            artifacts = workspace / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            outside = Path(td) / "outside.jsonl"
            outside.write_text("", encoding="utf-8")

            proc = subprocess.run(
                [
                    "python3",
                    "scripts/runtime_trace_retention.py",
                    "--workspace",
                    str(workspace),
                    "--trace-file",
                    str(outside),
                    "--dry-run",
                ],
                cwd=str(Path(__file__).resolve().parents[1]),
                env={
                    **os.environ,
                    "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
                },
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 1)
            payload = json.loads(proc.stdout.strip())
            self.assertEqual(payload["error"], "trace_file_must_be_within_workspace_artifacts")

    def test_is_path_within_dir(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            child = root / "a" / "b"
            child.mkdir(parents=True)
            self.assertTrue(is_path_within_dir(child, root))
            self.assertFalse(is_path_within_dir(Path("/tmp"), child))

    def test_retention_policy_from_env_parsing(self):
        with patch.dict(
            os.environ,
            {"AGENTOS_TRACE_RETENTION_DAYS": "9", "AGENTOS_TRACE_KEEP_ARCHIVES": "2"},
            clear=False,
        ):
            policy = retention_policy_from_env(default_days=7, default_keep_archives=1)
            self.assertEqual(policy["retention_days"], 9)
            self.assertEqual(policy["keep_archives"], 2)

    def test_retention_health_summary(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            trace = root / "runtime_trace.jsonl"
            trace.write_text("", encoding="utf-8")
            a1 = root / "runtime_trace.jsonl.1"
            a2 = root / "runtime_trace.jsonl.2"
            a1.write_text("a1", encoding="utf-8")
            a2.write_text("a2", encoding="utf-8")
            time.sleep(0.01)
            now = datetime.now(timezone.utc)
            old = now - timedelta(days=11)
            os.utime(a2, (old.timestamp(), old.timestamp()))

            summary = retention_health_summary(trace, retention_days=7, keep_archives=1, now=now)
            self.assertIn("policy", summary)
            self.assertEqual(summary["policy"]["retention_days"], 7)
            self.assertEqual(summary["archive_count"], 2)
            self.assertGreaterEqual(summary["pending_delete_count"], 1)


if __name__ == "__main__":
    unittest.main()
