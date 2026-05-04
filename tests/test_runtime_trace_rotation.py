from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kernel.runtime.trace import RuntimeTraceWriter, runtime_trace_max_bytes


class RuntimeTraceRotationTests(unittest.TestCase):
    def test_rotates_to_archive_when_size_exceeds_threshold(self):
        with tempfile.TemporaryDirectory() as td:
            trace = Path(td) / "runtime_trace.jsonl"
            trace.write_text("x" * 200, encoding="utf-8")

            writer = RuntimeTraceWriter(path=trace, enabled=True, max_bytes=64)
            writer.emit("run_start", {"v": 1})

            archive = Path(td) / "runtime_trace.jsonl.1"
            self.assertTrue(archive.exists())
            self.assertTrue(trace.exists())
            self.assertLess(trace.stat().st_size, archive.stat().st_size)
            line = trace.read_text(encoding="utf-8").strip()
            obj = json.loads(line)
            self.assertEqual(obj["event"], "run_start")

    def test_no_rotation_when_under_threshold(self):
        with tempfile.TemporaryDirectory() as td:
            trace = Path(td) / "runtime_trace.jsonl"
            writer = RuntimeTraceWriter(path=trace, enabled=True, max_bytes=1024)
            writer.emit("run_start", {})
            self.assertFalse((Path(td) / "runtime_trace.jsonl.1").exists())

    def test_runtime_trace_max_bytes_env_parsing(self):
        with patch.dict(os.environ, {"AGENTOS_RUNTIME_TRACE_MAX_BYTES": "2048"}, clear=True):
            self.assertEqual(runtime_trace_max_bytes(0), 2048)
        with patch.dict(os.environ, {"AGENTOS_RUNTIME_TRACE_MAX_BYTES": "bad"}, clear=True):
            self.assertEqual(runtime_trace_max_bytes(123), 123)


if __name__ == "__main__":
    unittest.main()
