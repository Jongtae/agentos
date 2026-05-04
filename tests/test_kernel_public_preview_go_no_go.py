from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel_public_preview_go_no_go import build_public_preview_go_no_go, validate_public_preview_go_no_go


class PublicPreviewGoNoGoTests(unittest.TestCase):
    def test_build_and_validate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appgng-", dir="/tmp") as tmpdir:
            workspace = Path(tmpdir) / "w"
            report_dir = Path(tmpdir) / "r"
            workspace.mkdir(parents=True, exist_ok=True)
            payload = build_public_preview_go_no_go(workspace=str(workspace), report_dir=str(report_dir), snapshot_label="c")
            self.assertEqual(payload["schema_version"], "agentos-public-preview-go-no-go.v1")
            self.assertIn(payload["summary"]["go_no_go"], {"go", "no_go"})
            self.assertEqual(validate_public_preview_go_no_go(payload), [])


if __name__ == "__main__":
    unittest.main()
