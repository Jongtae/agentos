from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel_public_preview_operating_brief import (
    build_public_preview_operating_brief,
    validate_public_preview_operating_brief,
)


class PublicPreviewOperatingBriefTests(unittest.TestCase):
    def test_build_and_validate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appob-", dir="/tmp") as tmpdir:
            workspace = Path(tmpdir) / "w"
            report_dir = Path(tmpdir) / "r"
            workspace.mkdir(parents=True, exist_ok=True)
            payload = build_public_preview_operating_brief(
                workspace=str(workspace),
                report_dir=str(report_dir),
                snapshot_label="c",
            )
            self.assertEqual(payload["schema_version"], "agentos-public-preview-operating-brief.v1")
            self.assertIn(payload["summary"]["operating_posture"], {"decision_ready", "decision_watch"})
            self.assertEqual(validate_public_preview_operating_brief(payload), [])


if __name__ == "__main__":
    unittest.main()
