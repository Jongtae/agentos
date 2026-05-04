from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kernel_public_preview_announcement_readiness import (
    build_public_preview_announcement_readiness,
    validate_public_preview_announcement_readiness,
)


class PublicPreviewAnnouncementReadinessTests(unittest.TestCase):
    def test_build_and_validate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="appar-", dir="/tmp") as tmpdir:
            workspace = Path(tmpdir) / "w"
            report_dir = Path(tmpdir) / "r"
            workspace.mkdir(parents=True, exist_ok=True)
            payload = build_public_preview_announcement_readiness(
                workspace=str(workspace),
                report_dir=str(report_dir),
                snapshot_label="c",
            )
            self.assertEqual(payload["schema_version"], "agentos-public-preview-announcement-readiness.v1")
            self.assertIn(payload["summary"]["announcement_decision"], {"announcement_ready_for_decision", "hold_announcement"})
            self.assertEqual(validate_public_preview_announcement_readiness(payload), [])


if __name__ == "__main__":
    unittest.main()
