from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel.runtime.checkpoint_saver import JsonCheckpointSaver


class CheckpointSaverTests(unittest.TestCase):
    def test_save_and_load_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "cp" / "agent_runner.json"
            saver = JsonCheckpointSaver(path)
            saver.save_checkpoint({"status": "running", "run_id": "r1"})
            payload = saver.load_checkpoint()
            self.assertEqual(payload["status"], "running")
            self.assertEqual(payload["run_id"], "r1")

    def test_load_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            saver = JsonCheckpointSaver(Path(td) / "missing.json")
            self.assertIsNone(saver.load_checkpoint())

    def test_load_invalid_json_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "cp.json"
            path.write_text("{invalid json", encoding="utf-8")
            saver = JsonCheckpointSaver(path)
            self.assertIsNone(saver.load_checkpoint())


if __name__ == "__main__":
    unittest.main()
