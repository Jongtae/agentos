from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from io_utils import scrub_payload, scrub_sensitive_text, write_json_file


class IoUtilsScrubTests(unittest.TestCase):
    def test_scrub_sensitive_text_masks_openai_env_value(self):
        old = os.environ.get("OPENAI_API_KEY")
        try:
            os.environ["OPENAI_API_KEY"] = "test-openai-key-placeholder"
            out = scrub_sensitive_text("token=test-openai-key-placeholder")
            self.assertNotIn("test-openai-key-placeholder", out)
            self.assertIn("REDACTED", out)
        finally:
            if old is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = old

    def test_scrub_payload_masks_nested_values(self):
        old = os.environ.get("OPENAI_API_KEY")
        try:
            os.environ["OPENAI_API_KEY"] = "openai-test-key-beta"
            payload = {"a": ["OPENAI_API_KEY=openai-test-key-alpha", {"b": "openai-test-key-beta"}]}
            out = scrub_payload(payload)
            self.assertNotIn("openai-test-key-alpha", str(out))
            self.assertNotIn("openai-test-key-beta", str(out))
        finally:
            if old is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = old

    def test_write_json_file_uses_scrubbed_payload(self):
        with tempfile.TemporaryDirectory() as td:
            out_file = Path(td) / "out.json"
            write_json_file(str(out_file), {"x": "OPENAI_API_KEY=openai-test-key-gamma"})
            body = out_file.read_text(encoding="utf-8")
            self.assertNotIn("openai-test-key-gamma", body)
            self.assertIn("REDACTED", body)


if __name__ == "__main__":
    unittest.main()
